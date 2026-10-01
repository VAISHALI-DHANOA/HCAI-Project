import type { MetricAvailability, MetricDisplayData } from "../metrics";

const STATUS_LABELS: Record<MetricAvailability, string> = {
  unavailable: "Not available yet",
  pending: "Pending",
  available: "Available",
  error: "Error",
};

export function MetricCard({ metric }: { metric: MetricDisplayData }) {
  const hasAgentValues = (metric.agentValues?.length ?? 0) > 0;
  const hasDetails = (metric.details?.length ?? 0) > 0;
  const hasHighlights = (metric.highlights?.length ?? 0) > 0;

  return (
    <article className="metric-card" data-status={metric.status}>
      <div className="metric-card__header">
        <div className="metric-card__identity">
          <span className="metric-card__icon" aria-hidden="true">{metric.icon}</span>
          <div>
            <h3>{metric.label}</h3>
            <span className="metric-card__status">{STATUS_LABELS[metric.status]}</span>
          </div>
        </div>
        <div className="metric-card__result">
          <strong className="metric-card__value">{metric.formattedValue ?? "—"}</strong>
          {metric.roundNumber ? <span className="metric-card__round">Round {metric.roundNumber}</span> : null}
        </div>
      </div>
      {metric.progress !== undefined ? (
        <div className="metric-card__meter" aria-label={`${metric.label}: ${Math.round(metric.progress * 100)} percent`}>
          <span style={{ width: `${Math.max(0, Math.min(1, metric.progress)) * 100}%` }} />
        </div>
      ) : null}
      {metric.steps ? (
        <div className="metric-card__steps" aria-label={`${metric.label} scale`}>
          {metric.steps.map((step, index) => (
            <span key={step} className={metric.activeStep === index ? "is-active" : ""} title={step}>
              <i aria-hidden="true" />
              <small>{step}</small>
            </span>
          ))}
        </div>
      ) : null}
      {hasHighlights ? (
        <ul className="metric-card__highlights">
          {metric.highlights!.map((highlight) => (
            <li key={highlight.label}>
              <strong>{highlight.label}</strong>
              <span>{highlight.value}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <details className="metric-card__details">
        <summary>Details</summary>
        <div className="metric-card__detail-content">
          <p>{metric.explanation ?? "No evaluation available yet."}</p>
          {hasDetails ? (
            <dl className="metric-card__facts">
              {metric.details!.map((detail) => (
                <div key={detail.label}>
                  <dt>{detail.label}</dt>
                  <dd>{detail.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {hasAgentValues ? (
            <dl className="metric-card__agent-values" aria-label={`${metric.label} agent values`}>
              {metric.agentValues!.map((agentValue) => (
                <div key={agentValue.agentId}>
                  <dt>{agentValue.agentLabel}</dt>
                  <dd>{agentValue.formattedValue ?? "—"}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      </details>
    </article>
  );
}

export function MetricsPanel({ metrics, layout = "stacked", labelledBy }: {
  metrics: MetricDisplayData[];
  layout?: "stacked" | "grid";
  labelledBy?: string;
}) {
  return (
    <div className={`metrics-panel metrics-panel--${layout}`} aria-labelledby={labelledBy}>
      {metrics.map((metric) => <MetricCard key={metric.id} metric={metric} />)}
    </div>
  );
}
