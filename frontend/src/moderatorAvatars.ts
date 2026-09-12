import consensusAvatar from "../artwork/Consensus.png";
import facilitatorAvatar from "../artwork/Facilitator.png";
import devilsAdvocateAvatar from "../artwork/Devils_advocate.png";

export const MODERATOR_AVATARS: Record<string, string> = {
  consensus: consensusAvatar,
  facilitator: facilitatorAvatar,
  devils_advocate: devilsAdvocateAvatar,
};

export function getModeratorAvatar(strategyId?: string): string {
  return MODERATOR_AVATARS[strategyId ?? "consensus"] ?? consensusAvatar;
}
