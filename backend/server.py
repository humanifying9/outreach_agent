"""FastAPI server: REST + WebSocket for the cold-emailer UI."""
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from .event_bus import EventBus
from .gmail_client import GmailClient
from .orchestrator import Orchestrator, list_drafts, delete_draft

FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="ColdEmailer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

bus = EventBus()
gmail = GmailClient(
    credentials_path=os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials/google_client_secret.json"),
    token_path=os.environ.get("GOOGLE_TOKEN_PATH", "credentials/google_token.json"),
)
orchestrator = Orchestrator(bus, gmail, headless_browser=False)


class CampaignRequest(BaseModel):
    query: str
    max_companies: int = 5
    additional_interests: str = ""
    create_gmail_drafts: bool = True


@app.get("/api/status")
async def status():
    return {
        "running": orchestrator.running,
        "gmail_connected": gmail.is_authenticated(),
        "gmail_email": gmail.get_connected_email(),
        "hunter_configured": bool(os.environ.get("HUNTER_API_KEY")),
    }


@app.post("/api/gmail/connect")
async def gmail_connect():
    try:
        email = await asyncio.to_thread(gmail.authenticate)
        return {"email": email}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth failed: {e}")


@app.post("/api/gmail/disconnect")
async def gmail_disconnect():
    gmail.logout()
    return {"ok": True}


@app.post("/api/campaign/start")
async def campaign_start(req: CampaignRequest):
    if orchestrator.running:
        raise HTTPException(status_code=409, detail="Campaign already running")
    asyncio.create_task(orchestrator.run_campaign(
        query=req.query,
        max_companies=req.max_companies,
        additional_interests=req.additional_interests,
        create_gmail_drafts=req.create_gmail_drafts,
    ))
    return {"ok": True}


@app.get("/api/drafts")
async def get_drafts():
    return list_drafts()


@app.delete("/api/drafts/{draft_id}")
async def remove_draft(draft_id: str):
    ok = delete_draft(draft_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"ok": True}


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    q = bus.subscribe()
    try:
        while True:
            event = await q.get()
            await ws.send_text(json.dumps(event.to_dict()))
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)


# Static frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIR / "index.html")
