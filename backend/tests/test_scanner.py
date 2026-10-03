import asyncio
import socket

import pytest

from scanner import (
    PublicResolver,
    ScanError,
    analyze,
    extract_links,
    public_ip,
    validate_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "https://[::1]",
        "https://[::ffff:127.0.0.1]",
        "http://169.254.169.254/latest/meta-data",
        "http://224.0.0.1",
        "ftp://example.com",
        "https://user:pass@example.com",
        "https://example.com:8080",
        "https://test.local",
        "https://example.com\\@localhost",
        "https://example.com\n",
    ],
)
def test_rejects_unsafe_urls(url):
    if url.endswith("\n"):
        assert validate_url(url) == "https://example.com"
    else:
        with pytest.raises(ScanError):
            validate_url(url)


def test_normalizes_public_url():
    assert validate_url("example.com/path#section") == "https://example.com/path"
    assert public_ip("8.8.8.8")
    assert not public_ip("100.64.0.1")


def test_resolver_blocks_mixed_public_private_answers(monkeypatch):
    async def run():
        loop = asyncio.get_running_loop()

        async def lookup(*args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            ]

        monkeypatch.setattr(loop, "getaddrinfo", lookup)
        with pytest.raises(ScanError):
            await PublicResolver().resolve("example.com", 443)

    asyncio.run(run())


def test_known_issues_and_scores():
    report = analyze(
        "http://example.com",
        "http://example.com",
        500,
        {},
        '<html><img src="x"><input><title></title></html>',
        2000,
        400000,
        0,
    )
    assert report["score"] == 0
    assert len(report["checks"]) == 12
    assert all(check["status"] == "failed" for check in report["checks"])
    assert all(check["evidence"] and check["fix"] for check in report["checks"])


def test_clean_fixture_and_decorative_image():
    html = '<html lang="en"><title>Test page</title><img alt=""><label for="email">Email</label><input id="email"><label>Name<input></label><input aria-label="Search"><span id="a">Label</span><input aria-labelledby="a"></html>'
    headers = {
        "content-security-policy": "default-src 'self'",
        "strict-transport-security": "max-age=31536000; includeSubDomains",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin-when-cross-origin",
    }
    report = analyze(
        "https://example.com", "https://example.com", 200, headers, html, 300, 1000, 1
    )
    assert report["score"] == 100
    assert all(value == 100 for value in report["scores"].values())
    assert all(check["status"] == "passed" for check in report["checks"])


def test_empty_labels_and_disabled_hsts_fail():
    html = '<html lang="en"><title>Test</title><label for="a"></label><input id="a"><input aria-labelledby="missing"></html>'
    report = analyze(
        "https://example.com",
        "https://example.com",
        200,
        {"strict-transport-security": "max-age=0", "x-content-type-options": "other"},
        html,
        10,
        100,
        0,
    )
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["form-labels"]["status"] == "failed"
    assert checks["strict-transport-security"]["status"] == "failed"
    assert checks["x-content-type-options"]["status"] == "failed"


class FakeContent:
    def __init__(self, body):
        self.body = body

    async def iter_chunked(self, size):
        for offset in range(0, len(self.body), size):
            yield self.body[offset : offset + size]


class FakeResponse:
    def __init__(
        self,
        status=200,
        headers=None,
        body=b'<html lang="en"><title>Fixture</title></html>',
    ):
        self.status = status
        self.headers = headers if headers is not None else {"Content-Type": "text/html"}
        self.content = FakeContent(body)
        self.charset = "utf-8"
        self.url = "https://example.com"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def fake_session(monkeypatch, responses):
    import scanner

    requests = []

    class Client:
        def __init__(self, **kwargs):
            self.connector = kwargs["connector"]
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.connector.close()

        def get(self, url, **kwargs):
            assert kwargs["allow_redirects"] is False
            requests.append(url)
            if not responses:
                raise TimeoutError()
            return responses.pop(0)

    monkeypatch.setattr(scanner.aiohttp, "ClientSession", Client)
    return requests


