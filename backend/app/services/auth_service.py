"""认证业务层：注册 / 登录（失败锁定）/ 双令牌刷新 / 登出 / 找回密码。

业务规则集中于此，统一抛 AuthError(status_code, biz_code, message)，
路由层按 biz_code 精确映射 HTTP 响应。
"""
import secrets
from datetime import datetime, timedelta

from fastapi import Request
from jose import jwt as jose_jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_token_strict,
    hash_password,
    verify_password,
)
from ..models import (
    LoginLog,
    PasswordResetCode,
    RefreshToken,
    Role,
    User,
    UserRole,
)

settings = get_settings()

# 登录动作枚举（login_logs.action）
ACTION_LOGIN = 1
ACTION_LOGOUT = 2
ACTION_FAILED = 3


class AuthError(Exception):
    def __init__(self, status_code: int, biz_code: str, message: str):
        self.status_code = status_code
        self.biz_code = biz_code
        self.message = message
        super().__init__(message)


# ---------------- 工具 ----------------
def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:500]


def _log_login(db: Session, user_id: int | None, username: str | None, action: int, request: Request) -> None:
    db.add(
        LoginLog(
            user_id=user_id,
            username=username,
            action=action,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    )


def _jti(token: str) -> str | None:
    try:
        payload = jose_jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALG],
            options={"verify_exp": False},
        )
        return payload.get("jti")
    except Exception:
        return None


def _ensure_default_roles(db: Session) -> None:
    for name in ("creator", "admin"):
        if db.query(Role).filter_by(name=name).first() is None:
            db.add(Role(name=name))
    db.flush()


def _is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > datetime.now()


def _issue_tokens(db: Session, user: User, remember: bool, request: Request) -> dict:
    access = create_access_token(user.id)
    refresh, expires_at, refresh_expires_in = create_refresh_token(user.id, remember)
    jti = _jti(refresh)
    if jti:
        db.add(
            RefreshToken(
                user_id=user.id,
                token_jti=jti,
                device_id=(request.headers.get("x-device-id") or "")[:128] or None,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
                expires_at=expires_at,
            )
        )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "refresh_expires_in": refresh_expires_in,
        "token_type": "bearer",
    }


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return email
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}{'*' * max(len(local) - len(head), 2)}@{domain}"


# ---------------- 注册 ----------------
def register(db: Session, body, request: Request) -> dict:
    if not body.agree_terms:
        raise AuthError(422, "TERMS_NOT_AGREED", "请先阅读并同意服务条款")
    if db.query(User).filter_by(username=body.username).first() is not None:
        raise AuthError(409, "USERNAME_TAKEN", "用户名已被注册")
    email = getattr(body, "email", None)
    if email and db.query(User).filter_by(email=email).first() is not None:
        raise AuthError(409, "EMAIL_TAKEN", "邮箱已被注册")

    _ensure_default_roles(db)
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        nickname=body.nickname or body.username,
        email=email,
    )
    db.add(user)
    db.flush()
    role = db.query(Role).filter_by(name="creator").first()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    try:
        db.commit()
    except IntegrityError:
        # 并发注册同名用户名/邮箱：唯一约束兜底，转成明确的 409
        db.rollback()
        if db.query(User).filter_by(username=body.username).first() is not None:
            raise AuthError(409, "USERNAME_TAKEN", "用户名已被注册")
        if email and db.query(User).filter_by(email=email).first() is not None:
            raise AuthError(409, "EMAIL_TAKEN", "邮箱已被注册")
        raise AuthError(409, "USERNAME_TAKEN", "用户名已被注册")
    db.refresh(user)
    # 预置默认风格预设（失败不影响注册）
    try:
        from ..services.style_seed import ensure_default_styles

        ensure_default_styles(db, user.id)
    except Exception:  # noqa: BLE001
        db.rollback()
    return {"user_id": user.id, "username": user.username, "created_at": user.created_at.isoformat(timespec="seconds")}


