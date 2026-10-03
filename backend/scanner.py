import asyncio
import ipaddress
import socket
import re
import time
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver
from bs4 import BeautifulSoup

MAX_BYTES = 2 * 1024 * 1024
MAX_LINKS = 20


class ScanError(ValueError):
    pass


def public_ip(value):
    address = ipaddress.ip_address(value.split("%")[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def validate_url(value):
    value = value.strip()
    if (
        not value
        or len(value) > 2048
        or any(ord(c) < 33 for c in value)
        or "\\" in value
    ):
        raise ScanError("Enter a valid public website URL.")
    if "://" not in value:
        value = "https://" + value
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = parsed.hostname
    except ValueError:
        raise ScanError("Enter a valid public website URL.")
    if (
        parsed.scheme not in ("http", "https")
        or not host
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ScanError("Use an HTTP or HTTPS URL without embedded credentials.")
    if port not in (None, 80, 443):
        raise ScanError("Only standard website ports 80 and 443 are supported.")
    host = host.lower().rstrip(".")
    if (
        host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
        or "%" in host
    ):
        raise ScanError("Private and local network addresses cannot be scanned.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not public_ip(str(address)):
        raise ScanError("Private and local network addresses cannot be scanned.")
    return parsed._replace(fragment="").geturl()


class PublicResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        entries = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM, family=family
        )
        if not entries or any(not public_ip(item[4][0]) for item in entries):
            raise ScanError(
                "This hostname resolves to a private or restricted network address."
            )
        return [
            {
                "hostname": host,
                "host": item[4][0],
                "port": port,
                "family": item[0],
                "proto": item[2],
                "flags": socket.AI_NUMERICHOST,
            }
            for item in entries
        ]

    async def close(self):
        pass


def extract_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    page = urlsplit(base_url)._replace(fragment="").geturl()
    links = []
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, anchor["href"].strip())
        if urlsplit(absolute).scheme not in ("http", "https"):
            continue
        try:
            absolute = validate_url(absolute)
        except ScanError:
            continue
        if absolute != page and absolute not in links:
            links.append(absolute)
    return links


async def check_link(client, url):
    try:
        for _ in range(4):
            async with client.get(url, allow_redirects=False) as response:
                status = response.status
                location = response.headers.get("Location")
            if status in (301, 302, 303, 307, 308) and location:
                url = validate_url(urljoin(url, location))
                continue
            return status
        return None
    except (ScanError, aiohttp.ClientSSLError):
        return None
    except aiohttp.ClientConnectorError:
        return 0
    except (aiohttp.ClientError, OSError, ValueError, TimeoutError):
        return None


async def check_links(links, budget=8):
    links = links[:MAX_LINKS]
    if not links:
        return {"found": 0, "checked": 0, "broken": [], "unverified": 0}
    connector = aiohttp.TCPConnector(
        resolver=PublicResolver(), use_dns_cache=False, limit=8, limit_per_host=4
    )
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=6),
        cookie_jar=aiohttp.DummyCookieJar(),
        trust_env=False,
        headers={"User-Agent": "SiteScan/0.1 (link check)"},
    ) as client:
        jobs = {asyncio.create_task(check_link(client, link)): link for link in links}
        done, waiting = await asyncio.wait(jobs, timeout=budget)
        for job in waiting:
            job.cancel()
        await asyncio.gather(*waiting, return_exceptions=True)
    statuses = {jobs[job]: job.result() for job in done}
    broken = [
        {"url": link, "status": statuses[link]}
        for link in links
        if statuses.get(link) is not None
        and (statuses[link] in (0, 404, 410) or statuses[link] >= 500)
    ]
    return {
        "found": len(links),
        "checked": sum(status is not None for status in statuses.values()),
        "broken": broken,
        "unverified": len(links) - sum(s is not None for s in statuses.values()),
    }


