import type { AgentPersonality, PersonalityCatalog } from "../types";

export function AgentStats({ personality, energy, catalog }: {
  personality?: AgentPersonality | null;
  energy: number;
  catalog: PersonalityCatalog;
}) {
  return <div className="agent-stats" aria-label="Agent stats">
    {personality && <div className="agent-stats__traits">
      {catalog.traits.map((trait) => <div className={`agent-stat trait--${trait.key}`} key={trait.key}>
        <span className="agent-stat__label">{trait.label}</span>
        <meter min={catalog.scale.min} max={catalog.scale.max} value={personality.ocean[trait.key]} aria-label={trait.label} />
        <span className="agent-stat__value">{personality.ocean[trait.key]}<small>/{catalog.scale.max}</small></span>
      </div>)}
    </div>}
    <div className="agent-stat agent-stat--energy">
      <span className="agent-stat__label">Energy</span>
      <meter min={0} max={1} value={energy} aria-label="Energy" />
      <span className="agent-stat__value">{Math.round(energy * 100)}<small>%</small></span>
    </div>
  </div>;
}
