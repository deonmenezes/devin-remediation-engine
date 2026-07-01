# The fully-automated remediation loop

Generated with the Codex CLI (`omc ask codex`), gpt-5.5. Renders natively on GitHub.

**Happy path (green, fully automated):** detect → dispatch → fix → verify → gate → merge → issue closed.
**Guard exits (the only times a human is touched):** no published fix, major-version bump, or an out-of-scope diff / failed `deps-verify`.

```mermaid
flowchart TD
  subgraph DEVIN["Devin Automations - cloud"]
    PRIVATE["Private repo required"]
    DAILY["Periodic Advisory Scan<br/>daily"]
    PUSH["Dependency Vulnerability<br/>on push"]
    FIXER["Dependency Issue Fix<br/>upgrade package and test"]
    PRBOT["Open PR<br/>security: upgrade pkg to ver<br/>Closes issue N"]
    MERGER["Auto-Review and Merge<br/>approve and squash-merge"]
  end

  subgraph ENGINE["Remediation Engine - Docker and FastAPI"]
    ORCH["Issue webhook<br/>list open remediation issues"]
    GROUP["Parse and group by package<br/>select highest fix version"]
    SENT{"Already dispatched?"}
    FIX{"Published fix?"}
    MAJOR{"Major bump?"}
    SESSION["Create Devin session<br/>with explicit upgrade prompt"]
    VERIFY["Verify every 30 seconds<br/>and on PR webhook<br/>integrity plus pip-audit"]
    STATUS["Post deps-verify status"]
    GREEN{"deps-verify green?"}
    READY["Convert draft to ready"]
    LEDGER["Poll session<br/>SQLite ledger<br/>dashboard and report"]
  end

  subgraph GITHUB["GitHub - deonmenezes/superset - private"]
    SCAN["Scan pinned dependencies"]
    ISSUE["One devin-remediate issue<br/>per CVE"]
    NOFIX_COMMENT["Comment blocked, no fix<br/>leave issue open"]
    MAJOR_COMMENT["Comment held for human review<br/>open no PR"]
    PR["Security upgrade PR"]
    FAIL_COMMENT["Comment verification blocker<br/>leave PR open"]
    PROTECT["Branch protection<br/>requires only deps-verify"]
    SCOPE{"Diff in scope?"}
    SCOPE_COMMENT["Comment out-of-scope diff<br/>leave PR open"]
    MERGED["Squash-merge"]
    CLOSED["Issue auto-closed<br/>by Closes issue N"]
  end

  subgraph HUMAN["Human"]
    H_NOFIX["Resolve missing fix"]
    H_MAJOR["Review major upgrade"]
    H_BLOCKER["Resolve failed verification<br/>or out-of-scope diff"]
  end

  PRIVATE --> DAILY
  PRIVATE --> PUSH
  DAILY --> SCAN
  PUSH --> SCAN
  SCAN --> ISSUE
  ISSUE --> ORCH
  ORCH --> GROUP
  GROUP --> SENT
  SENT -- Yes --> LEDGER
  SENT -- No --> FIX
  FIX -- No --> NOFIX_COMMENT --> H_NOFIX
  FIX -- Yes --> MAJOR
  MAJOR -- Yes --> MAJOR_COMMENT --> H_MAJOR
  MAJOR -- No --> SESSION
  SESSION --> FIXER --> PRBOT --> PR
  PR --> VERIFY --> STATUS --> GREEN
  GREEN -- No --> FAIL_COMMENT --> H_BLOCKER
  GREEN -- Yes --> READY --> PROTECT
  PROTECT --> SCOPE
  SCOPE -- No --> SCOPE_COMMENT --> H_BLOCKER
  SCOPE -- Yes --> MERGER --> MERGED --> CLOSED
  CLOSED -. observability feedback .-> LEDGER
  LEDGER -. PR status comment .-> ISSUE

  classDef auto fill:#dcfce7,stroke:#15803d,color:#14532d,stroke-width:2px;
  classDef guard fill:#fef3c7,stroke:#b45309,color:#78350f,stroke-width:2px;
  classDef human fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d,stroke-width:3px;
  classDef blocked fill:#fff1f2,stroke:#e11d48,color:#881337,stroke-width:2px;
  classDef observe fill:#e0f2fe,stroke:#0369a1,color:#0c4a6e,stroke-width:2px;

  class PRIVATE,DAILY,PUSH,SCAN,ISSUE,ORCH,GROUP,SESSION,FIXER,PRBOT,PR,VERIFY,STATUS,READY,PROTECT,MERGER,MERGED,CLOSED auto;
  class SENT,FIX,MAJOR,GREEN,SCOPE guard;
  class H_NOFIX,H_MAJOR,H_BLOCKER human;
  class NOFIX_COMMENT,MAJOR_COMMENT,FAIL_COMMENT,SCOPE_COMMENT blocked;
  class LEDGER observe;
```

**Legend** — 🟩 green = automated step · 🟨 amber diamond = decision guard · 🟥 red = human hand-off · 🟦 blue = observability.
