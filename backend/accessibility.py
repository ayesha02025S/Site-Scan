import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urljoin

import aiohttp

from network import PublicResolver, ScanError, validate_url

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))
AXE_PATH = ROOT / "node_modules" / "axe-core" / "axe.min.js"
RULES = {
    "color-contrast": ("Text color contrast", "medium"),
    "button-name": ("Accessible button names", "high"),
    "aria-valid-attr": ("Valid ARIA attributes", "medium"),
    "aria-valid-attr-value": ("Valid ARIA attribute values", "high"),
    "aria-roles": ("Valid ARIA roles", "high"),
    "aria-allowed-attr": ("ARIA attributes match roles", "high"),
    "aria-required-attr": ("Required ARIA attributes", "high"),
    "aria-required-children": ("Required ARIA child roles", "high"),
    "aria-required-parent": ("Required ARIA parent roles", "high"),
}


def unavailable(message):
    return {
        "status": "unavailable",
        "message": message,
        "engine": "axe-core",
        "checks": [make_check(rule, "inconclusive", message) for rule in RULES],
    }


def make_check(rule, status, evidence, nodes=None, help_url=None):
    title, severity = RULES[rule]
    return {
        "id": f"axe-{rule}",
        "category": "accessibility",
        "source": "axe-core",
        "title": title,
        "status": status,
        "severity": severity,
        "evidence": evidence,
        "fix": (
            "Review the affected elements and apply the specific fixes below."
            if nodes
            else "Re-run the browser audit after addressing any loading issues. Automated results still need manual review."
        ),
        "elements": nodes or [],
        "help_url": help_url,
    }


def convert_results(raw, partial=False):
    checks = []
    violations = {item["id"]: item for item in raw.get("violations", [])}
    incomplete = {item["id"]: item for item in raw.get("incomplete", [])}
    passes = {item["id"]: item for item in raw.get("passes", [])}
    inapplicable = {item["id"]: item for item in raw.get("inapplicable", [])}
    for rule in RULES:
        item = (
            violations.get(rule)
            or incomplete.get(rule)
            or passes.get(rule)
            or inapplicable.get(rule)
        )
        status = (
            "failed"
            if rule in violations
            else (
                "inconclusive"
                if rule in incomplete or partial or item is None
                else "passed" if rule in passes else "not_applicable"
            )
        )
        affected = violations.get(rule) or incomplete.get(rule) or {}
        nodes = []
        for node in affected.get("nodes", [])[:20]:
            if status not in ("failed", "inconclusive"):
                break
            suggestions = [
                check.get("message", "")
                for group in ("any", "all", "none")
                for check in node.get(group, [])
            ]
            nodes.append(
                {
                    "selector": " → ".join(
                        str(target) for target in node.get("target", [])
                    )[:1000],
                    "html": node.get("html", "")[:2000],
                    "fix": (
                        node.get("failureSummary")
                        or " ".join(suggestions)
                        or "Manually inspect this element and its accessible properties."
                    )[:3000],
                    "impact": node.get("impact"),
                }
            )
        count = len(affected.get("nodes", []))
        evidence = (
            f"{count} affected element(s) in the rendered page."
            if status == "failed"
            else (
                "The rendered audit is incomplete; manual review or another scan is needed."
                if status == "inconclusive"
                else (
                    "No elements applicable to this rule were found."
                    if status == "not_applicable"
                    else "Applicable rendered elements passed this axe-core rule."
                )
            )
        )
        if rule in violations and rule in incomplete:
            evidence += f' {len(incomplete[rule].get("nodes", []))} additional element(s) need manual review.'
        check = make_check(rule, status, evidence, nodes, (item or {}).get("helpUrl"))
        check["element_count"] = count
        checks.append(check)
    return checks


