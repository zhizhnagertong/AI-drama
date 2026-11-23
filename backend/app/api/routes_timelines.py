"""时间线与成片导出接口。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.db import get_db
from .. import models, schemas
from ..models import Asset, ShotVersion, Timeline, User
from ..api.routes_projects import get_owned_project
from ..api.routes_episodes import get_owned_episode
from ..services import task_engine

router = APIRouter()


def _get_owned_timeline(db: Session, user: User, timeline_id: int) -> Timeline:
    timeline = db.get(Timeline, timeline_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="时间线不存在")
    project = db.get(models.Project, timeline.project_id)
    if project is None or project.deleted or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="时间线不存在")
    return timeline


def _audio_map(db: Session, project_id: int) -> dict[int, str]:
    """storyboard_id → tts 音频 URL（来自 assets.meta，同镜取最新一条）。"""
    result: dict[int, str] = {}
    assets = (
        db.query(Asset)
        .filter(Asset.project_id == project_id, Asset.type == models.AssetType.audio)
        .order_by(Asset.id.desc())
        .all()
    )
    for asset in assets:
        meta = asset.meta or {}
        sb_id = meta.get("storyboard_id")
        if sb_id and sb_id not in result:
            result[int(sb_id)] = asset.url
    return result


def _auto_items(db: Session, project: models.Project, episode_id: int | None = None) -> list[dict]:
    """取所有已选版本的镜头，按分镜 seq 排序自动构建时间线 items。

    episode_id 存在时只取该集分镜（一集一条时间线）。
    """
    query = (
        db.query(models.Shot, models.Storyboard)
        .join(models.Storyboard, models.Shot.storyboard_id == models.Storyboard.id)
        .filter(
            models.Storyboard.project_id == project.id,
            models.Shot.selected_version_id.isnot(None),
        )
    )
    if episode_id is not None:
        query = query.filter(models.Storyboard.episode_id == episode_id)
    rows = query.order_by(models.Storyboard.seq).all()
    audio_map = _audio_map(db, project.id)
    items: list[dict] = []
    for shot, sb in rows:
        version = db.get(ShotVersion, shot.selected_version_id)
        if version is None:
            continue
        items.append(
            {
                "shot_id": shot.id,
                "version_id": version.id,
                "media_url": version.video_url or version.image_url,
                "duration_sec": sb.duration_sec or 5,
                "subtitle": sb.dialogue or None,
                "audio_url": audio_map.get(sb.id),
            }
        )
    return items


@router.get("/projects/{project_id}/timelines")
def list_timelines(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    get_owned_project(db, user, project_id)
    items = (
        db.query(Timeline)
        .filter(Timeline.project_id == project_id)
        .order_by(Timeline.id.desc())
        .all()
    )
    return {"items": [schemas.timeline_out(t) for t in items], "total": len(items)}


@router.post("/projects/{project_id}/timelines")
def create_timeline(
    project_id: int,
    body: schemas.TimelineCreate | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """构建时间线：默认自动构建；body.items 传入时覆盖。

    body.episode_id 存在时按集构建；缺省回退项目默认集（最小集号）。
    """
    project = get_owned_project(db, user, project_id)
    episode_id = body.episode_id if body else None
    if episode_id is not None:
        get_owned_episode(db, user, episode_id)
    else:
        ep = (
            db.query(models.Episode)
            .filter(
                models.Episode.project_id == project.id,
                models.Episode.deleted.is_(False),
            )
            .order_by(models.Episode.episode_number)
            .first()
        )
        episode_id = ep.id if ep else None
    if body and body.items:
        items = [i.model_dump() for i in body.items]
    else:
        items = _auto_items(db, project, episode_id)
    if not items:
        raise HTTPException(status_code=400, detail="没有可选版本的镜头，无法构建时间线")
    timeline = Timeline(
        project_id=project.id,
        episode_id=episode_id,
        items=items,
        composite_config=body.composite_config if body else None,
    )
    db.add(timeline)
    db.commit()
    db.refresh(timeline)
    return schemas.timeline_out(timeline)


@router.put("/timelines/{timeline_id}")
def update_timeline(
    timeline_id: int,
    body: schemas.TimelineUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    timeline = _get_owned_timeline(db, user, timeline_id)
    data = body.model_dump(exclude_unset=True)
    if "items" in data and data["items"] is not None:
        timeline.items = data["items"]
    if "composite_config" in data:
        timeline.composite_config = data["composite_config"]
    db.commit()
    db.refresh(timeline)
    return schemas.timeline_out(timeline)


@router.delete("/timelines/{timeline_id}")
def delete_timeline(
    timeline_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    timeline = _get_owned_timeline(db, user, timeline_id)
    db.delete(timeline)
    db.commit()
    return {"ok": True, "message": "时间线已删除"}


@router.post("/timelines/{timeline_id}/composite")
def composite_timeline(
    timeline_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    timeline = _get_owned_timeline(db, user, timeline_id)
    if not timeline.items:
        raise HTTPException(status_code=400, detail="时间线为空，无法合成")
    task = task_engine.submit_task(
        db, timeline.project_id, models.TaskType.composite, {"timeline_id": timeline.id, "retryable": False}
    )
    return {"task_id": task.id}


@router.get("/projects/{project_id}/export")
def export_project(
    project_id: int,
    episode_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    get_owned_project(db, user, project_id)
    query = db.query(Timeline).filter(
        Timeline.project_id == project_id,
        Timeline.status == models.TimelineStatus.completed,
    )
    if episode_id is not None:
        query = query.filter(Timeline.episode_id == episode_id)
    timeline = query.order_by(Timeline.id.desc()).first()
    if timeline is None or not timeline.output_url:
        raise HTTPException(status_code=404, detail="暂无已完成的成片，请先合成时间线")
    return {"output_url": timeline.output_url, "timeline_id": timeline.id}


@router.get("/episodes/{episode_id}/export")
def export_episode(
    episode_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ep = get_owned_episode(db, user, episode_id)
    timeline = (
        db.query(Timeline)
        .filter(
            Timeline.episode_id == ep.id,
            Timeline.status == models.TimelineStatus.completed,
        )
        .order_by(Timeline.id.desc())
        .first()
    )
    if timeline is None or not timeline.output_url:
        raise HTTPException(status_code=404, detail="该集暂无已完成的成片，请先合成时间线")
    return {"output_url": timeline.output_url, "timeline_id": timeline.id}