def analyze(
    url,
    final_url,
    status,
    headers,
    html,
    elapsed_ms,
    size,
    redirects,
    secure_chain=True,
    links=None,
):
    soup = BeautifulSoup(html, "html.parser")
    checks = []

    def add(key, category, title, passed, severity, evidence, fix):
        checks.append(
            {
                "id": key,
                "category": category,
                "title": title,
                "status": "passed" if passed else "failed",
                "severity": severity,
                "evidence": evidence,
                "fix": fix,
            }
        )

    https = urlsplit(final_url).scheme == "https"
    add(
        "https",
        "security",
        "Encrypted connection",
        https and urlsplit(url).scheme == "https" and secure_chain,
        "high",
        f'Submitted URL uses {urlsplit(url).scheme.upper()}; final page uses {urlsplit(final_url).scheme.upper()}. Redirect chain stayed on HTTPS: {"yes" if secure_chain else "no"}. HTTPS certificates are verified when connecting.',
        "Serve the page over HTTPS with a valid certificate and use HTTPS links from the start.",
    )
    for key, title, severity, fix in [
        (
            "content-security-policy",
            "Content Security Policy",
            "medium",
            "Configure a Content-Security-Policy response header with sources appropriate for your application.",
        ),
        (
            "strict-transport-security",
            "Strict Transport Security",
            "medium",
            "On HTTPS responses, configure Strict-Transport-Security with a positive max-age after verifying HTTPS works across your site.",
        ),
        (
            "x-content-type-options",
            "Content type protection",
            "low",
            "Set X-Content-Type-Options: nosniff to prevent MIME-type sniffing.",
        ),
        (
            "referrer-policy",
            "Referrer policy",
            "low",
            "Set a Referrer-Policy such as strict-origin-when-cross-origin to control referrer information.",
        ),
    ]:
        value = headers.get(key, "")
        passed = bool(value.strip())
        if key == "x-content-type-options":
            passed = value.strip().lower() == "nosniff"
        if key == "strict-transport-security":
            match = re.search(r"(?:^|;)\s*max-age\s*=\s*(\d+)\s*(?:;|$)", value, re.I)
            passed = https and bool(match and int(match[1]) > 0)
        add(
            key,
            "security",
            title,
            passed,
            severity,
            (
                f"{key}: {value[:350]}"
                if value
                else f"The {key} response header is missing."
            ),
            fix,
        )
    add(
        "http-status",
        "performance",
        "Successful HTTP response",
        200 <= status < 300,
        "high",
        f"The final page returned HTTP {status}.",
        "Investigate server errors, missing pages, or access rules so visitors receive a successful response.",
    )
    add(
        "response-time",
        "performance",
        "Page fetch time",
        elapsed_ms <= 1500,
        "medium",
        f"{elapsed_ms:,} ms to fetch the HTML, including redirects. Target: 1,500 ms or less.",
        "Review server processing, caching, and redirect chains. This is a server-side sample, not a browser loading metric.",
    )
    add(
        "page-size",
        "performance",
        "HTML document size",
        size <= 300 * 1024,
        "low",
        f"{round(size / 1024, 1):,} KB of decoded HTML. Target: 300 KB or less; images and scripts are excluded.",
        "Reduce unnecessary HTML and inline data, and paginate large documents.",
    )
    if links is not None:
        broken = links["broken"]
        listed = ", ".join(
            f'{item["url"][:120]} ({"unreachable" if item["status"] == 0 else "HTTP " + str(item["status"])})'
            for item in broken[:5]
        )
        evidence = (
            f'{len(broken)} of {links["checked"]} checked links are broken'
            + (f": {listed}" if listed else "")
            + (f" and {len(broken) - 5} more" if len(broken) > 5 else "")
            + "."
        )
        if links["unverified"]:
            evidence += f' {links["unverified"]} links could not be verified in time and were not counted.'
        if not links["found"]:
            evidence = "No HTTP or HTTPS links were found on this page."
        add(
            "broken-links",
            "performance",
            "Broken links",
            not broken,
            "medium",
            evidence
            + f" Up to {MAX_LINKS} unique links are checked; 404, 410, 5xx, and unreachable hosts count as broken.",
            "Update or remove links that point to missing pages, failing servers, or domains that no longer resolve.",
        )
    images = soup.find_all("img")
    missing_alt = [img for img in images if not img.has_attr("alt")]
    add(
        "image-alt",
        "accessibility",
        "Image alternative text",
        not missing_alt,
        "medium",
        f"{len(missing_alt)} of {len(images)} images lack an alt attribute. Empty alt attributes are allowed for decorative images.",
        'Add descriptive alt text to informative images; use alt="" only for decorative images. Review text quality manually.',
    )
    lang = soup.html.get("lang", "").strip() if soup.html else ""
    add(
        "document-language",
        "accessibility",
        "Document language",
        bool(lang),
        "medium",
        f'Document language: {lang[:100] or "not declared"}.',
        'Declare the primary language on the html element, for example <html lang="en">.',
    )
    title = soup.title.get_text(strip=True) if soup.title else ""
    add(
        "page-title",
        "accessibility",
        "Descriptive page title",
        bool(title),
        "low",
        f'Page title: {title[:180] or "missing or empty"}. This check verifies presence only.',
        "Add a non-empty, descriptive title element to the document head.",
    )
    labels = {
        label.get("for")
        for label in soup.find_all("label")
        if label.get_text(strip=True)
    }
    inputs = [
        el
        for el in soup.find_all(["input", "select", "textarea"])
        if el.get("type", "").lower()
        not in ("hidden", "submit", "reset", "button", "image")
    ]
    unlabeled = []
    for el in inputs:
        labelledby = el.get("aria-labelledby", "").split()
        aria_name = labelledby and all(
            soup.find(id=ref) and soup.find(id=ref).get_text(strip=True)
            for ref in labelledby
        )
        parent_label = el.find_parent("label")
        if not (
            el.get("id") in labels
            or (parent_label and parent_label.get_text(strip=True))
            or el.get("aria-label", "").strip()
            or aria_name
        ):
            unlabeled.append(el)
    add(
        "form-labels",
        "accessibility",
        "Form control labels",
        not unlabeled,
        "high",
        f"{len(unlabeled)} of {len(inputs)} supported form controls lack a detectable label. Static HTML only.",
        "Associate a visible label with each control using matching for/id attributes, or provide an accessible name with aria-label or aria-labelledby.",
    )
    weights = {"high": 3, "medium": 2, "low": 1}
    scores = {}
    for category in ("performance", "accessibility", "security"):
        group = [check for check in checks if check["category"] == category]
        scores[category] = round(
            100
            * sum(weights[c["severity"]] for c in group if c["status"] == "passed")
            / sum(weights[c["severity"]] for c in group)
        )
    return {
        "final_url": final_url,
        "http_status": status,
        "response_ms": elapsed_ms,
        "size_bytes": size,
        "redirects": redirects,
        "title": title[:250],
        "scores": scores,
        "score": round(sum(scores.values()) / len(scores)),
        "checks": checks,
    }


