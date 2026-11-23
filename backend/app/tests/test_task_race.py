"""任务引擎竞态测试：项目被删除时，运行中的 worker 必须优雅终止。

复现路径（联调中发现）：
1. worker 从 dbA 取出 GenTask 的 ORM 对象，开始执行 handler；
2. 用户删除项目，dbB 通过 bulk delete 物理删掉 gen_tasks 行；
3. worker 调 update_progress -> dbA.commit() 抛 StaleDataError；
4. 旧实现在 rollback-only 的 session 上访问 task.retries，二次抛
   PendingRollbackError，导致 _run_task 直接崩、任务卡中间态。

修复后期望：
- update_progress 抛 TaskGone（session 已 rollback）；
- _run_task 捕获后直接 return，不写终态、不推送、不重试；
- 普通任务失败路径仍然正常写 failed 并累加 retries。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.core.db import Base
from app.services import task_engine


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        eng,
        tables=[
            models.User.__table__,
            models.Project.__table__,
            models.GenTask.__table__,
        ],
    )
    yield eng
    eng.dispose()


@pytest.fixture()
def Session(engine, monkeypatch):
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    # _run_task 内部直接用模块级 SessionLocal，测试需指向同一个内存库
    monkeypatch.setattr(task_engine, "SessionLocal", maker)
    return maker


def _seed(Session):
    """建一个用户 + 项目 + running 任务，返回 (project_id, task_id)。"""
    db = Session()
    u = models.User(username="u", password_hash="x", email="u@example.com")
    db.add(u)
    db.commit()
    p = models.Project(user_id=u.id, title="p", style="s", aspect_ratio="9:16")
    db.add(p)
    db.commit()
    t = models.GenTask(
        project_id=p.id,
        type=models.TaskType.cover,
        status=models.TaskStatus.running,
        progress=5,
        payload={"retryable": True},
    )
    db.add(t)
    db.commit()
    ids = (p.id, t.id)
    db.close()
    return ids


def _delete_project(Session, project_id):
    """模拟 routes_projects._purge_project 的 bulk delete。"""
    db = Session()
    db.query(models.GenTask).filter(
        models.GenTask.project_id == project_id
    ).delete(synchronize_session=False)
    db.query(models.Project).filter(models.Project.id == project_id).delete(
        synchronize_session=False
    )
    db.commit()
    db.close()


def test_update_progress_raises_task_gone_after_row_deleted(Session, engine):
    """worker 持有旧 ORM 对象；行被删后 update_progress 应抛 TaskGone 而非 StaleDataError。"""
    pid, tid = _seed(Session)
    worker_db = Session()
    task = worker_db.get(models.GenTask, tid)

    _delete_project(Session, pid)

    with pytest.raises(task_engine.TaskGone):
        task_engine.update_progress(worker_db, task, 60)
    # session 必须已恢复（不是 rollback-only）
    assert worker_db.query(models.GenTask.id).filter(models.GenTask.id == tid).scalar() is None
    worker_db.close()


def test_update_progress_commit_race_also_raises_task_gone(Session, monkeypatch):
    """探测与 commit 之间行被删（竞态窗口）：也要转成 TaskGone。"""
    pid, tid = _seed(Session)
    worker_db = Session()
    task = worker_db.get(models.GenTask, tid)

    original_exists = task_engine._task_still_exists

    def delete_on_probe(db, task_id):
        # 第一次探测（update_progress 内）返回 True，随后删行，制造 commit 时行已消失
        if delete_on_probe.calls == 0:
            delete_on_probe.calls += 1
            _delete_project(Session, pid)
            return True
        return original_exists(db, task_id)

    delete_on_probe.calls = 0
    monkeypatch.setattr(task_engine, "_task_still_exists", delete_on_probe)

    with pytest.raises(task_engine.TaskGone):
        task_engine.update_progress(worker_db, task, 60)
    worker_db.close()


def test_run_task_exits_cleanly_when_handler_hits_deleted_project(Session, monkeypatch):
    """handler 内遇到任务行消失 -> _run_task 不抛异常、不写终态、不重试入队。"""
    pid, tid = _seed(Session)

    def handler(db, task):
        # 模拟外部 API 返回期间项目被删
        _delete_project(Session, pid)
        task_engine.update_progress(db, task, 60)
        return {"ok": True}

    monkeypatch.setitem(task_engine.HANDLERS, models.TaskType.cover, handler)
    enqueued = []
    monkeypatch.setattr(task_engine, "_enqueue", lambda tid_: enqueued.append(tid_))

    # 不应抛出（旧实现会二次抛 PendingRollbackError）
    task_engine._run_task(tid)

    check = Session()
    assert check.get(models.GenTask, tid) is None  # 行已被删，未写入 failed
    check.close()
    assert enqueued == []  # 不应重试


def test_run_task_marks_failed_on_ordinary_error(Session, monkeypatch):
    """普通 handler 异常仍应写 failed + retries+1（不能因修复被破坏）。"""
    _, tid = _seed(Session)

    def handler(db, task):
        raise RuntimeError("boom")

    monkeypatch.setitem(task_engine.HANDLERS, models.TaskType.cover, handler)
    monkeypatch.setattr(task_engine, "_enqueue", lambda tid_: None)
    monkeypatch.setattr(task_engine, "_publish", lambda t: None)

    task_engine._run_task(tid)

    check = Session()
    t = check.get(models.GenTask, tid)
    assert t is not None
    assert t.status == models.TaskStatus.failed
    assert t.retries == 1
    assert "boom" in (t.error or "")
    check.close()


def test_run_task_skips_when_row_deleted_before_start(Session):
    """任务行在 worker 取到之前就已被删：db.get 返回 None，直接 return。"""
    pid, tid = _seed(Session)
    _delete_project(Session, pid)

    task_engine._run_task(tid)  # 不应抛异常

    check = Session()
    assert check.get(models.GenTask, tid) is None
    check.close()
