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

    async def scan(url, allowed_origin=None):
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
    async def scan(url, allowed_origin=None):
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
    async def scan(url, allowed_origin=None):
        if allowed_origin:
            await asyncio.sleep(1)
        return report(url, ["https://example.com/slow"])

    monkeypatch.setattr(crawler, "scan_page", scan)
    monkeypatch.setattr(crawler, "CRAWL_SECONDS", 0.02)
    result = asyncio.run(crawler.scan_website("https://example.com/"))
    assert result["crawl"]["timed_out"]
    assert result["crawl"]["completed"] == 1


def test_redirect_aliases_do_not_duplicate_findings(monkeypatch):
    async def scan(url, allowed_origin=None):
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

    async def scan(url, allowed_origin=None):
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