def test_redirect_to_private_destination_never_requested(monkeypatch):
    from scanner import scan_page

    requests = fake_session(
        monkeypatch, [FakeResponse(302, {"Location": "http://127.0.0.1/admin"})]
    )
    with pytest.raises(ScanError, match="Private"):
        asyncio.run(scan_page("https://example.com"))
    assert requests == ["https://example.com"]


def test_redirect_limit(monkeypatch):
    from scanner import scan_page

    requests = fake_session(
        monkeypatch, [FakeResponse(302, {"Location": "/again"}) for _ in range(6)]
    )
    with pytest.raises(ScanError, match="five redirects"):
        asyncio.run(scan_page("https://example.com"))
    assert len(requests) == 6


def test_html_size_limit(monkeypatch):
    import scanner

    monkeypatch.setattr(scanner, "MAX_BYTES", 8)
    fake_session(monkeypatch, [FakeResponse(body=b"x" * 20)])
    with pytest.raises(ScanError, match="2 MB"):
        asyncio.run(scanner.scan_page("https://example.com"))


def test_non_html_rejected(monkeypatch):
    from scanner import scan_page

    fake_session(
        monkeypatch, [FakeResponse(headers={"Content-Type": "application/json"})]
    )
    with pytest.raises(ScanError, match="HTML"):
        asyncio.run(scan_page("https://example.com"))


def test_timeout_is_actionable(monkeypatch):
    from scanner import scan_page

    fake_session(monkeypatch, [])
    with pytest.raises(ScanError, match="too long"):
        asyncio.run(scan_page("https://example.com"))


def test_bounded_fetch_returns_real_analysis(monkeypatch):
    from scanner import scan_page

    fake_session(monkeypatch, [FakeResponse()])
    report = asyncio.run(scan_page("https://example.com"))
    assert report["title"] == "Fixture"
    assert report["http_status"] == 200
    assert len(report["checks"]) == 13


def test_https_downgrade_is_reported(monkeypatch):
    from scanner import scan_page

    fake_session(
        monkeypatch,
        [
            FakeResponse(302, {"Location": "http://example.com"}),
            FakeResponse(302, {"Location": "https://example.com"}),
            FakeResponse(),
        ],
    )
    report = asyncio.run(scan_page("https://example.com"))
    check = next(item for item in report["checks"] if item["id"] == "https")
    assert check["status"] == "failed"
    assert "stayed on HTTPS: no" in check["evidence"]


def test_extract_links_filters_and_dedupes():
    html = (
        '<a href="/about">A</a><a href="/about#team">B</a><a href="#top">C</a>'
        '<a href="mailto:x@example.com">D</a><a href="http://127.0.0.1/admin">E</a>'
        '<a href="https://other.example.org/page">F</a><a href="javascript:void(0)">G</a>'
    )
    assert extract_links(html, "https://example.com/") == [
        "https://example.com/about",
        "https://other.example.org/page",
    ]


def test_broken_links_check():
    args = ("https://example.com", "https://example.com", 200, {}, "<html></html>", 100, 100, 0)
    assert len(analyze(*args)["checks"]) == 12
    clean = analyze(
        *args, links={"found": 3, "checked": 3, "broken": [], "unverified": 0}
    )
    check = next(c for c in clean["checks"] if c["id"] == "broken-links")
    assert check["status"] == "passed" and check["category"] == "performance"
    report = analyze(
        *args,
        links={
            "found": 4,
            "checked": 3,
            "broken": [
                {"url": "https://example.com/gone", "status": 404},
                {"url": "https://dead.example", "status": 0},
            ],
            "unverified": 1,
        },
    )
    check = next(c for c in report["checks"] if c["id"] == "broken-links")
    assert check["status"] == "failed"
    assert "2 of 3" in check["evidence"] and "HTTP 404" in check["evidence"]
    assert "unreachable" in check["evidence"] and "1 links could not" in check["evidence"]
    assert report["scores"]["performance"] < clean["scores"]["performance"]
