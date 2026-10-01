"""Entry point — uvicorn main:app (PYTHONPATH=src)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_.auth import HEADER, require_token
from platform_.config import config
from platform_.db import SessionLocal, init_db
from write.api.routers import router as write_router
from write.application.stories import recover_interrupted

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        recover_interrupted(db)
    finally:
        db.close()
    if not config.folio_api_token:
        log.warning("FOLIO_API_TOKEN chưa đặt — API mở cho mọi request")
    yield


app = FastAPI(title="Write Service API", lifespan=lifespan)
app.middleware("http")(require_token)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", HEADER],
)
app.include_router(write_router)


@app.get("/api/health")
@app.get("/api/write/health")
def health():
    return {"status": "ok"}
