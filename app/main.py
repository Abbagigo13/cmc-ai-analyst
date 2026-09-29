import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from .llm import run_agent  # noqa: E402
from .dashboard import get_summary  # noqa: E402
from . import cmc  # noqa: E402

app = FastAPI(title="CMC AI Market Analyst")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class Turn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Turn] = []


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {
        "ok": True,
        "cmc_key_set": bool(os.environ.get("CMC_API_KEY")),
        "qwen_key_set": bool(os.environ.get("DASHSCOPE_API_KEY")),
        "model": os.environ.get("QWEN_MODEL", "qwen-plus"),
        "credits_used": cmc.CREDITS_USED,
    }


@app.get("/tokenized-assets")
async def tokenized_assets():
    try:
        assets = await cmc.get_rwa_listings(limit=50, sort="rwa_rank")
        return {"assets": assets, "count": len(assets)}
    except Exception as e:
        logging.exception("tokenized-assets failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/news")
async def news():
    try:
        return await cmc.get_news(limit=12)
    except Exception as e:
        logging.exception("news failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/markets/top200")
async def markets_top200():
    try:
        assets = await cmc.get_listings(limit=200, sort="market_cap")
        return {"assets": assets, "count": len(assets)}
    except Exception as e:
        logging.exception("markets200 failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/markets/top100")
async def markets_top100():
    try:
        assets = await cmc.get_listings(limit=100, sort="market_cap")
        return {"assets": assets, "count": len(assets)}
    except Exception as e:
        logging.exception("markets failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/dashboard/summary")
async def dashboard_summary():
    try:
        return await get_summary()
    except Exception as e:
        logging.exception("dashboard failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.post("/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")
    try:
        result = await run_agent(
            req.message,
            history=[t.model_dump() for t in req.history],
        )
        return result
    except Exception as e:
        logging.exception("chat failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")