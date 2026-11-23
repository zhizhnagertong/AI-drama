"""认证接口：注册 / 登录 / 刷新 / 登出 / 当前用户 / 找回密码 / 资料修改。

业务规则统一在 services/auth_service.py，本层只做 HTTP 映射；
AuthError 由 main.py 全局异常处理器转成 {code, biz_code, message} 响应。
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, get_optional_current_user
from ..core.db import get_db
from ..core.ratelimit import SlidingWindowLimiter
from ..core.security import hash_password, verify_password
from ..models import User
from ..schemas import (
    LoginRequest,
    LogoutRequest,
    PasswordChange,
    ProfileUpdate,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SendCodeRequest,
    VerifyCodeRequest,
    VerifyUserRequest,
    user_out,
)
from ..services import auth_service

router = APIRouter()

# 未鉴权认证接口的防刷限流（内存版，单实例；多实例部署需换 Redis）
_limiter = SlidingWindowLimiter()


def _client_ip(request: Request) -> str:
    """优先取反代传递的真实 IP，避免所有请求都算在网关地址上。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _guard(request: Request, scope: str, identity: str, limit: int, window: int = 60) -> None:
    """超限直接 429，带 retry_after 提示。"""
    key = f"{scope}:{identity}"
    if not _limiter.allow(key, limit, window):
        wait = _limiter.retry_after(key, window)
        raise auth_service.AuthError(
            429, "RATE_LIMITED", f"操作过于频繁，请 {wait} 秒后重试"
        )


@router.post("/register", status_code=201)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    _guard(request, "register", _client_ip(request), limit=10, window=60)
    return auth_service.register(db, body, request)


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    # 账号锁定之外再加一层 IP 限流，抑制撞库与用户名枚举
    _guard(request, "login", _client_ip(request), limit=20, window=60)
    return auth_service.login(db, body, request)


@router.post("/refresh")
def refresh(body: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    return auth_service.refresh(db, body.refresh_token, request)


@router.post("/logout")
def logout(
    body: LogoutRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
) -> dict:
    return auth_service.logout(db, user, body.refresh_token)


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return user_out(user)


@router.put("/me")
def update_me(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if body.nickname is not None:
        user.nickname = body.nickname.strip()
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.put("/me/password")
def change_password(
    body: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(body.old_password, user.password_hash):
        raise auth_service.AuthError(400, "OLD_PASSWORD_WRONG", "原密码错误")
    user.password_hash = hash_password(body.new_password)
    # 改密后吊销全部旧 refresh 令牌，避免已被窃取的会话继续续期
    auth_service.revoke_all_refresh_tokens(db, user.id)
    db.commit()
    return {"ok": True, "message": "密码已更新，请重新登录"}


# ---------------- 找回密码（三步） ----------------
@router.post("/verify-user")
def verify_user(
    body: VerifyUserRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    # 该接口会暴露用户名是否存在，必须限流，否则可批量枚举
    _guard(request, "verify-user-ip", _client_ip(request), limit=10, window=60)
    _guard(request, "verify-user-name", body.username, limit=5, window=60)
    return auth_service.verify_user(db, body.username)


@router.post("/password/send-code")
def send_code(
    body: SendCodeRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    _guard(request, "send-code-ip", _client_ip(request), limit=5, window=60)
    _guard(request, "send-code-name", body.username, limit=3, window=60)
    return auth_service.send_code(db, body.username)


@router.post("/password/verify-code")
def verify_code(
    body: VerifyCodeRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    _guard(request, "verify-code-ip", _client_ip(request), limit=15, window=60)
    _guard(request, "verify-code-name", body.username, limit=10, window=60)
    return auth_service.verify_code(db, body.username, body.code)


@router.post("/password/reset")
def reset_password(
    body: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    _guard(request, "reset-ip", _client_ip(request), limit=10, window=60)
    return auth_service.reset_password(db, body.username, body.code, body.new_password)
