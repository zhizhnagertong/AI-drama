"""镜头接口：详情 / 选版 / 生成视频 / 重新抽卡。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.db import get_db
from .. import models, schemas
from ..models import Shot, ShotVersion, User
from ..services import task_engine

router = APIRouter()


def _get_owned_shot(db: Session, user: User, shot_id: int) -> Shot:
    shot = db.get(Shot, shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="镜头不存在")
    sb = db.get(models.Storyboard, shot.storyboard_id)
    project = db.get(models.Project, sb.project_id) if sb else None
    if project is None or project.deleted or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="镜头不存在")
    return shot


def _get_owned_version(db: Session, user: User, shot: Shot, version_id: int) -> ShotVersion:
    version = db.get(ShotVersion, version_id)
    if version is None or version.shot_id != shot.id:
        raise HTTPException(status_code=404, detail="版本不存在或不属于该镜头")
    return version


@router.get("/shots/{shot_id}")
def get_shot(
    shot_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    shot = _get_owned_shot(db, user, shot_id)
    return schemas.shot_out(shot)


@router.post("/shots/{shot_id}/select-version")
def select_version(
    shot_id: int,
    body: schemas.SelectVersionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    shot = _get_owned_shot(db, user, shot_id)
    version = db.get(ShotVersion, body.version_id)
    if version is None or version.shot_id != shot.id:
        raise HTTPException(status_code=404, detail="版本不存在或不属于该镜头")
    for v in shot.versions:
        v.is_selected = v.id == version.id
    shot.selected_version_id = version.id
    db.commit()
    db.refresh(shot)
    return schemas.shot_out(shot)


@router.put("/shots/{shot_id}/versions/{version_id}")
def update_version(
    shot_id: int,
    version_id: int,
    body: schemas.ShotVersionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """编辑版本提示词 / seed。"""
    shot = _get_owned_shot(db, user, shot_id)
    version = _get_owned_version(db, user, shot, version_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(version, field, value)
    db.commit()
    db.refresh(version)
    return schemas.shot_version_out(version)


@router.delete("/shots/{shot_id}/versions/{version_id}")
def delete_version(
    shot_id: int,
    version_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """删除版本：若为选中版本则清空镜头选中引用，避免悬空；并清理产物文件与 Asset 行。"""
    shot = _get_owned_shot(db, user, shot_id)
    version = _get_owned_version(db, user, shot, version_id)
    urls = [version.image_url] if version.image_url else []
    if version.video_url:
        urls.append(version.video_url)
    if shot.selected_version_id == version.id:
        shot.selected_version_id = None
        if shot.video_url and shot.video_url == version.video_url:
            shot.video_url = None
    for a in db.query(models.Asset).filter(models.Asset.project_id == shot.storyboard.project_id).all():
        if (a.meta or {}).get("shot_version_id") == version.id:
            urls.append(a.url)
            db.delete(a)
    db.delete(version)
    db.commit()
    task_engine.purge_asset_files(urls)
    return {"ok": True, "message": "版本已删除"}


@router.post("/shots/{shot_id}/generate-video")
def generate_video(
    shot_id: int,
    body: schemas.GenerateVideoRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    shot = _get_owned_shot(db, user, shot_id)
    has_version = shot.selected_version_id or (
        db.query(ShotVersion).filter(ShotVersion.shot_id == shot.id).first() is not None
    )
    if not has_version:
        raise HTTPException(status_code=400, detail="该镜头还没有图片版本，请先生成图片")
    payload = {
        "shot_id": shot.id,
        "seconds": body.seconds if body else "5",
        "prompt_override": body.prompt_override if body else None,
        "retryable": True,
    }
    task = task_engine.submit_task(db, shot.storyboard.project_id, models.TaskType.video, payload)
    return {"task_id": task.id}


@router.post("/shots/{shot_id}/regenerate")
def regenerate(
    shot_id: int,
    body: schemas.ShotRegenerateRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """重新抽卡：等价于对该镜头所属分镜提交单版本出图任务。"""
    shot = _get_owned_shot(db, user, shot_id)
    payload = {
        "storyboard_id": shot.storyboard_id,
        "count": 1,
        "prompt_override": body.prompt_override if body else None,
        "seed": body.seed if body else None,
        "retryable": True,
    }
    task = task_engine.submit_task(db, shot.storyboard.project_id, models.TaskType.image, payload)
    return {"task_id": task.id}
