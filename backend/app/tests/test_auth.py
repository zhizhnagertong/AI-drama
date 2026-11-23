"""登录注册流程单测（SQLite 内存库 + dependency_overrides）。

覆盖规范要点：字段校验、重名 409、条款勾选、登录双令牌、失败锁定 423、
防枚举、refresh 轮换、登出撤销、找回密码三步与旧令牌失效。
"""
import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.router import api_router
from app.core.db import Base, get_db
from app.core.deps import get_current_user, get_optional_current_user
from app.services.auth_service import AuthError

GOOD_PWD = "Abcd1234"


def _build_app() -> FastAPI:
    """与 main.py 保持一致的异常映射（AuthError / 422 field_errors）。"""
    app = FastAPI()
    app.include_router(api_router)

    @app.exception_handler(AuthError)
    async def _auth_err(_: Request, exc: AuthError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "biz_code": exc.biz_code, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_err(_: Request, exc: RequestValidationError):
        field_errors: dict[str, str] = {}
        messages = []
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

    return app


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    app = _build_app()
    app.dependency_overrides[get_db] = lambda: db_session
    # 受保护接口默认按“未登录”处理，需要登录的用例自行 override
    app.dependency_overrides[get_optional_current_user] = lambda: None
    with TestClient(app) as c:
        yield c


API = "/api/v1/auth"


def _register(client, username="alice01", **over):
    body = {"username": username, "password": GOOD_PWD, "confirm_password": GOOD_PWD, "agree_terms": True}
    body.update(over)
    return client.post(f"{API}/register", json=body)


# ---------------- 注册 ----------------
def test_register_ok(client):
    r = _register(client)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["username"] == "alice01"
    assert "user_id" in data and "created_at" in data


def test_register_duplicate_username_409(client):
    assert _register(client).status_code == 201
    r = _register(client)
    assert r.status_code == 409
    assert r.json()["biz_code"] == "USERNAME_TAKEN"


def test_register_weak_password_422(client):
    r = _register(client, password="alllowercase1", confirm_password="alllowercase1")
    assert r.status_code == 422
    assert "password" in r.json()["field_errors"]


def test_register_confirm_mismatch_422(client):
    r = _register(client, confirm_password="Abcd9999")
    assert r.status_code == 422


def test_register_terms_required_422(client):
    r = _register(client, agree_terms=False)
    assert r.status_code == 422
    assert r.json()["biz_code"] == "TERMS_NOT_AGREED"


def test_register_invalid_username_charset_422(client):
    r = _register(client, username="ab_c!")
    assert r.status_code == 422


# ---------------- 登录 ----------------
def _login(client, username="alice01", password=GOOD_PWD, **over):
    body = {"username": username, "password": password}
    body.update(over)
    return client.post(f"{API}/login", json=body)


def _latest_reset_code(db_session, username="alice01"):
    """从库里取最新一条未使用的重置验证码。

    安全加固后（见 auth_service.send_code）：有邮箱的账号不再在响应里回显验证码
    （code_hint 为 None，仅打服务端日志），只有 channel=none 的历史账号才回显。
    因此走邮箱通道的用例必须直接从库中取证，不能再依赖 code_hint。
    """
    from app.models import PasswordResetCode, User

    user = db_session.query(User).filter_by(username=username).first()
    assert user is not None, f"用户 {username} 不存在"
    row = (
        db_session.query(PasswordResetCode)
        .filter_by(user_id=user.id, used=False)
        .order_by(PasswordResetCode.id.desc())
        .first()
    )
    assert row is not None, "没有下发的验证码记录"
    return row.code


def test_login_returns_dual_tokens(client):
    _register(client)
    r = _login(client)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["access_token"] and data["refresh_token"]
    assert data["expires_in"] == 900
    assert data["refresh_expires_in"] == 12 * 3600
    assert data["user"]["username"] == "alice01"


def test_login_remember_me_7days(client):
    _register(client)
    data = _login(client, remember=True).json()
    assert data["refresh_expires_in"] == 7 * 24 * 3600


def test_login_bad_credentials_401(client):
    _register(client)
    r = _login(client, password="Wrong12345")
    assert r.status_code == 401
    assert r.json()["biz_code"] == "BAD_CREDENTIALS"


def test_login_user_not_found_same_message(client):
    """防账号枚举：不存在的用户与密码错误返回同一 biz_code。"""
    r1 = _login(client, username="nobody99")
    _register(client)
    r2 = _login(client, password="Wrong12345")
    assert r1.json()["biz_code"] == r2.json()["biz_code"] == "BAD_CREDENTIALS"


def test_login_invalid_username_format_422(client):
    r = _login(client, username="a b")
    assert r.status_code == 422


def test_login_lock_after_5_fails(client):
    _register(client)
    for _ in range(4):
        assert _login(client, password="Wrong12345").status_code == 401
    r = _login(client, password="Wrong12345")
    assert r.status_code == 423
    assert r.json()["biz_code"] == "ACCOUNT_LOCKED"
    # 锁定期间正确密码也被拒
    r2 = _login(client)
    assert r2.status_code == 423


# ---------------- 刷新 / 登出 ----------------
def test_me_requires_auth(client):
    assert client.get(f"{API}/me").status_code == 401


def test_me_with_access_token(client, db_session):
    from app.models import User

    _register(client)
    token = _login(client).json()["access_token"]
    user = db_session.query(User).filter_by(username="alice01").first()
    r = client.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["id"] == user.id


def test_refresh_rotates(client):
    _register(client)
    data = _login(client).json()
    r = client.post(f"{API}/refresh", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["access_token"]
    assert new["refresh_token"] != data["refresh_token"]
    # 旧 refresh 已轮换作废
    r2 = client.post(f"{API}/refresh", json={"refresh_token": data["refresh_token"]})
    assert r2.status_code == 401


def test_refresh_invalid_token(client):
    r = client.post(f"{API}/refresh", json={"refresh_token": "not-a-jwt-token"})
    assert r.status_code == 401


def test_logout_revokes_refresh(client):
    _register(client)
    data = _login(client).json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    r = client.post(f"{API}/logout", json={"refresh_token": data["refresh_token"]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["revoked"] is True
    r2 = client.post(f"{API}/refresh", json={"refresh_token": data["refresh_token"]})
    assert r2.status_code == 401


# ---------------- 找回密码 ----------------
def test_forget_password_flow(client, db_session):
    _register(client, email="alice@example.com")
    # Step1 校验用户
    r = client.post(f"{API}/verify-user", json={"username": "alice01"})
    assert r.status_code == 200
    assert r.json()["exists"] is True
    assert r.json()["channel"] == "email"
    assert "*" in r.json()["masked_contact"]
    # 不存在的用户
    r = client.post(f"{API}/verify-user", json={"username": "ghost99"})
    assert r.json()["exists"] is False
    # Step2 下发验证码
    r = client.post(f"{API}/password/send-code", json={"username": "alice01"})
    assert r.status_code == 200
    # 安全：邮箱通道回显的 code_hint 必须为 null，验证码只进服务端日志
    assert r.json()["code_hint"] is None
    code = _latest_reset_code(db_session)
    # 重发冷却 429
    r = client.post(f"{API}/password/send-code", json={"username": "alice01"})
    assert r.status_code == 429
    # Step3 校验验证码（错误码）
    r = client.post(f"{API}/password/verify-code", json={"username": "alice01", "code": "000000"})
    assert r.status_code == 400
    r = client.post(f"{API}/password/verify-code", json={"username": "alice01", "code": code})
    assert r.json()["valid"] is True
    # 密码复用被拒
    r = client.post(
        f"{API}/password/reset",
        json={"username": "alice01", "code": code, "new_password": GOOD_PWD, "confirm_password": GOOD_PWD},
    )
    assert r.status_code == 400
    assert r.json()["biz_code"] == "PASSWORD_REUSED"
    # 正常重置
    new_pwd = "NewPwd1234"
    r = client.post(
        f"{API}/password/reset",
        json={"username": "alice01", "code": code, "new_password": new_pwd, "confirm_password": new_pwd},
    )
    assert r.status_code == 200
    # 旧 refresh 全部失效
    # （重新登录拿旧 token 场景：先登录拿 token，再重置，再刷新）


def test_reset_password_invalidates_old_tokens(client, db_session):
    _register(client, email="a@b.com")
    tokens = _login(client).json()
    r = client.post(f"{API}/password/send-code", json={"username": "alice01"})
    assert r.status_code == 200
    code = _latest_reset_code(db_session)
    new_pwd = "NewPwd1234"
    r = client.post(
        f"{API}/password/reset",
        json={"username": "alice01", "code": code, "new_password": new_pwd, "confirm_password": new_pwd},
    )
    assert r.status_code == 200
    r2 = client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401
    # 新密码可登录
    assert _login(client, password=new_pwd).status_code == 200


def test_reset_code_expired_410(client, db_session):
    from datetime import datetime, timedelta

    from app.models import PasswordResetCode

    _register(client, email="a@b.com")
    client.post(f"{API}/password/send-code", json={"username": "alice01"})
    # 手动把验证码置为过期
    db_session.query(PasswordResetCode).update({"expires_at": datetime.now() - timedelta(minutes=1)})
    db_session.commit()
    r = client.post(f"{API}/password/verify-code", json={"username": "alice01", "code": "123456"})
    assert r.status_code == 410
    assert r.json()["biz_code"] == "CODE_EXPIRED"


# ---------------- 令牌时效（回归：UTC/本地朴素时间混用曾致有效期缩短 8 小时） ----------------
def test_refresh_expiry_uses_local_naive_time():
    """create_refresh_token 返回的过期时间必须与 datetime.now() 同一时间基准。

    auth_service 用 `datetime.now()`（本地朴素）比较 expires_at；若签发端返回
    UTC aware 时间，东八区下会话级 refresh 实际只剩 4 小时，导致"用着用着就失效"。
    """
    from datetime import datetime

    from app.core.security import create_refresh_token

    for remember, hours in ((False, 12), (True, 24 * 7)):
        _, expires_at, seconds = create_refresh_token(1, remember)
        assert seconds == hours * 3600
        assert expires_at.tzinfo is None, "expires_at 必须是朴素本地时间，与 datetime.now() 同基准"
        delta = (expires_at - datetime.now()).total_seconds()
        # 允许 1 秒误差
        assert abs(delta - hours * 3600) < 1, f"remember={remember} 实际有效期 {delta/3600:.2f}h，应为 {hours}h"


def test_refresh_not_immediately_expired(client):
    """新签发的 refresh 立即刷新必须成功（回归：过期判定基准错配会误判过期）。"""
    _register(client)
    data = _login(client).json()
    r = client.post(f"{API}/refresh", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 200, r.text


# ---------------- 修改密码（已登录） ----------------
def test_change_password(client, db_session):
    from app.models import User

    _register(client)
    user = db_session.query(User).filter_by(username="alice01").first()
    app = _build_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as c:
        r = c.put(
            f"{API}/me/password",
            json={"old_password": "WrongPass1", "new_password": "NewPwd1234"},
        )
        assert r.status_code == 400
        r = c.put(
            f"{API}/me/password",
            json={"old_password": GOOD_PWD, "new_password": "NewPwd1234"},
        )
        assert r.status_code == 200


# ---------------- 回归：安全问题（代码审查发现） ----------------
def test_send_code_never_echoes_code_without_email(client):
    """send-code 是未鉴权接口：无 email 的历史账号也不得回显验证码。

    回归点：曾经 channel=="none" 时把验证码明文放进响应 code_hint，
    任何人凭用户名即可重置任意无邮箱账号（完整账号接管）。
    """
    _register(client)  # 不传 email → channel == "none"
    r = client.post(f"{API}/password/send-code", json={"username": "alice01"})
    assert r.status_code == 200
    body = r.json()
    assert body["channel"] == "none"
    assert body["code_hint"] is None


def test_change_password_revokes_refresh_tokens(client, db_session):
    """改密后必须吊销全部旧 refresh 令牌，否则被窃取的会话可无限续期。"""
    from app.models import User

    _register(client)
    tokens = _login(client).json()
    user = db_session.query(User).filter_by(username="alice01").first()
    app = _build_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as c:
        r = c.put(
            f"{API}/me/password",
            json={"old_password": GOOD_PWD, "new_password": "NewPwd1234"},
        )
        assert r.status_code == 200
    # 旧 refresh 已被吊销
    r2 = client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401
    # 新密码可正常登录
    assert _login(client, password="NewPwd1234").status_code == 200
