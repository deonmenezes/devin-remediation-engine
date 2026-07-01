# Devin Dependency Remediation Engine

An event-driven automation that turns dependency-vulnerability issues into
reviewed-ready pull requests, using [Devin](https://devin.ai) as the agent
that does the actual upgrade-and-PR work. Built against
[`deonmenezes/superset`](https://github.com/deonmenezes/superset), a fork of
Apache Superset seeded with real CVEs found in its pinned dependencies.

## The problem

A scheduled scanner (or Dependabot, or any SCA tool) files a GitHub issue
every time it finds a vulnerable pinned dependency. On a repo of any size
that turns into a steady drip of issues that someone has to triage, bump,
test, and PR — one at a time, forever. This project is the "someone": it
watches for those issues, groups them by package (so a package with five
open CVEs gets upgraded once, not five times), and hands each group to a
Devin session with explicit instructions and guardrails. It reports back
what happened so an engineering lead can see throughput and success rate
without reading every PR.

## Architecture — the full loop

```
  ┌─ STAGE 1 (Devin Automation) ────────────────────────────────┐
  │  Scheduled/push scan → files one `devin-remediate` issue per │
  │  CVE. Detection only, never opens a PR.                      │
  └──────────────────────────────┬──────────────────────────────┘
                                  ▼  (GitHub issues)
GitHub issue opened/labeled  ──┐
GitHub push                  ──┼─▶  POST /webhook/github  ──┐
Simulate-webhook button      ──┤    POST /simulate-webhook  │   ← STAGE 2 (this service)
Trigger-dispatch button      ──┘    POST /trigger           │
                                                              ▼
                                                       Orchestrator
                                            (app/orchestrator.py)
                                   1. list open `devin-remediate` issues
                                   2. parse + group by package, pick the
                                      highest fix version per package
                                   3. skip packages already dispatched
                                   4. for packages with a published fix:
                                        Devin v3 create_session(prompt)   ← STAGE 3 (Devin session
                                      for packages with none:                opens the PR)
                                        comment the blocker, no session
                                                              │
                                                              ▼
                                                   SQLite run ledger
                                                    (app/store.py)
                                                              │
                              background poll job ───────────┤
                              (apscheduler, every 30s)        │
                              checks running sessions,        │
                              records PR URL + ACU spent,     │
                              comments back on the issue(s)   │
                                                              ▼
                                          GET /status (JSON) · GET /dashboard (HTML)

  ┌─ STAGE 4 (Devin Automation) ────────────────────────────────┐
  │  PR opened (title "security: upgrade…") → check diff scope + │
  │  CI green → approve & merge, else comment the blocker.       │
  └─────────────────────────────────────────────────────────────┘
```

Stages 1 and 4 are no-code **Devin Automations** configured in the Devin app;
stages 2–3 are this Dockerized service. Together they close the loop from
"CVE disclosed" to "fix merged" with a human only in the loop when something
looks unsafe.

Key files:

| File | Responsibility |
|---|---|
| `app/main.py` | FastAPI app: webhook receiver, manual trigger, status/dashboard endpoints, schedules the poll loop |
| `app/orchestrator.py` | Issue parsing, package grouping, prompt construction, dispatch + poll logic |
| `app/devin_client.py` | Thin wrapper around the Devin v3 sessions API |
| `app/github_client.py` | Thin wrapper around the GitHub REST API (list issues, comment) |
| `app/store.py` | SQLite-backed ledger of every dispatch — the data behind `/status` and `/dashboard` |
| `scripts/simulate_webhook.py` | Fires a correctly-signed synthetic GitHub webhook at a local instance, so the event path can be demoed without a public tunnel |

## Why group by package instead of fixing issues one at a time?

Two issues that both say "upgrade starlette" but cite different CVEs should
become **one** PR, not two competing PRs editing the same line of
`requirements/base.txt`. The orchestrator collapses all open issues for a
package into a single remediation unit, takes the highest fix version among
them, and asks Devin to close every issue in that group from one PR.

## Why a dry-run mode?

`DRY_RUN=true` (the default) runs the full pipeline — fetch issues, parse,
group, decide what *would* be dispatched — without calling the Devin API,
opening a session, or commenting on GitHub. That's what `/plan` always shows
you, and what `/trigger` does when dry-run is on. Flip `DRY_RUN=false` only
after you've reviewed the plan, since live dispatch spends real ACU and opens
real pull requests.

## Running it

```bash
cp .env.example .env
# fill in DEVIN_API_KEY, DEVIN_ORG_ID, GITHUB_TOKEN — never commit this file

docker compose up --build
```

The service comes up on `http://localhost:8000` and redirects `/` straight to
the dashboard.

### The dashboard is the whole demo — no terminal required

Open **`http://localhost:8000/dashboard`**. It's a self-service "control room"
with a pipeline diagram, a step-by-step guide, and every action wired to a
working button:

| Button | Endpoint | What it does |
|---|---|---|
| **▶ Trigger dispatch** | `POST /trigger?limit=N` | Group the open issues and dispatch remediation for the top N packages |
| **⚡ Simulate GitHub webhook** | `POST /simulate-webhook` | Fire a correctly HMAC-signed `issues.opened` event at `/webhook/github` — proves the event-driven path (signature check included) with no public tunnel |
| **↻ Poll running sessions** | `POST /poll` | Refresh in-flight Devin sessions, pull back PR links + ACU |
| **⟳ Refresh** | — | Re-fetch every table now (also auto-refreshes every 8s) |
| **✕ Reset** | `POST /reset` | Clear the run ledger so you can demo again from a clean slate |

The page also lists the raw 17 open issues (linked to GitHub, with severity),
the package groups they collapse into, the live run ledger, and the four Devin
Automations (linked into the Devin app).

Other endpoints, for scripting: `GET /healthz`, `GET /plan` (read-only preview),
`GET /status` (JSON), `GET /automations`, `POST /webhook/github` (the real
webhook target).

### Wiring a real GitHub webhook

The `⚡ Simulate GitHub webhook` button (or `scripts/simulate_webhook.py`) sends
the exact signed payload GitHub would. To use a real webhook, point a GitHub
webhook at this service's `/webhook/github` (via an ngrok tunnel during a demo,
or a deployed instance) and set the same `GITHUB_WEBHOOK_SECRET` on both sides.

### Working through the existing issue backlog

The 17 seed issues in `deonmenezes/superset` were filed by a scheduled scan
*before* this service's webhook existed, so nothing will retroactively fire
for them. `POST /trigger` (or the periodic re-scan if `RESCAN_INTERVAL_SECONDS`
is set) is what picks up that backlog — it doesn't care whether a package's
issues are old or new, only whether that package has already been dispatched.

## Observability

`/dashboard` is the answer to "how do I know this is working": total runs,
a live breakdown by status (`running` / `fixed` / `blocked` / `skipped_no_fix`
/ `error`), cumulative ACU spent, and per-package PR links. `/status` exposes
the same data as JSON for scripting or piping into a real metrics stack.

## Security notes

- Secrets are read from environment variables only; nothing is hardcoded or
  logged. `.env` is gitignored.
- The webhook endpoint verifies GitHub's `X-Hub-Signature-256` HMAC before
  acting on a payload.
- Devin sessions are capped per-session via `MAX_ACU_PER_SESSION`, and dispatch
  is capped per-trigger via `DISPATCH_LIMIT_PER_RUN`, so a single event can't
  fan out into unbounded spend.
- A package with no published fix never gets force-pushed into a broken PR —
  the agent is explicitly instructed to comment the blocker and stop instead.

## Extending this for a real customer engagement

- Multi-repo / multi-ecosystem: today this assumes one repo and pip-style
  requirements files; the grouping and prompt-building logic generalizes
  to npm/cargo/go.mod with a different issue-title parser per ecosystem.
- Notify a Slack channel on `fixed`/`blocked` instead of (or in addition to)
  GitHub comments.
- Auto-merge on green CI + an approving review, instead of leaving every PR
  for manual merge.
- Replace the SQLite ledger with Postgres and the dashboard with a real
  metrics backend (Grafana/Datadog) once run volume justifies it.
- Add a severity-aware SLA: page someone if a `critical` advisory's package
  group hasn't reached `fixed` within N hours.
