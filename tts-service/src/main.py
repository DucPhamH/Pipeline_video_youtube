"""Entry point — uvicorn main:app (PYTHONPATH=src)."""
import logging
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_.auth import HEADER, require_token
from platform_.config import config
from platform_.db import init_db
from tts.api.routers import router as tts_router
from tts.application.export_audio import clean_exports
from tts.application.run_job import recover_interrupted

log = logging.getLogger(__name__)


def _has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    recover_interrupted()
    clean_exports()
    if not config.folio_api_token:
        log.warning("FOLIO_API_TOKEN chưa đặt — API mở cho mọi request")
    if not _has_ffmpeg():
        log.warning(
            "Không thấy ffmpeg/ffprobe — xuất M4B sẽ lỗi (ZIP mp3 vẫn chạy). "
            "Cài: sudo apt install ffmpeg | brew install ffmpeg | winget install ffmpeg"
        )
    yield


app = FastAPI(title="TTS Service API", lifespan=lifespan)
# Thêm trước CORS để CORS bọc ngoài: phản hồi 401 vẫn có header CORS.
app.middleware("http")(require_token)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", HEADER],
)
app.include_router(tts_router)


@app.get("/api/health")
@app.get("/api/tts/health")  # cùng prefix router để đi qua proxy /api/tts của nginx
def health():
    # `ffmpeg` cho UI biết có xuất M4B được không (thiếu thì tắt nút).
    return {"status": "ok", "ffmpeg": _has_ffmpeg()}
