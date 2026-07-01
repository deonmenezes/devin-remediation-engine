# Loom Script — Devin Dependency Remediation Engine (~5 min)

**Audience:** VP of Engineering + senior ICs curious about Devin.
**Goal:** Show a working, event-driven system that uses Devin as a core primitive to
close the loop from "CVE disclosed" to "fix merged" — and make the case for why an
autonomous coding agent is what makes it possible.

**Two tabs open before you hit record:**
1. `http://localhost:8000/dashboard` (DRY RUN, freshly Reset — clean slate)
2. `https://app.devin.ai/.../automations` (the 4 automations) — and a tab on the fork's Issues + Pull requests.

**Pre-flight checklist**
- [ ] `docker compose up` running; dashboard loads; mode badge says DRY RUN.
- [ ] Clicked **Reset** so the run ledger is empty.
- [ ] Decide the "money shot": either flip `DRY_RUN=false` beforehand to open a *real* PR live,
      or demo in DRY RUN and show a PR you opened in a prior live run. (Real PR is more convincing.)
- [ ] GitHub tab logged in; Devin automations tab logged in.

---

## 0:00 – 0:35 · WHAT — the problem

> "Every security scanner — Dependabot, pip-audit, Snyk — is really good at finding
> vulnerable dependencies and really good at generating *work*. On a repo the size of
> Apache Superset, that's a steady drip of 'upgrade this package' tickets that a human
> has to triage, bump, test, and open a PR for — one at a time, forever.
>
> The finding is the easy part. The *fix* is the bottleneck. That's the workflow I'm
> automating: turning a backlog of CVE issues into reviewed, merged pull requests — with
> Devin doing the actual engineering, and a human only in the loop when something looks unsafe."

