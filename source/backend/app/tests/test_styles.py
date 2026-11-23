"""风格预设 CRUD 接口单测（SQLite 内存库 + dependency_overrides）。"""
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.router import api_router
from app.core.db import Base, get_db
from app.core.deps import get_current_user
from app.models import StylePreset, User


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
def alice(db_session):
    user = User(username="alice", password_hash="x", nickname="Alice")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def bob(db_session):
    user = User(username="bob", password_hash="x", nickname="Bob")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def client(db_session, alice):
    """已登录（override get_current_user → alice）的测试客户端。"""
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: alice
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def anon_client(db_session):
    """未登录（不 override get_current_user）的测试客户端。"""
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c


def _payload(**over):
    data = {"name": "复古胶片", "prompt": "vintage film grain, warm tones"}
    data.update(over)
    return data


def test_list_lazy_seed(client, alice, db_session):
    r = client.get("/api/v1/styles")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 6
    names = [i["name"] for i in body["items"]]
    assert names == ["赛博朋克", "水墨国风", "日系动漫", "美式漫画", "3D卡通", "写实"]
    # 按 sort_order 升序
    orders = [i["sort_order"] for i in body["items"]]
    assert orders == sorted(orders)
    # seed 幂等：再次访问不重复插入
    client.get("/api/v1/styles")
    assert db_session.query(StylePreset).filter_by(user_id=alice.id).count() == 6


def test_create_and_get(client, db_session, alice):
    r = client.post("/api/v1/styles", json=_payload(description="颗粒感", color="#A0522D"))
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["name"] == "复古胶片"
    assert created["user_id"] == alice.id
    assert created["is_active"] is True
    assert created["created_at"] and created["updated_at"]
    r2 = client.get(f"/api/v1/styles/{created['id']}")
    assert r2.status_code == 200
    assert r2.json()["prompt"] == "vintage film grain, warm tones"


def test_create_duplicate_name_400(client):
    assert client.post("/api/v1/styles", json=_payload()).status_code == 200
    r = client.post("/api/v1/styles", json=_payload(prompt="other"))
    assert r.status_code == 400
    assert r.json()["detail"] == "风格名称已存在"


def test_update(client):
    pid = client.post("/api/v1/styles", json=_payload()).json()["id"]
    r = client.put(f"/api/v1/styles/{pid}", json={"name": "新名字", "sort_order": 9})
    assert r.status_code == 200
    assert r.json()["name"] == "新名字"
    assert r.json()["sort_order"] == 9
    # 未提供字段保持不变
    assert r.json()["prompt"] == "vintage film grain, warm tones"
    # 改名撞已有名称 → 400
    other = client.post("/api/v1/styles", json=_payload(name="另一个")).json()["id"]
    r2 = client.put(f"/api/v1/styles/{other}", json={"name": "新名字"})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "风格名称已存在"


def test_toggle(client):
    pid = client.post("/api/v1/styles", json=_payload()).json()["id"]
    r = client.patch(f"/api/v1/styles/{pid}/toggle")
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    # 默认列表不含停用项，include_inactive 包含
    ids_default = [i["id"] for i in client.get("/api/v1/styles").json()["items"]]
    assert pid not in ids_default
    ids_all = [i["id"] for i in client.get("/api/v1/styles", params={"include_inactive": True}).json()["items"]]
    assert pid in ids_all
    r2 = client.patch(f"/api/v1/styles/{pid}/toggle")
    assert r2.json()["is_active"] is True


def test_delete(client, db_session, alice):
    pid = client.post("/api/v1/styles", json=_payload()).json()["id"]
    r = client.delete(f"/api/v1/styles/{pid}")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "message": "风格已删除"}
    assert db_session.get(StylePreset, pid) is None
    assert client.get(f"/api/v1/styles/{pid}").status_code == 404


def test_cross_user_404(client, db_session, bob):
    pid = client.post("/api/v1/styles", json=_payload()).json()["id"]
    # 以 bob 身份访问 alice 的预设 → 404
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: bob
    with TestClient(app) as c:
        assert c.get(f"/api/v1/styles/{pid}").status_code == 404
        assert c.put(f"/api/v1/styles/{pid}", json={"name": "劫持"}).status_code == 404
        assert c.patch(f"/api/v1/styles/{pid}/toggle").status_code == 404
        assert c.delete(f"/api/v1/styles/{pid}").status_code == 404
        # bob 自己的列表互不可见
        assert all(i["user_id"] == bob.id for i in c.get("/api/v1/styles").json()["items"])


def test_unauthorized_401(anon_client):
    r = anon_client.get("/api/v1/styles")
    assert r.status_code == 401
    assert anon_client.post("/api/v1/styles", json=_payload()).status_code == 401


def test_seed_only_when_no_presets(client, db_session, alice):
    # 懒 seed 后用户已有预设，手动清空再建自定义项，不再触发 seed
    db_session.query(StylePreset).filter_by(user_id=alice.id).delete()
    db_session.commit()
    client.post("/api/v1/styles", json=_payload(name="自定义"))
    body = client.get("/api/v1/styles", params={"include_inactive": True}).json()
    assert [i["name"] for i in body["items"]] == ["自定义"]
