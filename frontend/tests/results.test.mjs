import test from "node:test";
import assert from "node:assert/strict";
import {
  compareResults,
  normalizedUrl,
  previousScan,
  resultLabel,
} from "../lib/results.ts";
const check = (id, status) => ({ id, status });
const result = (checks, extras = {}) => ({
  checks,
  score: 75,
  scanner_version: "2.0",
  scoring_version: "2.0",
  ...extras,
});
test("unknown and new checks are not regressions", () => {
  const before = result([
    check("a", "passed"),
    check("b", "failed"),
    check("c", "inconclusive"),
  ]);
  const after = result([
    check("a", "failed"),
    check("b", "passed"),
    check("c", "failed"),
    check("new", "failed"),
  ]);
  const diff = compareResults(after, before);
  assert.deepEqual(
    diff.introduced.map((c) => c.id),
    ["a"],
  );
  assert.deepEqual(
    diff.resolved.map((c) => c.id),
    ["b"],
  );
  assert.equal(diff.delta, null);
});
test("incomplete checks do not count as resolved", () => {
  const diff = compareResults(
    result([check("a", "inconclusive")]),
    result([check("a", "failed")]),
  );
  assert.equal(diff.resolved.length, 0);
});
test("legacy and version changes suppress comparison", () => {
  assert.equal(
    compareResults(
      result([]),
      result([], { scanner_version: undefined, scoring_version: undefined }),
    ).compatible,
    false,
  );
  assert.equal(
    compareResults(result([]), result([], { scoring_version: "1.0" })).delta,
    null,
  );
});
test("same coverage supports score delta and ongoing issues", () => {
  const diff = compareResults(
    result([check("a", "failed")], { score: 50 }),
    result([check("a", "failed")], { score: 60 }),
  );
  assert.equal(diff.delta, -10);
  assert.equal(diff.ongoing.length, 1);
});
test("canonical URL matching chooses most recent older completed scan", () => {
  assert.equal(
    normalizedUrl("https://EXAMPLE.com:443#top"),
    "https://example.com/",
  );
  const selected = {
    id: "3",
    url: "https://example.com/",
    created_at: "2026-10-06",
    status: "completed",
    result: result([]),
  };
  const scans = [
    { ...selected, id: "1", created_at: "2026-10-01" },
    {
      ...selected,
      id: "2",
      url: "https://EXAMPLE.com:443",
      created_at: "2026-10-04",
    },
    selected,
  ];
  assert.equal(previousScan(scans, selected).id, "2");
});
test("unknown check statuses are clearly labeled", () => {
  assert.equal(resultLabel(check("a", "inconclusive")), "REVIEW");
  assert.equal(resultLabel(check("a", "not_applicable")), "N/A");
});
