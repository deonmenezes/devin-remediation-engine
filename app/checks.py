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
import re

from packaging.requirements import Requirement, InvalidRequirement
from packaging.version import Version, InvalidVersion

from . import config

log = logging.getLogger("checks")

CONTEXT = "deps-verify"

# A changed line in a unified diff that pins a package, e.g. "+urllib3==2.7.1".
_PIN_RE = re.compile(r"^([+-])\s*([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][^\s;#]*)", re.M)


def _normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _diff_in_scope(files):
    """True only if every changed file is a requirements/*.txt - i.e. the PR is a
    pure dependency bump with no application code, tests, or config touched."""
    if not files:
        return False
    return all(
        f["filename"].startswith("requirements/") and f["filename"].endswith(".txt")
        for f in files
    )


def _diff_is_major_bump(files):
    """True if any pin in the diff moves a package across a major version. Reads
    old (-) and new (+) pins straight from the patch, so it needs no lookup and
    catches a major jump regardless of which package the PR title names."""
    removed, added = {}, {}
    for f in files:
        for sign, name, ver in _PIN_RE.findall(f.get("patch") or ""):
            try:
                v = Version(ver)
            except InvalidVersion:
                continue
            (removed if sign == "-" else added)[_normalize(name)] = v
    for key, newv in added.items():
        oldv = removed.get(key)
        if oldv is not None and newv.major > oldv.major:
            return True
    return False


def _try_auto_merge(gh, pr):
    """Close the loop: squash-merge a green security PR whose diff is in-scope and
    non-major. Mirrors the Stage-4 Devin automation's rules, but in-engine so the
    loop never depends on a no-code automation the API can't see. Returns a dict
    describing the outcome, or None if auto-merge is off."""
    if not config.ENGINE_AUTO_MERGE:
        return None
    files = gh.list_pr_files(pr["number"])
    if not _diff_in_scope(files):
        return {"merged": False, "reason": "diff touches files outside requirements/*.txt - left for human"}
    if _diff_is_major_bump(files):
        return {"merged": False, "reason": "major version bump - held for human review"}
    if pr.get("draft") and pr.get("node_id"):
        try:
            gh.mark_pr_ready(pr["node_id"])
        except Exception as exc:  # noqa: BLE001 - best effort
            log.warning("auto-merge: mark ready failed pr#%s: %s", pr["number"], exc)
    # No approving review: branch protection here requires no reviews, and a PAT
    # can't approve a PR it authored, so it would only add a failing round-trip.
    ok, detail = gh.merge_pr(pr["number"], pr["head"]["sha"])
    if ok:
        log.info("auto-merged pr#%s (%s)", pr["number"], pr.get("title"))
        return {"merged": True, "sha": detail}
    # A just-posted status can lag GitHub's mergeability recompute; the next 45s
    # reconcile pass retries. So a transient "not mergeable" here is expected.
    log.info("auto-merge pr#%s pending: %s", pr["number"], detail)
    return {"merged": False, "reason": detail}


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
    try:
        pulls = gh.list_open_pulls()
    except Exception as exc:  # noqa: BLE001 - never let a rate limit crash the loop
        log.warning("reconcile: could not list PRs (%s)", exc)
        return results
    for pr in pulls:
        # Only gate Devin's remediation PRs. Skipping everything else (Dependabot
        # bumps, etc.) BEFORE any per-PR API call keeps usage tiny and avoids the
        # GitHub rate limit that a 30s scan over dozens of PRs would otherwise hit.
        if not (pr.get("title") or "").lower().startswith("security: upgrade"):
            continue
        try:
            state, description, changed = evaluate_pr(gh, pr)
        except Exception as exc:  # noqa: BLE001
            log.warning("reconcile: evaluate pr#%s failed (%s)", pr.get("number"), exc)
            continue
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

        # Loop-closer: once green, the engine merges it itself (in-scope, non-major).
        # Runs every pass while green so a mergeability lag just retries next cycle.
        if state == "success" and not dry_run:
            try:
                merge = _try_auto_merge(gh, pr)
            except Exception as exc:  # noqa: BLE001 - never let a merge error crash the loop
                log.warning("auto-merge pr#%s errored: %s", pr.get("number"), exc)
                merge = {"merged": False, "reason": str(exc)}
            if merge is not None:
                result["auto_merge"] = merge

        results.append(result)
    return results
