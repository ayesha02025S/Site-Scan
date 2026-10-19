import json
import logging
import os

import aiohttp

logger = logging.getLogger(__name__)
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
WEIGHTS = {"high": 3, "medium": 2, "low": 1}
MAX_FINDINGS = 25
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "top_fixes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "check_id": {"type": "STRING"},
                    "why": {"type": "STRING"},
                    "how": {"type": "STRING"},
                },
                "required": ["check_id", "why", "how"],
            },
        },
    },
    "required": ["summary", "top_fixes"],
}


def failed_checks(result):
    checks = [c for c in result.get("checks", []) if c.get("status") == "failed"]
    return sorted(
        checks,
        key=lambda c: (
            -WEIGHTS.get(c.get("severity"), 0),
            -c.get("element_count", len(c.get("elements", []))),
        ),
    )


def rule_based(result, note):
    failed = failed_checks(result)
    if failed:
        summary = (
            f"{len(failed)} check(s) failed. The fixes below are ranked by severity "
            "and the number of affected elements."
        )
    else:
        summary = "No checks failed in this scan, so there are no fixes to recommend."
    return {
        "source": "rules",
        "model": None,
        "note": note,
        "summary": summary,
        "top_fixes": [
            {
                "check_id": c["id"],
                "title": c["title"],
                "category": c["category"],
                "severity": c["severity"],
                "why": c["evidence"],
                "how": c["fix"],
            }
            for c in failed[:3]
        ],
    }


def build_prompt(result):
    findings = []
    for check in failed_checks(result)[:MAX_FINDINGS]:
        finding = {
            "check_id": check["id"],
            "page_url": check.get("page_url"),
            "title": check["title"],
            "category": check["category"],
            "severity": check["severity"],
            "evidence": check["evidence"],
            "suggested_fix": check["fix"],
        }
        if check.get("elements"):
            finding["affected_elements"] = [
                {"selector": e["selector"][:200], "fix": e["fix"][:400]}
                for e in check["elements"][:3]
            ]
        findings.append(finding)
    page = {
        "url": result.get("final_url"),
        "title": result.get("title"),
        "overall_score": result.get("score"),
        "category_scores": result.get("scores"),
    }
    return (
        "You are explaining an automated website audit to a website owner who may not be "
        "a developer. Use only the failed checks listed below. Do not invent new problems, "
        "do not change the scores, and do not mention checks that are not listed.\n\n"
        "Write a 2-4 sentence plain-language summary of the page's biggest problems. Then "
        "pick the three failed checks that would most improve the site if fixed first, "
        "weighing severity, how many elements are affected, and impact on real visitors. "
        "For each, set check_id to the exact check_id from the list, explain in 1-2 "
        "sentences why it matters to visitors, and give concrete steps to fix it. If fewer "
        "than three checks failed, return only those.\n\n"
        f"Page: {json.dumps(page)}\n"
        f"Failed checks: {json.dumps(findings)}"
    )


async def ask_gemini(prompt, api_key, model):
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as client:
        async with client.post(
            GEMINI_URL.format(model=model),
            json=body,
            headers={"x-goog-api-key": api_key},
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"Gemini returned HTTP {response.status}")
            data = await response.json()
    return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])


def validate_answer(answer, result):
    failed = {c["id"]: c for c in failed_checks(result)}
    fixes = []
    for item in answer.get("top_fixes", []):
        check = failed.get(item.get("check_id"))
        if check is None or any(f["check_id"] == check["id"] for f in fixes):
            continue
        fixes.append(
            {
                "check_id": check["id"],
                "title": check["title"],
                "category": check["category"],
                "severity": check["severity"],
                "why": str(item.get("why", "")).strip()[:1000] or check["evidence"],
                "how": str(item.get("how", "")).strip()[:2000] or check["fix"],
            }
        )
    summary = str(answer.get("summary", "")).strip()[:2000]
    if not summary or len(fixes) < min(3, len(failed)):
        raise ValueError("Gemini response did not reference enough failed checks")
    return summary, fixes[:3]


async def explain_scan(result):
    if not failed_checks(result):
        return rule_based(result, None)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return rule_based(
            result, "AI explanations are off because GEMINI_API_KEY is not set."
        )
    model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    try:
        answer = await ask_gemini(build_prompt(result), api_key, model)
        summary, fixes = validate_answer(answer, result)
    except Exception as exc:
        logger.warning("AI explanation failed: %s", exc)
        return rule_based(
            result,
            "The AI explanation could not be generated, so fixes are ranked by severity instead.",
        )
    return {
        "source": "ai",
        "model": model,
        "note": None,
        "summary": summary,
        "top_fixes": fixes,
    }
