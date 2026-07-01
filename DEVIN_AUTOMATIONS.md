# Devin Automations — configuration

The four no-code automations that drive the event loop live in the Devin app
(org `deon-menezes-demo-4`). Devin has no public API to edit automations, so the
prompts below are pasted into each automation's config by hand. Stages 1–3 are
already working; the **only change needed for fully-hands-free merging** is
updating automation #4 to gate on the `deps-verify` check.

| # | Name | Trigger | Automation |
|---|---|---|---|
| 1 | Periodic Advisory Scan | Schedule (daily 09:00 PDT) | [`bff7cdd6…`](https://app.devin.ai/org/deon-menezes-demo-4/automations/bff7cdd68a6244d3b82b712370716b1a) |
| 2 | Dependency Issue Fix | GitHub issue opened | [`26478a64…`](https://app.devin.ai/org/deon-menezes-demo-4/automations/26478a64abc04073b950f5dabd2e9b12) |
| 3 | Dependency Vulnerability (Push) | GitHub push | [`cafa0e0e…`](https://app.devin.ai/org/deon-menezes-demo-4/automations/cafa0e0ef8af4bfebba0be3fc222f948) |
| 4 | Dependency PR Auto-Review & Merge | GitHub PR opened, title starts `security: upgrade` | [`4ca315ef…`](https://app.devin.ai/org/deon-menezes-demo-4/automations/4ca315ef46a6416091482578c986fa84) |

---

## #4 — Auto-Review & Merge  ← paste this to finish the loop

**Trigger:** Pull request opened in `deonmenezes/superset` where the title starts
with `security: upgrade`.

**Prompt:**

```
A pull request was just opened in deonmenezes/superset with a title starting
"security: upgrade". Review and, if safe, merge it with no human involvement.

Steps:
1. Read the PR diff. Confirm it is scoped to a dependency bump ONLY — changes to
   requirements/*.txt (and, if the compiled lockfile needs it, the matching
   pinned transitive lines). If the diff touches application code, tests, or
   config beyond what the upgrade strictly requires, do NOT merge: leave a
   comment explaining the unexpected scope and stop.
2. Confirm the PR closes at least one issue (a "Closes #NN" reference).
3. Wait for the required status check named "deps-verify" to report success.
   This check is posted by the remediation engine (not GitHub Actions) within
   ~30 seconds of the PR opening — poll for up to 3 minutes. Do NOT look at any
   other checks; upstream Superset CI is intentionally disabled on this fork and
   "deps-verify" is the only required gate. If deps-verify reports failure,
   comment the failure and stop without merging.
4. Once the diff is in-scope AND deps-verify is green, approve the PR and
   squash-merge it. If the PR is still a draft, mark it ready first.
5. Comment a one-line summary: merged, and which issue(s) it closed.

Never merge a PR whose title upgrade crosses a major version boundary (e.g.
X.y.z where X increases) — comment that it needs human review and stop.
```

Why this changed: the fork's GitHub Actions are billing-blocked, so "wait for CI
to go green" would wait forever. The remediation engine now posts a single
first-class commit status, `deps-verify`, and `master` branch protection requires
exactly that context — so gating on it is both correct and sufficient.

---

## #2 — Dependency Issue Fix (small robustness tweak, optional)

Ensure the fixer **opens the PR as ready-for-review, not a draft**, and titles it
`security: upgrade <package> to <version> (<advisories>)` with a `Closes #NN` in
the body. (The engine also flips drafts to ready when deps-verify goes green, so
this is belt-and-suspenders.)

---

## What the engine owns vs. what Devin owns

| Concern | Owner |
|---|---|
| Detect CVEs, file issues | Devin automations #1 / #3 |
| Open the fix PR | Devin automation #2 (or engine `/trigger` dispatch) |
| **`deps-verify` merge gate (CI)** | **This engine** (`app/checks.py`, every 30s) |
| Approve + squash-merge on green | Devin automation #4 |
| Hold major bumps / no-fix packages | This engine (`is_major_bump`, no-fix comment) |

## Branch protection (already applied)

`master` requires the `deps-verify` status check (bound to `app_id: -1` so the
engine's PAT-posted status satisfies it), `strict: false`, no required reviews,
`enforce_admins: false`. Re-apply with:

```bash
gh api -X PATCH repos/deonmenezes/superset/branches/master/protection/required_status_checks \
  --input - <<'JSON'
{ "strict": false, "checks": [ { "context": "deps-verify", "app_id": -1 } ] }
JSON
```
