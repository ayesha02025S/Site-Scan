import asyncio
import hashlib
from urllib.parse import urlsplit

from scanner import ScanError, scan_page, score_checks, validate_url

MAX_PAGES = 10
CRAWL_SECONDS = 240


async def scan_website(url):
    url = validate_url(url)
    queue = [url]
    seen = {url}
    completed = set()
    pages = []
    checks = []
    root = None
    origin = None
    deadline = asyncio.get_running_loop().time() + CRAWL_SECONDS
    timed_out = False
    while queue and len(pages) < MAX_PAGES:
        current = queue.pop(0)
        if current in completed:
            continue
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            timed_out = True
            break
        try:
            async with asyncio.timeout(remaining):
                page = await scan_page(current, allowed_origin=origin)
        except (ScanError, TimeoutError) as exc:
            if root is None:
                raise ScanError(str(exc) or "The website scan timed out.") from exc
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
        final = validate_url(page["final_url"])
        if root is None:
            root = page
            origin = (urlsplit(final).scheme, urlsplit(final).netloc)
        if final in completed:
            pages.append({"url": current, "final_url": final, "status": "duplicate"})
            continue
        completed.update((current, final))
        seen.add(final)
        for target in page.pop("discovered_links", []):
            try:
                target = validate_url(target)
            except ValueError:
                continue
            if (
                urlsplit(target).scheme,
                urlsplit(target).netloc,
            ) == origin and target not in seen:
                seen.add(target)
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
        "scanner_version": "3.0",
        "scoring_version": "3.0",
        "pages": pages,
        "crawl": {
            "limit": MAX_PAGES,
            "attempted": len(pages),
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
