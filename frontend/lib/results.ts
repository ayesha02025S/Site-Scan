export type Category = "performance" | "accessibility" | "security";
export type CheckResult = {
  id: string;
  page_url?: string;
  category: Category;
  title: string;
  status: "passed" | "failed" | "inconclusive" | "not_applicable";
  severity: "high" | "medium" | "low";
  evidence: string;
  fix: string;
  source?: string;
  help_url?: string;
  element_count?: number;
  elements?: { selector: string; html: string; fix: string; impact?: string }[];
  links?: { url: string; status: number | null; outcome?: string }[];
};
export type Explanation = {
  source: "ai" | "rules";
  model: string | null;
  note: string | null;
  summary: string;
  top_fixes: {
    check_id: string;
    title: string;
    category: Category;
    severity: CheckResult["severity"];
    why: string;
    how: string;
  }[];
};
export type Result = {
  pages?: {
    url: string;
    final_url?: string;
    status: string;
    title?: string;
    score?: number;
    error?: string;
  }[];
  crawl?: {
    limit: number;
    completed: number;
    attempted: number;
    remaining: number;
    timed_out: boolean;
    status: string;
  };
  final_url: string;
  http_status: number;
  response_ms: number;
  size_bytes: number;
  redirects: number;
  title: string;
  scores: Record<Category, number>;
  score: number;
  checks: CheckResult[];
  scanner_version?: string;
  scoring_version?: string;
  explanation?: Explanation;
  rendered_accessibility?: {
    status: string;
    message: string;
    engine_version?: string;
  };
};
export type Scan = {
  id: string;
  url: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  result: Result | null;
  error: string | null;
};

export function normalizedUrl(value: string) {
  try {
    const url = new URL(value);
    url.hash = "";
    return url.href;
  } catch {
    return value;
  }
}

export function previousScan(scans: Scan[], selected: Scan) {
  return scans
    .filter(
      (item) =>
        item.id !== selected.id &&
        normalizedUrl(item.url) === normalizedUrl(selected.url) &&
        item.status === "completed" &&
        item.result &&
        new Date(item.created_at) < new Date(selected.created_at),
    )
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )[0];
}

export function compareResults(current: Result, previous: Result) {
  const compatible =
    !!current.scoring_version &&
    current.scoring_version === previous.scoring_version &&
    current.scanner_version === previous.scanner_version;
  const before = new Map(previous.checks.map((check) => [check.id, check]));
  const after = new Map(current.checks.map((check) => [check.id, check]));
  const evaluated = (result: Result) =>
    result.checks
      .filter((c) => c.status === "passed" || c.status === "failed")
      .map((c) => c.id)
      .sort()
      .join("|");
  return {
    compatible,
    delta:
      compatible && evaluated(current) === evaluated(previous)
        ? current.score - previous.score
        : null,
    introduced: compatible
      ? current.checks.filter(
          (c) => c.status === "failed" && before.get(c.id)?.status === "passed",
        )
      : [],
    resolved: compatible
      ? previous.checks.filter(
          (c) => c.status === "failed" && after.get(c.id)?.status === "passed",
        )
      : [],
    ongoing: compatible
      ? current.checks.filter(
          (c) => c.status === "failed" && before.get(c.id)?.status === "failed",
        )
      : [],
  };
}

export function resultClass(check: CheckResult) {
  return check.status === "failed" ? check.severity : check.status;
}

export function resultLabel(check: CheckResult) {
  return check.status === "failed"
    ? check.severity.toUpperCase()
    : check.status === "inconclusive"
      ? "REVIEW"
      : check.status === "not_applicable"
        ? "N/A"
        : "PASSED";
}

export function trendScans(scans: Scan[], selected: Scan) {
  return scans
    .filter(
      (scan) =>
        scan.status === "completed" &&
        scan.result &&
        Number.isFinite(Date.parse(scan.created_at)) &&
        normalizedUrl(scan.url) === normalizedUrl(selected.url),
    )
    .sort(
      (a, b) =>
        Date.parse(a.created_at) - Date.parse(b.created_at) ||
        a.id.localeCompare(b.id),
    );
}