class SafeResources:
    def __init__(self, client):
        self.client = client
        self.requests = 0
        self.bytes = 0
        self.blocked = 0
        self.slots = asyncio.Semaphore(5)

    async def fetch(self, url):
        for _ in range(6):
            url = validate_url(url)
            async with self.client.get(url, allow_redirects=False) as response:
                if response.status in (301, 302, 303, 307, 308):
                    destination = response.headers.get("Location")
                    if not destination:
                        raise ScanError("Missing redirect destination")
                    url = validate_url(urljoin(url, destination))
                    continue
                if response.status >= 400:
                    self.blocked += 1
                data = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    data.extend(chunk)
                    self.bytes += len(chunk)
                    if len(data) > 3 * 1024 * 1024 or self.bytes > 15 * 1024 * 1024:
                        raise ScanError("Browser resource limit reached")
                headers = {
                    key: value
                    for key, value in response.headers.items()
                    if key.lower()
                    not in (
                        "content-encoding",
                        "content-length",
                        "transfer-encoding",
                        "set-cookie",
                        "connection",
                        "content-security-policy-report-only",
                    )
                }
                return response.status, headers, bytes(data)
        raise ScanError("Too many resource redirects")

    async def route(self, route):
        self.requests += 1
        try:
            if (
                self.requests > 80
                or route.request.method != "GET"
                or route.request.resource_type in ("media", "websocket", "eventsource")
            ):
                raise ScanError("Request excluded from bounded audit")
            async with self.slots:
                status, headers, body = await self.fetch(route.request.url)
            await route.fulfill(status=status, headers=headers, body=body)
        except Exception:
            self.blocked += 1
            try:
                await route.abort()
            except Exception:
                pass


async def run_axe(page, source):
    await page.evaluate(source)
    return await page.evaluate(
        """async (rules) => {
        const result = await axe.run(document, {
            runOnly: {type: 'rule', values: rules},
            resultTypes: ['violations', 'incomplete'],
            iframes: false
        });
        return JSON.parse(JSON.stringify(result));
    }""",
        list(RULES),
    )


async def audit_page(url):
    try:
        validate_url(url)
        source = AXE_PATH.read_text()
        from playwright.async_api import async_playwright
    except (OSError, ImportError):
        return unavailable(
            "Browser audit is not installed. Run npm ci in backend, then python -m playwright install chromium with the documented browser path."
        )

    async def deny_connection(reader, writer):
        writer.close()
        await writer.wait_closed()

    try:
        async with asyncio.timeout(35):
            async with await asyncio.start_server(
                deny_connection, "127.0.0.1", 0
            ) as deny_proxy:
                proxy_port = deny_proxy.sockets[0].getsockname()[1]
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(
                        headless=True,
                        chromium_sandbox=True,
                        proxy={
                            "server": f"http://127.0.0.1:{proxy_port}",
                            "bypass": "<-loopback>",
                        },
                        args=[
                            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                            "--disable-background-networking",
                        ],
                    )
                    try:
                        context = await browser.new_context(
                            viewport={"width": 1280, "height": 900},
                            service_workers="block",
                            accept_downloads=False,
                        )
                        await context.route_web_socket("**/*", lambda ws: ws.close())
                        connector = aiohttp.TCPConnector(
                            resolver=PublicResolver(), use_dns_cache=False, limit=5
                        )
                        async with aiohttp.ClientSession(
                            connector=connector,
                            timeout=aiohttp.ClientTimeout(total=8),
                            trust_env=False,
                            cookie_jar=aiohttp.DummyCookieJar(),
                            headers={
                                "User-Agent": "SiteScan/0.2 (rendered accessibility audit)"
                            },
                        ) as client:
                            resources = SafeResources(client)
                            await context.route("**/*", resources.route)
                            page = await context.new_page()
                            script_errors = []
                            page.on(
                                "pageerror",
                                lambda error: script_errors.append(str(error)),
                            )
                            response = await page.goto(
                                url, wait_until="load", timeout=18000
                            )
                            if response is None or response.status >= 400:
                                return unavailable(
                                    "The rendered page did not load successfully. Static checks are still available."
                                )
                            await page.wait_for_timeout(600)
                            raw = await run_axe(page, source)
                            frames = await page.locator("iframe").count()
                            partial = (
                                resources.blocked > 0
                                or bool(script_errors)
                                or frames > 0
                            )
                            return {
                                "status": "partial" if partial else "completed",
                                "message": (
                                    "Some resources, scripts, or embedded frames could not be audited. Confirmed issues are shown; other rules may be inconclusive."
                                    if partial
                                    else "Rendered in Chromium at 1280 × 900. Automated accessibility checks do not replace a manual audit."
                                ),
                                "engine": "axe-core",
                                "engine_version": raw.get("testEngine", {}).get(
                                    "version"
                                ),
                                "blocked_resources": resources.blocked,
                                "script_errors": len(script_errors),
                                "checks": convert_results(raw, partial),
                            }
                    finally:
                        await browser.close()
    except TimeoutError:
        return unavailable(
            "The browser audit timed out. Static checks are preserved; try scanning again."
        )
    except Exception:
        logging.getLogger(__name__).exception("Rendered accessibility audit failed")
        return unavailable(
            "The browser audit could not finish. Verify Chromium is installed and retry; static checks are preserved."
        )
