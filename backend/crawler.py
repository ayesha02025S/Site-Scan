import asyncio
import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from scanner import PageSkipped, ScanError, scan_page, score_checks, validate_url

MAX_PAGES = 20
CRAWL_SECONDS = 240
TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid", "msclkid", "ref_src"}
NON_PAGE_SUFFIXES = (
    ".7z", ".avi", ".css", ".csv", ".dmg", ".doc", ".docx", ".exe", ".gif", ".gz",
    ".ico", ".jpeg", ".jpg", ".js", ".json", ".mov", ".mp3", ".mp4", ".pdf", ".png",
    ".ppt", ".pptx", ".rar", ".rss", ".svg", ".tar", ".wav", ".webm", ".webp", ".xls",
    ".xlsx", ".xml", ".zip",
)


def crawl_key(url):
    """Identify URLs that serve the same page, ignoring a trailing slash and tracking tags."""
    parts = urlsplit(url)
    query = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not name.lower().startswith("utm_")
        and name.lower() not in TRACKING_PARAMETERS
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/"), urlencode(query), "")
    )


async def scan_website(url):
    url = validate_url(url)
    queue = [url]
    seen = {crawl_key(url)}
    completed = set()
    link_cache = {}
    pages = []
    checks = []
    attempts = 0
    root = None
    origin = None
    deadline = asyncio.get_running_loop().time() + CRAWL_SECONDS
    timed_out = False
    while queue and attempts < MAX_PAGES:
        current = queue.pop(0)
        if crawl_key(current) in completed:
            continue
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            timed_out = True
            break
        try:
            async with asyncio.timeout(remaining):
                page = await scan_page(
                    current, allowed_origin=origin, link_cache=link_cache
                )
        except PageSkipped as exc:
            if root is None:
                raise ScanError(str(exc)) from exc
            pages.append({"url": current, "status": "skipped", "error": str(exc)})
            continue
        except (ScanError, TimeoutError) as exc:
            if root is None:
                raise ScanError(str(exc) or "The website scan timed out.") from exc
            attempts += 1
            pages.append(
                {
                    "url": current,
                    "status": "failed",
                    "error": str(exc) or "Page timed out.",
                }
            )
            if isinstance(exc, TimeoutError):
                timed_out = True
                break
            continue
        attempts += 1
        final = validate_url(page["final_url"])
        final_key = crawl_key(final)
        if root is None:
            root = page
            origin = (urlsplit(final).scheme, urlsplit(final).netloc)
        if final_key in completed:
            pages.append({"url": current, "final_url": final, "status": "duplicate"})
            continue
        completed.update((crawl_key(current), final_key))
        seen.add(final_key)
        for target in page.pop("discovered_links", []):
            try:
                target = validate_url(target)
            except ValueError:
                continue
            parts = urlsplit(target)
            if (
                (parts.scheme, parts.netloc) == origin
                and crawl_key(target) not in seen
                and not parts.path.lower().endswith(NON_PAGE_SUFFIXES)
            ):
                seen.add(crawl_key(target))
                queue.append(target)
        page_key = hashlib.sha256(final.encode()).hexdigest()[:16]
        for check in page["checks"]:
            checks.append(
                {
                    **check,
                    "rule_id": check["id"],
                    "id": f'{page_key}-{check["id"]}',
                    "page_url": final,
                }
            )
        pages.append(
            {
                "url": current,
                "final_url": final,
                "status": "completed",
                "title": page["title"],
                "http_status": page["http_status"],
                "score": page["score"],
                "scores": page["scores"],
                "rendered_accessibility": page.get("rendered_accessibility"),
            }
        )
    scores, score = score_checks(checks)
    partial = timed_out or bool(queue) or any(p["status"] == "failed" for p in pages)
    browser_partial = any(
        p.get("rendered_accessibility", {}).get("status") != "completed"
        for p in pages
        if p["status"] == "completed"
    )
    return {
        **root,
        "checks": checks,
        "scores": scores,
        "score": score,
        "scanner_version": "3.1",
        "scoring_version": "3.0",
        "pages": pages,
        "crawl": {
            "limit": MAX_PAGES,
            "attempted": attempts,
            "completed": sum(p["status"] == "completed" for p in pages),
            "remaining": len(queue),
            "timed_out": timed_out,
            "status": "partial" if partial else "completed",
        },
        "coverage": {
            state: sum(c["status"] == state for c in checks)
            for state in ("passed", "failed", "inconclusive", "not_applicable")
        },
        "rendered_accessibility": {
            "status": "partial" if partial or browser_partial else "completed",
            "message": "Each completed page was audited separately. Scores include evaluated checks only; failed pages and incomplete browser checks need review.",
        },
    }
