import re
import logging

from packaging.version import Version, InvalidVersion

from . import config, store
from .devin_client import DevinClient
from .github_client import GitHubClient

log = logging.getLogger("orchestrator")

# Matches issue titles produced by the advisory scan, e.g.:
#   "[security] CVE-2026-6357: upgrade pip 25.1.1 -> 26.1"
#   "[security] CVE-2026-44405: upgrade paramiko 3.5.1 -> no fixed version published"
TITLE_RE = re.compile(
    r"^\[security\]\s*(?P<advisory>\S+):\s*upgrade\s+(?P<package>\S+)\s+"
    r"(?P<current>\S+)\s*(?:→|->)\s*(?P<fixed>.+)$",
    re.IGNORECASE,
)

NO_FIX_MARKERS = ("no fixed version", "no fix")

# Pulls extra detail out of the issue body the advisory scan writes, e.g.:
#   "- **Severity:** `medium`"
#   "- **File:** `requirements/development.txt`"
SEVERITY_RE = re.compile(r"\*\*Severity:\*\*\s*`?([\w-]+)`?", re.IGNORECASE)
FILE_RE = re.compile(r"\*\*File:\*\*\s*`?([^`\n]+)`?", re.IGNORECASE)


def parse_issue(issue):
    match = TITLE_RE.match(issue["title"].strip())
    if not match:
        return None
    fixed = match.group("fixed").strip()
    has_fix = not any(marker in fixed.lower() for marker in NO_FIX_MARKERS)
    body = issue.get("body") or ""
    severity_match = SEVERITY_RE.search(body)
    file_match = FILE_RE.search(body)
    return {
        "number": issue["number"],
        "title": issue["title"],
        "advisory": match.group("advisory"),
        "package": match.group("package"),
        "current": match.group("current"),
        "fixed": fixed if has_fix else None,
        "has_fix": has_fix,
        "severity": severity_match.group(1).lower() if severity_match else "unknown",
        "file": file_match.group(1).strip() if file_match else None,
        "html_url": issue.get("html_url"),
    }


def _higher_version(a, b):
    try:
        return a if Version(a) >= Version(b) else b
    except InvalidVersion:
        # Fall back to string comparison if a version doesn't parse cleanly.
        return a if a >= b else b


def group_by_package(parsed_issues):
    """Collapse parsed issues into one remediation unit per package, picking
    the highest fix version so a package is only upgraded once."""
    groups = {}
    for item in parsed_issues:
        pkg = item["package"]
        group = groups.setdefault(
            pkg,
            {"package": pkg, "fixed": None, "issues": [], "advisories": [], "has_fix": item["has_fix"]},
        )
        group["issues"].append(item["number"])
        group["advisories"].append(item["advisory"])
        if item["has_fix"]:
            group["has_fix"] = True
            group["fixed"] = item["fixed"] if group["fixed"] is None else _higher_version(group["fixed"], item["fixed"])
        elif group["fixed"] is None:
            group["has_fix"] = False
    return list(groups.values())


def build_prompt(group, repo):
    issue_refs = ", ".join(f"#{n}" for n in group["issues"])
    advisories = ", ".join(sorted(set(group["advisories"])))
    return f"""You are an autonomous remediation agent working in the repository {repo}.

## Objective
Upgrade the dependency `{group['package']}` to version `{group['fixed']}` to resolve
the following published security advisories: {advisories}.
This single upgrade should close these GitHub issues: {issue_refs}.

## Steps
1. Locate every pin of `{group['package']}` (requirements files, lockfiles, pyproject.toml).
2. Upgrade it to `{group['fixed']}`. If requirements are compiled (*.in -> *.txt),
   regenerate the lockfile rather than hand-editing transitive pins.
3. Resolve any resulting dependency conflicts with the minimal necessary change.
4. If the upgrade requires small code changes for compatibility, make them and explain why.
5. Run the relevant test suite and confirm it passes.
6. Open a pull request titled `security: upgrade {group['package']} to {group['fixed']} ({advisories})`
   whose description includes `Closes {issue_refs}` and explains what changed, why, and how it
   was verified.

## Constraints
- Make the smallest change that fixes the advisories above. Do not bump unrelated packages.
- Open a PR only if tests pass. If you cannot complete this safely, do NOT open a broken PR —
  instead comment on {issue_refs} explaining what blocked you, and end the session without a PR.
- One PR for this package. Do not duplicate work already done in an open PR.

## Output
End with a one-line summary: PR URL (or the blocker), and which issues it closes.
"""


