"use client";

import { useState } from "react";
import { compareResults, trendScans, type Scan } from "../lib/results";

const series = [
  { key: "overall", label: "Overall", color: "#e4e7e9" },
  { key: "performance", label: "Performance", color: "#d8ae68" },
  { key: "accessibility", label: "Accessibility", color: "#88b4dc" },
  { key: "security", label: "Security", color: "#c69ad9" },
] as const;
type Metric = (typeof series)[number]["key"];
const value = (scan: Scan, key: Metric) =>
  key === "overall" ? scan.result?.score : scan.result?.scores[key];
const valid = (n: number | undefined): n is number =>
  typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 100;
const date = (s: string) => new Date(s).toLocaleString();

export default function HealthTrends({
  scans,
  selected,
  onSelect,
}: {
  scans: Scan[];
  selected: Scan;
  onSelect: (scan: Scan) => void;
}) {
  const history = trendScans(scans, selected);
  const [hidden, setHidden] = useState<Metric[]>([]);
  const x = (i: number) =>
    history.length === 1 ? 400 : 48 + (i * 704) / (history.length - 1);
  const y = (n: number) => 220 - n * 1.9;
  return (
    <section className="health-trends panel" aria-label="Website health trends">
      <div className="section-heading">
        <h2>Health over time</h2>
        <span className="tag">{history.length} SAVED SCANS</span>
      </div>
      <p className="trend-note">
        Completed scans of the same starting URL, oldest to newest. Based on the
        latest 100 saved assessments. Gaps separate changes in scanner versions
        or evaluated checks; scores may reflect different page coverage.
      </p>
      {history.length < 2 && (
        <p className="trend-empty">
          Run another assessment of this URL to see how its health changes over
          time.
        </p>
      )}
      <div className="trend-legend" aria-label="Chart series">
        {series.map((s) => (
          <button
            key={s.key}
            type="button"
            aria-pressed={!hidden.includes(s.key)}
            onClick={() =>
              setHidden((old) =>
                old.includes(s.key)
                  ? old.filter((k) => k !== s.key)
                  : [...old, s.key],
              )
            }
          >
            <span style={{ background: s.color }} />
            {s.label}
          </button>
        ))}
      </div>
      <svg
        className="trend-chart"
        viewBox="0 0 800 260"
        role="img"
        aria-label="Website scores from 0 to 100 over saved scans. Exact scores and report links are in the table below."
      >
        {[0, 25, 50, 75, 100].map((n) => (
          <g key={n}>
            <line x1="48" x2="752" y1={y(n)} y2={y(n)} stroke="#292d31" />
            <text x="34" y={y(n) + 4} textAnchor="end">
              {n}
            </text>
          </g>
        ))}
        {series
          .filter((s) => !hidden.includes(s.key))
          .map((s) => (
            <g key={s.key}>
              {history.map((scan, i) => {
                const n = value(scan, s.key);
                if (!valid(n)) return null;
                const prev = history[i - 1];
                const p = prev && value(prev, s.key);
                const linked =
                  prev?.result &&
                  scan.result &&
                  compareResults(scan.result, prev.result).delta !== null;
                return (
                  <g key={scan.id}>
                    {linked && valid(p) && (
                      <line
                        x1={x(i - 1)}
                        y1={y(p)}
                        x2={x(i)}
                        y2={y(n)}
                        stroke={s.color}
                        strokeWidth="2"
                        strokeDasharray={
                          s.key === "overall" ? undefined : "5 3"
                        }
                      />
                    )}
                    <circle
                      cx={x(i)}
                      cy={y(n)}
                      r={scan.id === selected.id ? 5 : 3}
                      fill={s.color}
                    >
                      <title>{`${date(scan.created_at)} · ${s.label}: ${n}/100`}</title>
                    </circle>
                  </g>
                );
              })}
            </g>
          ))}
        {history.length > 0 && (
          <>
            <text x="48" y="247">
              {new Date(history[0].created_at).toLocaleDateString()}
            </text>
            <text x="752" y="247" textAnchor="end">
              {new Date(
                history[history.length - 1].created_at,
              ).toLocaleDateString()}
            </text>
          </>
        )}
      </svg>
      <details className="trend-details">
        <summary>View scores and open saved reports</summary>
        <div className="trend-table-wrap">
          <table>
            <caption>
              Scores by assessment date. A dash means no score is available.
            </caption>
            <thead>
              <tr>
                <th scope="col">Assessment</th>
                {series.map((s) => (
                  <th key={s.key} scope="col">
                    {s.label}
                  </th>
                ))}
                <th scope="col">Pages / coverage</th>
              </tr>
            </thead>
            <tbody>
              {history.map((scan) => (
                <tr
                  key={scan.id}
                  aria-current={scan.id === selected.id ? "true" : undefined}
                >
                  <th scope="row">
                    <button onClick={() => onSelect(scan)}>
                      {date(scan.created_at)}
                      {scan.id === selected.id ? " · selected" : ""}
                    </button>
                  </th>
                  {series.map((s) => (
                    <td key={s.key}>
                      {valid(value(scan, s.key)) ? value(scan, s.key) : "—"}
                    </td>
                  ))}
                  <td>
                    {scan.result?.crawl
                      ? `${scan.result.crawl.completed} · ${scan.result.crawl.status}`
                      : "Single page"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
