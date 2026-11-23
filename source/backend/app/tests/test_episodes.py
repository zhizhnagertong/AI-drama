"""剧集（项目→集→分镜）模块测试：内存 SQLite 驱动，覆盖模型/回填/CRUD/按集生成/按集时间线。"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.core.db import Base, _backfill_episodes
from app.api import routes_episodes, routes_projects, routes_storyboards, routes_timelines
from app.api.routes_projects import get_owned_project
from app.api.routes_episodes import get_owned_episode
from app.services import task_engine


# ---------------- 测试夹具 ----------------
@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(
        engine,
        tables=[
            models.User.__table__,
            models.Project.__table__,
            models.Episode.__table__,
            models.Character.__table__,
            models.Storyboard.__table__,
            models.Shot.__table__,
            models.ShotVersion.__table__,
            models.Asset.__table__,
            models.GenTask.__table__,
            models.AgentRun.__table__,
            models.Prompt.__table__,
            models.Timeline.__table__,
            models.StylePreset.__table__,
        ],
    )
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def user(db):
    u = models.User(username="tester", password_hash="x")
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def project(db, user):
    p = models.Project(user_id=user.id, title="测试项目", style="赛博朋克", aspect_ratio="9:16")
    db.add(p)
    db.flush()
    db.add(models.Prompt(project_id=p.id, type="negative", content="no text"))
    db.commit()
    return p


def make_storyboard(db, project, episode_id, seq, video=False):
    sb = models.Storyboard(
        project_id=project.id, episode_id=episode_id, seq=seq,
        scene=f"场景{seq}", status=models.StoryboardStatus.ready,
    )
    db.add(sb)
    db.flush()
    shot = models.Shot(storyboard_id=sb.id, status=models.ShotStatus.pending)
    db.add(shot)
    db.flush()
    v = models.ShotVersion(
        shot_id=shot.id, version_no=1, image_url="/static/images/x.png",
        video_url="/static/videos/x.mp4" if video else None,
        status=models.ShotVersionStatus.succeeded, is_selected=True,
    )
    db.add(v)
    db.flush()
    shot.selected_version_id = v.id
    if video:
        shot.status = models.ShotStatus.ready
        shot.video_url = v.video_url
    return sb


# ---------------- 1. 模型与迁移 ----------------
def test_model_fields(db, project):
    ep = models.Episode(
        project_id=project.id, episode_number=1, title="第1集",
        style=project.style, aspect_ratio=project.aspect_ratio,
    )
    db.add(ep)
    db.commit()
    assert ep.id is not None
    assert ep.status == models.EpisodeStatus.draft
    assert ep.deleted is False
    sb = models.Storyboard(project_id=project.id, episode_id=ep.id, seq=1)
    db.add(sb)
    db.commit()
    assert sb.episode_id == ep.id


def test_backfill_episodes_real_function(db, user):
    """直接调用真实 _backfill_episodes：为无集项目建第 1 集并归入存量分镜/时间线。"""
    p = models.Project(
        user_id=user.id, title="legacy", status=models.ProjectStatus.producing,
        style="赛博朋克", aspect_ratio="9:16", voice_config={"voice": "longwan"},
    )
    db.add(p)
    db.flush()
    old_sb = models.Storyboard(project_id=p.id, seq=1, scene="旧分镜")
    old_tl = models.Timeline(project_id=p.id, items=[])
    db.add_all([old_sb, old_tl])
    db.commit()

    conn = db.connection()
    _backfill_episodes(conn)
    db.commit()

    eps = db.query(models.Episode).filter(models.Episode.project_id == p.id).all()
    assert len(eps) == 1
    assert eps[0].episode_number == 1 and eps[0].title == "第1集"
    assert eps[0].status == models.EpisodeStatus.producing  # 继承项目状态
    assert eps[0].style == "赛博朋克" and eps[0].aspect_ratio == "9:16"
    assert eps[0].voice_config == {"voice": "longwan"}
    db.refresh(old_sb)
    db.refresh(old_tl)
    assert old_sb.episode_id == eps[0].id
    assert old_tl.episode_id == eps[0].id

    # 幂等：再跑一次不产生第二个集
    _backfill_episodes(db.connection())
    db.commit()
    assert db.query(models.Episode).filter(models.Episode.project_id == p.id).count() == 1


# ---------------- 2. Episode CRUD ----------------
def test_list_empty(db, user, project):
    r = routes_episodes.list_episodes(project.id, user=user, db=db)
    assert r["items"] == [] and r["total"] == 0


def test_create_episode_number_and_snapshot(db, user, project):
    ep1 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    assert ep1["episode_number"] == 1
    assert ep1["title"] == "第1集"
    # 配置快照继承项目
    assert ep1["style"] == project.style and ep1["aspect_ratio"] == "9:16"
    body = schemas_body("第2集", synopsis="梗概", inspiration="点子")
    ep2 = routes_episodes.create_episode(project.id, body=body, user=user, db=db)
    assert ep2["episode_number"] == 2 and ep2["title"] == "第2集"
    assert ep2["status"] == "draft"
    # 软删中间集后新集号 = max(未删)+1
    routes_episodes.delete_episode(ep2["id"], user=user, db=db)
    ep3 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    assert ep3["episode_number"] == 2


def test_get_episode_detail(db, user, project):
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    make_storyboard(db, project, ep["id"], 1)
    detail = routes_episodes.get_episode(ep["id"], user=user, db=db)
    assert detail["stats"]["storyboard_count"] == 1
    assert len(detail["storyboards"]) == 1
    assert detail["storyboards"][0]["episode_id"] == ep["id"]


def test_update_and_delete(db, user, project):
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    from app import schemas

    upd = routes_episodes.update_episode(
        ep["id"], schemas.EpisodeUpdate(title="改名", status="completed"), user=user, db=db
    )
    assert upd["title"] == "改名" and upd["status"] == "completed"
    with pytest.raises(HTTPException) as exc:
        routes_episodes.update_episode(
            ep["id"], schemas.EpisodeUpdate(status="nope"), user=user, db=db
        )
    assert exc.value.status_code == 400
    # 仅剩一集：禁止删除
    with pytest.raises(HTTPException) as exc:
        routes_episodes.delete_episode(ep["id"], user=user, db=db)
    assert exc.value.status_code == 400
    ep2 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    r = routes_episodes.delete_episode(ep2["id"], user=user, db=db)
    assert r["ok"] is True
    lst = routes_episodes.list_episodes(project.id, user=user, db=db)
    assert [e["id"] for e in lst["items"]] == [ep["id"]]


def test_cross_user_404(db, user, project):
    other = models.User(username="other", password_hash="x")
    db.add(other)
    db.commit()
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    with pytest.raises(HTTPException) as exc:
        get_owned_episode(db, other, ep["id"])
    assert exc.value.status_code == 404


def schemas_body(title=None, synopsis=None, inspiration=None):
    from app import schemas

    return schemas.EpisodeCreate(title=title, synopsis=synopsis, inspiration=inspiration)


# ---------------- 3. 创建项目自动建第 1 集 ----------------
def test_create_project_makes_episode1(db, user):
    from app import schemas

    body = schemas.ProjectCreate(title="新项目", inspiration="灵感", style="日系", aspect_ratio="16:9")
    out = routes_projects.create_project(body, user=user, db=db)
    eps = db.query(models.Episode).filter(models.Episode.project_id == out["id"]).all()
    assert len(eps) == 1
    assert eps[0].episode_number == 1 and eps[0].inspiration == "灵感"
    assert eps[0].style == "日系" and eps[0].aspect_ratio == "16:9"


def test_project_detail_includes_episodes(db, user, project):
    routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    data = routes_projects.get_project(project.id, user=user, db=db)
    assert len(data["episodes"]) == 1
    assert data["episodes"][0]["stats"]["storyboard_count"] == 0


# ---------------- 4. 项目级生成入口路由到默认集 ----------------
def test_project_script_routes_to_default_episode(db, user, project, monkeypatch):
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    ep2 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    captured = {}

    def fake_submit(db_, project_id, type_, payload=None, idempotency_key=None):
        captured["payload"] = payload
        return type("T", (), {"id": 999})()

    monkeypatch.setattr(task_engine, "submit_task", fake_submit)
    r = routes_projects.generate_script(project.id, body=None, user=user, db=db)
    assert r["task_id"] == 999
    assert captured["payload"]["episode_id"] == ep["id"]  # 默认集 = 最小集号
    r = routes_projects.pipeline(project.id, body=None, user=user, db=db)
    assert captured["payload"]["pipeline"] is True
    assert captured["payload"]["episode_id"] == ep["id"]
    # 软删默认集后路由到下一集
    routes_episodes.delete_episode(ep["id"], user=user, db=db)
    routes_projects.generate_script(project.id, body=None, user=user, db=db)
    assert captured["payload"]["episode_id"] == ep2["id"]


def test_episode_script_endpoint(db, user, project, monkeypatch):
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    captured = {}

    def fake_submit(db_, project_id, type_, payload=None, idempotency_key=None):
        captured.update(payload or {})
        captured["project_id"] = project_id
        return type("T", (), {"id": 555})()

    monkeypatch.setattr(task_engine, "submit_task", fake_submit)
    from app import schemas

    r = routes_episodes.generate_script(
        ep["id"], schemas.GenerateScriptRequest(inspiration="集级点子"), user=user, db=db
    )
    assert r["task_id"] == 555
    assert captured["episode_id"] == ep["id"]
    assert captured["inspiration"] == "集级点子"
    assert captured["project_id"] == project.id  # 任务仍挂项目，SSE 兼容


# ---------------- 5. 按集剧本 handler ----------------
SCRIPT_JSON = {
    "title": "AI 标题",
    "logline": "一句话梗概",
    "characters": [{"name": "小美", "description": "d", "prompt_template": "p", "voice": "longxiaochun"}],
    "storyboards": [
        {"seq": 1, "shot_size": "中景", "scene": "s1", "dialogue": "d1", "emotion": "e", "duration_sec": 5, "image_prompt": "ip1"},
        {"seq": 2, "shot_size": "近景", "scene": "s2", "dialogue": "", "emotion": "e", "duration_sec": 4, "image_prompt": "ip2"},
    ],
}


def _fake_writer(monkeypatch, data):
    from app.agents import writer

    monkeypatch.setattr(writer, "generate_script", lambda db_, project_, inspiration_: data)


def test_script_handler_scoped_to_episode(db, user, project, monkeypatch):
    ep1 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    ep2 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    # 两集各有一个存量分镜
    make_storyboard(db, project, ep1["id"], 1)
    make_storyboard(db, project, ep2["id"], 1)
    _fake_writer(monkeypatch, SCRIPT_JSON)

    task = models.GenTask(
        project_id=project.id, type=models.TaskType.script,
        status=models.TaskStatus.running,
        payload={"episode_id": ep1["id"], "inspiration": "x"},
    )
    db.add(task)
    db.commit()
    result = task_engine._handle_script(db, task)

    assert result["episode_id"] == ep1["id"]
    assert result["storyboard_count"] == 2
    # ep1 旧分镜被重建，ep2 分镜保留
    assert db.query(models.Storyboard).filter(models.Storyboard.episode_id == ep1["id"]).count() == 2
    assert db.query(models.Storyboard).filter(models.Storyboard.episode_id == ep2["id"]).count() == 1
    # 新分镜全部归属 ep1
    for sb in db.query(models.Storyboard).filter(models.Storyboard.episode_id == ep1["id"]).all():
        assert sb.project_id == project.id
    # 集状态与标题/logline 更新
    ep1_row = db.get(models.Episode, ep1["id"])
    assert ep1_row.status == models.EpisodeStatus.script_ready
    assert ep1_row.title == "AI 标题"
    assert ep1_row.logline == "一句话梗概"
    # 角色为项目级
    assert db.query(models.Character).filter(models.Character.project_id == project.id).count() == 1


def test_script_handler_pipeline_and_fallback(db, user, project, monkeypatch):
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    _fake_writer(monkeypatch, SCRIPT_JSON)
    submitted = []
    monkeypatch.setattr(
        task_engine, "submit_task",
        lambda db_, pid, t, payload=None, idempotency_key=None: submitted.append(payload) or type("T", (), {"id": 1})(),
    )
    task = models.GenTask(
        project_id=project.id, type=models.TaskType.script,
        status=models.TaskStatus.running, payload={"pipeline": True},  # 无 episode_id → 回退默认集
    )
    db.add(task)
    db.commit()
    result = task_engine._handle_script(db, task)
    assert result["episode_id"] == ep["id"]
    assert len(submitted) == 2  # 每个分镜一个出图任务
    assert all(s["count"] == 2 and s["retryable"] for s in submitted)
    assert db.get(models.Episode, ep["id"]).status == models.EpisodeStatus.producing


def test_script_handler_no_episode(db, user, project, monkeypatch):
    """没有任何集的项目（极端存量数据）：episode_id=None 分镜仍创建成功。"""
    _fake_writer(monkeypatch, SCRIPT_JSON)
    task = models.GenTask(
        project_id=project.id, type=models.TaskType.script,
        status=models.TaskStatus.running, payload={},
    )
    db.add(task)
    db.commit()
    result = task_engine._handle_script(db, task)
    assert result["episode_id"] is None
    assert result["storyboard_count"] == 2
    assert db.query(models.Storyboard).filter(models.Storyboard.episode_id.is_(None)).count() == 2


# ---------------- 6. 分镜按集 ----------------
def test_storyboard_episode_endpoints(db, user, project):
    from app import schemas

    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    ep2 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    body = schemas.StoryboardCreate(scene="手动一幕", duration_sec=5)
    sb = routes_storyboards.create_storyboard_for_episode(ep["id"], body, user=user, db=db)
    assert sb["episode_id"] == ep["id"] and sb["seq"] == 1
    routes_storyboards.create_storyboard_for_episode(ep["id"], body, user=user, db=db)
    r = routes_storyboards.list_storyboards_for_episode(ep["id"], user=user, db=db)
    assert r["total"] == 2
    # 项目级创建缺省归属默认集
    sb3 = routes_storyboards.create_storyboard(project.id, body, user=user, db=db)
    assert sb3["episode_id"] == ep["id"] and sb3["seq"] == 3
    # 指定另一集
    body_ep2 = schemas.StoryboardCreate(episode_id=ep2["id"], scene="第二集一幕")
    sb4 = routes_storyboards.create_storyboard(project.id, body_ep2, user=user, db=db)
    assert sb4["episode_id"] == ep2["id"] and sb4["seq"] == 1
    # 删除集 1 的分镜后，只有集 1 的 seq 重新归一化，集 2 不受影响
    routes_storyboards.delete_storyboard(sb["id"], user=user, db=db)
    sbs_ep1 = routes_storyboards.list_storyboards_for_episode(ep["id"], user=user, db=db)["items"]
    assert [s["seq"] for s in sbs_ep1] == [1, 2]
    sbs_ep2 = routes_storyboards.list_storyboards_for_episode(ep2["id"], user=user, db=db)["items"]
    assert [s["seq"] for s in sbs_ep2] == [1]


# ---------------- 7. 时间线按集 ----------------
def test_timeline_per_episode(db, user, project):
    from app import schemas

    ep1 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    ep2 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    make_storyboard(db, project, ep1["id"], 1, video=True)
    make_storyboard(db, project, ep2["id"], 1, video=True)
    tl1 = routes_timelines.create_timeline(
        project.id, schemas.TimelineCreate(episode_id=ep1["id"]), user=user, db=db
    )
    assert tl1["episode_id"] == ep1["id"]
    assert len(tl1["items"]) == 1  # 只含 ep1 的镜头
    # 缺省回退默认集
    tl2 = routes_timelines.create_timeline(project.id, None, user=user, db=db)
    assert tl2["episode_id"] == ep1["id"]
    # 导出按集过滤
    tl2_row = db.get(models.Timeline, tl2["id"])
    tl2_row.status = models.TimelineStatus.completed
    tl2_row.output_url = "/static/composites/timeline_2.mp4"
    db.commit()
    r = routes_timelines.export_project(project.id, episode_id=ep1["id"], user=user, db=db)
    assert r["timeline_id"] == tl2["id"]
    with pytest.raises(HTTPException):
        routes_timelines.export_project(project.id, episode_id=ep2["id"], user=user, db=db)
    r2 = routes_timelines.export_episode(ep1["id"], user=user, db=db)
    assert r2["timeline_id"] == tl2["id"]


# ---------------- 8. 级联删除 ----------------
def test_project_delete_cascades_episodes(db, user, project):
    """硬删除：项目及其全部关联数据物理删除。"""
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    make_storyboard(db, project, ep["id"], 1, video=True)
    db.add(models.Character(project_id=project.id, name="角色A", ref_image_url="/static/images/c.png"))
    db.add(models.Asset(project_id=project.id, type=models.AssetType.image, url="/static/images/a.png"))
    db.commit()
    pid = project.id

    routes_projects.delete_project(pid, user=user, db=db)

    assert db.query(models.Project).filter(models.Project.id == pid).first() is None
    assert db.query(models.Episode).filter(models.Episode.project_id == pid).count() == 0
    assert db.query(models.Storyboard).filter(models.Storyboard.project_id == pid).count() == 0
    assert db.query(models.Character).filter(models.Character.project_id == pid).count() == 0
    assert db.query(models.Asset).filter(models.Asset.project_id == pid).count() == 0
    assert db.query(models.Prompt).filter(models.Prompt.project_id == pid).count() == 0
    assert db.query(models.ShotVersion).count() == 0
    assert db.query(models.Shot).count() == 0


def test_episode_delete_keeps_data_unreachable(db, user, project):
    """软删集后其分镜保留（episode_id 不变）但不再可达：按集列表 404，项目详情不含该集。"""
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    ep2 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    sb = make_storyboard(db, project, ep["id"], 1)
    routes_episodes.delete_episode(ep["id"], user=user, db=db)
    db.refresh(sb)
    assert sb.episode_id == ep["id"]  # 数据保留
    with pytest.raises(HTTPException) as exc:
        routes_storyboards.list_storyboards_for_episode(ep["id"], user=user, db=db)
    assert exc.value.status_code == 404
    r = routes_storyboards.list_storyboards_for_episode(ep2["id"], user=user, db=db)
    assert r["total"] == 0
    lst = routes_episodes.list_episodes(project.id, user=user, db=db)
    assert ep["id"] not in [e["id"] for e in lst["items"]]


# ---------------- 9. pipeline-status / composite-check ----------------
def test_pipeline_status_states(db, user, project):
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    # 空集：全 pending
    ps = routes_episodes.pipeline_status(ep["id"], user=user, db=db)
    assert ps["steps"]["script"]["status"] == "pending"
    assert ps["steps"]["image"]["total"] == 0
    # 加 2 分镜（1 有台词，1 已选画面 + 视频）
    make_storyboard(db, project, ep["id"], 1, video=True)  # 有画面有视频
    sb2 = make_storyboard(db, project, ep["id"], 2)
    sb2.dialogue = "台词"
    db.commit()
    ps = routes_episodes.pipeline_status(ep["id"], user=user, db=db)
    assert ps["steps"]["script"]["status"] == "done"
    assert ps["steps"]["board"]["status"] == "done"
    # image：2 镜都已有 selected（make_storyboard 默认选中）→ done
    assert ps["steps"]["image"]["status"] == "done"
    assert ps["steps"]["image"]["completed"] == 2
    # video：只有 1 镜有视频 → partial
    assert ps["steps"]["video"]["status"] == "partial"
    assert ps["steps"]["video"]["completed"] == 1
    # voice：1 镜有台词但无配音 → pending（completed 0）
    assert ps["steps"]["voice"]["total"] == 1
    assert ps["steps"]["voice"]["status"] == "pending"


def test_composite_check_lists_missing(db, user, project):
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    make_storyboard(db, project, ep["id"], 1, video=True)
    make_storyboard(db, project, ep["id"], 2)  # 无视频
    cc = routes_episodes.composite_check(ep["id"], user=user, db=db)
    assert cc["total"] == 2
    assert cc["ready"] == 1
    assert len(cc["missing"]) == 1
    assert cc["missing"][0]["seq"] == 2


def test_batch_images_cross_episode_400(db, user, project):
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    ep2 = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    sb = make_storyboard(db, project, ep2["id"], 1)  # 属于 ep2
    with pytest.raises(HTTPException) as exc:
        routes_episodes.batch_images(
            ep["id"], schemas.BatchImageRequest(storyboard_ids=[sb.id]), user=user, db=db
        )
    assert exc.value.status_code == 400


def test_batch_videos_submits_only_eligible(db, user, project, monkeypatch):
    """批量视频：已选画面且无视频的才提交；已有视频 / 无选定画面的跳过。"""
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    make_storyboard(db, project, ep["id"], 1, video=True)  # 已有视频 → skip
    make_storyboard(db, project, ep["id"], 2)  # 已选画面无视频 → submit
    submitted = []
    monkeypatch.setattr(
        task_engine, "submit_task",
        lambda db_, pid, t, payload=None, idempotency_key=None: submitted.append(payload)
        or type("T", (), {"id": len(submitted) + 1})(),
    )
    r = routes_episodes.batch_videos(ep["id"], schemas.BatchVideoRequest(), user=user, db=db)
    assert r["submitted"] == 1
    assert len(r["skipped"]) == 1
    assert submitted[0]["retryable"] is True


def test_batch_images_default_picks_unselected(db, user, project, monkeypatch):
    """批量出图缺省：只提交还没有已选画面的分镜。"""
    ep = routes_episodes.create_episode(project.id, body=None, user=user, db=db)
    make_storyboard(db, project, ep["id"], 1, video=True)  # 已选画面 → 不提交
    # 第二个：无 selected_version
    sb2 = models.Storyboard(project_id=project.id, episode_id=ep["id"], seq=2, scene="x")
    db.add(sb2)
    db.flush()
    db.add(models.Shot(storyboard_id=sb2.id, status=models.ShotStatus.pending))
    db.commit()
    submitted = []
    monkeypatch.setattr(
        task_engine, "submit_task",
        lambda db_, pid, t, payload=None, idempotency_key=None: submitted.append(payload)
        or type("T", (), {"id": len(submitted) + 1})(),
    )
    r = routes_episodes.batch_images(ep["id"], None, user=user, db=db)
    assert r["submitted"] == 1
    assert submitted[0]["storyboard_id"] == sb2.id


def test_project_update_status_validates(db, user, project):
    from fastapi import HTTPException as H
    out = routes_projects.update_project(
        project.id, schemas.ProjectUpdate(status="completed"), user=user, db=db
    )
    assert out["status"] == "completed"
    with pytest.raises(H) as exc:
        routes_projects.update_project(
            project.id, schemas.ProjectUpdate(status="nope"), user=user, db=db
        )
    assert exc.value.status_code == 400


# ---------------- 10. _build_image_prompt 分支回归 ----------------
def test_build_image_prompt_all_branches(db, user, project):
    """回归：style_negative 未初始化导致 UnboundLocalError（无预设 / override 分支）。"""
    sb = models.Storyboard(project_id=project.id, seq=1, scene="雨夜", image_prompt="rainy")
    db.add(sb)
    db.commit()
    # 风格名无匹配预设（原崩溃场景）
    r = task_engine._build_image_prompt(db, project, sb, None)
    assert "Negative" in r
    # 预设存在但无负面词
    preset = models.StylePreset(user_id=user.id, name=project.style or "x", prompt="anime style")
    db.add(preset)
    db.commit()
    assert "anime style" in task_engine._build_image_prompt(db, project, sb, None)
    # 预设含负面词
    preset.negative_prompt = "extra fingers"
    db.commit()
    assert "extra fingers" in task_engine._build_image_prompt(db, project, sb, None)
    # override 分支（原同样崩溃）
    assert task_engine._build_image_prompt(db, project, sb, "custom").startswith("custom")
