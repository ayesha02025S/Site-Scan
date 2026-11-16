import asyncio
import base64
from pathlib import Path

import pytest

from accessibility import AXE_PATH, RULES, SafeResources, audit_page, convert_results
from network import ScanError


def test_partial_results_dont_pass():
    raw = {
        "passes": [{"id": "button-name", "nodes": [{"target": ["#good"]}]}],
        "inapplicable": [{"id": "aria-roles", "nodes": []}],
    }
    checks = convert_results(raw, partial=True)
    assert all(check["status"] == "inconclusive" for check in checks)
    assert all(check["elements"] == [] for check in checks)
    assert all(check["element_count"] == 0 for check in checks)


def test_failure_details_are_preserved_as_text():
    raw = {
        "violations": [
            {
                "id": "button-name",
                "nodes": [
                    {
                        "target": ["#send"],
                        "html": '<button id="send"></button>',
                        "failureSummary": "Add accessible text.",
                    }
                ],
            }
        ]
    }
    c = next(c for c in convert_results(raw) if c["id"] == "axe-button-name")
    assert c["status"] == "failed"
    assert c["elements"][0]["selector"] == "#send"
    assert c["elements"][0]["fix"] == "Add accessible text."


def test_network_guard_rejects_private_resources_before_request():
    class Client:
        def get(self, *args, **kwargs):
            raise AssertionError("Private network request occurred")

    async def run():
        guard = SafeResources(Client())
        for url in [
            "http://127.0.0.1/secret",
            "http://169.254.169.254/",
            "file:///etc/passwd",
            "https://[::1]/",
        ]:
            with pytest.raises(ScanError):
                await guard.fetch(url)

    asyncio.run(run())


def test_missing_axe_is_inconclusive(monkeypatch, tmp_path):
    monkeypatch.setattr("accessibility.AXE_PATH", tmp_path / "absent.js")
    result = asyncio.run(audit_page("https://example.com/"))
    assert result["status"] == "unavailable"
    assert len(result["checks"]) == len(RULES)
    assert all(c["status"] == "inconclusive" for c in result["checks"])


@pytest.mark.browser
def test_real_chromium_detects_rendered_violations_and_fixes(monkeypatch):
    html = (Path(__file__).parent / "fixtures/accessibility.html").read_text()

    async def fetch_fixture(self, url):
        if url.rstrip("/") != "https://fixture.example":
            raise ScanError("Only fixture resources are allowed")
        return 200, {"Content-Type": "text/html"}, html.encode()

    monkeypatch.setattr(SafeResources, "fetch", fetch_fixture)
    report = asyncio.run(audit_page("https://fixture.example/"))
    assert report["status"] in ("completed", "partial"), report["message"]
    visual = report["visual_audit"]
    assert visual["status"] == "completed"
    image = base64.b64decode(visual["image_base64"])
    assert image.startswith(b"\xff\xd8") and len(image) <= 200000
    button = next(item for item in visual["highlights"] if item["selector"] == "#dynamic-button")
    assert button["rule_id"] == "axe-button-name"
    assert 0 <= button["x"] < 1280 and 0 <= button["y"] < 900
    assert {key: button[key] for key in ("x", "y", "width", "height")} == {"x": 200, "y": 200, "width": 100, "height": 40}
    checks = {c["id"]: c for c in report["checks"]}
    for rule in [
        "color-contrast",
        "button-name",
        "aria-valid-attr",
        "aria-valid-attr-value",
    ]:
        assert checks["axe-" + rule]["status"] == "failed", checks["axe-" + rule]
        assert checks["axe-" + rule]["elements"][0]["fix"]
    assert checks["axe-button-name"]["elements"][0]["selector"] == "#dynamic-button"
    html = (
        html.replace("color:#ccc", "color:#333")
        .replace('aria-checked="invalid"', 'aria-checked="false"')
        .replace('aria-madeup="yes"', 'aria-label="Settings"')
        .replace(
            "b.id='dynamic-button';",
            "b.id='dynamic-button';b.setAttribute('aria-label','Close');",
        )
    )
    fixed = asyncio.run(audit_page("https://fixture.example/"))
    fixed_checks = {c["id"]: c for c in fixed["checks"]}
    for rule in [
        "color-contrast",
        "button-name",
        "aria-valid-attr",
        "aria-valid-attr-value",
    ]:
        assert fixed_checks["axe-" + rule]["status"] == "passed", fixed_checks[
            "axe-" + rule
        ]


def test_redirect_to_private_resource_is_blocked():
    class Redirect:
        status = 302
        headers = {"Location": "http://127.0.0.1/secret"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Client:
        calls = []

        def get(self, url, **kwargs):
            self.calls.append(url)
            assert len(self.calls) == 1
            return Redirect()

    client = Client()

    async def run():
        with pytest.raises(ScanError):
            await SafeResources(client).fetch("https://example.com/")

    asyncio.run(run())
    assert client.calls == ["https://example.com/"]


def test_visual_capture_failure_is_nonfatal():
    from accessibility import capture_visual

    class BrokenPage:
        async def evaluate(self, *args):
            raise RuntimeError("Screenshot unavailable")

    result = asyncio.run(capture_visual(BrokenPage(), {}))
    assert result["status"] == "unavailable"


@pytest.mark.browser
def test_slow_image_does_not_discard_rendered_findings(monkeypatch):
    html = '<!doctype html><html lang="en"><head><title>Slow resource</title></head><body><main><h1>Loaded content</h1><button id="unnamed"></button><img src="/slow.png" alt="Test"></main></body></html>'

    async def fetch_fixture(self, url):
        if url.endswith('/slow.png'):
            await asyncio.sleep(8)
            return 200, {"Content-Type": "image/png"}, b''
        return 200, {"Content-Type": "text/html"}, html.encode()

    monkeypatch.setattr(SafeResources, "fetch", fetch_fixture)
    report = asyncio.run(audit_page("https://fixture.example/"))
    assert report["status"] == "partial", report
    assert report["load_incomplete"] is True
    button = next(c for c in report["checks"] if c["id"] == "axe-button-name")
    assert button["status"] == "failed"
    assert report["visual_audit"]["status"] == "completed"


def test_moving_layout_does_not_return_misplaced_markers():
    from accessibility import capture_visual

    class MovingPage:
        calls = 0

        async def evaluate(self, *args):
            self.calls += 1
            return [{"x": self.calls * 100}]

        async def screenshot(self, **kwargs):
            return b"jpeg"

    result = asyncio.run(capture_visual(MovingPage(), {}))
    assert result["status"] == "unavailable"
    assert "layout moved" in result["message"]
    assert "image_base64" not in result


@pytest.mark.browser
def test_loading_screen_does_not_pass_accessibility(monkeypatch):
    async def fetch_fixture(self, url):
        return 200, {"Content-Type": "text/html"}, b'<html><body><main>Loading your account...</main></body></html>'

    monkeypatch.setattr(SafeResources, "fetch", fetch_fixture)
    report = asyncio.run(audit_page("https://fixture.example/"))
    assert report["status"] == "unavailable"
    assert "loading screen" in report["message"]
    assert all(c["status"] == "inconclusive" for c in report["checks"])
