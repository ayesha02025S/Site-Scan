"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  Crosshair,
  ExternalLink,
  GitCompareArrows,
  FileText,
  Globe2,
  Layers3,
  LoaderCircle,
  Plus,
  Radar,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
  Zap,
} from "lucide-react";

import {
  type Category,
  type Scan,
  compareResults,
  previousScan,
  resultClass,
  resultLabel,
} from "../lib/results";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const categories: Category[] = ["performance", "accessibility", "security"];
const categoryIcons = {
  performance: Zap,
  accessibility: Crosshair,
  security: ShieldCheck,
};
const descriptions = {
  performance: "Response & document delivery",
  accessibility: "Foundations for an inclusive web",
  security: "Transport & response protections",
};
const hostname = (url: string) => {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
};
const tone = (score: number) =>
  score >= 90 ? "good" : score >= 60 ? "warning" : "bad";
const dateLabel = (date: string) =>
  new Date(date).toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(API + path, {
      ...options,
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    throw new Error(
      "Cannot reach the scanner. Check that the backend is running on port 8000, then retry.",
    );
  }
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail[0]?.msg?.replace("Value error, ", "") ||
            "Check the website URL."
          : "Something went wrong. Please try again.",
    );
  }
  return data;
}

export default function Home() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<"overview" | "history" | "methodology">(
    "overview",
  );
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [online, setOnline] = useState(false);
  const [filter, setFilter] = useState<"all" | Category>("all");
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const revision = useRef(0);
  const refreshing = useRef(false);
  const scan = scans.find((item) => item.id === selected);
  const result = scan?.result;
  const pending = scan?.status === "queued" || scan?.status === "running";
  const issues =
    result?.checks.filter((check) => check.status === "failed") || [];
  const previous = scan && result ? previousScan(scans, scan) : undefined;
  const comparison =
    result && previous?.result ? compareResults(result, previous.result) : null;
  const inconclusive =
    result?.checks.filter((check) => check.status === "inconclusive").length ||
    0;
  const checks = (result?.checks || []).filter(
    (check) =>
      (filter === "all" || check.category === filter) &&
      (!onlyIssues ||
        check.status === "failed" ||
        check.status === "inconclusive"),
  );

  async function refresh(initial = false) {
    if (refreshing.current) return;
    refreshing.current = true;
    const currentRevision = revision.current;
    try {
      const list = await request<Scan[]>("/scans");
      if (currentRevision !== revision.current) return;
      setScans(list);
      setOnline(true);
      setError("");
      if (initial) setSelected(list[0]?.id || null);
    } catch (exc) {
      setOnline(false);
      setError((exc as Error).message);
    } finally {
      setLoading(false);
      refreshing.current = false;
    }
  }

  useEffect(() => {
    void refresh(true);
  }, []);
  const hasPending = scans.some(
    (item) => item.status === "queued" || item.status === "running",
  );
  useEffect(() => {
    if (!hasPending) return;
    const interval = setInterval(() => void refresh(), 1800);
    return () => clearInterval(interval);
  }, [hasPending]);

  async function submit(event?: FormEvent, override?: string) {
    event?.preventDefault();
    const value = (override || url).trim();
    if (!value || submitting) return;
    revision.current += 1;
    setSubmitting(true);
    setError("");
    try {
      const created = await request<Scan>("/scans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: value }),
      });
      setScans((items) => [created, ...items].slice(0, 100));
      setSelected(created.id);
      setView("overview");
      setFilter("all");
      setExpanded(null);
      setOnlyIssues(false);
      setOnline(true);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function selectScan(item: Scan) {
    setSelected(item.id);
    setView("overview");
    setFilter("all");
    setExpanded(null);
    setOnlyIssues(false);
  }
  function newScan() {
    setView("overview");
    requestAnimationFrame(() => {
      input.current?.focus();
      input.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  return (
    <div className="app-shell">
      <header className="sidebar">
        <a className="brand" href="/" aria-label="Site Scan home">
          <div className="brand-mark">
            <Crosshair size={23} strokeWidth={1.3} />
          </div>
          <span>
            SITE<span className="brand-light">SCAN</span>
            <small>WEB INTELLIGENCE PLATFORM</small>
          </span>
        </a>
        <nav aria-label="Main navigation">
          <button
            className={view === "overview" ? "nav-item active" : "nav-item"}
            onClick={() => setView("overview")}
          >
            <Layers3 size={17} />
            Overview<span className="nav-key">01</span>
          </button>
          <button
            className={view === "history" ? "nav-item active" : "nav-item"}
            onClick={() => setView("history")}
          >
            <Clock3 size={17} />
            Scan history
            <span className="nav-count">
              {scans.length.toString().padStart(2, "0")}
            </span>
          </button>
          <button
            className={view === "methodology" ? "nav-item active" : "nav-item"}
            onClick={() => setView("methodology")}
          >
            <FileText size={17} />
            Methodology
            <ArrowUpRight size={13} className="nav-key" />
          </button>
        </nav>
        <div className="nav-status">
          <span className={`status-dot ${online ? "connected" : ""}`} />
          {online ? "SYSTEM ONLINE" : loading ? "CONNECTING" : "SYSTEM OFFLINE"}
        </div>
      </header>
      <div className="main-shell">
        <main>
          <div
            className={`page-heading ${view === "overview" ? "hero-heading" : ""}`}
          >
            <div>
              <div className="eyebrow">
                <span /> SITE SCAN /{" "}
                {view === "overview"
                  ? "OVERVIEW"
                  : view === "history"
                    ? "ARCHIVE"
                    : "REFERENCE"}
              </div>
              <h1>
                {view === "overview" ? (
                  <>
                    See beyond
                    <br />
                    the surface.
                  </>
                ) : view === "history" ? (
                  "Your scan archive."
                ) : (
                  "Behind the assessment."
                )}
              </h1>
              <p>
                {view === "overview"
                  ? "A clear view of your website’s performance, accessibility, and security. One URL. Every signal that matters."
                  : view === "history"
                    ? "Every assessment, preserved. Return to a previous scan to inspect its findings."
                    : "Transparent checks. Reproducible findings. No black box."}
              </p>
            </div>
            {view === "overview" && (
              <div className="hero-art" aria-hidden="true">
                <svg viewBox="0 0 600 470" fill="none">
                  <defs>
                    <radialGradient id="globe-light" cx=".35" cy=".25" r=".8">
                      <stop stopColor="#3a4146" />
                      <stop offset=".45" stopColor="#171c20" />
                      <stop offset="1" stopColor="#050607" />
                    </radialGradient>
                    <linearGradient
                      id="line-light"
                      x1="80"
                      y1="40"
                      x2="440"
                      y2="420"
                      gradientUnits="userSpaceOnUse"
                    >
                      <stop stopColor="#b7c3cb" stopOpacity=".8" />
                      <stop offset=".45" stopColor="#6e7c87" stopOpacity=".4" />
                      <stop offset="1" stopColor="#29313a" stopOpacity=".1" />
                    </linearGradient>
                    <clipPath id="sphere-clip">
                      <circle cx="300" cy="235" r="174" />
                    </clipPath>
                  </defs>
                  <g transform="rotate(-24 300 235)">
                    <circle
                      cx="300"
                      cy="235"
                      r="174"
                      fill="url(#globe-light)"
                    />
                    <g
                      clipPath="url(#sphere-clip)"
                      stroke="url(#line-light)"
                      strokeWidth=".65"
                    >
                      {[25, 55, 87, 117, 143, 163, 174].map((r) => (
                        <ellipse key={r} cx="300" cy="235" rx={r} ry="174" />
                      ))}
                      {[-150, -120, -85, -45, 0, 45, 85, 120, 150].map((y) => (
                        <ellipse
                          key={y}
                          cx="300"
                          cy={235 + y}
                          rx={Math.sqrt(174 * 174 - y * y)}
                          ry={Math.sqrt(174 * 174 - y * y) * 0.18}
                        />
                      ))}
                    </g>
                    <circle
                      cx="300"
                      cy="235"
                      r="174"
                      stroke="url(#line-light)"
                    />
                    <ellipse
                      cx="300"
                      cy="235"
                      rx="253"
                      ry="62"
                      stroke="#8295a3"
                      strokeOpacity=".25"
                      strokeWidth=".7"
                    />
                    <ellipse
                      cx="300"
                      cy="235"
                      rx="231"
                      ry="204"
                      stroke="#778792"
                      strokeOpacity=".12"
                      strokeDasharray="2 8"
                    />
                    <circle cx="65" cy="211" r="3" fill="#bbc8d1" />
                    <circle cx="441" cy="86" r="2" fill="#899ba8" />
                  </g>
                  <path
                    d="M39 395h25m-12-12v25M536 68h25m-12-12v25"
                    stroke="#707c84"
                    strokeWidth=".6"
                  />
                  <text
                    x="65"
                    y="450"
                    fill="#697781"
                    fontSize="7"
                    fontFamily="monospace"
                    letterSpacing="2"
                  >
                    SURFACE ANALYSIS / 001
                  </text>
                </svg>
                <div className="hero-art-caption">
                  <span>PUBLIC WEB INTELLIGENCE</span>
                  <span>01 — 03</span>
                </div>
              </div>
            )}
            <button
              className="button secondary heading-button"
              onClick={newScan}
            >
              <Plus size={15} />
              New scan
            </button>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              {online ? (
                <button onClick={() => setError("")}>
                  Dismiss <X size={13} />
                </button>
              ) : (
                <button onClick={() => void refresh(true)}>
                  Retry connection <ArrowRight size={13} />
                </button>
              )}
            </div>
          )}
          {view === "methodology" ? (
            <section className="methodology panel">
              <div className="section-heading">
                <span className="section-number">01</span>
                <h2>What a scan measures</h2>
              </div>
              <p>
                Site Scan fetches one public HTML page and runs 13 static/link
                and 9 rendered-page checks. It follows up to five redirects,
                verifies HTTPS certificates, and records the final response. It
                checks up to 20 links on the page for dead destinations and
                renders the submitted page in Chromium for axe-core
                accessibility checks. It does not crawl linked pages. When a URL
                has been scanned before, the overview compares the result with
                the previous completed scan.
              </p>
              <div className="method-grid">
                {categories.map((category) => (
                  <article key={category}>
                    <div className="eyebrow">{category}</div>
                    <h3>{descriptions[category]}</h3>
                    <p>
                      {category === "performance"
                        ? "HTTP success, an HTML fetch time of at most 1,500 ms, a decoded HTML size of at most 300 KB, and a bounded link check (404, 410, and 5xx). Unreachable or restricted destinations are inconclusive. Fetch time includes redirects; it is not Core Web Vitals or a browser load time."
                        : category === "accessibility"
                          ? "Static HTML foundations plus axe-core checks on the rendered page: text color contrast, accessible button names, and valid ARIA roles, attributes, and relationships. A 1280 × 900 Chromium snapshot is evaluated; embedded frames and interaction-dependent states need manual review. These checks do not establish WCAG compliance."
                          : "HTTPS use, Content Security Policy presence, HSTS with positive max-age, X-Content-Type-Options: nosniff, and Referrer-Policy presence. Header presence alone does not establish secure configuration."}
                    </p>
                  </article>
                ))}
              </div>
              <h3>How scores work</h3>
              <p>
                Within each category, passed checks earn their severity weight:
                high = 3, medium = 2, low = 1. The category score is the
                percentage of evaluated weight earned. Inconclusive and
                not-applicable checks are excluded from the score. The overall
                score is the rounded mean of the three category scores. Scores
                of 90–100 are labeled “Strong,” 60–89 “Needs attention,” and
                0–59 “Action required.” These are project heuristics, not an
                industry certification.
              </p>
              <h3>Scope and storage</h3>
              <p>
                Only standard HTTP/HTTPS ports and public destinations are
                allowed. Private addresses are rejected during DNS resolution
                and at each redirect. Page fetching is limited to 25 seconds and
                2 MB; link checks have an 8-second budget and browser checks
                have a separate 35-second deadline. Completed and failed scans
                are saved locally. The history view displays the latest 100
                scans. Scans interrupted by a server restart are marked failed.
                This local prototype has no accounts or authentication; deploy
                only after adding access controls and durable workers.
              </p>
            </section>
          ) : (
            <>
              {view === "overview" && (
                <>
                  <section className="scan-panel panel">
                    <div className="scan-panel-top">
                      <div>
                        <Crosshair size={16} />
                        <h2>Start a site assessment</h2>
                      </div>
                      <span className="tag">SINGLE-PAGE SCAN</span>
                    </div>
                    <form onSubmit={submit}>
                      <label htmlFor="target-url" className="sr-only">
                        Website URL
                      </label>
                      <div className="url-input">
                        <Globe2 size={18} />
                        <input
                          ref={input}
                          id="target-url"
                          value={url}
                          onChange={(event) => setUrl(event.target.value)}
                          placeholder="Enter a website URL — https://example.com"
                          required
                          maxLength={2048}
                          autoComplete="url"
                          spellCheck={false}
                        />
                      </div>
                      <button
                        className="button primary"
                        type="submit"
                        disabled={submitting || pending}
                      >
                        {submitting || pending ? (
                          <LoaderCircle size={16} className="spin" />
                        ) : (
                          <Radar size={17} />
                        )}{" "}
                        {submitting
                          ? "Submitting"
                          : pending
                            ? "Scanning"
                            : "Run assessment"}
                        <ArrowRight size={16} />
                      </button>
                    </form>
                    <div className="scan-caption">
                      <span>
                        <ShieldCheck size={12} />
                        Non-intrusive checks. Public pages only.
                      </span>
                      <span>
                        PERFORMANCE<span className="tiny-cross">+</span>
                        ACCESSIBILITY<span className="tiny-cross">+</span>
                        SECURITY
                      </span>
                    </div>
                  </section>
                  {loading ? (
                    <div className="empty panel">
                      <LoaderCircle className="spin" />
                      <h2>Connecting to your workspace</h2>
                      <p>Loading saved assessments.</p>
                    </div>
                  ) : pending ? (
                    <div className="scanning panel" role="status">
                      <div className="radar-visual">
                        <span />
                        <span />
                        <Crosshair size={35} />
                      </div>
                      <div className="eyebrow">ASSESSMENT IN PROGRESS</div>
                      <h2>Acquiring the signal.</h2>
                      <p>
                        Fetching {hostname(scan.url)} and evaluating the page.
                      </p>
                      <div className="scanning-steps">
                        <span>
                          <LoaderCircle size={12} className="spin" />
                          {scan.status === "queued"
                            ? "Queued for assessment"
                            : "Checking links & rendered accessibility"}
                        </span>
                        <span>
                          Results appear automatically; rendering takes longer
                        </span>
                      </div>
                    </div>
                  ) : scan?.status === "failed" ? (
                    <div className="empty panel" role="status">
                      <div className="empty-icon bad">
                        <X size={26} />
                      </div>
                      <div className="eyebrow">ASSESSMENT INTERRUPTED</div>
                      <h2>We couldn’t complete this scan.</h2>
                      <p>{scan.error}</p>
                      <span className="mono muted">{scan.url}</span>
                      <button
                        className="button secondary"
                        onClick={() => void submit(undefined, scan.url)}
                      >
                        Try again
                        <ArrowRight size={14} />
                      </button>
                    </div>
                  ) : result && scan ? (
                    <>
                      <div className="assessment-heading">
                        <div>
                          <span className="status-dot connected" />
                          <h2>{hostname(scan.url)}</h2>
                          <a
                            href={result.final_url}
                            target="_blank"
                            rel="noreferrer"
                            aria-label="Open scanned website"
                          >
                            <ExternalLink size={13} />
                          </a>
                          <span className="tag">ASSESSMENT COMPLETE</span>
                        </div>
                        <span className="mono muted">
                          {dateLabel(scan.created_at)}
                        </span>
                      </div>
                      <section
                        className="score-grid"
                        aria-label="Assessment scores"
                      >
                        <article className="overall-card panel">
                          <div className="card-label">
                            OVERALL HEALTH
                            <ArrowUpRight size={14} />
                          </div>
                          <div className="overall-body">
                            <div
                              className={`score-dial ${tone(result.score)}`}
                              style={
                                {
                                  "--score": `${result.score}%`,
                                } as React.CSSProperties
                              }
                            >
                              <div>
                                <strong>{result.score}</strong>
                                <span>OUT OF 100</span>
                              </div>
                            </div>
                            <div>
                              <span
                                className={`score-status ${tone(result.score)}`}
                              >
                                {result.score >= 90
                                  ? "Strong"
                                  : result.score >= 60
                                    ? "Needs attention"
                                    : "Action required"}
                              </span>
                              <p>
                                {issues.length} finding
                                {issues.length === 1 ? "" : "s"} to review
                                <br />
                                {
                                  result.checks.filter(
                                    (c) =>
                                      c.status === "passed" ||
                                      c.status === "failed",
                                  ).length
                                }{" "}
                                checks evaluated
                              </p>
                            </div>
                          </div>
                          <div className="card-footer">
                            SINGLE-PAGE HEALTH INDEX<span>01 / 01</span>
                          </div>
                        </article>
                        {categories.map((category) => {
                          const Icon = categoryIcons[category];
                          const categoryIssues = issues.filter(
                            (check) => check.category === category,
                          ).length;
                          return (
                            <button
                              key={category}
                              className={`category-card panel ${filter === category ? "selected" : ""}`}
                              onClick={() =>
                                setFilter(
                                  filter === category ? "all" : category,
                                )
                              }
                              aria-pressed={filter === category}
                            >
                              <div className="card-label">
                                <Icon size={17} />
                                <ArrowUpRight size={14} />
                              </div>
                              <h3>{category}</h3>
                              <div className="category-score">
                                {result.scores[category]}
                                <span>/ 100</span>
                              </div>
                              <div className="score-track">
                                <span
                                  className={tone(result.scores[category])}
                                  style={{
                                    width: `${result.scores[category]}%`,
                                  }}
                                />
                              </div>
                              <div className="category-bottom">
                                <span>
                                  {categoryIssues
                                    ? `${categoryIssues} finding${categoryIssues === 1 ? "" : "s"}`
                                    : result.checks.some(
                                          (c) =>
                                            c.category === category &&
                                            c.status === "inconclusive",
                                        )
                                      ? "Review incomplete checks"
                                      : "Evaluated checks passed"}
                                </span>
                                <span
                                  className={`small-dot ${tone(result.scores[category])}`}
                                />
                              </div>
                            </button>
                          );
                        })}
                      </section>
                      <div className="metrics-bar">
                        <span>
                          <Activity size={13} />
                          HTTP <strong>{result.http_status}</strong>
                        </span>
                        <span>
                          <Clock3 size={13} />
                          FETCH{" "}
                          <strong>
                            {result.response_ms.toLocaleString()} ms
                          </strong>
                        </span>
                        <span>
                          <FileText size={13} />
                          HTML{" "}
                          <strong>
                            {(result.size_bytes / 1024).toFixed(1)} KB
                          </strong>
                        </span>
                        <span>
                          <ArrowRight size={13} />
                          REDIRECTS <strong>{result.redirects}</strong>
                        </span>
                        <a href={`${API}/scans/${scan.id}/export`} download>
                          <ArrowDownToLine size={13} />
                          Export JSON
                        </a>
                      </div>
                      {result.rendered_accessibility && (
                        <section
                          className="audit-summary panel"
                          aria-label="Rendered accessibility status"
                        >
                          <div>
                            <Crosshair size={17} />
                            <strong>Browser accessibility</strong>
                            <span className="tag">
                              {result.rendered_accessibility.status.toUpperCase()}
                            </span>
                          </div>
                          <p>{result.rendered_accessibility.message}</p>
                          <small>
                            {inconclusive} checks need review. Inconclusive and
                            not-applicable checks are excluded from scores.
                          </small>
                        </section>
                      )}
                      {comparison && previous && (
                        <section
                          className="comparison panel"
                          aria-label="Changes since previous scan"
                        >
                          <div className="section-heading">
                            <GitCompareArrows size={15} />
                            <h2>Since the previous scan</h2>
                            <span className="mono muted">
                              {dateLabel(previous.created_at)}
                            </span>
                            <button
                              className="text-button"
                              onClick={() => selectScan(previous)}
                            >
                              Open previous
                              <ArrowUpRight size={13} />
                            </button>
                          </div>
                          {!comparison.compatible ? (
                            <p className="comparison-notice">
                              These reports use different or older scanner
                              versions. Score and issue changes are not
                              comparable. Run another scan with the current
                              version to establish a baseline.
                            </p>
                          ) : (
                            <div className="comparison-grid">
                              <div>
                                <span className="eyebrow">SCORE CHANGE</span>
                                <strong
                                  className={
                                    comparison.delta !== null &&
                                    comparison.delta > 0
                                      ? "good"
                                      : comparison.delta !== null &&
                                          comparison.delta < 0
                                        ? "bad"
                                        : "muted"
                                  }
                                >
                                  {comparison.delta !== null &&
                                  comparison.delta > 0
                                    ? "+"
                                    : ""}
                                  {comparison.delta ?? "—"}
                                </strong>
                                <small>
                                  {comparison.delta === null
                                    ? "Different check coverage"
                                    : `${previous.result?.score} → ${result.score}`}
                                </small>
                              </div>
                              {(
                                [
                                  ["NEW ISSUES", comparison.introduced, "bad"],
                                  ["RESOLVED", comparison.resolved, "good"],
                                  [
                                    "STILL FAILING",
                                    comparison.ongoing,
                                    "warning",
                                  ],
                                ] as const
                              ).map(([label, items, toneName]) => (
                                <div key={label}>
                                  <span className="eyebrow">{label}</span>
                                  <strong
                                    className={
                                      items.length ? toneName : "muted"
                                    }
                                  >
                                    {items.length}
                                  </strong>
                                  <ul>
                                    {items.map((check) => (
                                      <li key={check.id}>{check.title}</li>
                                    ))}
                                    {!items.length && (
                                      <li className="muted">None</li>
                                    )}
                                  </ul>
                                </div>
                              ))}
                            </div>
                          )}
                        </section>
                      )}
                      <section className="findings panel">
                        <div className="section-heading">
                          <span className="section-number">01</span>
                          <h2>Assessment findings</h2>
                          <span className="count-badge">
                            {result.checks.length}
                          </span>
                          <label className="issues-toggle">
                            <input
                              type="checkbox"
                              checked={onlyIssues}
                              onChange={(e) => setOnlyIssues(e.target.checked)}
                            />
                            <SlidersHorizontal size={13} />
                            Needs review
                          </label>
                        </div>
                        <div
                          className="filters"
                          role="group"
                          aria-label="Filter findings"
                        >
                          {(["all", ...categories] as const).map((category) => (
                            <button
                              className={
                                filter === category ? "filter active" : "filter"
                              }
                              key={category}
                              onClick={() => setFilter(category)}
                            >
                              {category === "all" ? "All checks" : category}
                              <span>
                                {
                                  result.checks.filter(
                                    (check) =>
                                      category === "all" ||
                                      check.category === category,
                                  ).length
                                }
                              </span>
                            </button>
                          ))}
                        </div>
                        <div className="finding-table-heading">
                          <span>CHECK / DESCRIPTION</span>
                          <span>CATEGORY</span>
                          <span>RESULT</span>
                          <span />
                        </div>
                        {checks.length === 0 && (
                          <div className="no-findings">
                            <Check size={20} />
                            No findings match this filter.
                          </div>
                        )}
                        {checks.map((check) => (
                          <div className="finding" key={check.id}>
                            <button
                              className="finding-row"
                              aria-expanded={expanded === check.id}
                              onClick={() =>
                                setExpanded(
                                  expanded === check.id ? null : check.id,
                                )
                              }
                            >
                              <span className="finding-title">
                                <span
                                  className={`check-icon ${resultClass(check)}`}
                                >
                                  {check.status === "passed" ? (
                                    <Check size={12} />
                                  ) : check.status === "failed" ? (
                                    "!"
                                  ) : (
                                    "—"
                                  )}
                                </span>
                                <span>
                                  {check.title}
                                  <small>
                                    {check.status === "failed"
                                      ? `${check.severity} severity · Review recommended`
                                      : check.status === "inconclusive"
                                        ? "Incomplete · Manual review needed"
                                        : check.status === "not_applicable"
                                          ? "No applicable elements"
                                          : "Meets this check’s criteria"}
                                  </small>
                                </span>
                              </span>
                              <span className="finding-category">
                                {check.category}
                              </span>
                              <span
                                className={`result-badge ${resultClass(check)}`}
                              >
                                {resultLabel(check)}
                              </span>
                              <ChevronDown
                                size={14}
                                className={
                                  expanded === check.id ? "rotate" : ""
                                }
                              />
                            </button>
                            {expanded === check.id && (
                              <div className="finding-detail">
                                <div>
                                  <span className="eyebrow">OBSERVATION</span>
                                  <p>{check.evidence}</p>
                                </div>
                                <div>
                                  <span className="eyebrow">
                                    {check.status === "passed"
                                      ? "GUIDANCE"
                                      : "RECOMMENDED ACTION"}
                                  </span>
                                  <p>{check.fix}</p>
                                </div>
                                {!!check.elements?.length && (
                                  <div className="affected-elements">
                                    <span className="eyebrow">
                                      AFFECTED ELEMENTS ·{" "}
                                      {check.element_count ??
                                        check.elements.length}
                                    </span>
                                    {check.elements.map((element, index) => (
                                      <article
                                        key={`${element.selector}-${index}`}
                                      >
                                        <code className="element-selector">
                                          {element.selector}
                                        </code>
                                        <pre>{element.html}</pre>
                                        <p>{element.fix}</p>
                                      </article>
                                    ))}
                                    {(check.element_count || 0) >
                                      check.elements.length && (
                                      <p>
                                        Showing the first{" "}
                                        {check.elements.length} elements.
                                      </p>
                                    )}
                                  </div>
                                )}
                                {!!check.links?.length && (
                                  <div className="affected-elements">
                                    <span className="eyebrow">
                                      LINK RESULTS
                                    </span>
                                    {check.links.map((link) => (
                                      <p key={link.url}>
                                        <code>{link.url}</code> —{" "}
                                        {link.outcome || "broken"}
                                        {link.status
                                          ? ` (HTTP ${link.status})`
                                          : ""}
                                      </p>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                        <div className="findings-foot">
                          <span>
                            <Crosshair size={12} />
                            Deterministic checks. No AI-generated findings.
                          </span>
                          <button onClick={() => setView("methodology")}>
                            How scoring works
                            <ArrowUpRight size={12} />
                          </button>
                        </div>
                      </section>
                    </>
                  ) : (
                    <div className="empty panel">
                      <div className="empty-target">
                        <Crosshair size={38} strokeWidth={1} />
                        <span />
                        <span />
                      </div>
                      <div className="eyebrow">
                        READY FOR YOUR FIRST ASSESSMENT
                      </div>
                      <h2>Your next move starts here.</h2>
                      <p>
                        Enter a public URL above to uncover performance,
                        <br className="desktop-break" /> accessibility, and
                        security findings in one clear report.
                      </p>
                      <div className="empty-categories">
                        {categories.map((category, index) => {
                          const Icon = categoryIcons[category];
                          return (
                            <div key={category}>
                              <span className="mono">0{index + 1}</span>
                              <Icon size={18} strokeWidth={1.3} />
                              <span>{category}</span>
                            </div>
                          );
                        })}
                      </div>
                      <div className="empty-bottom">
                        <span>STATIC + RENDERED CHECKS</span>
                        <span>ONE PAGE. THREE PERSPECTIVES.</span>
                      </div>
                    </div>
                  )}
                </>
              )}
              {(view === "history" || scans.length > 0) && (
                <section className="history panel">
                  <div className="section-heading">
                    <span className="section-number">
                      {view === "history" ? "01" : "02"}
                    </span>
                    <h2>
                      {view === "history"
                        ? "Saved assessments"
                        : "Recent assessments"}
                    </h2>
                    <span className="count-badge">{scans.length}</span>
                    {view === "overview" ? (
                      <button
                        className="text-button"
                        onClick={() => setView("history")}
                      >
                        View all
                        <ArrowUpRight size={13} />
                      </button>
                    ) : (
                      <div className="history-search">
                        <Search size={14} />
                        <input
                          aria-label="Search scan history"
                          placeholder="Search by URL"
                          value={query}
                          onChange={(e) => setQuery(e.target.value)}
                        />
                      </div>
                    )}
                  </div>
                  <div className="history-table">
                    <div className="history-head">
                      <span>TARGET WEBSITE</span>
                      <span>SCANNED AT</span>
                      <span>HEALTH</span>
                      <span>STATUS</span>
                      <span />
                    </div>
                    {scans
                      .filter(
                        (item) =>
                          view !== "history" ||
                          item.url.toLowerCase().includes(query.toLowerCase()),
                      )
                      .slice(0, view === "history" ? 100 : 4)
                      .map((item) => (
                        <button
                          className={`history-row ${selected === item.id ? "current" : ""}`}
                          key={item.id}
                          onClick={() => selectScan(item)}
                        >
                          <span className="history-target">
                            <span className="site-icon">
                              <Globe2 size={16} />
                            </span>
                            <span>
                              {hostname(item.url)}
                              <small>{item.url}</small>
                            </span>
                          </span>
                          <span className="mono muted">
                            {dateLabel(item.created_at)}
                          </span>
                          <span
                            className={`history-score ${item.result ? tone(item.result.score) : "muted"}`}
                          >
                            {item.result?.score ?? "—"}
                            <small>/ 100</small>
                          </span>
                          <span className={`history-status ${item.status}`}>
                            <span />
                            {item.status}
                          </span>
                          <ArrowUpRight size={15} />
                        </button>
                      ))}
                  </div>
                  {view === "history" &&
                    !scans.some((item) =>
                      item.url.toLowerCase().includes(query.toLowerCase()),
                    ) && (
                      <div className="no-findings">
                        {scans.length
                          ? "No assessments match your search."
                          : "Your saved scans will appear here after your first assessment."}
                      </div>
                    )}
                </section>
              )}
            </>
          )}
          <footer>
            <span>
              <Crosshair size={12} />
              SITE SCAN<span className="footer-separator">/</span>OBSERVE.
              UNDERSTAND. IMPROVE.
            </span>
            <span>
              CS 4094<span className="footer-separator">/</span>V0.1.0
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
