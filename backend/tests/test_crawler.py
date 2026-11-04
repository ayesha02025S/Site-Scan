import asyncio

import pytest

import crawler
from scanner import ScanError


def report(url, links=()):
    return {
        "final_url": url,
        "title": url,
        "http_status": 200,
        "score": 100,
        "scores": {},
        "checks": [
            {
                "id": "title",
                "category": "accessibility",
                "severity": "high",
                "status": "passed",
            }
        ],
        "discovered_links": list(links),
        "rendered_accessibility": {"status": "completed"},
    }


def test_limit_dedup_scope_and_page_ids(monkeypatch):
    calls = []

    async def scan(url, allowed_origin=None, link_cache=None):
        calls.append(url)
        return report(
            url,
            [f"https://example.com/{i}" for i in range(20)]
            + [url + "#fragment", "https://other.com/"],
        )

    monkeypatch.setattr(crawler, "scan_page", scan)
    result = asyncio.run(crawler.scan_website("https://example.com/"))
    assert len(calls) == len(set(calls)) == 20
    assert all(url.startswith("https://example.com/") for url in calls)
    assert len({c["id"] for c in result["checks"]}) == 20
    assert result["crawl"]["limit"] == 20
    assert result["crawl"]["attempted"] == 20
    assert result["crawl"]["remaining"] == 1
    assert "https://example.com/19" not in calls
    assert result["crawl"]["status"] == "partial"
    assert all(c["page_url"] for c in result["checks"])


def test_child_failure_and_nested_discovery(monkeypatch):
    async def scan(url, allowed_origin=None, link_cache=None):
        if url.endswith("/bad"):
            raise ScanError("Unavailable")
        links = {
            "https://example.com/": [
                "https://example.com/bad",
                "https://example.com/two",
            ],
            "https://example.com/two": ["https://example.com/three"],
        }
        return report(url, links.get(url, []))

    monkeypatch.setattr(crawler, "scan_page", scan)
    result = asyncio.run(crawler.scan_website("https://example.com/"))
    assert result["crawl"]["completed"] == 3
    assert result["crawl"]["attempted"] == 4
    assert result["pages"][1]["error"] == "Unavailable"


def test_root_failure(monkeypatch):
    async def scan(*args, **kwargs):
        raise ScanError("Unavailable")

    monkeypatch.setattr(crawler, "scan_page", scan)
    with pytest.raises(ScanError):
        asyncio.run(crawler.scan_website("https://example.com/"))


def test_deadline_keeps_completed_pages(monkeypatch):
    async def scan(url, allowed_origin=None, link_cache=None):
        if allowed_origin:
            await asyncio.sleep(1)
        return report(url, ["https://example.com/slow"])

    monkeypatch.setattr(crawler, "scan_page", scan)
    monkeypatch.setattr(crawler, "CRAWL_SECONDS", 0.02)
    result = asyncio.run(crawler.scan_website("https://example.com/"))
    assert result["crawl"]["timed_out"]
    assert result["crawl"]["completed"] == 1


def test_redirect_aliases_do_not_duplicate_findings(monkeypatch):
    async def scan(url, allowed_origin=None, link_cache=None):
        if not allowed_origin:
            return report(
                url, ["https://example.com/alias", "https://example.com/target"]
            )
        return report("https://example.com/target")

    monkeypatch.setattr(crawler, "scan_page", scan)
    result = asyncio.run(crawler.scan_website("https://example.com/"))
    assert result["crawl"]["completed"] == 2
    assert len(result["checks"]) == 2


def test_same_origin_excludes_subdomains_and_scheme_changes(monkeypatch):
    calls = []

    async def scan(url, allowed_origin=None, link_cache=None):
        calls.append(url)
        return report(
            url,
            [
                "http://example.com/",
                "https://sub.example.com/",
                "https://example.com/a",
            ],
        )

    monkeypatch.setattr(crawler, "scan_page", scan)
    asyncio.run(crawler.scan_website("https://example.com/"))
    assert calls == ["https://example.com/", "https://example.com/a"]


def test_non_pages_are_not_crawled_and_skips_keep_full_coverage(monkeypatch):
    from scanner import PageSkipped

    calls = []

    async def scan(url, allowed_origin=None, link_cache=None):
        calls.append(url)
        if url.endswith("/feed"):
            raise PageSkipped("The URL did not return an HTML page.")
        return report(
            url,
            [
                "https://example.com/guide.PDF",
                "https://example.com/feed",
                "https://example.com/about/",
                "https://example.com/about",
                "https://example.com/about?utm_source=mail",
                "https://example.com/list?page=2",
            ],
        )

    monkeypatch.setattr(crawler, "scan_page", scan)
    result = asyncio.run(crawler.scan_website("https://example.com/"))
    assert calls == [
        "https://example.com/",
        "https://example.com/feed",
        "https://example.com/about/",
        "https://example.com/list?page=2",
    ]
    assert result["crawl"]["status"] == "completed"
    assert result["crawl"]["attempted"] == 3
    assert [p["status"] for p in result["pages"]].count("skipped") == 1


def test_root_page_that_cannot_be_audited_fails_the_scan(monkeypatch):
    from scanner import PageSkipped

    async def scan(url, allowed_origin=None, link_cache=None):
        raise PageSkipped("The website refused the automated scan (HTTP 403).")

    monkeypatch.setattr(crawler, "scan_page", scan)
    with pytest.raises(ScanError, match="refused"):
        asyncio.run(crawler.scan_website("https://example.com/"))


def test_redirect_duplicates_leave_room_for_unique_pages(monkeypatch):
    async def scan(url, **kwargs):
        if url == 'https://example.com/':
            return report(url, ['https://example.com/a', 'https://example.com/alias', 'https://example.com/b'])
        if url.endswith('/alias'):
            return report('https://example.com/a')
        return report(url)
    monkeypatch.setattr(crawler, 'scan_page', scan)
    monkeypatch.setattr(crawler, 'MAX_PAGES', 3)
    result = asyncio.run(crawler.scan_website('https://example.com/'))
    assert result['crawl']['completed'] == result['crawl']['attempted'] == 3
    assert result['crawl']['status'] == 'completed'
    assert any(page['url'].endswith('/b') for page in result['pages'])


def test_tracking_variants_keep_same_finding_identity(monkeypatch):
    async def scan(url, **kwargs):
        return report(url)
    monkeypatch.setattr(crawler, 'scan_page', scan)
    one = asyncio.run(crawler.scan_website('https://example.com/about/?utm_source=mail'))
    two = asyncio.run(crawler.scan_website('https://example.com/about'))
    assert one['checks'][0]['id'] == two['checks'][0]['id']
