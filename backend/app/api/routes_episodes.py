"""剧集接口：项目下的多集 CRUD、按集剧本生成 / 流水线、按集统计。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.db import get_db
from .. import models, schemas
from ..models import Episode, User
from ..api.routes_projects import get_owned_project, _episode_stats
from ..services import task_engine

router = APIRouter()

# 单次批量出图/出视频的分镜上限：每个分镜都会创建一个付费 AI 任务
MAX_BATCH_SIZE = 50


def get_owned_episode(db: Session, user: User, episode_id: int) -> Episode:
    ep = db.get(Episode, episode_id)
    if ep is None or ep.deleted:
        raise HTTPException(status_code=404, detail="剧集不存在")
    project = db.get(models.Project, ep.project_id)
    if project is None or project.deleted or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="剧集不存在")
    return ep


@router.get("/projects/{project_id}/episodes")
def list_episodes(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, user, project_id)
    eps = (
        db.query(Episode)
        .filter(Episode.project_id == project.id, Episode.deleted.is_(False))
        .order_by(Episode.episode_number)
        .all()
    )
    return {
        "items": [schemas.episode_out(e, stats=_episode_stats(db, e.id)) for e in eps],
        "total": len(eps),
    }


@router.post("/projects/{project_id}/episodes")
def create_episode(
    project_id: int,
    body: schemas.EpisodeCreate | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """新增一集：episode_number 取当前最大值 +1（软删的集不占号），并锁定生成配置快照。"""
    project = get_owned_project(db, user, project_id)
    # 串行化同一项目的建集请求：episode_number = max+1 在并发下会算到同一个值。
    # 行锁持有到事务提交（SQLite 忽略 FOR UPDATE，测试环境不受影响）。
    db.query(models.Project).filter(models.Project.id == project.id).with_for_update().first()
    max_num = (
        db.query(func.max(Episode.episode_number))
        .filter(Episode.project_id == project.id, Episode.deleted.is_(False))
        .scalar()
        or 0
    )
    next_num = max_num + 1
    ep = Episode(
        project_id=project.id,
        episode_number=next_num,
        title=(body.title if body and body.title else f"第{next_num}集"),
        synopsis=body.synopsis if body else None,
        inspiration=body.inspiration if body else None,
        # 配置快照：建集时固化项目当前风格/比例/配音，后续项目改动不影响本集
        style=project.style,
        aspect_ratio=project.aspect_ratio,
        voice_config=project.voice_config,
        status=models.EpisodeStatus.draft,
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return schemas.episode_out(ep, stats=_episode_stats(db, ep.id))


@router.get("/episodes/{episode_id}/pipeline-status")
def pipeline_status(
    episode_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """按集返回 6 环节流水线状态（done / partial / pending + 计数），供工作台侧栏与顶栏使用。"""
    ep = get_owned_episode(db, user, episode_id)
    sbs = db.query(models.Storyboard).filter(models.Storyboard.episode_id == ep.id).all()
    sb_ids = {sb.id for sb in sbs}
    shots = (
        db.query(models.Shot).filter(models.Shot.storyboard_id.in_(sb_ids)).all() if sb_ids else []
    )
    shot_ids = {sh.id for sh in shots}
    versions = (
        db.query(models.ShotVersion)
        .filter(models.ShotVersion.shot_id.in_(shot_ids))
        .all() if shot_ids else []
    )
    selected_shot_ids = {sh.id for sh in shots if sh.selected_version_id}
    video_shot_ids = {v.shot_id for v in versions if v.video_url} | {
        sh.id for sh in shots if sh.video_url
    }
    char_count = (
        db.query(func.count(models.Character.id))
        .filter(models.Character.project_id == ep.project_id)
        .scalar()
        or 0
    )
    # 配音：该集有台词的分镜中，已有 audio asset（meta.storyboard_id）的数量
    dialogue_ids = {sb.id for sb in sbs if sb.dialogue and sb.dialogue.strip()}
    voiced_ids: set[int] = set()
    if dialogue_ids:
        audio_assets = (
            db.query(models.Asset)
            .filter(
                models.Asset.project_id == ep.project_id,
                models.Asset.type == models.AssetType.audio,
            )
            .all()
        )
        for a in audio_assets:
            sb_id = (a.meta or {}).get("storyboard_id")
            if sb_id and int(sb_id) in dialogue_ids:
                voiced_ids.add(int(sb_id))
    final_tl = (
        db.query(models.Timeline)
        .filter(
            models.Timeline.episode_id == ep.id,
            models.Timeline.status == models.TimelineStatus.completed,
        )
        .order_by(models.Timeline.id.desc())
        .first()
    )
    tl_count = (
        db.query(func.count(models.Timeline.id))
        .filter(models.Timeline.episode_id == ep.id)
        .scalar()
        or 0
    )

    def step(done: bool, partial: bool) -> str:
        return "done" if done else ("partial" if partial else "pending")

    total = len(sbs)
    steps = {
        "script": {"status": step(total > 0, False), "count": total},
        "character": {"status": step(char_count > 0, False), "count": char_count},
        "board": {"status": step(total > 0, False), "count": total},
        "image": {
            "status": step(total > 0 and len(selected_shot_ids) >= total, len(selected_shot_ids) > 0),
            "completed": len(selected_shot_ids),
            "total": total,
        },
        "video": {
            "status": step(total > 0 and len(video_shot_ids) >= total, len(video_shot_ids) > 0),
            "completed": len(video_shot_ids),
            "total": total,
        },
        "voice": {
            "status": step(
                bool(dialogue_ids) and len(voiced_ids) >= len(dialogue_ids),
                len(voiced_ids) > 0,
            ),
            "completed": len(voiced_ids),
            "total": len(dialogue_ids),
        },
        "final": {
            "status": "done" if final_tl else ("partial" if tl_count else "pending"),
            "merged_url": final_tl.output_url if final_tl else None,
        },
    }
    return {"episode_id": ep.id, "steps": steps}


@router.post("/episodes/{episode_id}/batch-images")
def batch_images(
    episode_id: int,
    body: schemas.BatchImageRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """批量出图：storyboard_ids 缺省 = 该集所有还没有已选画面的分镜。"""
    ep = get_owned_episode(db, user, episode_id)
    ids = body.storyboard_ids if body and body.storyboard_ids else None
    count = body.count if body else 2
    # 规模上限 + 去重：每个分镜都会创建一个付费出图任务，重复 id 会重复扣费
    if ids:
        ids = list(dict.fromkeys(ids))
        if len(ids) > MAX_BATCH_SIZE:
            raise HTTPException(
                status_code=400, detail=f"单次最多批量处理 {MAX_BATCH_SIZE} 个分镜"
            )
        sbs = (
            db.query(models.Storyboard)
            .filter(models.Storyboard.id.in_(ids), models.Storyboard.episode_id == ep.id)
            .all()
        )
        if len(sbs) != len(set(ids)):
            raise HTTPException(status_code=400, detail="存在不属于该集的分镜")
    else:
        sbs = (
            db.query(models.Storyboard)
            .filter(models.Storyboard.episode_id == ep.id)
            .order_by(models.Storyboard.seq)
            .all()
        )
        keep = []
        for sb in sbs:
            shot = db.query(models.Shot).filter(models.Shot.storyboard_id == sb.id).first()
            if shot is None or not shot.selected_version_id:
                keep.append(sb)
        sbs = keep
        if len(sbs) > MAX_BATCH_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"该集待出图分镜 {len(sbs)} 个，超过单次上限 {MAX_BATCH_SIZE}，请分批提交",
            )
    task_ids = [
        task_engine.submit_task(
            db,
            ep.project_id,
            models.TaskType.image,
            {"storyboard_id": sb.id, "count": count, "retryable": True},
        ).id
        for sb in sbs
    ]
    return {"task_ids": task_ids, "submitted": len(task_ids)}


@router.post("/episodes/{episode_id}/batch-videos")
def batch_videos(
    episode_id: int,
    body: schemas.BatchVideoRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """批量出视频：storyboard_ids 缺省 = 该集已选定画面且尚无视频的分镜；显式传入则强制生成。"""
    ep = get_owned_episode(db, user, episode_id)
    seconds = body.seconds if body else "5"
    ids = body.storyboard_ids if body and body.storyboard_ids else None
    if ids:
        ids = list(dict.fromkeys(ids))
        if len(ids) > MAX_BATCH_SIZE:
            raise HTTPException(
                status_code=400, detail=f"单次最多批量处理 {MAX_BATCH_SIZE} 个分镜"
            )
    query = db.query(models.Storyboard).filter(models.Storyboard.episode_id == ep.id)
    if ids:
        query = query.filter(models.Storyboard.id.in_(ids))
    sbs = query.order_by(models.Storyboard.seq).all()
    if ids and len(sbs) != len(set(ids)):
        raise HTTPException(status_code=400, detail="存在不属于该集的分镜")
    task_ids: list[int] = []
    skipped: list[int] = []
    for sb in sbs:
        shot = db.query(models.Shot).filter(models.Shot.storyboard_id == sb.id).first()
        if shot is None:
            skipped.append(sb.id)
            continue
        has_video = shot.video_url or any(v.video_url for v in (shot.versions or []))
        has_any_version = bool(shot.selected_version_id) or bool(shot.versions)
        # 缺省模式只挑已选定画面的；显式传入时强制生成，但完全没有画面的仍跳过
        eligible = not has_video and has_any_version and (bool(ids) or bool(shot.selected_version_id))
        if not eligible:
            skipped.append(sb.id)
            continue
        task_ids.append(
            task_engine.submit_task(
                db,
                ep.project_id,
                models.TaskType.video,
                {"shot_id": shot.id, "seconds": seconds, "retryable": True},
            ).id
        )
    return {"task_ids": task_ids, "submitted": len(task_ids), "skipped": skipped}


@router.post("/episodes/{episode_id}/extract-characters")
def extract_characters(
    episode_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """只重提角色：按该集现有分镜文本重新提取/更新角色，不删除分镜。"""
    from ..agents import writer

    ep = get_owned_episode(db, user, episode_id)
    project = db.get(models.Project, ep.project_id)
    sbs = (
        db.query(models.Storyboard)
        .filter(models.Storyboard.episode_id == ep.id)
        .order_by(models.Storyboard.seq)
        .all()
    )
    if not sbs:
        raise HTTPException(status_code=400, detail="该集还没有分镜，请先生成剧本")
    script_text = "\n".join(
        f"{sb.seq}. {sb.scene or ''} 台词：{sb.dialogue or '无'}" for sb in sbs
    )
    data = writer.extract_characters(db, project, script_text)
    created = 0
    updated = 0
    for c in data.get("characters", []):
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        char = (
            db.query(models.Character)
            .filter(models.Character.project_id == project.id, models.Character.name == name)
            .first()
        )
        if char is None:
            char = models.Character(project_id=project.id, name=name)
            db.add(char)
            created += 1
        else:
            updated += 1
        if c.get("description"):
            char.description = c["description"]
        if c.get("prompt_template"):
            char.prompt_template = c["prompt_template"]
        if c.get("voice"):
            char.voice = str(c["voice"])
    db.commit()
    return {"created": created, "updated": updated}


@router.get("/episodes/{episode_id}/composite-check")
def composite_check(
    episode_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """合成预检：返回该集缺少视频的镜头清单（时间线会自动跳过它们）。"""
    ep = get_owned_episode(db, user, episode_id)
    sbs = (
        db.query(models.Storyboard)
        .filter(models.Storyboard.episode_id == ep.id)
        .order_by(models.Storyboard.seq)
        .all()
    )
    missing = []
    ready = 0
    for sb in sbs:
        shot = db.query(models.Shot).filter(models.Shot.storyboard_id == sb.id).first()
        if shot and (shot.video_url or any(v.video_url for v in (shot.versions or []))):
            ready += 1
        else:
            missing.append({"storyboard_id": sb.id, "seq": sb.seq, "scene": (sb.scene or "")[:40]})
    return {"ready": ready, "total": len(sbs), "missing": missing}


@router.get("/episodes/{episode_id}")
def get_episode(
    episode_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ep = get_owned_episode(db, user, episode_id)
    data = schemas.episode_out(ep, stats=_episode_stats(db, ep.id))
    sbs = (
        db.query(models.Storyboard)
        .filter(models.Storyboard.episode_id == ep.id)
        .order_by(models.Storyboard.seq)
        .all()
    )
    data["storyboards"] = [schemas.storyboard_out(sb) for sb in sbs]
    data["timelines"] = [
        schemas.timeline_out(t)
        for t in db.query(models.Timeline)
        .filter(models.Timeline.episode_id == ep.id)
        .order_by(models.Timeline.id.desc())
        .all()
    ]
    return data


@router.put("/episodes/{episode_id}")
def update_episode(
    episode_id: int,
    body: schemas.EpisodeUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ep = get_owned_episode(db, user, episode_id)
    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        raw = data["status"]
        try:
            data["status"] = models.EpisodeStatus(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"非法的剧集状态: {raw}")
    for field, value in data.items():
        setattr(ep, field, value)
    db.commit()
    db.refresh(ep)
    return schemas.episode_out(ep, stats=_episode_stats(db, ep.id))


@router.delete("/episodes/{episode_id}")
def delete_episode(
    episode_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """软删除一集：其分镜/时间线保留但不可达；项目仅剩一集时不允许删除。"""
    ep = get_owned_episode(db, user, episode_id)
    remaining = (
        db.query(func.count(Episode.id))
        .filter(Episode.project_id == ep.project_id, Episode.deleted.is_(False))
        .scalar()
        or 0
    )
    if remaining <= 1:
        raise HTTPException(status_code=400, detail="项目至少需保留一集，请改为删除项目")
    ep.deleted = True
    db.commit()
    return {"ok": True, "message": "剧集已删除"}


@router.post("/episodes/{episode_id}/generate-script")
def generate_script(
    episode_id: int,
    body: schemas.GenerateScriptRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ep = get_owned_episode(db, user, episode_id)
    # 创作者编写过的故事梗概优先于建集时的灵感
    inspiration = (
        (body.inspiration if body and body.inspiration else None)
        or ep.synopsis
        or ep.inspiration
        or ""
    )
    task = task_engine.submit_task(
        db,
        ep.project_id,
        models.TaskType.script,
        {"inspiration": inspiration, "episode_id": ep.id, "retryable": True},
    )
    return {"task_id": task.id}


@router.post("/episodes/{episode_id}/pipeline")
def pipeline(
    episode_id: int,
    body: schemas.GenerateScriptRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """按集一键流水线：剧本完成后自动为该集每个分镜提交出图任务（每镜 2 版）。"""
    ep = get_owned_episode(db, user, episode_id)
    # 创作者编写过的故事梗概优先于建集时的灵感
    inspiration = (
        (body.inspiration if body and body.inspiration else None)
        or ep.synopsis
        or ep.inspiration
        or ""
    )
    task = task_engine.submit_task(
        db,
        ep.project_id,
        models.TaskType.script,
        {"inspiration": inspiration, "episode_id": ep.id, "pipeline": True, "retryable": True},
    )
    return {"task_id": task.id}
