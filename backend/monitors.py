import logging
import os
from datetime import timedelta
from urllib.parse import urlsplit

import aiohttp

logger = logging.getLogger(__name__)

FREQUENCIES = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}
MAX_MONITORS_PER_USER = 5
RETRY_AFTER_FAILURE = timedelta(minutes=15)
FAILURES_BEFORE_ALERT = 2
# A single slow fetch flips this rule, so on its own it is not worth an alert.
VOLATILE_RULES = {"response-time"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
MAX_LISTED_ISSUES = 5
RESEND_URL = "https://api.resend.com/emails"


def new_issues(current, previous):
    """Return checks that passed in the previous report and fail in the current one."""
    same_rules = current.get("scanner_version") and all(
        current.get(key) == previous.get(key)
        for key in ("scanner_version", "scoring_version")
    )
    if not same_rules:
        return []
    before = {check["id"]: check["status"] for check in previous.get("checks", [])}
    issues = [
        check
        for check in current.get("checks", [])
        if check["status"] == "failed"
        and before.get(check["id"]) == "passed"
        and check.get("rule_id", check["id"]) not in VOLATILE_RULES
    ]
    return sorted(issues, key=lambda check: SEVERITY_ORDER[check["severity"]])


def issues_alert(url, issues):
    count = len(issues)
    lines = [
        f'{check["severity"].upper()}: {check["title"]} ({check.get("page_url", url)})'
        for check in issues[:MAX_LISTED_ISSUES]
    ]
    if count > MAX_LISTED_ISSUES:
        lines.append(f"...and {count - MAX_LISTED_ISSUES} more.")
    noun = "issue" if count == 1 else "issues"
    return {
        "kind": "new_issues",
        "title": f"{count} new {noun} on {urlsplit(url).hostname}",
        "body": "\n".join(lines),
    }


def failure_alert(url, error):
    return {
        "kind": "scan_failed",
        "title": f"{urlsplit(url).hostname} could not be scanned",
        "body": f"Two scans in a row failed. Latest reason: {error}",
    }


def recovery_alert(url):
    return {
        "kind": "recovered",
        "title": f"{urlsplit(url).hostname} can be scanned again",
        "body": "The latest scheduled scan completed after earlier failures.",
    }


async def send_email(to, subject, body):
    """Send an alert if email is configured. The in-app notification is already saved."""
    api_key = os.getenv("RESEND_API_KEY")
    sender = os.getenv("NOTIFICATION_FROM_EMAIL")
    if not (api_key and sender and to):
        return False
    origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10), trust_env=False
        ) as client:
            async with client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "from": sender,
                    "to": [to],
                    "subject": subject,
                    "text": f"{body}\n\nOpen Site Scan: {origin}",
                },
            ) as response:
                if response.status >= 400:
                    logger.warning("Alert email rejected: HTTP %s", response.status)
                    return False
        return True
    except (aiohttp.ClientError, TimeoutError, OSError) as exc:
        logger.warning("Alert email failed: %s", type(exc).__name__)
        return False
