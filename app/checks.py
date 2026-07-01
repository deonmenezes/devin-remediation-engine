"""The `deps-verify` merge gate, run by the engine instead of GitHub Actions.

Upstream Superset CI is an 84-job matrix that needs Postgres/MySQL services,
browser e2e infra and paid GitHub-hosted runners - none of which work on this
private fork (the account's Actions billing is blocked). So the engine plays the
role of external CI: for every open dependency PR it validates that the changed
requirements are well-formed and fully pinned, then reports the outcome as a
`deps-verify` commit status. Branch protection requires that context, so a PR is
only mergeable once the engine has actually checked it - and the Devin
auto-review-and-merge automation then lands it with no human in the loop.
"""

import logging

from packaging.requirements import Requirement, InvalidRequirement

from . import config

log = logging.getLogger("checks")

CONTEXT = "deps-verify"


def verify_requirements_text(name, text):
    """Return (problems, checked) for one requirements file's contents.

    A problem is a line that won't parse as a requirement, or a direct
    dependency that carries a version specifier that isn't an exact pin.
    Comment lines, -r/-c includes, URLs and --hash continuations are ignored.
    """
    problems, checked = [], 0
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-") or line.startswith("http"):
            continue
        spec = line.split(";")[0].split("--hash")[0].strip().rstrip("\\").strip()
        if not spec:
            continue
        try:
            req = Requirement(spec)
        except InvalidRequirement as exc:
            problems.append(f"{name}: cannot parse '{spec}' ({exc})")
            continue
        checked += 1
        pins = [s for s in req.specifier if s.operator in ("==", "===")]
        if req.specifier and not pins:
            problems.append(f"{name}: {req.name} is not exactly pinned ({req.specifier})")
    return problems, checked


def _is_dependency_pr(gh, pr):
    """A PR is in scope for the gate if it touches requirements/*.txt."""
    changed = [
        f["filename"]
        for f in gh.list_pr_files(pr["number"])
        if f["filename"].startswith("requirements/") and f["filename"].endswith(".txt")
    ]
    return changed


def evaluate_pr(gh, pr):
    """Run the gate for one PR. Returns (state, description, changed_files)."""
    changed = _is_dependency_pr(gh, pr)
    if not changed:
        return None, "not a dependency PR", []
    sha = pr["head"]["sha"]
    problems, checked = [], 0
    for path in changed:
        text = gh.get_file_at_ref(path, sha)
        if text is None:
            continue
        p, c = verify_requirements_text(path, text)
        problems += p
        checked += c
    if problems:
        return "failure", f"{len(problems)} dependency integrity problem(s)", changed
    return "success", f"requirements integrity OK ({checked} pins across {len(changed)} file(s))", changed


def reconcile_pr_checks(gh, dry_run):
    """Post/refresh the deps-verify status on every open dependency PR.

    Idempotent: only writes when the state actually changes, so it's safe to run
    on a 30s scheduler. When the gate goes green on a draft PR it also flips the
    PR to ready-for-review, since draft PRs can't be merged.
    """
    results = []
    for pr in gh.list_open_pulls():
        state, description, changed = evaluate_pr(gh, pr)
        if state is None:
            continue
        sha = pr["head"]["sha"]
        current = gh.status_state_for_context(sha, CONTEXT)
        result = {"pr": pr["number"], "state": state, "description": description, "changed": len(changed)}
        if current != state:
            if not dry_run:
                gh.post_status(sha, state, CONTEXT, description)
                if state == "success" and pr.get("draft") and pr.get("node_id"):
                    try:
                        gh.mark_pr_ready(pr["node_id"])
                        result["marked_ready"] = True
                    except Exception as exc:  # noqa: BLE001 - best effort
                        log.warning("mark ready failed for pr#%s: %s", pr["number"], exc)
            result["posted"] = True
            log.info("deps-verify=%s pr#%s (%s)", state, pr["number"], description)
        else:
            result["posted"] = False
        results.append(result)
    return results
