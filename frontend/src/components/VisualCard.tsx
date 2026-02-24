import { Component, type ReactNode } from "react";
import type { VisualSpec } from "../types";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line,
  ScatterChart, Scatter,
} from "recharts";

interface VisualCardProps {
  visual: VisualSpec;
  agentColor: string;
  agentName: string;
}

/** Error boundary so a single malformed visual doesn't crash the app. */
class VisualErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  render() {
    if (this.state.hasError) {
      return <p style={{ color: "#94a3b8", fontSize: "0.78rem" }}>Visual could not be rendered.</p>;
    }
    return this.props.children;
  }
}

const CHART_W = 280;
const CHART_H = 150;

export function VisualCard({ visual, agentColor, agentName }: VisualCardProps) {
  if (!visual || !visual.data) {
    return null;
  }

  return (
    <div className="visual-card" style={{ "--agent-color": agentColor } as React.CSSProperties}>
      <div className="visual-card__header">
        <span className="visual-card__agent">{agentName}</span>
        <span className="visual-card__title">{visual.title}</span>
      </div>
      <div className="visual-card__body">
        <VisualErrorBoundary>
          {renderVisual(visual, agentColor)}
        </VisualErrorBoundary>
      </div>
      {visual.description && (
        <p className="visual-card__description">{visual.description}</p>
      )}
    </div>
  );
}

function renderVisual(spec: VisualSpec, color: string) {
  try {
    switch (spec.visual_type) {
      case "bar_chart":
        return renderBarChart(spec.data, color);
      case "line_chart":
        return renderLineChart(spec.data, color);
      case "scatter":
        return renderScatterChart(spec.data, color);
      case "table":
      case "heatmap":
        return renderTable(spec.data);
      case "stat_card":
        return renderStatCard(spec.data);
      default:
        return <p style={{ color: "#94a3b8", fontSize: "0.78rem" }}>Unsupported visual type</p>;
    }
  } catch {
    return <p style={{ color: "#94a3b8", fontSize: "0.78rem" }}>Visual could not be rendered.</p>;
  }
}

function renderBarChart(data: any, color: string) {
  const labels = Array.isArray(data.labels) ? data.labels : [];
  const values = Array.isArray(data.values) ? data.values : [];
  if (labels.length === 0) return <p style={{ color: "#94a3b8", fontSize: "0.78rem" }}>No chart data</p>;

  const chartData = labels.map((label: string, i: number) => ({
    name: String(label),
    value: Number(values[i]) || 0,
  }));
  return (
    <BarChart width={CHART_W} height={CHART_H} data={chartData}>
      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
      <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#94a3b8" }} />
      <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} />
      <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid rgba(56,189,248,0.3)", fontSize: 11, color: "#e2e8f0" }} />
      <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} />
    </BarChart>
  );
}

function renderLineChart(data: any, color: string) {
  const labels = Array.isArray(data.labels) ? data.labels : [];
  const values = Array.isArray(data.values) ? data.values : [];
  if (labels.length === 0) return <p style={{ color: "#94a3b8", fontSize: "0.78rem" }}>No chart data</p>;

  const chartData = labels.map((label: string, i: number) => ({
    name: String(label),
    value: Number(values[i]) || 0,
  }));
  return (
    <LineChart width={CHART_W} height={CHART_H} data={chartData}>
      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
      <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#94a3b8" }} />
      <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} />
      <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid rgba(56,189,248,0.3)", fontSize: 11, color: "#e2e8f0" }} />
      <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={{ r: 3, fill: color }} />
    </LineChart>
  );
}

function renderScatterChart(data: any, color: string) {
  const points = Array.isArray(data.points) ? data.points : [];
  if (points.length === 0) return <p style={{ color: "#94a3b8", fontSize: "0.78rem" }}>No chart data</p>;

  const chartData = points.map((pt: any) => ({ x: Number(pt.x) || 0, y: Number(pt.y) || 0 }));
  return (
    <ScatterChart width={CHART_W} height={CHART_H}>
      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
      <XAxis dataKey="x" name={data.x_label || "X"} tick={{ fontSize: 9, fill: "#94a3b8" }} />
      <YAxis dataKey="y" name={data.y_label || "Y"} tick={{ fontSize: 9, fill: "#94a3b8" }} />
      <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid rgba(56,189,248,0.3)", fontSize: 11, color: "#e2e8f0" }} />
      <Scatter data={chartData} fill={color} />
    </ScatterChart>
  );
}

/** Normalize a row: if it's an object, extract values using headers order; if array, use as-is. */
function normalizeRow(row: any, headers: string[]): any[] {
  if (Array.isArray(row)) return row;
  if (row && typeof row === "object") {
    return headers.map((h) => row[h] ?? "");
  }
  return [];
}

function renderTable(data: any) {
  const headers: string[] = Array.isArray(data.headers) ? data.headers : [];
  const rawRows: any[] = Array.isArray(data.rows) ? data.rows : [];
  if (headers.length === 0) return <p style={{ color: "#94a3b8", fontSize: "0.78rem" }}>No table data</p>;

  return (
    <div className="visual-table-wrap">
      <table className="visual-table">
        <thead>
          <tr>{headers.map((h, i) => <th key={i}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rawRows.map((row, ri) => {
            const cells = normalizeRow(row, headers);
            return (
              <tr key={ri}>{cells.map((cell: any, ci: number) => <td key={ci}>{String(cell)}</td>)}</tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function renderStatCard(data: any) {
  const stats: Array<{ label: string; value: string }> = Array.isArray(data.stats) ? data.stats : [];
  if (stats.length === 0) return <p style={{ color: "#94a3b8", fontSize: "0.78rem" }}>No stats data</p>;

  return (
    <div className="visual-stat-grid">
      {stats.map((stat, i) => (
        <div className="visual-stat-item" key={i}>
          <span className="visual-stat-item__label">{stat.label}</span>
          <span className="visual-stat-item__value">{String(stat.value)}</span>
        </div>
      ))}
    </div>
  );
}