*[ON SCREEN: the fork's Issues tab — 17 `devin-remediate` issues, each an [security] CVE title.]*

---

## 0:35 – 1:15 · THE SETUP — a closed loop, not a script

> "Here's the fork of Superset. A scheduled Devin automation scanned its dependencies and
> filed these 17 CVE issues — pip, starlette, flask, and so on. Detection only; it never
> touches code.
>
> I built four Devin automations that form a closed loop, plus a service that orchestrates
> the middle. Stage one *finds* — it files these issues. Stage two, my engine, *groups and
> dispatches*. Stage three, a Devin session, *fixes* — opens the PR. Stage four, another
> Devin automation, *reviews and merges* — but only if it's safe."

*[ON SCREEN: the Devin Automations page — point at the four: Periodic Advisory Scan,
Dependency Vulnerability (Push), Dependency Issue Fix, Dependency PR Auto-Review & Merge.]*

> "The point: this isn't one prompt. It's an event-driven system where Devin is the
> primitive doing the work at three of the four stages."

---

## 1:15 – 3:15 · HOW — live demo + the architecture decisions

*[ON SCREEN: switch to the dashboard — the Control Room.]*

> "This is the control room for the middle of that loop — a Dockerized FastAPI service.
> Up top is the pipeline. Below it, the live backlog: 17 issues collapsed into 7 package
> groups. And that first decision is the important one."

**Decision 1 — group by package.**
> "Two issues both say 'upgrade starlette' but cite different CVEs. If I fixed issues
> one-to-one, I'd get two PRs editing the same line of requirements — a merge conflict I
> created myself. So the orchestrator groups by package, takes the *highest* fix version
> that satisfies all of them, and asks Devin for *one* PR that closes the whole group.
> Seventeen issues, seven PRs."

*[ON SCREEN: click **Simulate GitHub webhook**. Action log shows 'Webhook 200 · signature verified · dispatched…'.]*

**Decision 2 — it's genuinely event-driven.**
> "That button fired a real, HMAC-signed `issues.opened` event at my webhook endpoint —
> signature verified, exactly like GitHub would send. In production a GitHub webhook hits
> the same route. The runs table just filled in — one row per package Devin is now working."

**Decision 3 — safety rails, because this spends money and writes code.**
> "Notice the mode badge says DRY RUN — that's the default. The full pipeline runs, but no
> real Devin session starts and no PR opens until I explicitly go live. Every dispatch is
> capped: N packages per trigger, a hard ACU ceiling per session. And `paramiko` has no
> published fix — so instead of forcing a broken upgrade, the agent is told to comment the
> blocker and stop. You can see it flagged right here."

*[ON SCREEN: point at paramiko → 'no fix published' in the Package Groups table.]*

**The money shot — Devin behind the scenes.**
*[If live: switch to the Devin session that just opened; show it editing requirements, running tests, opening the PR. Then the GitHub PR with `Closes #75 #74 #73…`.]*
> "Here's Devin actually doing it: reading the issue, upgrading the pin, running the test
> suite, and opening a PR that closes all five starlette issues at once. My code never wrote
> a line of the fix — it wrote the *instructions and the guardrails*. Devin wrote the fix."

*[ON SCREEN: click **Generate report**.]*

**Observability — how a leader knows it's working.**
> "And this is the answer to 'how would I, as an eng leader, know this is working?' —
> a one-page executive report: open CVEs, PRs opened, issues closed, ACU spent, success rate.
> Exportable to Markdown for Slack, JSON for a BI pipeline, or PDF. There's even a 'call me'
> button — it'll phone you and read the status out loud."

---

## 3:15 – 4:10 · WHY — why this needs an autonomous agent

> "Here's the honest question: why Devin, and not a Dependabot rule or a shell script?
>
> Because a version bump is the *easy* 20%. The other 80% is judgment: this upgrade broke an
> import — patch the two call sites. The lockfile needs recompiling, not hand-editing. The
> test suite fails for a reason unrelated to my change — is it safe anyway? A script can bump
> a number. It can't *read the failure, decide, and adapt*. Dependabot opens the PR and then
> stops at exactly the hard part — a human still has to make it green.
>
> Devin closes that gap. It's not a smarter regex; it's an engineer that reads the diff, runs
> the tests, fixes the fallout, and knows when to stop and ask. That's what makes a *closed*
> loop possible instead of a loop that always dead-ends on a person. And the auto-merge stage
> only merges when the diff is scoped to the bump and CI is green — so autonomy never means
> reckless."

---

## 4:10 – 4:50 · WHEN — extending this in a real engagement

> "In a real customer engagement, this generalizes fast:
>
> - **Multi-repo, multi-ecosystem** — the grouping and prompt logic isn't pip-specific; swap
>   the issue parser and it covers npm, cargo, go modules across a whole org.
> - **Policy-aware autonomy** — auto-merge low-risk patch bumps on green CI; require human
>   review for majors. The dial between 'agent proposes' and 'agent ships' is a config value.
> - **Route the hard ones to humans** — when Devin comments a blocker, that becomes a triage
>   queue, so engineers only see the genuinely ambiguous cases.
> - **Plug into the real stack** — Slack alerts on merge, the ledger into Datadog, a severity
>   SLA that pages if a critical CVE isn't merged within N hours."

---

## 4:50 – 5:00 · CLOSE

> "So: a scanner finds it, my engine groups and dispatches it, Devin fixes and opens the PR,
> and a second agent reviews and merges it — a security backlog that drains itself, with
> people focused only on the calls that actually need a human. That's Devin as a core
> primitive, not a helper. Thanks for watching."

---

### Delivery notes
- ~720 spoken words → lands near 5:00 with demo pauses. If short on time, trim the WHEN bullets to two.
- Keep the cursor moving to what you're describing; silence during clicks is fine — let the UI talk.
- If demoing fully live, flip `DRY_RUN=false`, recreate the container, and pre-open one Devin session
  so the "behind the scenes" moment is instant rather than a wait.
- Fallback if a live session is slow: narrate over a PR + Devin session from an earlier live run.
