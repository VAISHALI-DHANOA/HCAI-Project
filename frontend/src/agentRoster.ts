import { createPersonalityFromPreset } from "./personality";
import type { DraftAgent, OceanTraits, PersonalityCatalog } from "./types";

export const MAX_AGENTS = 25;

function objectValue(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("The selected file is not an agent roster.");
  }
  return value as Record<string, unknown>;
}

export function parseAgentRoster(text: string, catalog: PersonalityCatalog): DraftAgent[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("The selected file is not valid JSON.");
  }

  const roster = objectValue(parsed);
  if (roster.version !== 1 || !Array.isArray(roster.agents)) {
    throw new Error("Unsupported agent roster format.");
  }
  if (roster.agents.length > MAX_AGENTS) {
    throw new Error(`An agent roster can contain at most ${MAX_AGENTS} agents.`);
  }

  return roster.agents.map((value, index) => {
    const agent = objectValue(value);
    const personality = objectValue(agent.personality);
    const ocean = objectValue(personality.ocean);
    const name = typeof agent.name === "string" ? agent.name.trim() : "";
    const persona = typeof agent.persona_text === "string" ? agent.persona_text.trim() : "";
    const energy = agent.energy;
    const presetId = personality.preset_id;

    if (!name || name.length > 80 || !persona || persona.length > 500) {
      throw new Error(`Agent ${index + 1} needs a valid name and persona.`);
    }
    if (typeof energy !== "number" || !Number.isFinite(energy) || energy < 0 || energy > 1) {
      throw new Error(`Agent ${index + 1} has an invalid energy value.`);
    }
    if (typeof presetId !== "string" || !catalog.presets.some((preset) => preset.id === presetId)) {
      throw new Error(`Agent ${index + 1} uses an unknown personality preset.`);
    }

    const traitEntries = catalog.traits.map(({ key }) => [key, ocean[key]] as const);
    if (traitEntries.some(([, trait]) => typeof trait !== "number" || !Number.isFinite(trait) || trait < catalog.scale.min || trait > catalog.scale.max)) {
      throw new Error(`Agent ${index + 1} has invalid personality traits.`);
    }

    const customInstructions = personality.custom_instructions;
    if (typeof customInstructions !== "string" || customInstructions.length > 1000) {
      throw new Error(`Agent ${index + 1} has invalid custom instructions.`);
    }

    return {
      name,
      persona_text: persona,
      energy,
      personality: createPersonalityFromPreset(catalog, presetId, {
        ocean: Object.fromEntries(traitEntries) as unknown as OceanTraits,
        custom_instructions: customInstructions,
      }),
    };
  });
}

export function downloadAgentRoster(agents: DraftAgent[]): void {
  const contents = JSON.stringify({
    version: 1,
    agents: agents.map(({ name, persona_text, energy, personality }) => ({
      name, persona_text, energy, personality,
    })),
  }, null, 2);
  const url = URL.createObjectURL(new Blob([contents], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "arena-agents.json";
  link.click();
  URL.revokeObjectURL(url);
}
