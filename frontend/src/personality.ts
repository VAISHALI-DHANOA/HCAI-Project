import type { AgentPersonality, PersonalityCatalog, PersonalityPreset } from "./types";

// Backend supplies every preset, effective default, level, and version.
// This module only looks up and clones those configurations for form editing.
export function getPersonalityPreset(catalog: PersonalityCatalog, presetId: string): PersonalityPreset {
  const preset = catalog.presets.find((item) => item.id === presetId);
  if (!preset) throw new Error(`Unknown personality preset: ${presetId}`);
  return preset;
}

export function createPersonalityFromPreset(
  catalog: PersonalityCatalog,
  presetId: string,
  overrides: Partial<Pick<AgentPersonality, "role_goal" | "ocean" | "custom_instructions">> = {},
): AgentPersonality {
  const config = getPersonalityPreset(catalog, presetId).personality;
  return {
    ...config,
    role_goal: overrides.role_goal ?? config.role_goal,
    ocean: { ...config.ocean, ...overrides.ocean },
    custom_instructions: overrides.custom_instructions ?? config.custom_instructions,
  };
}
