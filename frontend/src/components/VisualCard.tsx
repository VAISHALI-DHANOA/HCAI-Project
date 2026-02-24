import { Component, type ReactNode } from "react";
import type { VisualSpec } from "../types";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
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

export function VisualCard({ visual, agentColor, agentName }: VisualCardProps) {
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
}

function renderBarChart(data: any, color: string) {
  const chartData = (data.labels || []).map((label: string, i: number) => ({
    name: label,
    value: (data.values || [])[i] ?? 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#94a3b8" }} />
        <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
        <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid rgba(56,189,248,0.3)", fontSize: 12, color: "#e2e8f0" }} />
        <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function renderLineChart(data: any, color: string) {
  const chartData = (data.labels || []).map((label: string, i: number) => ({
    name: label,
    value: (data.values || [])[i] ?? 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#94a3b8" }} />
        <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
        <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid rgba(56,189,248,0.3)", fontSize: 12, color: "#e2e8f0" }} />
        <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={{ r: 3, fill: color }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function renderScatterChart(data: any, color: string) {
  const chartData = (data.points || []).map((pt: any) => ({ x: pt.x, y: pt.y }));
  return (
    <ResponsiveContainer width="100%" height={160}>
      <ScatterChart>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis dataKey="x" name={data.x_label || "X"} tick={{ fontSize: 10, fill: "#94a3b8" }} />
        <YAxis dataKey="y" name={data.y_label || "Y"} tick={{ fontSize: 10, fill: "#94a3b8" }} />
        <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid rgba(56,189,248,0.3)", fontSize: 12, color: "#e2e8f0" }} />
        <Scatter data={chartData} fill={color} />
      </ScatterChart>
    </ResponsiveContainer>
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
  const headers: string[] = data.headers || [];
  const rawRows: any[] = data.rows || [];
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
  const stats: Array<{ label: string; value: string }> = data.stats || [];
  return (
    <div className="visual-stat-grid">
      {stats.map((stat, i) => (
        <div className="visual-stat-item" key={i}>
          <span className="visual-stat-item__label">{stat.label}</span>
          <span className="visual-stat-item__value">{stat.value}</span>
        </div>
      ))}
    </div>
  );
}
