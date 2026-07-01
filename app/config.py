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