async def scan_page(url):
    url = validate_url(url)
    connector = aiohttp.TCPConnector(
        resolver=PublicResolver(), use_dns_cache=False, limit=4
    )
    try:
        async with asyncio.timeout(25):
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=12),
                cookie_jar=aiohttp.DummyCookieJar(),
                trust_env=False,
                headers={
                    "User-Agent": "SiteScan/0.1 (single-page educational audit)",
                    "Accept": "text/html,application/xhtml+xml",
                },
            ) as client:
                current = url
                secure_chain = urlsplit(url).scheme == "https"
                started = time.monotonic()
                for redirects in range(6):
                    current = validate_url(current)
                    secure_chain = secure_chain and urlsplit(current).scheme == "https"
                    async with client.get(current, allow_redirects=False) as response:
                        if response.status in (301, 302, 303, 307, 308):
                            location = response.headers.get("Location")
                            if not location:
                                raise ScanError(
                                    "The website returned a redirect without a destination."
                                )
                            current = validate_url(urljoin(str(response.url), location))
                            continue
                        content_type = response.headers.get("Content-Type", "").lower()
                        if not any(
                            kind in content_type
                            for kind in ("text/html", "application/xhtml+xml")
                        ):
                            raise ScanError(
                                "The URL did not return an HTML page. Try a webpage rather than a file or API."
                            )
                        body = bytearray()
                        async for chunk in response.content.iter_chunked(65536):
                            body.extend(chunk)
                            if len(body) > MAX_BYTES:
                                raise ScanError(
                                    "The HTML exceeds the 2 MB scan limit. Try a smaller page."
                                )
                        elapsed = round((time.monotonic() - started) * 1000)
                        charset = response.charset or "utf-8"
                        try:
                            html = body.decode(charset, errors="replace")
                        except LookupError:
                            html = body.decode("utf-8", errors="replace")
                        page = (
                            url,
                            str(response.url),
                            response.status,
                            {k.lower(): v for k, v in response.headers.items()},
                            html,
                            elapsed,
                            len(body),
                            redirects,
                            secure_chain,
                        )
                        break
                else:
                    raise ScanError(
                        "The website exceeded the limit of five redirects."
                    )
            links = await check_links(extract_links(page[4], page[1]))
            return analyze(*page, links=links)
    except ScanError:
        raise
    except (aiohttp.ClientConnectorCertificateError, aiohttp.ClientSSLError):
        raise ScanError(
            "The HTTPS certificate could not be verified. Check the site’s TLS configuration."
        )
    except TimeoutError:
        raise ScanError("The website took too long to respond. Please try again later.")
    except (aiohttp.ClientError, OSError, ValueError):
        raise ScanError(
            "The website could not be reached. Check the address and try again."
        )
