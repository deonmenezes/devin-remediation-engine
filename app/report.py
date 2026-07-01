"""Report generation — turns the run ledger + live backlog into an executive
summary a VP of Engineering can read at a glance, available as standalone HTML,
Markdown (shareable in Slack/email), or JSON (for a real metrics pipeline)."""
from datetime import datetime, timezone

from . import config, store
from .orchestrator import Orchestrator

_TERMINAL_OK = {"fixed", "merged"}
_TERMINAL_BLOCKED = {"blocked", "error"}


def build_report():
    plan = Orchestrator().plan()
    runs = store.all_runs()
    summary = store.summary()

    fixable = [g for g in plan["groups"] if g["has_fix"]]
    no_fix = [g for g in plan["groups"] if not g["has_fix"]]

    prs = [r["pr_url"] for r in runs if r.get("pr_url")]
    issues_closed = sum(len(r["issue_numbers"]) for r in runs if r["status"] in _TERMINAL_OK)
    resolved = [r for r in runs if r["status"] in _TERMINAL_OK]
    blocked = [r for r in runs if r["status"] in _TERMINAL_BLOCKED]
    terminal = len(resolved) + len(blocked)
    success_rate = round(100 * len(resolved) / terminal) if terminal else None

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "repo": config.GITHUB_REPO,
        "repo_url": f"https://github.com/{config.GITHUB_REPO}",
        "mode": "LIVE" if not config.DRY_RUN else "DRY RUN",
        "kpis": {
            "open_issues": plan["total_issues"],
            "package_groups": len(plan["groups"]),
            "fixable_packages": len(fixable),
            "no_fix_packages": len(no_fix),
            "runs_dispatched": summary["total_runs"],
            "prs_opened": len(prs),
            "issues_closed_by_prs": issues_closed,
            "acu_consumed": round(summary["total_acu_consumed"], 1),
            "success_rate_pct": success_rate,
        },
        "by_status": summary["by_status"],
        "runs": runs,
        "groups": plan["groups"],
        "automations": config.AUTOMATIONS,
    }


def to_markdown(rep):
    k = rep["kpis"]
    lines = [
        f"# Dependency Remediation Report — `{rep['repo']}`",
        "",
        f"_Generated {rep['generated_at']} · mode: **{rep['mode']}**_",
        "",
        "## Executive summary",
        "",
        f"- **Open CVE issues in backlog:** {k['open_issues']}",
        f"- **Collapsed into package groups:** {k['package_groups']} "
        f"({k['fixable_packages']} with a published fix, {k['no_fix_packages']} awaiting one)",
        f"- **Remediation runs dispatched:** {k['runs_dispatched']}",
        f"- **Pull requests opened:** {k['prs_opened']}",
        f"- **Issues closed by those PRs:** {k['issues_closed_by_prs']}",
        f"- **ACU consumed:** {k['acu_consumed']}",
        f"- **Success rate (of finished runs):** "
        f"{str(k['success_rate_pct']) + '%' if k['success_rate_pct'] is not None else 'n/a (nothing finished yet)'}",
        "",
        "## Status breakdown",
        "",
    ]
    if rep["by_status"]:
        for status, count in rep["by_status"].items():
            lines.append(f"- {status.replace('_', ' ')}: {count}")
    else:
        lines.append("- _no runs yet_")
    lines += ["", "## Runs", "", "| Package | Closes | Status | PR | ACU |", "|---|---|---|---|---|"]
    if rep["runs"]:
        for r in rep["runs"]:
            issues = " ".join(f"#{n}" for n in r["issue_numbers"])
            pr = r["pr_url"] or "—"
            lines.append(f"| `{r['package']}` | {issues} | {r['status'].replace('_',' ')} | {pr} | {r['acu_consumed'] or '—'} |")
    else:
        lines.append("| _no runs dispatched yet_ | | | | |")
    lines += ["", "## Remaining backlog (package groups)", "", "| Package | Issues | Fix version | State |", "|---|---|---|---|"]
    for g in rep["groups"]:
        issues = " ".join(f"#{n}" for n in g["issues"])
        fixed = g["fixed"] or "no fix published"
        state = "dispatched" if g["already_dispatched"] else "pending"
        lines.append(f"| `{g['package']}` | {issues} | {fixed} | {state} |")
    lines += ["", "## Automations in the loop", ""]
    for a in rep["automations"]:
        lines.append(f"- **{a['name']}** — _{a['trigger']}_. {a['purpose']}")
    lines.append("")
    return "\n".join(lines)