# ---------------- 登录 ----------------
def login(db: Session, body, request: Request) -> dict:
    user = db.query(User).filter_by(username=body.username).first()

    # 防账号枚举：用户不存在与密码错误返回同一提示
    if user is None:
        _log_login(db, None, body.username, ACTION_FAILED, request)
        db.commit()
        raise AuthError(401, "BAD_CREDENTIALS", "用户名或密码错误")

    if _is_locked(user):
        raise AuthError(423, "ACCOUNT_LOCKED", "账号已锁定，请 30 分钟后再试")

    if not verify_password(body.password, user.password_hash):
        user.fail_count = (user.fail_count or 0) + 1
        remaining = settings.LOGIN_MAX_FAILS - user.fail_count
        if remaining <= 0:
            user.locked_until = datetime.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            user.fail_count = 0
            _log_login(db, user.id, user.username, ACTION_FAILED, request)
            db.commit()
            raise AuthError(423, "ACCOUNT_LOCKED", "连续失败次数过多，账号已锁定 30 分钟")
        _log_login(db, user.id, user.username, ACTION_FAILED, request)
        db.commit()
        raise AuthError(
            401,
            "BAD_CREDENTIALS",
            f"用户名或密码错误，剩余 {remaining} 次尝试机会",
        )

    if not user.is_active:
        raise AuthError(403, "ACCOUNT_DISABLED", "账号已被禁用")

    user.fail_count = 0
    user.locked_until = None
    tokens = _issue_tokens(db, user, body.remember, request)
    _log_login(db, user.id, user.username, ACTION_LOGIN, request)
    db.commit()
    from ..schemas import user_out

    return {**tokens, "user": user_out(user)}


# ---------------- 刷新 ----------------
def refresh(db: Session, refresh_token: str, request: Request) -> dict:
    user_id, err = decode_token_strict(refresh_token, "refresh")
    if err == "expired":
        raise AuthError(401, "REFRESH_EXPIRED", "登录已过期，请重新登录")
    if err or user_id is None:
        raise AuthError(401, "REFRESH_INVALID", "刷新令牌无效")

    jti = _jti(refresh_token)
    record = db.query(RefreshToken).filter_by(token_jti=jti).first() if jti else None
    if record is None or record.revoked:
        raise AuthError(401, "REFRESH_REVOKED", "登录状态已失效，请重新登录")
    if record.expires_at <= datetime.now():
        raise AuthError(401, "REFRESH_EXPIRED", "登录已过期，请重新登录")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError(401, "USER_INVALID", "用户不存在或已被禁用")

    # 轮换：旧 refresh 作废，签发新对（记住我策略按原有效期剩余时长继承）
    record.revoked = True
    remember = (record.expires_at - datetime.now()) > timedelta(days=1)
    tokens = _issue_tokens(db, user, remember=remember, request=request)
    db.commit()
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_in": tokens["expires_in"],
        "refresh_expires_in": tokens["refresh_expires_in"],
    }


# ---------------- 登出 ----------------
def logout(db: Session, user: User | None, refresh_token: str | None) -> dict:
    revoked = False
    if refresh_token:
        jti = _jti(refresh_token)
        record = db.query(RefreshToken).filter_by(token_jti=jti).first() if jti else None
        if record and not record.revoked:
            record.revoked = True
            revoked = True
    if user is not None:
        db.add(LoginLog(user_id=user.id, username=user.username, action=ACTION_LOGOUT))
    db.commit()
    return {"revoked": revoked}


# ---------------- 找回密码 ----------------
def verify_user(db: Session, username: str) -> dict:
    """Step1：校验用户是否存在。存在则返回脱敏联系方式。"""
    user = db.query(User).filter_by(username=username).first()
    if user is None:
        return {"exists": False, "channel": None, "masked_contact": None}
    if user.email:
        return {"exists": True, "channel": "email", "masked_contact": _mask_email(user.email)}
    # 无邮箱的历史账号：走站内回显（开发模式），仍视为可找回
    return {"exists": True, "channel": "none", "masked_contact": None}


