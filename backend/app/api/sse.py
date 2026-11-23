"""SSE 事件流：GET /api/v1/projects/{id}/stream。

EventSource 无法携带自定义 Header，因此鉴权支持 ?token= 查询参数
（与 Authorization: Bearer 等效）；心跳 15s 一次。
"""
import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import decode_token
from .. import models
from ..models import GenTask, Project, User
from ..services import event_bus

router = APIRouter()

HEARTBEAT_INTERVAL = 15

# 视为"进行中"的任务状态：连接建立时补发一次快照，避免断线期间的状态永远丢失
ACTIVE_STATUSES = (
    models.TaskStatus.pending,
    models.TaskStatus.queued,
    models.TaskStatus.running,
)


def _task_snapshot(db: Session, project_id: int) -> list[dict]:
    rows = (
        db.query(GenTask)
        .filter(GenTask.project_id == project_id, GenTask.status.in_(ACTIVE_STATUSES))
        .order_by(GenTask.id)
        .all()
    )
    return [
        {
            "type": "task_update",
            "task_id": t.id,
            "task_type": t.type.value if hasattr(t.type, "value") else t.type,
            "status": t.status.value if hasattr(t.status, "value") else t.status,
            "progress": t.progress or 0,
            "error": t.error,
        }
        for t in rows
    ]


async def _event_generator(project_id: int, snapshot: list[dict]):
    queue = event_bus.subscribe(project_id)
    try:
        connected = json.dumps({"type": "connected", "project_id": project_id}, ensure_ascii=False)
        yield f"data: {connected}\n\n"
        # 补发进行中任务快照：SSE 没有事件重放，断线/重连期间的事件本来会永久丢失
        if snapshot:
            payload = json.dumps(
                {"type": "snapshot", "tasks": snapshot}, ensure_ascii=False, default=str
            )
            yield f"data: {payload}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                yield "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        event_bus.unsubscribe(project_id, queue)


@router.get("/projects/{project_id}/stream")
async def stream(
    project_id: int,
    token: str | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    # 优先 Authorization: Bearer，其次 ?token= 查询参数
    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    token_value = token or bearer
    user_id = decode_token(token_value) if token_value else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="未登录或令牌无效")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")
    project = db.get(Project, project_id)
    if project is None or project.deleted or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="项目不存在")

    return StreamingResponse(
        _event_generator(project_id, _task_snapshot(db, project_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