def build_no_fix_comment(group):
    advisories = ", ".join(sorted(set(group["advisories"])))
    return (
        f"**Automated remediation status: blocked**\n\n"
        f"No fixed version has been published yet for `{group['package']}` "
        f"({advisories}). Leaving this open — the periodic advisory scan will "
        f"pick it up automatically once a fix is released. No PR opened."
    )


class Orchestrator:
    def __init__(self, dry_run=None):
        self.dry_run = config.DRY_RUN if dry_run is None else dry_run
        self.gh = GitHubClient()
        self.devin = DevinClient()

    def plan(self):
        """Read-only: fetch issues, parse, group. No side effects."""
        issues = self.gh.list_open_issues()
        parsed = [p for p in (parse_issue(i) for i in issues) if p]
        unparsed = [i["number"] for i in issues if not parse_issue(i)]
        groups = group_by_package(parsed)
        already = store.dispatched_packages()
        for g in groups:
            g["already_dispatched"] = g["package"] in already
        parsed.sort(key=lambda p: p["number"], reverse=True)
        return {
            "groups": groups,
            "issues": parsed,
            "unparsed_issue_numbers": unparsed,
            "total_issues": len(issues),
        }

    def dispatch(self, limit=None):
        """Dispatch up to `limit` new (not-yet-dispatched) package groups.
        Packages with no published fix get a comment instead of a session."""
        limit = limit if limit is not None else config.DISPATCH_LIMIT_PER_RUN
        plan = self.plan()
        candidates = [g for g in plan["groups"] if not g["already_dispatched"]]
        # Highest issue-count groups first (proxy for blast radius / severity).
        candidates.sort(key=lambda g: len(g["issues"]), reverse=True)

        dispatched = []
        for group in candidates[:limit]:
            if not group["has_fix"]:
                if not self.dry_run:
                    for n in group["issues"]:
                        self.gh.comment_on_issue(n, build_no_fix_comment(group))
                record = store.record_run(
                    package=group["package"],
                    issue_numbers=group["issues"],
                    advisories=group["advisories"],
                    session_id=None,
                    status="skipped_no_fix",
                    dry_run=self.dry_run,
                )
                dispatched.append(record)
                continue

            prompt = build_prompt(group, self.gh.repo)
            title = f"security: upgrade {group['package']} to {group['fixed']}"
            if self.dry_run:
                session_id = None
                status = "dry_run"
            else:
                session = self.devin.create_session(
                    prompt=prompt,
                    title=title,
                    tags=["dependency-remediation", group["package"]],
                    max_acu_limit=config.MAX_ACU_PER_SESSION,
                )
                session_id = session.get("session_id") or session.get("id")
                status = "running"

            record = store.record_run(
                package=group["package"],
                issue_numbers=group["issues"],
                advisories=group["advisories"],
                session_id=session_id,
                status=status,
                dry_run=self.dry_run,
            )
            dispatched.append(record)
            log.info("dispatched package=%s issues=%s status=%s", group["package"], group["issues"], status)

        return dispatched

    def poll_running(self):
        """Refresh status for every run still in-flight. Safe to call repeatedly
        (e.g. from a scheduler) — only touches rows that aren't terminal yet."""
        updated = []
        for run in store.running_runs():
            if not run["session_id"]:
                continue
            session = self.devin.get_session(run["session_id"])
            if DevinClient.is_error(session):
                new_status = "error"
            elif DevinClient.is_terminal(session):
                prs = DevinClient.pull_request_urls(session)
                new_status = "fixed" if prs else "blocked"
            else:
                new_status = "running"

            pr_urls = DevinClient.pull_request_urls(session)
            acu = session.get("acus_consumed")
            store.update_run(
                run["id"],
                status=new_status,
                pr_url=pr_urls[0] if pr_urls else None,
                acu_consumed=acu,
            )

            if new_status in ("fixed", "blocked") and run["status"] not in ("fixed", "blocked"):
                self._notify_issues(run, new_status, pr_urls[0] if pr_urls else None)

            updated.append(run["id"])
        return updated

    def _notify_issues(self, run, status, pr_url):
        if self.dry_run:
            return
        if status == "fixed" and pr_url:
            body = f"Automated remediation opened {pr_url} for `{run['package']}`."
        else:
            body = (
                f"Automated remediation session for `{run['package']}` finished without a PR. "
                f"Check the Devin session for details — leaving this issue open for manual follow-up."
            )
        for n in run["issue_numbers"]:
            self.gh.comment_on_issue(n, body)
