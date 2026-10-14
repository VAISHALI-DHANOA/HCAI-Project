import type { PublicTurn, RoundResult, State } from "./types";

type PendingRound = { turns: PublicTurn[]; result?: RoundResult; next: number };
export interface PlaybackOptions {
  duration: () => number;
  speak: (turn: PublicTurn) => Promise<void>;
  stopAudio: () => void;
  requestRound: (signal: AbortSignal) => Promise<State>;
  snapshot: (state: State) => void;
  contribution: (turn: PublicTurn, round: number, index: number) => void;
  completed: (round: RoundResult) => void;
  busy: (busy: boolean) => void;
  autoChanged: (enabled: boolean) => void;
  error: (message: string) => void;
}

/** Owns only pending playback; completed transcripts remain in State.rounds. */
export class PlaybackController {
  private runId = "";
  private finishedRound = 0;
  private rounds = new Map<number, PendingRound>();
  private generation = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private releaseTimer: (() => void) | undefined;
  private requestAbort: AbortController | undefined;
  private displaying = false;
  private requesting = false;
  private active = true;
  private planned = 0;
  private automatic = false;

  constructor(private options: PlaybackOptions) {}

  sync(state: State, baseline = false) {
    if (state.run_id !== this.runId || baseline) {
      this.cancel();
      this.runId = state.run_id;
      this.finishedRound = state.rounds?.[state.rounds.length - 1]?.round_number ?? state.round_number;
      this.active = true;
      return;
    }
    if (!this.active) return;
    for (const result of state.rounds ?? []) {
      if (result.round_number <= this.finishedRound) continue;
      const pending = this.rounds.get(result.round_number) ?? { turns: [], next: 0 };
      // Reuse the authoritative array, including any turns missed on the socket.
      pending.turns = result.turns;
      pending.result = result;
      this.rounds.set(result.round_number, pending);
    }
    this.pump();
  }

  turn(run: string, round: number, index: number, turn: PublicTurn) {
    if (!this.active || run !== this.runId || round <= this.finishedRound || !Number.isInteger(index) || index < 0) return;
    const pending = this.rounds.get(round) ?? { turns: [], next: 0 };
    if (!pending.result && !pending.turns[index]) pending.turns[index] = turn;
    this.rounds.set(round, pending);
    this.pump();
  }

  run(count: number) {
    if (this.requesting || this.displaying || this.rounds.size || this.planned) return;
    this.active = true;
    this.planned = count;
    this.pump();
  }

  resume() {
    this.active = true;
    this.pump();
  }

  auto(enabled: boolean) {
    this.automatic = enabled;
    this.options.autoChanged(enabled);
    if (enabled) this.active = true;
    this.pump();
  }

  cancel() {
    this.generation++;
    clearTimeout(this.timer);
    this.releaseTimer?.();
    this.releaseTimer = undefined;
    this.timer = undefined;
    this.requestAbort?.abort();
    this.requestAbort = undefined;
    this.options.stopAudio();
    this.rounds.clear();
    this.displaying = false;
    this.requesting = false;
    this.planned = 0;
    this.automatic = false;
    this.active = false;
    this.options.autoChanged(false);
    this.options.busy(false);
  }

  private pump() {
    if (!this.active || this.displaying) return;
    const number = this.finishedRound + 1;
    const round = this.rounds.get(number);
    if (round) {
      const turn = round.turns[round.next];
      if (turn) {
        this.displaying = true;
        this.options.busy(true);
        const generation = this.generation;
        const configured = this.options.duration();
        const duration = (Number.isFinite(configured) ? Math.max(1, configured) : 12) * 1000;
        this.options.contribution(turn, number, round.next);
        const elapsed = new Promise<void>((resolve) => {
          this.releaseTimer = resolve;
          this.timer = setTimeout(resolve, duration);
        });
        const audio = Promise.resolve().then(() => {
          if (generation === this.generation) return this.options.speak(turn);
        }).catch((error: unknown) => {
          if (generation === this.generation) this.options.error(error instanceof Error ? error.message : "Audio playback failed");
        });
        void Promise.all([elapsed, audio]).then(() => {
          if (generation !== this.generation) return;
          round.next++;
          this.displaying = false;
          this.timer = undefined;
          this.releaseTimer = undefined;
          this.pump();
        });
        return;
      }
      if (!round.result || round.next < round.result.turns.length) return;
      this.rounds.delete(number);
      this.finishedRound = number;
      this.options.completed(round.result);
      this.pump();
      return;
    }
    if (this.rounds.size || this.requesting) return;
    if (!this.planned && !this.automatic) { this.options.busy(false); return; }
    if (this.planned) this.planned--;
    this.requesting = true;
    this.options.busy(true);
    const generation = this.generation;
    this.requestAbort = new AbortController();
    void this.options.requestRound(this.requestAbort.signal).then((state) => {
      if (generation !== this.generation) return;
      this.options.snapshot(state);
    }).catch((error: unknown) => {
      if (generation !== this.generation) return;
      // A failed request may have streamed an incomplete round: do not wait
      // forever for a completion marker that will never arrive.
      this.cancel();
      this.options.error(error instanceof Error ? error.message : "Round request failed");
    }).finally(() => {
      if (generation !== this.generation) return;
      this.requesting = false;
      this.requestAbort = undefined;
      this.pump();
    });
  }
}
