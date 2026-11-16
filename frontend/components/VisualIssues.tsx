"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import type { Result } from "../lib/results";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function VisualIssues({
  scanId,
  result,
}: {
  scanId: string;
  result: Result;
}) {
  const pages = result.pages || [];
  const available = pages
    .map((page, index) => ({ page, index }))
    .filter(({ page }) => page.visual_audit?.has_screenshot);
  const [pageIndex, setPageIndex] = useState(available[0]?.index ?? 0);
  const [selected, setSelected] = useState<number | null>(null);
  const [image, setImage] = useState("");
  const [error, setError] = useState("");
  const { getToken } = useAuth();
  const page = pages[pageIndex];
  const visual = page?.visual_audit;
  const hasScreenshot = !!visual?.has_screenshot;

  useEffect(() => {
    setImage("");
    setError("");
    setSelected(null);
    if (!hasScreenshot) return;
    const controller = new AbortController();
    let objectUrl = "";
    async function loadImage() {
      try {
        const token = await getToken();
        if (!token)
          throw new Error("Please sign in again to view the screenshot.");
        const response = await fetch(
          `${API}/scans/${scanId}/pages/${pageIndex}/screenshot`,
          {
            headers: { Authorization: `Bearer ${token}` },
            cache: "no-store",
            signal: AbortSignal.any([
              controller.signal,
              AbortSignal.timeout(15000),
            ]),
          },
        );
        if (!response.ok)
          throw new Error(
            "The screenshot could not be loaded. Try reopening this report.",
          );
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setImage(objectUrl);
      } catch (exc) {
        if (!controller.signal.aborted) setError((exc as Error).message);
      }
    }
    void loadImage();
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [getToken, scanId, pageIndex, hasScreenshot]);

  const highlights = visual?.highlights || [];
  const unavailableReasons = [...new Set(pages.map((item) => item.visual_audit?.message || (item.rendered_accessibility?.status !== "completed" ? item.rendered_accessibility?.message : undefined)).filter(Boolean))];
  const highlight = selected === null ? undefined : highlights[selected];
  const check =
    highlight &&
    result.checks.find(
      (item) =>
        item.page_url === (page.final_url || page.url) &&
        item.rule_id === highlight.rule_id,
    );
  const element = check?.elements?.find(
    (item) => item.selector === highlight?.selector,
  );

  return (
    <section
      className="visual-issues panel"
      aria-label="Visual accessibility findings"
    >
      <div className="section-heading">
        <h2>See accessibility issues</h2>
        <span className="tag">PAGE SNAPSHOT</span>
      </div>
      <p className="visual-note">
        When available, a 1280 × 900 viewport captured during this scan. Select a numbered
        marker to inspect a confirmed axe-core issue. Markers cover visible elements only. Issues below the captured area
        and elements without a visible rectangle remain in Assessment findings.
      </p>
      {result.rendered_accessibility?.status !== "completed" && result.rendered_accessibility && (
        <p className="visual-note" role="status">Browser audit incomplete. Missing markers do not establish that the page has no accessibility issues.</p>
      )}
      {available.length > 0 ? (
        <>
          <label className="visual-page-label">
            Scanned page
            <select
              value={pageIndex}
              onChange={(event) => setPageIndex(Number(event.target.value))}
            >
              {available.map(({ page: item, index }) => (
                <option value={index} key={index}>
                  {item.final_url || item.url}
                </option>
              ))}
            </select>
          </label>
          {error ? (
            <p role="alert" className="visual-note">
              {error}
            </p>
          ) : !image ? (
            <p role="status" className="visual-note">
              Loading private screenshot…
            </p>
          ) : (
            <>
              <div
                className="visual-canvas"
                style={{
                  aspectRatio: `${visual?.width || 1280} / ${visual?.height || 900}`,
                }}
              >
                <img
                  src={image}
                  alt={`Captured viewport of ${page.final_url || page.url}`}
                />
                {highlights.map((item, index) => (
                  <button
                    key={index}
                    type="button"
                    className={`visual-marker ${selected === index ? "selected" : ""}`}
                    aria-label={`Issue ${index + 1}: ${item.selector}`}
                    aria-pressed={selected === index}
                    onClick={() => setSelected(index)}
                    style={{
                      left: `${(100 * item.x) / visual!.width}%`,
                      top: `${(100 * item.y) / visual!.height}%`,
                      width: `${(100 * item.width) / visual!.width}%`,
                      height: `${(100 * item.height) / visual!.height}%`,
                    }}
                  >
                    <span>{index + 1}</span>
                  </button>
                ))}
              </div>
              <p className="visual-note">
                {highlights.length} highlighted element
                {highlights.length === 1 ? "" : "s"} in this viewport.
              </p>
              <div className="visual-list" aria-label="Highlighted elements">
                {highlights.map((item, index) => (
                  <button
                    type="button"
                    key={index}
                    aria-pressed={selected === index}
                    onClick={() => setSelected(index)}
                  >
                    {index + 1}. {item.selector}
                  </button>
                ))}
              </div>
              {highlight && (
                <div className="visual-detail" aria-live="polite">
                  <h3>{check?.title || "Accessibility issue"}</h3>
                  <code>{highlight.selector}</code>
                  <p>
                    {element?.fix ||
                      check?.fix ||
                      "Review this element in Assessment findings."}
                  </p>
                </div>
              )}
            </>
          )}
        </>
      ) : (
        <p className="visual-note">
          This report has no screenshot. Run another assessment to capture one.
          Screenshots may be unavailable if the page or browser audit could not
          finish. {unavailableReasons.slice(0, 3).join(" ")}
        </p>
      )}
    </section>
  );
}