def to_html(rep):
    k = rep["kpis"]
    sr = f"{k['success_rate_pct']}%" if k["success_rate_pct"] is not None else "—"

    def kpi(n, label):
        return f'<div class="kpi"><div class="n">{n}</div><div class="l">{label}</div></div>'

    kpis = "".join([
        kpi(k["open_issues"], "Open CVE issues"),
        kpi(k["package_groups"], "Package groups"),
        kpi(k["runs_dispatched"], "Runs dispatched"),
        kpi(k["prs_opened"], "PRs opened"),
        kpi(k["issues_closed_by_prs"], "Issues closed"),
        kpi(k["acu_consumed"], "ACU consumed"),
        kpi(sr, "Success rate"),
    ])

    run_rows = "".join(
        f"<tr><td><code>{r['package']}</code></td>"
        f"<td>{' '.join(f'#{n}' for n in r['issue_numbers'])}</td>"
        f"<td><span class='b b-{r['status']}'>{r['status'].replace('_',' ')}</span></td>"
        f"<td>{('<a href=' + chr(34) + r['pr_url'] + chr(34) + ' target=_blank>PR ↗</a>') if r['pr_url'] else '—'}</td>"
        f"<td>{r['acu_consumed'] or '—'}</td></tr>"
        for r in rep["runs"]
    ) or "<tr><td colspan=5 style='color:#888'>No runs dispatched yet.</td></tr>"

    group_rows = "".join(
        f"<tr><td><code>{g['package']}</code></td>"
        f"<td>{' '.join(f'#{n}' for n in g['issues'])}</td>"
        f"<td>{g['fixed'] or '<span style=color:#e05260>no fix published</span>'}</td>"
        f"<td><span class='b b-{'done' if g['already_dispatched'] else 'pending'}'>"
        f"{'dispatched' if g['already_dispatched'] else 'pending'}</span></td></tr>"
        for g in rep["groups"]
    )

    auto_items = "".join(
        f"<li><b>{a['name']}</b> — <i>{a['trigger']}</i>. {a['purpose']}</li>"
        for a in rep["automations"]
    )

    return f"""<!DOCTYPE html><html><head><meta charset=utf-8>
<title>Remediation Report · {rep['repo']}</title>
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
<style>
  body{{font-family:'Inter',-apple-system,system-ui,sans-serif;background:#f6f7f9;color:#111827;margin:0;padding:40px 24px 64px}}
  .sheet{{max-width:960px;margin:0 auto}}
  h1{{font-size:23px;margin:0 0 4px;letter-spacing:-.01em}} .meta{{color:#6b7280;font-size:13px;margin-bottom:24px}}
  h2{{font-size:14px;margin:30px 0 12px;color:#374151}}
  .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:12px;margin-bottom:8px}}
  .kpi{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:15px 17px}}
  .kpi .n{{font-size:25px;font-weight:700;color:#111827}} .kpi .l{{font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em;margin-top:6px;font-weight:600}}
  table{{width:100%;border-collapse:collapse;font-size:13px;background:#fff;border-radius:10px;overflow:hidden;border:1px solid #e5e7eb}}
  th{{text-align:left;padding:10px 14px;font-size:10.5px;text-transform:uppercase;color:#6b7280;background:#f9fafb;letter-spacing:.05em;font-weight:600;border-bottom:1px solid #e5e7eb}}
  td{{padding:11px 14px;border-top:1px solid #eef0f3;color:#374151}}
  code{{background:#f3f4f6;padding:1px 6px;border-radius:5px;font-family:ui-monospace,monospace;border:1px solid #eef0f3}}
  .b{{padding:2px 9px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid transparent}}
  .b-fixed,.b-merged,.b-done{{background:#ecfdf5;color:#15803d;border-color:#d1fae5}}
  .b-running{{background:#fffbeb;color:#b45309;border-color:#fde68a}}
  .b-blocked,.b-error{{background:#fef2f2;color:#b91c1c;border-color:#fecaca}}
  .b-skipped_no_fix,.b-pending{{background:#eff6ff;color:#1d4ed8;border-color:#dbeafe}}
  .b-dry_run{{background:#f3f4f6;color:#4b5563;border-color:#e5e7eb}}
  a{{color:#2563eb}} ul{{line-height:1.7;color:#374151;font-size:13px}}
  .actions{{margin:22px 0;display:flex;gap:10px;flex-wrap:wrap}}
  .actions a{{display:inline-flex;align-items:center;font-size:13px;font-weight:600;padding:8px 14px;border-radius:8px;border:1px solid #e5e7eb;background:#fff;color:#374151;text-decoration:none}}
  .actions a:hover{{background:#f9fafb}}
  .callcard{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 18px;margin:0 0 8px}}
  .callcard .ct{{font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px;margin-bottom:4px}}
  .callcard .cb{{font-size:12.5px;color:#6b7280;margin:0 0 12px}}
  .callform{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
  .callform input{{font-family:inherit;font-size:13px;padding:8px 11px;border:1px solid #e5e7eb;border-radius:8px;width:210px}}
  .callform button{{font-family:inherit;font-size:13px;font-weight:600;padding:8px 15px;border-radius:8px;border:1px solid #111827;background:#111827;color:#fff;cursor:pointer}}
  .callform button:hover{{background:#000}} .callform button:disabled{{opacity:.5;cursor:default}}
  .callmsg{{font-size:12.5px;margin-top:9px}} .callmsg.ok{{color:#15803d}} .callmsg.err{{color:#b91c1c}}
  .callcard.off{{opacity:.6}}
  @media print{{body{{background:#fff}} .actions,.callcard{{display:none}}}}
</style></head><body><div class=sheet>
<h1>Dependency Remediation Report</h1>
<div class=meta>Repository <a href="{rep['repo_url']}" target=_blank>{rep['repo']}</a> · generated {rep['generated_at']} · mode <b>{rep['mode']}</b></div>
<div class=actions>
  <a href="/report.md">Download Markdown</a>
  <a href="/report.json">Download JSON</a>
  <a href="javascript:window.print()">Print / Save PDF</a>
  <a href="/dashboard">Back to dashboard</a>
</div>
<div class=callcard id=callcard>
  <div class=ct><svg width=16 height=16 viewBox="0 0 24 24" fill="none" stroke="#111827" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3.1-8.7A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.5-1.2a2 2 0 0 1 2.1-.5c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2z"/></svg>Prefer to listen? Get a call that reads this report aloud</div>
  <p class=cb id=callblurb>We'll phone you and a voice agent will brief you on the remediation status — open CVEs, PRs opened, issues closed, and anything blocked.</p>
  <div class=callform>
    <input id=phone type=tel inputmode=tel placeholder="+1 415 555 0142" aria-label="Your phone number">
    <button id=callbtn>Call me now</button>
  </div>
  <div class=callmsg id=callmsg></div>
</div>
<script>
(function(){{
  var card=document.getElementById('callcard'), btn=document.getElementById('callbtn'),
      msg=document.getElementById('callmsg'), blurb=document.getElementById('callblurb');
  fetch('/voice-status').then(function(r){{return r.json()}}).then(function(s){{
    if(!s.configured){{ card.className='callcard off'; btn.disabled=true;
      blurb.textContent='Calling isn\\'t configured yet — set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER to enable a voice briefing of this report.'; }}
  }});
  btn.onclick=function(){{
    var phone=document.getElementById('phone').value;
    if(!phone){{ msg.className='callmsg err'; msg.textContent='Enter your phone number first.'; return; }}
    btn.disabled=true; msg.className='callmsg'; msg.textContent='Placing call…';
    fetch('/call-report',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{phone:phone}})}})
      .then(function(r){{return r.json().then(function(d){{return {{ok:r.ok,d:d}}}})}})
      .then(function(res){{
        if(!res.ok) throw new Error(res.d.detail||'Could not place the call');
        msg.className='callmsg ok';
        msg.textContent='Calling '+res.d.to+' now — the voice agent will read out the report'+(res.d.used_claude?' (script written by Claude).':'.');
      }})
      .catch(function(e){{ msg.className='callmsg err'; msg.textContent=e.message; }})
      .finally(function(){{ btn.disabled=false; }});
  }};
}})();
</script>
<h2>Executive summary</h2>
<div class=kpis>{kpis}</div>
<h2>Remediation runs</h2>
<table><thead><tr><th>Package</th><th>Closes</th><th>Status</th><th>PR</th><th>ACU</th></tr></thead><tbody>{run_rows}</tbody></table>
<h2>Backlog — package groups</h2>
<table><thead><tr><th>Package</th><th>Issues</th><th>Fix version</th><th>State</th></tr></thead><tbody>{group_rows}</tbody></table>
<h2>Automations in the loop</h2>
<ul>{auto_items}</ul>
</div></body></html>"""
