"""分镜接口：列表 / 新增 / 编辑 / 排序 / 出图 / 配音。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.db import get_db
from .. import models, schemas
from ..models import Storyboard, User
from ..api.routes_projects import get_owned_project
from ..api.routes_episodes import get_owned_episode
from ..services import task_engine

router = APIRouter()


def _get_owned_storyboard(db: Session, user: User, storyboard_id: int) -> Storyboard:
    sb = db.get(Storyboard, storyboard_id)
    if sb is None:
        raise HTTPException(status_code=404, detail="分镜不存在")
    project = db.get(models.Project, sb.project_id)
    if project is None or project.deleted or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return sb


@router.post("/episodes/{episode_id}/storyboards")
def create_storyboard_for_episode(
    episode_id: int,
    body: schemas.StoryboardCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """在某集下手动新增一幕：追加到该集末尾（seq = 该集 max+1）。"""
    ep = get_owned_episode(db, user, episode_id)
    max_seq = (
        db.query(func.max(Storyboard.seq))
        .filter(Storyboard.episode_id == ep.id)
        .scalar()
        or 0
    )
    sb = Storyboard(
        project_id=ep.project_id,
        episode_id=ep.id,
        seq=max_seq + 1,
        shot_size=body.shot_size or "中景",
        scene=body.scene,
        dialogue=body.dialogue,
        emotion=body.emotion,
        duration_sec=body.duration_sec,
        status=models.StoryboardStatus.pending,
        image_prompt=body.image_prompt,
    )
    db.add(sb)
    db.flush()
    db.add(models.Shot(storyboard_id=sb.id, status=models.ShotStatus.pending))
    db.commit()
    db.refresh(sb)
    return schemas.storyboard_out(sb)


@router.get("/episodes/{episode_id}/storyboards")
def list_storyboards_for_episode(
    episode_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    get_owned_episode(db, user, episode_id)
    items = (
        db.query(Storyboard)
        .filter(Storyboard.episode_id == episode_id)
        .order_by(Storyboard.seq)
        .all()
    )
    return {"items": [schemas.storyboard_out(sb) for sb in items], "total": len(items)}


@router.post("/projects/{project_id}/storyboards")
def create_storyboard(
    project_id: int,
    body: schemas.StoryboardCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """手动新增一幕：追加到末尾（seq = max+1），并配套创建空镜头。

    归属集：优先 body.episode_id（须属于本项目），否则项目默认集（最小集号）。
    """
    project = get_owned_project(db, user, project_id)
    episode_id = getattr(body, "episode_id", None)
    if episode_id is not None:
        ep = get_owned_episode(db, user, episode_id)
        if ep.project_id != project.id:
            raise HTTPException(status_code=400, detail="该集不属于此项目")
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
    if episode_id is not None:
        seq_filter = Storyboard.episode_id == episode_id
    else:
        seq_filter = Storyboard.episode_id.is_(None)
    max_seq = (
        db.query(func.max(Storyboard.seq))
        .filter(Storyboard.project_id == project.id, seq_filter)
        .scalar()
        or 0
    )
    sb = Storyboard(
        project_id=project.id,
        episode_id=episode_id,
        seq=max_seq + 1,
        shot_size=body.shot_size or "中景",
        scene=body.scene,
        dialogue=body.dialogue,
        emotion=body.emotion,
        duration_sec=body.duration_sec,
        status=models.StoryboardStatus.pending,
        image_prompt=body.image_prompt,
    )
    db.add(sb)
    db.flush()
    db.add(models.Shot(storyboard_id=sb.id, status=models.ShotStatus.pending))
    db.commit()
    db.refresh(sb)
    return schemas.storyboard_out(sb)


@router.get("/projects/{project_id}/storyboards")
def list_storyboards(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    get_owned_project(db, user, project_id)
    items = (
        db.query(Storyboard)
        .filter(Storyboard.project_id == project_id)
        .order_by(Storyboard.seq)
        .all()
    )
    return {"items": [schemas.storyboard_out(sb) for sb in items], "total": len(items)}


@router.get("/storyboards/{storyboard_id}")
def get_storyboard(
    storyboard_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    sb = _get_owned_storyboard(db, user, storyboard_id)
    return schemas.storyboard_out(sb)


@router.put("/storyboards/{storyboard_id}")
def update_storyboard(
    storyboard_id: int,
    body: schemas.StoryboardUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    sb = _get_owned_storyboard(db, user, storyboard_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(sb, field, value)
    db.commit()
    db.refresh(sb)
    return schemas.storyboard_out(sb)


@router.delete("/storyboards/{storyboard_id}")
def delete_storyboard(
    storyboard_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """删除分镜：级联删除关联 shot 及全部版本，剩余分镜 seq 归一化为 1..n。"""
    sb = _get_owned_storyboard(db, user, storyboard_id)
    project_id = sb.project_id
    episode_id = sb.episode_id
    # 删除前收集产物文件与关联 Asset（须在级联删除生效前查询 shot/version）
    stale_urls = task_engine.collect_storyboard_artifacts(db, project_id, [sb.id])
    db.delete(sb)
    db.flush()
    remain_query = db.query(Storyboard).filter(Storyboard.project_id == project_id)
    remain_query = (
        remain_query.filter(Storyboard.episode_id == episode_id)
        if episode_id is not None
        else remain_query.filter(Storyboard.episode_id.is_(None))
    )
    remain = remain_query.order_by(Storyboard.seq).all()
    for i, row in enumerate(remain, start=1):
        row.seq = i
    db.commit()
    task_engine.purge_asset_files(stale_urls)
    return {"ok": True, "message": "分镜已删除"}


@router.put("/projects/{project_id}/storyboards/reorder")
def reorder_storyboards(
    project_id: int,
    body: schemas.ReorderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    get_owned_project(db, user, project_id)
    ids = set(body.ordered_ids)
    rows = db.query(Storyboard).filter(Storyboard.id.in_(ids)).all()
    by_id = {sb.id: sb for sb in rows}
    for sb in rows:
        if sb.project_id != project_id:
            raise HTTPException(status_code=404, detail=f"分镜 {sb.id} 不属于该项目")
    for seq, sid in enumerate(body.ordered_ids, start=1):
        sb = by_id.get(sid)
        if sb is None:  # 并发下已被删除：跳过而非 500
            continue
        sb.seq = seq
    db.commit()
    items = (
        db.query(Storyboard)
        .filter(Storyboard.project_id == project_id)
        .order_by(Storyboard.seq)
        .all()
    )
    return {"items": [schemas.storyboard_out(sb) for sb in items], "total": len(items)}


@router.post("/storyboards/{storyboard_id}/generate-image")
def generate_image(
    storyboard_id: int,
    body: schemas.GenerateImageRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    sb = _get_owned_storyboard(db, user, storyboard_id)
    payload = {
        "storyboard_id": sb.id,
        "count": body.count if body else 2,
        "prompt_override": body.prompt_override if body else None,
        "seed": body.seed if body else None,
        "retryable": True,
    }
    task = task_engine.submit_task(db, sb.project_id, models.TaskType.image, payload)
    return {"task_id": task.id}


@router.post("/storyboards/{storyboard_id}/generate-voice")
def generate_voice(
    storyboard_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    sb = _get_owned_storyboard(db, user, storyboard_id)
    task = task_engine.submit_task(
        db, sb.project_id, models.TaskType.tts, {"storyboard_id": sb.id, "retryable": True}
    )
    return {"task_id": task.id}
