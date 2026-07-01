import hashlib
import hmac
import logging

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
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


@app.post("/poll")
def manual_poll():
    updated = orchestrator.poll_running()
    return {"updated_run_ids": updated}


@app.get("/status")
def status():
    return JSONResponse({"summary": store.summary(), "runs": store.all_runs()})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "summary": store.summary(), "runs": store.all_runs(), "dry_run": config.DRY_RUN},
    )
