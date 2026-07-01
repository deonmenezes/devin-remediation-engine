# Loom Script: Devin Dependency Remediation Engine (~5 min)

**Audience:** a VP of Engineering and a few senior engineers who are evaluating Devin.
**Framing:** you are a Forward Deployed Engineer showing how Devin solves a real, expensive
workflow problem end to end. Devin is the hero. Your code is the thin layer that puts Devin to work.

**Two tabs open before you record:**
1. `http://localhost:8000/dashboard` (mode says DRY RUN, freshly Reset so the table is empty)
2. The Devin Automations page, plus a tab on the fork's Issues and Pull Requests.

**Pre-flight checklist**
- [ ] `docker compose up` running, dashboard loads, mode badge says DRY RUN.
- [ ] Clicked Reset so the run ledger is empty.
- [ ] Money shot ready: either flip `DRY_RUN=false` beforehand so Devin opens a real PR live,
      or have a real Devin PR from an earlier run open in a tab.
- [ ] Logged in on the GitHub tab and the Devin tab.

---

## 0:00 to 0:35 · WHAT (the problem a VP feels)

> "Every security scanner your team runs, Dependabot, Snyk, pip-audit, is great at one thing:
> finding vulnerable dependencies and turning them into tickets. On a codebase the size of
> Apache Superset that becomes a constant stream of 'upgrade this package' work. Someone has
> to triage each one, bump the version, fix whatever breaks, run the tests, and open a pull
> request. Finding the problem is cheap. Fixing it is where your engineers actually burn hours.
> So I pointed Devin at that bottleneck. The goal is simple: take a backlog of security tickets
> and turn it into reviewed, merged pull requests, with Devin doing the engineering and a person
> stepping in only when something genuinely needs judgment."

*[ON SCREEN: the fork's Issues tab, 17 security tickets, each a CVE.]*

---

## 0:35 to 1:15 · THE SETUP (Devin doing the whole loop)

> "Here is the fork. Devin already scanned it and filed these 17 security tickets. That is the
> first thing Devin is doing for me, running as a scheduled automation that just watches for new
> vulnerabilities and reports them.
>
> From there I have Devin run the entire remediation loop. One Devin automation finds the
> vulnerabilities. When a ticket appears, Devin picks it up, writes the fix, and opens the pull
> request. And when that pull request lands, a second Devin automation reviews it and merges it,
> but only when it is safe. Devin is doing the finding, the fixing, and the reviewing. The small
> service in the middle just decides what to hand Devin and when."

*[ON SCREEN: the Devin Automations page. Point to each automation as you name it.]*

---

## 1:15 to 3:15 · HOW (see Devin work, and the one decision that matters)

*[ON SCREEN: switch to the dashboard.]*

> "This dashboard is mission control. It reads the live backlog straight from GitHub. Seventeen
> tickets, and notice they collapse into seven pieces of work. That is the one design decision
> worth calling out."

**The grouping decision, in plain terms.**
> "Two of these tickets both say 'upgrade starlette', just for different CVEs. If I sent Devin
> after each ticket separately, I would get two pull requests editing the same line, and they
> would fight each other. So I group the tickets by package and give Devin one clear job per
> package: upgrade it once, to the version that clears every CVE, and close all of those tickets
> in a single pull request. Seventeen tickets become seven clean pull requests."

*[ON SCREEN: click Simulate GitHub webhook. Point at the action log.]*

> "I just simulated GitHub telling us a new ticket was opened. It came in signed, we verified it,
> and Devin was dispatched. You can see the work show up in the table, one row per package Devin
> is now handling. In production this is a real GitHub webhook, so the moment a vulnerability is
> filed, Devin starts on it. No one has to notice or assign it."

**Guardrails, because Devin is writing real code and spending real budget.**
> "A few things I want a VP to see. The badge says DRY RUN, which is the safe default. Nothing
> real happens until I choose to go live. Every run is capped, so a flood of tickets can never
> turn into runaway cost. And look at paramiko. There is no published fix for it yet, so instead
> of forcing a broken upgrade, Devin is told to comment on the ticket, explain the blocker, and
> stop. Devin knows when not to act."

**The money shot: Devin behind the scenes.**
*[If live: open the Devin session that just started. Show it editing requirements, running the
tests, and opening the PR that says Closes #75 #74 #73…]*
> "This is Devin actually doing the work. It reads the ticket, upgrades the dependency, runs the
> test suite, and opens a pull request that closes all five starlette tickets at once. I want to
> be clear: I did not write the fix. I wrote Devin's instructions and its guardrails. Devin wrote
> and verified the code."

*[ON SCREEN: click Generate report.]*

> "And this is how a leader knows it is working without reading every pull request. Open
> vulnerabilities, pull requests opened, tickets closed, budget spent, success rate, on one page.
> You can export it to your team channel or your dashboards. It will even call your phone and read
> the status out loud."

---

## 3:15 to 4:10 · WHY (why this only works with Devin)

> "The fair question is: why does this need Devin, instead of a Dependabot rule or a script?
> Because bumping a version number is the easy part. The hard part is everything after. The
> upgrade breaks an import, so something has to go fix the callers. The lockfile has to be
> recompiled, not hand-edited. A test fails, and someone has to read it and decide whether it is
> related or safe to ship. A script cannot do any of that. It changes a number and hands the real
> work back to a human. That is exactly why Dependabot pull requests pile up unmerged.
>
> Devin is what closes that gap, because Devin behaves like an engineer. It reads the failure,
> makes the fix, and knows when it is out of its depth and should ask. That is what turns this
> from a tool that creates more work into a loop that actually finishes the work. And the review
> step keeps it safe, because Devin only merges when the change is scoped to the upgrade and the
> tests are green."

---

## 4:10 to 4:50 · WHEN (where we take it next)

> "In a real rollout with your team, this grows quickly. It is not tied to Python, so the same
> pattern covers your npm, Go, and Java services across every repo. You set the risk policy, so
> Devin can auto-merge low-risk patches and route the bigger upgrades to a human for approval.
> The tickets Devin flags as blocked become a clean triage queue, so your engineers only ever
> look at the genuinely hard cases. And it plugs into your stack, a Slack note on every merge,
> the data feeding your dashboards, and an alert if a critical vulnerability is not fixed in time."

---

## 4:50 to 5:00 · CLOSE

> "So Devin finds the vulnerability, Devin writes and opens the fix, and Devin reviews and merges
> it. A security backlog that clears itself, with your engineers spending their time only on the
> decisions that actually need a person. That is Devin as the engine, not an assistant. Thanks for
> watching."

---

### Delivery notes
- Around 720 spoken words. With demo pauses it lands near five minutes.
- Say "Devin" out loud often. The VP should leave remembering Devin did the work.
- Let the screen carry the clicks. A short silence while the UI updates is fine.
- For the strongest version, go fully live: flip `DRY_RUN=false`, recreate the container, and have
  one Devin session already opened so the behind-the-scenes moment is instant instead of a wait.
- If a live session is slow, narrate over a real Devin pull request from an earlier run.