def send_code(db: Session, username: str) -> dict:
    """Step2：下发验证码（重发冷却 + TTL）。"""
    user = db.query(User).filter_by(username=username).first()
    if user is None:
        raise AuthError(404, "USER_NOT_FOUND", "用户不存在")

    now = datetime.now()
    latest = (
        db.query(PasswordResetCode)
        .filter_by(user_id=user.id)
        .order_by(PasswordResetCode.id.desc())
        .first()
    )
    if latest and (now - latest.created_at).total_seconds() < settings.RESET_CODE_RESEND_SECONDS:
        wait = int(settings.RESET_CODE_RESEND_SECONDS - (now - latest.created_at).total_seconds())
        raise AuthError(429, "RESEND_TOO_FAST", f"发送过于频繁，请 {wait} 秒后重试")

    code = f"{secrets.randbelow(1000000):06d}"
    channel = "email" if user.email else "none"
    db.add(
        PasswordResetCode(
            user_id=user.id,
            code=code,
            channel=channel,
            expires_at=now + timedelta(minutes=settings.RESET_CODE_TTL_MINUTES),
        )
    )
    db.commit()
    # 安全：验证码绝不能随 HTTP 响应回显（否则任何人可凭用户名重置任意账号）。
    # 无邮箱的历史账号（channel=none）无其他通道，保留站内回显走通流程；
    # 邮箱通道仅输出到服务端日志，待接入邮件发送后移除该 print。
    if channel == "none":
        code_hint = code
    else:
        code_hint = None
        print(f"[auth] 找回密码验证码 username={user.username} code={code}")
    return {
        "sent": True,
        "channel": channel,
        "expires_in": settings.RESET_CODE_TTL_MINUTES * 60,
        "resend_interval": settings.RESET_CODE_RESEND_SECONDS,
        "code_hint": code_hint,
    }


def _find_active_code(db: Session, username: str) -> tuple[User | None, PasswordResetCode | None]:
    user = db.query(User).filter_by(username=username).first()
    if user is None:
        return None, None
    now = datetime.now()
    record = (
        db.query(PasswordResetCode)
        .filter_by(user_id=user.id, used=False)
        .order_by(PasswordResetCode.id.desc())
        .first()
    )
    if record is None or record.expires_at <= now:
        return user, None
    return user, record


def verify_code(db: Session, username: str, code: str) -> dict:
    user, record = _find_active_code(db, username)
    if user is None:
        raise AuthError(404, "USER_NOT_FOUND", "用户不存在")
    if record is None:
        raise AuthError(410, "CODE_EXPIRED", "验证码已过期，请重新获取")
    if record.attempts >= settings.RESET_CODE_MAX_ATTEMPTS:
        record.used = True
        db.commit()
        raise AuthError(400, "CODE_ATTEMPTS_EXCEEDED", "验证码错误次数过多，请重新获取")
    if record.code != code:
        record.attempts += 1
        db.commit()
        raise AuthError(400, "CODE_INVALID", "验证码错误")
    return {"valid": True}


def reset_password(db: Session, username: str, code: str, new_password: str) -> dict:
    user, record = _find_active_code(db, username)
    if user is None:
        raise AuthError(404, "USER_NOT_FOUND", "用户不存在")
    if record is None:
        raise AuthError(410, "CODE_EXPIRED", "验证码已过期，请重新获取")
    # 与 verify_code 同样的次数上限：防止绕过 verify-code 步骤对 reset 接口暴力枚举
    if record.attempts >= settings.RESET_CODE_MAX_ATTEMPTS:
        record.used = True
        db.commit()
        raise AuthError(400, "CODE_ATTEMPTS_EXCEEDED", "验证码错误次数过多，请重新获取")
    if record.code != code:
        record.attempts += 1
        db.commit()
        raise AuthError(400, "CODE_INVALID", "验证码错误")
    if verify_password(new_password, user.password_hash):
        raise AuthError(400, "PASSWORD_REUSED", "新密码不能与原密码相同")

    user.password_hash = hash_password(new_password)
    user.fail_count = 0
    user.locked_until = None
    record.used = True
    # 使全部旧 refresh 令牌失效（异地重置场景强制下线）
    db.query(RefreshToken).filter_by(user_id=user.id, revoked=False).update({RefreshToken.revoked: True})
    db.commit()
    return {"username": user.username}
