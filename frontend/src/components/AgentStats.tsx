import type { AgentPersonality, OceanLevel, PersonalityCatalog } from "../types";

function oceanLevel(value: OceanLevel): { label: "Low" | "Medium" | "High"; position: number } {
  if (value === "low") return { label: "Low", position: 1 };
  if (value === "high") return { label: "High", position: 3 };
  return { label: "Medium", position: 2 };
}

export function AgentStats({ personality, catalog }: {
  personality?: AgentPersonality | null;
  catalog: PersonalityCatalog;
}) {
  return <div className="agent-stats" aria-label="Agent stats">
    {personality && <div className="agent-stats__traits">
      {catalog.traits.map((trait) => {
        const level = oceanLevel(personality.ocean[trait.key]);
        return <div className={`agent-stat trait--${trait.key}`} key={trait.key}>
          <span className="agent-stat__label">{trait.label}</span>
          <span
            className="agent-stat__pips"
            role="img"
            aria-label={`${trait.label}: ${level.label}`}
          >
            {[1, 2, 3].map((pip) => <span key={pip} className={pip <= level.position ? "is-filled" : ""} aria-hidden="true" />)}
          </span>
          <span className="agent-stat__level-label" aria-hidden="true">{level.label}</span>
        </div>;
      })}
    </div>}
  </div>;
}
