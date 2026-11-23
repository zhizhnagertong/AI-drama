"""项目接口：CRUD、生成剧本、一键流水线。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.db import get_db
from .. import models, schemas
from ..models import Episode, Project, Prompt, User
from ..services import storage, task_engine

router = APIRouter()

# 默认负面提示词（创建项目时写入 prompts 表，出图时使用）
DEFAULT_NEGATIVE_PROMPT = (
    "no text, no watermark, no logo, no signature, deformed hands, extra limbs, "
    "extra fingers, blurry, low quality, distorted face, ugly"
)


def get_owned_project(db: Session, user: User, project_id: int) -> Project:
    """按归属校验项目，不存在或非本人返回 404（避免资源探测）。"""
    project = db.get(Project, project_id)
    if project is None or project.deleted or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("")
def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    keyword: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(Project).filter(Project.user_id == user.id, Project.deleted.is_(False))
    if status:
        try:
            query = query.filter(Project.status == models.ProjectStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"非法的项目状态: {status}")
    if keyword:
        kw = f"%{keyword}%"
        query = query.filter(or_(Project.title.like(kw), Project.genre.like(kw)))
    total = query.count()
    items = query.order_by(Project.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [schemas.project_out(p) for p in items], "total": total}


@router.post("")
def create_project(
    body: schemas.ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = Project(
        user_id=user.id,
        title=body.title.strip() or "未命名项目",
        genre=body.genre,
        style=body.style,
        aspect_ratio=body.aspect_ratio or "9:16",
        inspiration=body.inspiration,
        voice_config=body.voice_config,
    )
    db.add(project)
    db.flush()
    # 预置负面提示词
    db.add(Prompt(project_id=project.id, type="negative", content=DEFAULT_NEGATIVE_PROMPT))
    # 自动创建第 1 集（项目 → 剧集 → 分镜 三层结构的入口）
    db.add(
        Episode(
            project_id=project.id,
            episode_number=1,
            title="第1集",
            inspiration=body.inspiration,
            style=project.style,
            aspect_ratio=project.aspect_ratio,
            voice_config=project.voice_config,
        )
    )
    db.commit()
    db.refresh(project)
    return schemas.project_out(project)


def _live_episode_ids():
    """未软删除的剧集 id 子查询。"""
    return select(Episode.id).where(Episode.deleted.is_(False))


def _sb_alive_clause():
    """分镜可见条件：未挂集（项目级）或所属剧集未软删除。

    剧集是软删除的，分镜行不会随之消失，因此所有按项目统计/查询分镜的查询
    都必须带上该条件，否则已删剧集的分镜仍会出现在工作台并继续可操作。
    """
    return or_(
        models.Storyboard.episode_id.is_(None),
        models.Storyboard.episode_id.in_(_live_episode_ids()),
    )


def _tl_alive_clause():
    """时间线可见条件：未挂集或所属剧集未软删除。"""
    return or_(
        models.Timeline.episode_id.is_(None),
        models.Timeline.episode_id.in_(_live_episode_ids()),
    )


def _project_stats(db: Session, project: Project) -> dict:
    storyboard_count = (
        db.query(func.count(models.Storyboard.id))
        .filter(models.Storyboard.project_id == project.id, _sb_alive_clause())
        .scalar()
        or 0
    )
    shot_rows = (
        db.query(models.Shot.id, models.Shot.status, models.Shot.video_url)
        .join(models.Storyboard, models.Shot.storyboard_id == models.Storyboard.id)
        .filter(models.Storyboard.project_id == project.id, _sb_alive_clause())
        .all()
    )
    completed = sum(1 for _, s, _ in shot_rows if models.ShotStatus(s) == models.ShotStatus.ready)
    videos = sum(1 for _, _, v in shot_rows if v)
    return {
        "storyboard_count": int(storyboard_count),
        "shot_count": len(shot_rows),
        "completed_count": completed,
        "video_count": videos,
    }


def _episode_stats(db: Session, episode_id: int) -> dict:
    """单集统计：分镜数 / 镜头数 / 已出图数 / 视频数 / 是否已有成片。"""
    storyboard_count = (
        db.query(func.count(models.Storyboard.id))
        .filter(models.Storyboard.episode_id == episode_id)
        .scalar()
        or 0
    )
    shot_rows = (
        db.query(models.Shot.id, models.Shot.status, models.Shot.video_url)
        .join(models.Storyboard, models.Shot.storyboard_id == models.Storyboard.id)
        .filter(models.Storyboard.episode_id == episode_id)
        .all()
    )
    completed = sum(1 for _, s, _ in shot_rows if models.ShotStatus(s) == models.ShotStatus.ready)
    videos = sum(1 for _, _, v in shot_rows if v)
    timeline = (
        db.query(models.Timeline)
        .filter(
            models.Timeline.episode_id == episode_id,
            models.Timeline.status == models.TimelineStatus.completed,
        )
        .order_by(models.Timeline.id.desc())
        .first()
    )
    return {
        "storyboard_count": int(storyboard_count),
        "shot_count": len(shot_rows),
        "completed_count": completed,
        "video_count": videos,
        "has_final": timeline is not None and bool(timeline.output_url),
    }


@router.get("/{project_id}")
def get_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, user, project_id)
    data = schemas.project_out(project, stats=_project_stats(db, project))
    # 聚合创作工作台所需数据：剧集/分镜(含镜头版本)/角色/素材/时间线
    eps = (
        db.query(models.Episode)
        .filter(models.Episode.project_id == project.id, models.Episode.deleted.is_(False))
        .order_by(models.Episode.episode_number)
        .all()
    )
    data["episodes"] = [
        schemas.episode_out(e, stats=_episode_stats(db, e.id)) for e in eps
    ]
    sbs = (
        db.query(models.Storyboard)
        .filter(models.Storyboard.project_id == project.id, _sb_alive_clause())
        .order_by(models.Storyboard.seq)
        .all()
    )
    data["storyboards"] = [schemas.storyboard_out(sb) for sb in sbs]
    data["characters"] = [
        schemas.character_out(c)
        for c in db.query(models.Character)
        .filter(models.Character.project_id == project.id)
        .all()
    ]
    data["assets"] = [
        schemas.asset_out(a)
        for a in db.query(models.Asset)
        .filter(models.Asset.project_id == project.id)
        .order_by(models.Asset.id.desc())
        .all()
    ]
    data["timelines"] = [
        schemas.timeline_out(t)
        for t in db.query(models.Timeline)
        .filter(models.Timeline.project_id == project.id, _tl_alive_clause())
        .order_by(models.Timeline.id.desc())
        .all()
    ]
    return data


@router.post("/{project_id}/generate-cover")
def generate_cover(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """提交项目封面生成任务（异步），完成后通过 SSE 推送并写入 cover_url。"""
    project = get_owned_project(db, user, project_id)
    task = task_engine.submit_task(
        db, project.id, models.TaskType.cover, {"retryable": True}
    )
    return {"task_id": task.id}


# 允许的状态流转：防止把已完成的项目直接打回草稿、或跳过制作直接标完成
_PROJECT_TRANSITIONS: dict[models.ProjectStatus, set[models.ProjectStatus]] = {
    models.ProjectStatus.draft: {
        models.ProjectStatus.script_ready,
        models.ProjectStatus.producing,
        models.ProjectStatus.failed,
    },
    models.ProjectStatus.script_ready: {
        models.ProjectStatus.draft,
        models.ProjectStatus.producing,
        models.ProjectStatus.failed,
    },
    models.ProjectStatus.producing: {
        models.ProjectStatus.script_ready,
        models.ProjectStatus.completed,
        models.ProjectStatus.failed,
    },
    models.ProjectStatus.completed: {
        models.ProjectStatus.producing,
        models.ProjectStatus.failed,
    },
    models.ProjectStatus.failed: {
        models.ProjectStatus.draft,
        models.ProjectStatus.script_ready,
        models.ProjectStatus.producing,
    },
}


def _validate_project_status(
    db: Session, project: Project, target: models.ProjectStatus
) -> None:
    if target == project.status:
        return
    allowed = _PROJECT_TRANSITIONS.get(project.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"不允许的状态流转：{project.status.value} → {target.value}",
        )
    if target == models.ProjectStatus.completed:
        from ..models import Timeline, TimelineStatus

        has_final = (
            db.query(Timeline.id)
            .filter(
                Timeline.project_id == project.id,
                Timeline.status == TimelineStatus.completed,
                Timeline.output_url.isnot(None),
            )
            .first()
        )
        if has_final is None:
            raise HTTPException(status_code=400, detail="尚无已完成的成片，无法标记为已完成")


@router.put("/{project_id}")
def update_project(
    project_id: int,
    body: schemas.ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, user, project_id)
    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        raw = data["status"]
        try:
            data["status"] = models.ProjectStatus(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"非法的项目状态: {raw}")
        _validate_project_status(db, project, data["status"])
    for field, value in data.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return schemas.project_out(project)


def _purge_project(db: Session, project_id: int) -> list[str]:
    """硬删除项目及其全部关联数据，返回已生成文件的 URL 列表（供提交后清理磁盘）。"""
    sb_ids = [
        r[0]
        for r in db.query(models.Storyboard.id)
        .filter(models.Storyboard.project_id == project_id)
        .all()
    ]
    shot_ids: list[int] = []
    if sb_ids:
        shot_ids = [
            r[0]
            for r in db.query(models.Shot.id)
            .filter(models.Shot.storyboard_id.in_(sb_ids))
            .all()
        ]

    # 先收集产物文件 URL，再删行
    urls: list[str] = []
    urls += [u for (u,) in db.query(models.Asset.url).filter(models.Asset.project_id == project_id).all()]
    urls += [
        u
        for (u,) in db.query(Project.cover_url)
        .filter(Project.id == project_id, Project.cover_url.isnot(None))
        .all()
    ]
    urls += [
        u
        for (u,) in db.query(models.Character.ref_image_url)
        .filter(models.Character.project_id == project_id, models.Character.ref_image_url.isnot(None))
        .all()
    ]
    urls += [
        u
        for (u,) in db.query(models.Timeline.output_url)
        .filter(models.Timeline.project_id == project_id, models.Timeline.output_url.isnot(None))
        .all()
    ]
    if shot_ids:
        for iu, vu in (
            db.query(models.ShotVersion.image_url, models.ShotVersion.video_url)
            .filter(models.ShotVersion.shot_id.in_(shot_ids))
            .all()
        ):
            urls.append(iu)
            if vu:
                urls.append(vu)
        urls += [
            u
            for (u,) in db.query(models.Shot.video_url)
            .filter(models.Shot.id.in_(shot_ids), models.Shot.video_url.isnot(None))
            .all()
        ]

    # 按依赖顺序物理删除：版本 → 镜头 → 分镜 → 剧集 → 其余子表 → 项目
    if shot_ids:
        db.query(models.ShotVersion).filter(models.ShotVersion.shot_id.in_(shot_ids)).delete(
            synchronize_session=False
        )
        db.query(models.Shot).filter(models.Shot.id.in_(shot_ids)).delete(synchronize_session=False)
    if sb_ids:
        db.query(models.Storyboard).filter(models.Storyboard.id.in_(sb_ids)).delete(
            synchronize_session=False
        )
    # Timeline 引用 episodes 外键，须先于 Episode 删除
    for model in (
        models.Timeline,
        models.Episode,
        models.Character,
        models.Asset,
        models.GenTask,
        models.AgentRun,
        models.Prompt,
    ):
        db.query(model).filter(model.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
    return urls


def _remove_files(urls: list[str]) -> None:
    """尽力清理本地产物文件；单个文件失败不阻断删除流程。"""
    for u in urls:
        if not u.startswith("/static/"):
            continue
        try:
            storage.local_path(u).unlink(missing_ok=True)
        except OSError:
            pass


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, user, project_id)
    file_urls = _purge_project(db, project.id)
    db.commit()
    _remove_files(file_urls)
    return {"ok": True, "message": "项目已彻底删除"}


def _default_episode(db: Session, project: Project) -> Episode | None:
    """取项目当前最小未删集号（用于项目级生成入口向后兼容路由）。"""
    return (
        db.query(Episode)
        .filter(Episode.project_id == project.id, Episode.deleted.is_(False))
        .order_by(Episode.episode_number)
        .first()
    )


@router.post("/{project_id}/generate-script")
def generate_script(
    project_id: int,
    body: schemas.GenerateScriptRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, user, project_id)
    # 不显式传入时交给任务层按 梗概 > 集灵感 > 项目灵感 解析
    inspiration = (body.inspiration if body and body.inspiration else None) or None
    payload: dict = {"retryable": True}
    if inspiration:
        payload["inspiration"] = inspiration
    ep = _default_episode(db, project)
    if ep is not None:
        payload["episode_id"] = ep.id
    task = task_engine.submit_task(db, project.id, models.TaskType.script, payload)
    return {"task_id": task.id}


@router.post("/{project_id}/pipeline")
def pipeline(
    project_id: int,
    body: schemas.GenerateScriptRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """一键流水线：剧本完成后自动为每个分镜提交出图任务（每镜 2 版）。"""
    project = get_owned_project(db, user, project_id)
    # 不显式传入时交给任务层按 梗概 > 集灵感 > 项目灵感 解析
    inspiration = (body.inspiration if body and body.inspiration else None) or None
    payload: dict = {"pipeline": True, "retryable": True}
    if inspiration:
        payload["inspiration"] = inspiration
    ep = _default_episode(db, project)
    if ep is not None:
        payload["episode_id"] = ep.id
    task = task_engine.submit_task(db, project.id, models.TaskType.script, payload)
    return {"task_id": task.id}
