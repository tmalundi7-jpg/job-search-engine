"""
Optional FastAPI dashboard for health, metrics, job viewing, feedback, and manual scan.
"""
from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.responses import JSONResponse, PlainTextResponse
import uvicorn
import config
from database import Database
from metrics import get_metrics
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="Swarm Engine Dashboard")

class FeedbackModel(BaseModel):
    job_url: str
    feedback: str  # 'good', 'bad', 'neutral'

async def verify_api_key(x_api_key: str = Header(None)):
    if config.DASHBOARD_API_KEY and x_api_key != config.DASHBOARD_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return True

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/metrics", dependencies=[Depends(verify_api_key)])
async def metrics():
    return PlainTextResponse(get_metrics().decode('utf-8') if isinstance(get_metrics(), bytes) else str(get_metrics()), media_type="text/plain")

@app.get("/jobs", dependencies=[Depends(verify_api_key)])
async def get_jobs():
    db = getattr(app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")
    jobs = await db.get_all_matching_jobs()
    return JSONResponse([job.to_dict() for job in jobs])

@app.get("/report", dependencies=[Depends(verify_api_key)])
async def get_report():
    try:
        with open(config.REPORT_OUTPUT_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        return PlainTextResponse(content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found")

@app.post("/feedback", dependencies=[Depends(verify_api_key)])
async def submit_feedback(fb: FeedbackModel):
    db = getattr(app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")
    await db.add_feedback(fb.job_url, fb.feedback)
    return {"status": "ok"}

@app.post("/scan", dependencies=[Depends(verify_api_key)])
async def trigger_scan(background_tasks: BackgroundTasks):
    engine = getattr(app.state, "engine", None)
    if engine:
        background_tasks.add_task(engine.run_cycle)
        return {"status": "scan triggered"}
    else:
        raise HTTPException(status_code=500, detail="Engine not available")

async def start_dashboard(db: Database, engine=None):
    app.state.db = db
    app.state.engine = engine
    config_uvicorn = uvicorn.Config(app, host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, log_level="info")
    server = uvicorn.Server(config_uvicorn)
    await server.serve()
