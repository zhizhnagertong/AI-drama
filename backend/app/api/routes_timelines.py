"""时间线与成片导出接口。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
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
            # 排除已软删除剧集下的分镜
            or_(
                models.Storyboard.episode_id.is_(None),
                models.Storyboard.episode_id.in_(
                    select(models.Episode.id).where(models.Episode.deleted.is_(False))
                ),
            ),
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


def _validate_items(db: Session, project: models.Project, items: list[dict]) -> None:
    """校验时间线片段：数量上限 + 素材地址必须属于本项目。

    安全：media_url 会被合成器交给 ffmpeg 读取，远程地址还会被服务端下载。
    若不校验，客户端可传 `/static/../../backend/app/core/config.py`（路径穿越）
    或 `http://169.254.169.254/...`（SSRF）。这里只接受项目内已登记的素材地址。
    """
    if len(items) > 200:
        raise HTTPException(status_code=400, detail="时间线片段过多，单次最多 200 个")

    urls: set[str] = set()
    for it in items:
        for key in ("media_url", "audio_url"):
            value = (it or {}).get(key)
            if value:
                urls.add(str(value))
    if not urls:
        return

    known: set[str] = {
        row[0]
        for row in db.query(Asset.url).filter(Asset.project_id == project.id).all()
        if row[0]
    }
    # 兼容历史数据：版本/镜头上直接记录的地址也算合法
    for (image_url,) in db.query(ShotVersion.image_url).join(
        models.Shot, ShotVersion.shot_id == models.Shot.id
    ).join(models.Storyboard, models.Shot.storyboard_id == models.Storyboard.id).filter(
        models.Storyboard.project_id == project.id
    ):
        if image_url:
            known.add(image_url)
    for (video_url,) in db.query(ShotVersion.video_url).join(
        models.Shot, ShotVersion.shot_id == models.Shot.id
    ).join(models.Storyboard, models.Shot.storyboard_id == models.Storyboard.id).filter(
        models.Storyboard.project_id == project.id
    ):
        if video_url:
            known.add(video_url)

    unknown = urls - known
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"时间线包含不属于本项目的素材地址：{sorted(unknown)[0][:120]}",
        )


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
        ep = get_owned_episode(db, user, episode_id)
        # 剧集必须属于本项目：否则可把时间线挂到别的项目的剧集 id 上
        if ep.project_id != project.id:
            raise HTTPException(status_code=400, detail="剧集不属于该项目")
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
        _validate_items(db, project, items)
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
        project = db.get(models.Project, timeline.project_id)
        _validate_items(db, project, data["items"])
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
