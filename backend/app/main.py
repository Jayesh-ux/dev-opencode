import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes.chat import router as chat_router
from app.routes.realtime import router as realtime_router
from app.routes.voice import router as voice_router
from app.routes.terminal import router as terminal_router
from app.services.ws_manager import sessions
from app.snapshotter import list_snapshots
from app.services.token_monitor import token_monitor


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(sessions.run_cleanup_loop())
    token_monitor.start()
    yield
    await token_monitor.stop()
    cleanup_task.cancel()


logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
app = FastAPI(title="AI Assistant Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(realtime_router)
app.include_router(terminal_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": f"Internal server error: {str(exc)}"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/snapshots")
async def snapshots():
    try:
        return {"snapshots": list_snapshots()}
    except Exception as e:
        return {"snapshots": [], "error": str(e)}
