import type { AgentPersonality, PersonalityCatalog, PersonalityPreset } from "./types";

// Backend supplies every preset, effective default, scale, and version.
// This module only looks up and clones those configurations for form editing.
export function getPersonalityPreset(catalog: PersonalityCatalog, presetId: string): PersonalityPreset {
  const preset = catalog.presets.find((item) => item.id === presetId);
  if (!preset) throw new Error(`Unknown personality preset: ${presetId}`);
  return preset;
}

export function createPersonalityFromPreset(
  catalog: PersonalityCatalog,
  presetId: string,
  overrides: Partial<Pick<AgentPersonality, "ocean" | "custom_instructions">> = {},
): AgentPersonality {
  const config = getPersonalityPreset(catalog, presetId).personality;
  return {
    ...config,
    ocean: { ...config.ocean, ...overrides.ocean },
    behavioral_rules: [...config.behavioral_rules],
    custom_instructions: overrides.custom_instructions ?? config.custom_instructions,
  };
}
