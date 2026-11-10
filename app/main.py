"""「见微」AI for Science 大陆情报系统 — 应用入口。

约束：uvicorn 单 worker 运行（调度器在进程内），生产由 systemd 管理（端口 8010）。
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import BASE_DIR, settings
from app.db import migrate, session_scope
from app.ingest.registry import sync_sources
from app.log import log_event, now_iso
from app.scheduler import start_scheduler, stop_scheduler
from app.seeds import run_seeds

STATIC_DIR = os.path.join(BASE_DIR, "static")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    migrate()
    run_seeds()
    with session_scope() as db:
        sync_sources(db)
    if settings.scheduler_enabled:
        start_scheduler()
    log_event("app.started", scheduler=settings.scheduler_enabled)
    yield
    stop_scheduler()


app = FastAPI(title="见微 · AI for Science 大陆情报系统", version="1.0.0",
              lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
# Starlette 1.3.1 的 GZipMiddleware 只接受 minimum_size / compresslevel，
# 并且已经跳过 text/event-stream（攒包会卡住对话的第一帧）。不要加构造参数。
# nginx 侧再关 proxy_buffering，见 nginx-aidrug.conf。
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(api_router)


@app.get("/healthz")
@app.get("/api/health")  # 兼容 v0.1 探活
def healthz():
    return {"status": "ok", "ts": now_iso()}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"),
                        media_type="application/manifest+json")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8010, reload=True)
