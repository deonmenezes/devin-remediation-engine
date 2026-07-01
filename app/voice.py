"""Voice briefing - "call me and explain this report out loud."

Ported from the GridPath Twilio integration: build a short spoken script from
the live remediation report, wrap it in inline TwiML, and POST it to the Twilio
Calls REST API. Self-contained - no public webhook, SDK, or media server
needed, so it works straight from localhost. Claude writes a natural script when
ANTHROPIC_API_KEY is set; otherwise a deterministic template keeps it working.
"""
import re

import requests

from . import config

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
TWILIO_VOICE = "Polly.Joanna-Neural"

# Report-specific persona/prompt (this is the "different prompt" - GridPath's
# Riley briefs on a map location; here the autopilot briefs on remediation status).
BRIEF_SYSTEM = (
    "You are the voice of a security dependency-remediation autopilot, leaving a short "
    "spoken status briefing on a phone call for an engineering leader (a VP of Engineering). "
    "Write ONLY the words to be spoken aloud - no markdown, no bullet points, no numbered "
    "lists, no stage directions. Keep it to roughly 40 to 55 seconds when read aloud "
    "(about 100 to 140 words). Be warm, crisp, and executive. Open by saying this is the "
    "Devin remediation autopilot with a status update on the repository. Cover: how many "
    "open CVE issues are in the backlog, how they collapse into a smaller number of package "
    "upgrades, how many remediations have been dispatched, how many pull requests were "
    "opened and issues closed, the ACU spent, and explicitly flag any package that has no "
    "published fix yet. Close by noting they can read the full report on the dashboard. "
    "Speak numbers naturally (say 'seventeen', not '17'). Do not invent any figure beyond "
    "the facts provided."
)


def normalize_phone(raw):
    """Best-effort E.164. Requires '+' for international; assumes US otherwise."""
    raw = (raw or "").strip()
    if raw.startswith("+"):
        digits = re.sub(r"\D", "", raw[1:])
        return f"+{digits}" if len(digits) >= 8 else None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) >= 11:  # they typed a country code without the plus
        return f"+{digits}"
    return None


def build_facts(rep):
    """Plain facts the brief must cover - also fed to Claude as grounding."""
    k = rep["kpis"]
    sr = f"{k['success_rate_pct']} percent" if k["success_rate_pct"] is not None else "not applicable yet"
    lines = [
        f"Repository: {rep['repo']}.",
        f"Mode: {rep['mode']}.",
        f"Open CVE issues in the backlog: {k['open_issues']}.",
        f"They collapse into {k['package_groups']} package upgrades; "
        f"{k['fixable_packages']} have a published fix and {k['no_fix_packages']} have none yet.",
        f"Remediation runs dispatched: {k['runs_dispatched']}.",
        f"Pull requests opened: {k['prs_opened']}.",
        f"Issues closed by those pull requests: {k['issues_closed_by_prs']}.",
        f"ACU consumed: {k['acu_consumed']}.",
        f"Success rate of finished runs: {sr}.",
    ]
    if rep["by_status"]:
        parts = ", ".join(f"{v} {s.replace('_', ' ')}" for s, v in rep["by_status"].items())
        lines.append(f"Run status breakdown: {parts}.")
    no_fix = [g["package"] for g in rep["groups"] if not g["has_fix"]]
    if no_fix:
        lines.append(f"Packages with no fix available yet: {', '.join(no_fix)}.")
    return "\n".join(lines)


def fallback_brief(rep):
    """Deterministic spoken script - always available, no API key needed."""
    k = rep["kpis"]
    no_fix = [g["package"] for g in rep["groups"] if not g["has_fix"]]
    parts = [
        f"Hi, this is the Devin remediation autopilot with a status update on {rep['repo']}.",
        f"Right now there are {k['open_issues']} open C-V-E issues in the backlog, "
        f"and they collapse into just {k['package_groups']} package upgrades - "
        f"{k['fixable_packages']} with a published fix.",
        f"So far, {k['runs_dispatched']} remediations have been dispatched, "
        f"opening {k['prs_opened']} pull requests and closing {k['issues_closed_by_prs']} issues, "
        f"using {k['acu_consumed']} A-C-U.",
    ]
    if no_fix:
        parts.append(
            f"One thing to flag: {', '.join(no_fix)} "
            f"{'has' if len(no_fix) == 1 else 'have'} no published fix yet, so "
            f"{'it is' if len(no_fix) == 1 else 'they are'} being left open on purpose."
        )
    parts.append("You can read the full report on the dashboard. Thanks, and have a great day!")
    return " ".join(parts)


def claude_brief(rep):
    """Ask Claude to write a warmer, natural script. None if no key or on error."""
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": config.CLAUDE_MODEL,
                "max_tokens": 600,
                "system": BRIEF_SYSTEM,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Facts about the current remediation status:\n\n{build_facts(rep)}\n\nWrite the spoken briefing.",
                    }
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        blocks = resp.json().get("content", [])
        text = next((b.get("text") for b in blocks if b.get("type") == "text"), None)
        return text.strip() if text else None
    except Exception:
        return None


def _escape_xml(s):
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&apos;")
    )


def to_twiml(script, voice=TWILIO_VOICE):
    """Wrap spoken text in TwiML the Twilio Calls API can play inline."""
    chunks = [c.strip() for c in re.split(r"(?<=[.!?])\s+", script) if c.strip()]
    say = "".join(f'<Say voice="{voice}">{_escape_xml(c)}</Say><Pause length="0"/>' for c in chunks)
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Pause length="1"/>{say}</Response>'


def build_script(rep):
    """The spoken script + whether Claude authored it."""
    script = claude_brief(rep)
    return (script, True) if script else (fallback_brief(rep), False)


def place_call(to, script):
    """Place an outbound Twilio call that speaks `script`. Returns the Twilio
    response dict; raises RuntimeError with a friendly message on failure."""
    sid, token, from_ = config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN, config.TWILIO_FROM_NUMBER
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    resp = requests.post(
        url,
        auth=(sid, token),
        data={"To": to, "From": from_, "Twiml": to_twiml(script)},
        timeout=30,
    )
    if not resp.ok:
        detail = ""
        try:
            detail = resp.json().get("message", "")
        except Exception:
            pass
        raise RuntimeError(detail or f"Twilio could not place the call (HTTP {resp.status_code}).")
    return resp.json()
