"""密码哈希与 JWT 签发/校验（双令牌）。"""
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings

settings = get_settings()

# 使用 pbkdf2_sha256：避开 bcrypt 72 字节限制与 passlib/bcrypt 版本兼容坑
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# 注册用户名：3-20 位字母/数字
REGISTER_USERNAME_RE = re.compile(r"^[A-Za-z0-9]{3,20}$")
# 登录用户名：3-20 位，允许中文/下划线（兼容历史账号，与前端一致）
LOGIN_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5]{3,20}$")
# 密码：8-20 位，含大写 + 小写 + 数字，不含空格
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)\S{8,20}$")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "jti": uuid4().hex,
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def create_refresh_token(user_id: int, remember: bool = False) -> tuple[str, datetime, int]:
    """签发 refresh 令牌。

    返回 (token, 绝对过期时间, 有效期秒数)。勾选「记住我」7 天，否则会话级 12 小时。

    过期时间用**本地朴素时间**返回：全库时间戳约定为 `datetime.now()`（本地朴素），
    JWT 的 exp 声明另按 UTC 编码，二者不可混用，否则东八区下有效期会凭空缩短 8 小时。
    """
    if remember:
        delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_REMEMBER_DAYS)
    else:
        delta = timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_SESSION_HOURS)
    expire_utc = datetime.now(timezone.utc) + delta
    payload = {
        "sub": str(user_id),
        "typ": "refresh",
        "jti": uuid4().hex,
        "iat": datetime.now(timezone.utc),
        "exp": expire_utc,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return token, datetime.now() + delta, int(delta.total_seconds())


def decode_token(token: str) -> int | None:
    """解析 access JWT，返回 user_id；无效/过期返回 None（兼容旧调用方）。"""
    user_id, _ = decode_token_strict(token, "access")
    return user_id


def decode_token_strict(token: str, typ: str) -> tuple[int | None, str | None]:
    """严格解析 JWT 并校验类型声明。

    返回 (user_id, error)，error ∈ {None, "expired", "invalid"}。
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except JWTError as exc:
        name = exc.__class__.__name__
        if name in ("ExpiredSignatureError", "ExpiredSignature"):
            return None, "expired"
        return None, "invalid"
    if payload.get("typ") != typ:
        return None, "invalid"
    sub = payload.get("sub")
    if sub is None:
        return None, "invalid"
    try:
        return int(sub), None
    except (TypeError, ValueError):
        return None, "invalid"
