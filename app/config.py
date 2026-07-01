import os


def _bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


DEVIN_API_KEY = os.environ.get("DEVIN_API_KEY", "")
DEVIN_ORG_ID = os.environ.get("DEVIN_ORG_ID", "")
DEVIN_API_BASE = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai/v3")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "deonmenezes/superset")
GITHUB_ISSUE_LABEL = os.environ.get("GITHUB_ISSUE_LABEL", "devin-remediate")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

DISPATCH_LIMIT_PER_RUN = int(os.environ.get("DISPATCH_LIMIT_PER_RUN", "3"))
MAX_ACU_PER_SESSION = int(os.environ.get("MAX_ACU_PER_SESSION", "15"))
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))
RESCAN_INTERVAL_SECONDS = int(os.environ.get("RESCAN_INTERVAL_SECONDS", "0"))  # 0 = disabled

DRY_RUN = _bool("DRY_RUN", default=True)  # default safe: no real sessions, no real PRs

DB_PATH = os.environ.get("DB_PATH", "/data/runs.db")

PORT = int(os.environ.get("PORT", "8000"))

# Voice briefing ("call me and explain this report"). Ported from GridPath's
# Twilio integration. All three Twilio vars are required for calling; the
# Anthropic key is optional (falls back to a deterministic spoken template).
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")


def voice_configured():
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER)

# Reference-only metadata for the no-code Devin Automations configured directly
# in the Devin dashboard for this org. There's no public API to list or poll
# automation status (docs.devin.ai/product-guides/automations confirms this),
# so this is a static panel that links out to the real thing rather than a
# live integration.
DEVIN_ORG_SLUG = os.environ.get("DEVIN_ORG_SLUG", "deon-menezes-demo-4")

AUTOMATIONS = [
    {
        "name": "Periodic Advisory Scan for dependencies",
        "trigger": "Scheduled — daily 09:00 PDT",
        "purpose": (
            "Detection only: runs pip-audit against requirements/*.txt and checks GitHub "
            "Dependabot alerts, files a new devin-remediate issue per finding, dedupes "
            "against issues already open. Never opens a PR."
        ),
        "automation_id": "bff7cdd68a6244d3b82b712370716b1a",
    },
    {
        "name": "Dependency Issue Fix",
        "trigger": "GitHub issue opened in deonmenezes/superset",
        "purpose": (
            "The fixer this service's /trigger and /webhook/github routes duplicate in code: "
            "upgrades the affected package, runs tests, opens a PR that closes the issue(s) — "
            "or comments the blocker instead of forcing a broken PR."
        ),
        "automation_id": "26478a64abc04073b950f5dabd2e9b12",
    },
    {
        "name": "Dependency Vulnerability (Push)",
        "trigger": "GitHub push to deonmenezes/superset",
        "purpose": "Same detection-only scan as the periodic one, fired on push events instead of a schedule.",
        "automation_id": "cafa0e0ef8af4bfebba0be3fc222f948",
    },
    {
        "name": "Dependency PR Auto-Review & Merge",
        "trigger": "GitHub pull request opened in deonmenezes/superset, title starts with \"security: upgrade\"",
        "purpose": (
            "Closes the loop: checks the PR diff is scoped to only the dependency bump it claims, "
            "waits for CI to go green, then approves and merges. If scope is unexpected or a required "
            "check fails, it comments the blocker and leaves the PR unmerged for a human instead."
        ),
        "automation_id": "4ca315ef46a6416091482578c986fa84",
    },
]

for _automation in AUTOMATIONS:
    _automation["url"] = f"https://app.devin.ai/org/{DEVIN_ORG_SLUG}/automations/{_automation['automation_id']}"


def missing_required():
    """Returns a list of required env vars that are unset. Webhook secret and
    GitHub token are only required for live (non-dry-run) operation."""
    missing = []
    if not DRY_RUN:
        if not DEVIN_API_KEY:
            missing.append("DEVIN_API_KEY")
        if not DEVIN_ORG_ID:
            missing.append("DEVIN_ORG_ID")
        if not GITHUB_TOKEN:
            missing.append("GITHUB_TOKEN")
    return missing
