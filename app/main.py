import hashlib
import hmac
import json
import logging

import requests
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler

from . import config, store
from .orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")

app = FastAPI(title="Devin Dependency Remediation Engine")
templates = Jinja2Templates(directory="app/templates")

store.init_db()
orchestrator = Orchestrator()

_scheduler = BackgroundScheduler()
_scheduler.add_job(lambda: orchestrator.poll_running(), "interval", seconds=config.POLL_INTERVAL_SECONDS, id="poll")
if config.RESCAN_INTERVAL_SECONDS > 0:
    _scheduler.add_job(
        lambda: orchestrator.dispatch(),
        "interval",
        seconds=config.RESCAN_INTERVAL_SECONDS,
        id="rescan",
    )
_scheduler.start()


def _verify_signature(secret: str, body: bytes, signature_header: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/healthz")
def healthz():
    missing = config.missing_required()
    return {"ok": not missing, "dry_run": config.DRY_RUN, "missing_env": missing}


@app.post("/webhook/github")
async def github_webhook(request: Request):
    body = await request.body()
    if config.GITHUB_WEBHOOK_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_signature(config.GITHUB_WEBHOOK_SECRET, body, sig):
            raise HTTPException(status_code=401, detail="invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()

    interesting = event == "issues" and payload.get("action") in ("opened", "labeled")
    interesting = interesting or (event == "push")
    if not interesting:
        return {"skipped": True, "event": event, "action": payload.get("action")}

    log.info("webhook received event=%s action=%s — dispatching", event, payload.get("action"))
    dispatched = orchestrator.dispatch()
    return {"event": event, "dispatched": [d["package"] for d in dispatched]}


@app.post("/trigger")
def manual_trigger(limit: int = Query(default=None)):
    """Manually fire a dispatch pass — used for demos and for working through
    the existing issue backlog that predates any webhook wiring."""
    dispatched = orchestrator.dispatch(limit=limit)
    return {"dispatched": [{"package": d["package"], "status": d["status"]} for d in dispatched]}


@app.get("/plan")
def plan():
    """Read-only preview: what would be dispatched next, without side effects."""
    return orchestrator.plan()


@app.post("/simulate-webhook")
def simulate_webhook():
    """Fire a correctly-signed synthetic GitHub `issues.opened` event at our own
    /webhook/github endpoint. This lets a reviewer demo the real event-driven
    path from a dashboard button — signature verification and all — without
    needing a public tunnel or a real GitHub webhook."""
    payload = {
        "action": "opened",
        "issue": {
            "number": 999999,
            "title": "[security] SIMULATED: dashboard webhook button",
            "labels": [{"name": config.GITHUB_ISSUE_LABEL}, {"name": "security"}],
            "html_url": f"https://github.com/{config.GITHUB_REPO}/issues/999999",
        },
        "repository": {"full_name": config.GITHUB_REPO},
    }
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-GitHub-Event": "issues"}
    if config.GITHUB_WEBHOOK_SECRET:
        sig = hmac.new(config.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={sig}"
    resp = requests.post(
        f"http://localhost:{config.PORT}/webhook/github", data=body, headers=headers, timeout=30
    )
    return {"webhook_status": resp.status_code, "result": resp.json()}


@app.post("/poll")
def manual_poll():
    updated = orchestrator.poll_running()
    return {"updated_run_ids": updated}


@app.post("/reset")
def reset():
    """Clear the run ledger so a demo can start from a clean slate."""
    deleted = store.clear_runs()
    return {"cleared_runs": deleted}


@app.get("/status")
def status():
    return JSONResponse({"summary": store.summary(), "runs": store.all_runs()})


@app.get("/automations")
def automations():
    """Reference metadata for the Devin Automations configured in the dashboard
    for this org. Devin has no public API to list/poll automations, so this is
    static — it links out to the real thing rather than faking a live status."""
    return {"automations": config.AUTOMATIONS}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "summary": store.summary(),
            "runs": store.all_runs(),
            "plan": orchestrator.plan(),
            "dry_run": config.DRY_RUN,
            "default_limit": config.DISPATCH_LIMIT_PER_RUN,
            "automations": config.AUTOMATIONS,
            "repo": config.GITHUB_REPO,
            "repo_url": f"https://github.com/{config.GITHUB_REPO}",
            "issue_label": config.GITHUB_ISSUE_LABEL,
            "max_acu": config.MAX_ACU_PER_SESSION,
        },
    )
