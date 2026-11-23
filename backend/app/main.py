"""AI 漫剧智能制作平台 - FastAPI 后端入口。"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.router import api_router
from .core.config import get_settings
from .core.db import init_db
from .services import event_bus, storage, task_engine
from .services.auth_service import AuthError

logger = logging.getLogger(__name__)

settings = get_settings()
storage.ensure_dirs()  # /static 挂载前确保目录存在

# 弱密钥自检：JWT_SECRET 仍是模板默认值（或过短）时任何人可伪造令牌
_WEAK_SECRETS = {"change-me", "please_change_me_to_a_random_string", ""}
if settings.JWT_SECRET in _WEAK_SECRETS or len(settings.JWT_SECRET) < 32:
    logger.warning(
        "JWT_SECRET 使用默认值或长度不足（%d 字符），任何拿到源码的人都能伪造登录令牌，"
        "请在 backend/.env 中替换为随机串：python -c \"import secrets;print(secrets.token_urlsafe(48))\"",
        len(settings.JWT_SECRET),
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 启动：自动建库建表 + 启动任务 worker 池
    init_db()
    event_bus.set_loop(asyncio.get_running_loop())
    await task_engine.start_workers(4)
    yield
    # 关停：优雅结束 worker
    await task_engine.stop_workers()


app = FastAPI(title="AI 漫剧智能制作平台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # 鉴权走 Authorization 头而非 Cookie，因此不能开启 credentials：
    # 按 Fetch 规范 allow_origins=["*"] 与 allow_credentials=True 是非法组合，浏览器会直接拒绝。
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(settings.storage_path)), name="static")
app.include_router(api_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------- 统一错误响应 {code, message} ----------------
@app.exception_handler(AuthError)
async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "biz_code": exc.biz_code, "message": exc.message},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "message" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    messages = []
    field_errors: dict[str, str] = {}
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", [])[1:])
        msg = str(err.get("msg"))
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        messages.append(f"{loc}: {msg}" if loc else msg)
        if loc and loc not in field_errors:
            field_errors[loc] = msg
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "biz_code": "VALIDATION_ERROR",
            "message": "; ".join(messages) or "请求参数校验失败",
            "field_errors": field_errors,
        },
    )
