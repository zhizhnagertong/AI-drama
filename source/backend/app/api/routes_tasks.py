"""任务接口：列表 / 详情 / 重试。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.db import get_db
from .. import models, schemas
from ..models import GenTask, Project, User
from ..api.routes_projects import get_owned_project
from ..services import task_engine

router = APIRouter()


def _get_owned_task(db: Session, user: User, task_id: int) -> GenTask:
    task = db.get(GenTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    project = db.get(Project, task.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/tasks")
def list_tasks(
    project_id: int | None = None,
    type: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = (
        db.query(GenTask)
        .join(Project, GenTask.project_id == Project.id)
        .filter(Project.user_id == user.id)
    )
    if project_id is not None:
        get_owned_project(db, user, project_id)
        query = query.filter(GenTask.project_id == project_id)
    if type:
        try:
            query = query.filter(GenTask.type == models.TaskType(type))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"非法的任务类型: {type}")
    if status:
        try:
            query = query.filter(GenTask.status == models.TaskStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"非法的任务状态: {status}")
    total = query.count()
    items = (
        query.order_by(GenTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": [schemas.task_out(t) for t in items], "total": total}


@router.get("/tasks/{task_id}")
def get_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    task = _get_owned_task(db, user, task_id)
    return schemas.task_out(task)


@router.post("/tasks/{task_id}/retry")
def retry_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """失败任务重置为 queued 并重新入队。"""
    task = _get_owned_task(db, user, task_id)
    if task.status != models.TaskStatus.failed:
        raise HTTPException(status_code=400, detail="仅失败任务可以重试")
    task.status = models.TaskStatus.queued
    task.progress = 0
    db.commit()
    db.refresh(task)
    task_engine.requeue(task.id)
    return schemas.task_out(task)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """取消排队中/运行中的任务（运行中为协作式取消，在下个检查点停止）。"""
    task = _get_owned_task(db, user, task_id)
    if task.status not in (
        models.TaskStatus.pending,
        models.TaskStatus.queued,
        models.TaskStatus.running,
    ):
        raise HTTPException(status_code=400, detail="任务已结束，无法取消")
    task_engine.cancel_task(db, task)
    db.refresh(task)
    return schemas.task_out(task)
