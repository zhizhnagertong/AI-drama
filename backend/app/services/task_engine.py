"""进程内异步任务引擎：模块级队列 + 4 个 worker 协程。

- submit_task：写 gen_tasks（幂等键去重）并投递内部队列；
- worker：取任务 → 独立 SessionLocal 会话执行 handler → 状态/进度变化均
  commit 并通过 event_bus.publish 推送 SSE 事件；
- handler 为同步函数，统一由 asyncio.to_thread 执行，避免阻塞事件循环。
"""
import asyncio
import enum
import random
import traceback

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from .. import models
from ..core.db import SessionLocal
from . import event_bus

QUEUE: asyncio.Queue = asyncio.Queue()
_workers: list[asyncio.Task] = []
_loop: asyncio.AbstractEventLoop | None = None


def _enqueue(task_id: int) -> None:
    """线程安全入队：worker 线程（to_thread）内提交任务时经主循环投递。"""
    if _loop is None:
        QUEUE.put_nowait(task_id)
        return
    try:
        current = asyncio.get_running_loop()
    except RuntimeError:
        current = None
    if current is _loop:
        QUEUE.put_nowait(task_id)
    else:
        _loop.call_soon_threadsafe(QUEUE.put_nowait, task_id)


# ---------------- 事件 ----------------
def _enum_value(x):
    return x.value if isinstance(x, enum.Enum) else x


class TaskGone(Exception):
    """任务行已被删除（例如所属项目被彻底删除），handler 应立即停止。

    worker 持有一个跨会话的 ORM 对象；项目删除走 bulk delete 会直接删掉
    gen_tasks 行，此后任何 commit 都会抛 StaleDataError。必须把这个场景与
    普通任务失败区分开：既不能写 failed 终态（行已不存在），也不该重试。
    """


def _task_still_exists(db: Session, task_id: int) -> bool:
    """独立查询任务行是否还在（不受当前 session 快照影响）。"""
    return (
        db.query(models.GenTask.id).filter(models.GenTask.id == task_id).scalar()
        is not None
    )


def _publish(task: models.GenTask) -> None:
    event_bus.publish(
        task.project_id,
        {
            "type": "task_update",
            "task_id": task.id,
            "task_type": _enum_value(task.type),
            "status": _enum_value(task.status),
            "progress": task.progress or 0,
            "error": task.error,
        },
    )


def update_progress(
    db: Session,
    task: models.GenTask,
    progress: int | None = None,
    status: models.TaskStatus | None = None,
) -> None:
    """handler 内部更新进度/状态：每次变化都 commit 并推送事件。

    任务所属项目可能在 handler 执行期间被删除（bulk delete 直接删掉 gen_tasks 行）。
    此时 commit 会抛 StaleDataError，且 session 进入 rollback-only 状态；
    必须先 rollback 恢复，再抛 TaskGone 让 worker 优雅终止，避免二次异常。
    """
    # 先取 id：rollback 会让 ORM 对象属性过期，之后不能再访问 task.*
    task_id = task.id
    # 先探测行是否还在：比依赖 commit 抛错更早、更可控
    if not _task_still_exists(db, task_id):
        db.rollback()
        raise TaskGone(f"task {task_id} no longer exists")

    if progress is not None:
        task.progress = max(0, min(100, int(progress)))
    if status is not None:
        task.status = status
    try:
        db.commit()
    except StaleDataError:
        # 探测与 commit 之间行被删（竞态窗口）：统一按任务消失处理
        db.rollback()
        raise TaskGone(f"task {task_id} deleted during commit") from None
    _publish(task)


# ---------------- 提交 / 重试 ----------------
def submit_task(
    db: Session,
    project_id: int,
    type_: models.TaskType,
    payload: dict | None = None,
    idempotency_key: str | None = None,
) -> models.GenTask:
    """创建任务并入队；幂等键重复时直接返回已存在任务。"""
    if idempotency_key:
        existing = db.query(models.GenTask).filter_by(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing
    task = models.GenTask(
        project_id=project_id,
        type=type_,
        status=models.TaskStatus.queued,
        progress=0,
        payload=payload or {},
        idempotency_key=idempotency_key,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    _publish(task)
    _enqueue(task.id)
    return task


def requeue(task_id: int) -> None:
    _enqueue(task_id)


# ---------------- 取消 ----------------
class TaskCanceled(Exception):
    """任务被用户取消，handler 应停止执行。"""


def cancel_task(db: Session, task: models.GenTask) -> None:
    """置 canceled 并推送事件；排队中的任务被 worker 取到时会因状态检查而跳过。"""
    task.status = models.TaskStatus.canceled
    task.error = None
    db.commit()
    _publish(task)


def check_canceled(db: Session, task_id: int) -> None:
    """handler 协作式取消检查点：独立查询最新状态，避免会话快照过期。"""
    status = (
        db.query(models.GenTask.status).filter(models.GenTask.id == task_id).scalar()
    )
    if status == models.TaskStatus.canceled:
        raise TaskCanceled()


def purge_asset_files(urls: list[str]) -> None:
    """尽力清理本地产物文件（按 /static URL）；单个失败不阻断。"""
    from . import storage

    for u in urls:
        if not u or not u.startswith("/static/"):
            continue
        try:
            storage.local_path(u).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


def collect_storyboard_artifacts(
    db: Session, project_id: int, storyboard_ids: list[int]
) -> list[str]:
    """删除分镜前调用：收集其全部产物文件 URL，并删除关联 Asset 行。

    覆盖 ShotVersion.image_url/video_url、Shot.video_url，以及 meta 带
    storyboard_id / shot_id / shot_version_id 的 Asset（图片/配音/视频）。
    不动角色参考图（character_id）与封面（cover）。返回去重 URL 供 purge_asset_files。
    须在级联删除 Storyboard 之前调用（否则查不到 shot/version）。
    """
    if not storyboard_ids:
        return []
    urls: set[str] = set()
    shots = db.query(models.Shot).filter(models.Shot.storyboard_id.in_(storyboard_ids)).all()
    shot_ids = [sh.id for sh in shots]
    for sh in shots:
        if sh.video_url:
            urls.add(sh.video_url)
    versions = (
        db.query(models.ShotVersion).filter(models.ShotVersion.shot_id.in_(shot_ids)).all()
        if shot_ids
        else []
    )
    version_ids = [v.id for v in versions]
    for v in versions:
        if v.image_url:
            urls.add(v.image_url)
        if v.video_url:
            urls.add(v.video_url)
    sb_set = {str(i) for i in storyboard_ids}
    shot_set = set(shot_ids)
    ver_set = set(version_ids)
    for a in db.query(models.Asset).filter(models.Asset.project_id == project_id).all():
        meta = a.meta or {}
        sb_id = meta.get("storyboard_id")
        if (
            (sb_id is not None and str(sb_id) in sb_set)
            or (meta.get("shot_id") in shot_set)
            or (meta.get("shot_version_id") in ver_set)
        ):
            urls.add(a.url)
            db.delete(a)
    return [u for u in urls if u]


# ---------------- worker ----------------
def recover_pending_tasks() -> int:
    """启动时恢复内存队列丢失的任务（进程重启后 queued/running 无人接管）。

    - queued：尚未开始，直接重新入队（无损）；
    - running：已提交外部 API，重跑会重复计费，故标记 failed 让用户手动决定是否重试。
    返回重新入队数量。
    """
    db = SessionLocal()
    try:
        running = (
            db.query(models.GenTask)
            .filter(models.GenTask.status == models.TaskStatus.running)
            .all()
        )
        for t in running:
            t.status = models.TaskStatus.failed
            t.error = "服务重启导致任务中断，请手动重试"
            t.retries = 3  # 阻断自动重试
        queued = (
            db.query(models.GenTask)
            .filter(models.GenTask.status == models.TaskStatus.queued)
            .order_by(models.GenTask.id)
            .all()
        )
        db.commit()
        ids = [t.id for t in queued]
        for tid in ids:
            QUEUE.put_nowait(tid)
        if running or queued:
            print(
                f"[task_engine] 启动恢复：running→failed {len(running)} 个，"
                f"queued 重新入队 {len(queued)} 个"
            )
        return len(ids)
    finally:
        db.close()


async def start_workers(n: int = 4) -> None:
    global _loop
    _loop = asyncio.get_running_loop()
    recover_pending_tasks()
    for i in range(n):
        _workers.append(asyncio.create_task(_worker_loop(i), name=f"task-worker-{i}"))


async def stop_workers() -> None:
    for w in _workers:
        w.cancel()
    for w in _workers:
        try:
            await w
        except (asyncio.CancelledError, Exception):
            pass
    _workers.clear()


async def _worker_loop(index: int) -> None:
    while True:
        task_id = await QUEUE.get()
        try:
            await asyncio.to_thread(_run_task, task_id)
        except Exception:  # noqa: BLE001  worker 不允许退出
            traceback.print_exc()
        finally:
            QUEUE.task_done()


def _run_task(task_id: int) -> None:
    """在独立会话中执行任务（运行于 to_thread 线程）。"""
    db = SessionLocal()
    try:
        task = db.get(models.GenTask, task_id)
        if task is None or task.status in (models.TaskStatus.succeeded, models.TaskStatus.canceled):
            return
        task.status = models.TaskStatus.running
        if not task.progress:
            task.progress = 1
        try:
            db.commit()
        except StaleDataError:
            # 排队期间项目被删、任务行已不存在：直接放弃，不推送也不重试
            db.rollback()
            return
        _publish(task)

        handler = HANDLERS.get(models.TaskType(task.type))
        no_retry = False  # 配置缺失类错误：重试无意义
        # 终态写入时需要用到的值，先存下来：rollback 后 ORM 对象会过期
        payload = dict(task.payload or {})
        retries = task.retries or 0
        final_status: models.TaskStatus | None = None
        result_value = None
        error_text = ""
        try:
            if handler is None:
                raise RuntimeError(f"未知任务类型: {task.type}")
            result = handler(db, task)
            # handler 执行期间用户可能已取消（cancel_task 在另一会话写 canceled），
            # 写终态前重查最新状态，避免把 canceled 覆盖成 succeeded
            # 行若已被删除（项目被删）同样不能写终态，按消失处理
            latest = db.query(models.GenTask.status).filter(models.GenTask.id == task_id).scalar()
            if latest is None:
                raise TaskGone(f"task {task_id} no longer exists")
            if latest == models.TaskStatus.canceled:
                raise TaskCanceled()
            final_status = models.TaskStatus.succeeded
            result_value = result
        except TaskGone:
            # 任务行已被删除：无需写终态、无需推送、无需重试。
            # rollback 丢弃 handler 未提交的半成品（可能引用了同样被删的 project/asset）。
            db.rollback()
            return
        except TaskCanceled:
            db.rollback()  # 丢弃 handler 未提交的半成品
            final_status = models.TaskStatus.canceled
        except Exception as exc:  # noqa: BLE001
            from .providers.dashscope import ConfigError

            traceback.print_exc()
            # 异常可能来自 StaleDataError / flush 失败，此时 session 处于
            # rollback-only 状态；必须先 rollback 才能再访问 task 属性，
            # 否则会二次抛 PendingRollbackError 导致整个 worker 任务崩掉。
            db.rollback()
            final_status = models.TaskStatus.failed
            error_text = str(exc)[:2000]
            retries += 1
            no_retry = isinstance(exc, ConfigError)

        # rollback 后重新取对象再写终态：原 ORM 实例已过期，直接赋值不会持久化
        if not _task_still_exists(db, task_id):
            db.rollback()
            return
        fresh = db.get(models.GenTask, task_id)
        fresh.status = final_status
        if final_status == models.TaskStatus.succeeded:
            fresh.progress = 100
            fresh.error = None
            fresh.result = result_value
        elif final_status == models.TaskStatus.canceled:
            fresh.error = None
        else:
            fresh.error = error_text
            fresh.retries = retries
        db.commit()
        _publish(fresh)

        # 失败自动重试：payload.retryable 且重试次数 < 3 时重新入队
        if final_status == models.TaskStatus.failed and retries < 3 and not no_retry:
            if payload.get("retryable", False):
                _enqueue(task_id)
    finally:
        db.close()


# ---------------- 提示词组装 ----------------
def _style_preset_for(db: Session, project: models.Project) -> models.StylePreset | None:
    """按项目风格名查该用户启用中的风格预设。"""
    if not project.style:
        return None
    return (
        db.query(models.StylePreset)
        .filter(
            models.StylePreset.user_id == project.user_id,
            models.StylePreset.name == project.style,
            models.StylePreset.is_active.is_(True),
        )
        .first()
    )


def _build_image_prompt(db: Session, project: models.Project, sb: models.Storyboard, override: str | None) -> str:
    """项目风格 + 涉及角色的固定描述词 + 场景/画面提示词 + 负面词。"""
    style_negative = None
    if override:
        base = override.strip()
    else:
        parts: list[str] = []
        if project.style:
            # 命中该用户的启用风格预设时，用其英文提示词替换裸风格名
            preset = _style_preset_for(db, project)
            parts.append(preset.prompt if preset and preset.prompt else str(project.style))
            if preset and preset.negative_prompt:
                style_negative = preset.negative_prompt
        scene_text = " ".join(x for x in [sb.scene or "", sb.dialogue or ""] if x)
        characters = (
            db.query(models.Character).filter(models.Character.project_id == project.id).all()
        )
        for c in characters:
            # 在分镜文本中匹配角色名，注入角色固定描述词
            if c.name and c.name in scene_text and c.prompt_template:
                parts.append(f"{c.name}: {c.prompt_template}")
        if sb.scene:
            parts.append(sb.scene)
        if sb.image_prompt:
            parts.append(sb.image_prompt)
        base = "，".join(p.strip() for p in parts if p and p.strip())

    negative_row = (
        db.query(models.Prompt)
        .filter(models.Prompt.project_id == project.id, models.Prompt.type == "negative")
        .first()
    )
    negative = negative_row.content if negative_row else "no text, no watermark, no logo, deformed hands, extra limbs, blurry, low quality, distorted face"
    if style_negative:
        negative = f"{negative}, {style_negative}"
    return f"{base}. Negative: {negative}"


def _style_text(db: Session, project: models.Project) -> str:
    """项目风格对应的统一画风提示词（预设英文提示词优先，回退裸风格名）。"""
    if not project or not project.style:
        return ""
    preset = _style_preset_for(db, project)
    return (preset.prompt if preset and preset.prompt else str(project.style)).strip()


def _build_video_prompt(db: Session, project: models.Project, sb: models.Storyboard) -> str:
    """统一画风 + 镜头/场景/情绪描述，保证成片与分镜画面风格一致。"""
    parts = []
    style_text = _style_text(db, project)
    if style_text:
        parts.append(style_text)
    if sb.shot_size:
        parts.append(f"{sb.shot_size}镜头")
    if sb.scene:
        parts.append(sb.scene)
    if sb.emotion:
        parts.append(f"角色情绪：{sb.emotion}")
    parts.append("画面连贯自然，保持原画面风格不变，动作流畅")
    return "，".join(parts)


# ---------------- handlers ----------------
def _handle_script(db: Session, task: models.GenTask) -> dict:
    """编剧智能体：生成剧本 → 重建角色/分镜/镜头；pipeline 模式自动提交出图任务。

    payload.episode_id 存在时按集生成（分镜归属该集，只重建该集分镜）；
    缺省回退项目默认集（最小集号），保持项目级入口向后兼容。
    """
    from ..agents import writer

    project = db.get(models.Project, task.project_id)
    if project is None:
        raise RuntimeError("项目不存在")

    payload = task.payload or {}
    episode_id = payload.get("episode_id")
    episode = db.get(models.Episode, episode_id) if episode_id else None
    if episode is not None and episode.project_id != project.id:
        raise RuntimeError("剧集不属于该项目")
    if episode is None:
        episode = (
            db.query(models.Episode)
            .filter(
                models.Episode.project_id == project.id,
                models.Episode.deleted.is_(False),
            )
            .order_by(models.Episode.episode_number)
            .first()
        )

    # 显式传入优先；其次创作者编写的故事梗概，再次集级灵感，最后项目灵感
    inspiration = (
        payload.get("inspiration")
        or ((episode.synopsis or episode.inspiration) if episode else None)
        or project.inspiration
        or ""
    )
    data = writer.generate_script(db, project, inspiration)
    update_progress(db, task, 50)

    pipeline = bool(payload.get("pipeline"))

    # 重新生成场景：删除旧分镜（级联删除 shot / versions）；按集生成时只删该集分镜
    check_canceled(db, task.id)
    sb_query = db.query(models.Storyboard).filter(models.Storyboard.project_id == project.id)
    if episode is not None:
        sb_query = sb_query.filter(models.Storyboard.episode_id == episode.id)
    old_sbs = sb_query.all()
    old_sb_ids = [sb.id for sb in old_sbs]
    stale_urls = collect_storyboard_artifacts(db, project.id, old_sb_ids)
    for sb in old_sbs:
        db.delete(sb)
    db.flush()
    purge_asset_files(stale_urls)

    # 角色：同名更新，否则新建
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
        char.description = c.get("description") or ""
        char.prompt_template = c.get("prompt_template") or ""
        if c.get("voice"):
            char.voice = str(c["voice"])
    db.flush()

    # 分镜逐条入库，并为每条建 1 个 shots 行
    created: list[models.Storyboard] = []
    for i, sb_data in enumerate(data.get("storyboards", []), start=1):
        try:
            duration = int(sb_data.get("duration_sec") or 5)
        except (TypeError, ValueError):
            duration = 5
        sb = models.Storyboard(
            project_id=project.id,
            episode_id=episode.id if episode else None,
            seq=i,  # 序号归一化为 1..n
            shot_size=str(sb_data.get("shot_size") or "中景"),
            scene=str(sb_data.get("scene") or ""),
            dialogue=sb_data.get("dialogue") or None,
            emotion=sb_data.get("emotion") or None,
            duration_sec=max(1, min(60, duration)),
            status=models.StoryboardStatus.pending,
            image_prompt=sb_data.get("image_prompt") or None,
        )
        db.add(sb)
        db.flush()
        db.add(models.Shot(storyboard_id=sb.id, status=models.ShotStatus.pending))
        created.append(sb)

    project.status = models.ProjectStatus.script_ready
    if episode is not None:
        episode.status = models.EpisodeStatus.script_ready
        episode.logline = data.get("logline")
        if not episode.title or episode.title == f"第{episode.episode_number}集":
            episode.title = data.get("title") or episode.title
    # 创建时未填标题的项目：用 AI 生成的剧本标题回填
    if project.title == "未命名项目" and data.get("title"):
        project.title = str(data["title"])[:200]
    update_progress(db, task, 90)

    # 一键流水线：剧本完成后自动为每个分镜提交出图任务（抽卡 2 版）
    if pipeline:
        project.status = models.ProjectStatus.producing
        if episode is not None:
            episode.status = models.EpisodeStatus.producing
        for sb in created:
            submit_task(
                db,
                project.id,
                models.TaskType.image,
                {"storyboard_id": sb.id, "count": 2, "retryable": True},
            )
    db.commit()
    return {
        "title": data.get("title"),
        "logline": data.get("logline"),
        "episode_id": episode.id if episode else None,
        "character_count": len(data.get("characters", [])),
        "storyboard_count": len(created),
    }


def _handle_image(db: Session, task: models.GenTask) -> dict:
    """分镜出图：抽卡 count 个版本（不同 seed），落盘并写 shot_versions。"""
    from .providers import agnes
    from . import storage

    payload = task.payload or {}
    sb = db.get(models.Storyboard, payload.get("storyboard_id"))
    if sb is None or sb.project_id != task.project_id:
        raise RuntimeError("分镜不存在")
    project = db.get(models.Project, task.project_id)

    sb.status = models.StoryboardStatus.generating
    db.commit()
    _publish(task)

    prompt = _build_image_prompt(db, project, sb, payload.get("prompt_override"))
    count = max(1, min(6, int(payload.get("count") or 2)))
    base_seed = payload.get("seed")

    shot = db.query(models.Shot).filter(models.Shot.storyboard_id == sb.id).first()
    if shot is None:
        shot = models.Shot(storyboard_id=sb.id)
        db.add(shot)
        db.flush()
    version_no = (
        db.query(func.max(models.ShotVersion.version_no))
        .filter(models.ShotVersion.shot_id == shot.id)
        .scalar()
        or 0
    )

    try:
        version_ids: list[int] = []
        AGNES_SEED_MAX = 999  # Agnes 图像接口 seed 范围 -1~999
        for i in range(count):
            check_canceled(db, task.id)
            seed = (int(base_seed) + i) % (AGNES_SEED_MAX + 1) if base_seed is not None else random.randint(0, AGNES_SEED_MAX)
            urls = agnes.generate_image(
                prompt, size="2K", ratio=project.aspect_ratio or "9:16", seed=seed
            )
            remote = urls[0]
            local = storage.save_from_url(remote, "images")
            version_no += 1
            version = models.ShotVersion(
                shot_id=shot.id,
                version_no=version_no,
                image_url=local,
                video_url=None,
                prompt=prompt,
                seed=seed,
                is_selected=False,
                status=models.ShotVersionStatus.succeeded,
            )
            db.add(version)
            db.flush()
            # 记录远程地址，供视频生成传参考图（本地地址外网不可达）
            db.add(
                models.Asset(
                    project_id=project.id,
                    type=models.AssetType.image,
                    url=local,
                    meta={"shot_version_id": version.id, "storyboard_id": sb.id, "remote_url": remote},
                )
            )
            version_ids.append(version.id)
            update_progress(db, task, int((i + 1) / count * 95))
    except BaseException:
        # 失败/取消时把分镜从 generating 拉回 pending，避免状态永久卡死
        sb.status = models.StoryboardStatus.pending
        db.commit()
        raise

    shot.status = models.ShotStatus.ready
    # 首次出图自动选中第一个版本，便于后续视频/时间线流程
    if shot.selected_version_id is None and version_ids:
        shot.selected_version_id = version_ids[0]
        db.get(models.ShotVersion, version_ids[0]).is_selected = True
    sb.status = models.StoryboardStatus.ready
    db.commit()
    return {"shot_id": shot.id, "version_ids": version_ids}


def _handle_ref_image(db: Session, task: models.GenTask) -> dict:
    """角色定妆照：多角度主形象图（统一注入项目风格预设，保证全项目画风一致）。"""
    from .providers import agnes
    from . import storage

    char = db.get(models.Character, (task.payload or {}).get("character_id"))
    if char is None or char.project_id != task.project_id:
        raise RuntimeError("角色不存在")
    project = db.get(models.Project, task.project_id)
    preset = _style_preset_for(db, project) if project else None
    style_text = _style_text(db, project) if project else ""
    parts = [
        style_text,
        char.prompt_template or char.description or char.name or "",
        "character reference sheet, 同一角色多角度设定图（正面、侧面、全身），纯色背景，高质量，细节丰富",
    ]
    if style_text:
        # 结尾重复并强调画风，防止角色描述把模型带偏到写实/3D 等其他风格
        parts.append(f"所有视角严格保持同一画风，禁止混合风格：{style_text}")
    prompt = "，".join(p.strip() for p in parts if p and p.strip())
    negative_row = (
        db.query(models.Prompt)
        .filter(models.Prompt.project_id == task.project_id, models.Prompt.type == "negative")
        .first()
    )
    neg_list = [
        negative_row.content if negative_row else None,
        preset.negative_prompt if preset else None,
        "mixed styles, inconsistent art style, style collision" if style_text else None,
    ]
    negatives = [n for n in neg_list if n]
    if negatives:
        prompt += ". Negative: " + ", ".join(negatives)
    seed = random.randint(0, 999)  # Agnes seed 范围 -1~999
    urls = agnes.generate_image(prompt, size="2K", ratio="1:1", seed=seed)
    remote = urls[0]
    local = storage.save_from_url(remote, "images")
    char.ref_image_url = local
    db.add(
        models.Asset(
            project_id=task.project_id,
            type=models.AssetType.image,
            url=local,
            meta={"character_id": char.id, "remote_url": remote},
        )
    )
    db.commit()
    return {"ref_image_url": local}


def _handle_cover(db: Session, task: models.GenTask) -> dict:
    """项目封面：按项目风格/题材/灵感生成海报图，写入 projects.cover_url。"""
    from .providers import agnes
    from . import storage

    project = db.get(models.Project, task.project_id)
    if project is None:
        raise RuntimeError("项目不存在")
    update_progress(db, task, 5)

    style_text = str(project.style or "")
    preset = (
        db.query(models.StylePreset)
        .filter(
            models.StylePreset.user_id == project.user_id,
            models.StylePreset.name == style_text,
            models.StylePreset.is_active.is_(True),
        )
        .first()
    )
    if preset and preset.prompt:
        style_text = preset.prompt
    parts = [style_text, str(project.genre or ""), str(project.title or "")]
    if project.inspiration:
        parts.append(project.inspiration[:200])
    parts.append(
        "短剧海报封面，电影感构图，主体突出，高质量，细节丰富，无文字，无水印"
    )
    prompt = "，".join(p.strip() for p in parts if p and p.strip())
    negative_row = (
        db.query(models.Prompt)
        .filter(models.Prompt.project_id == project.id, models.Prompt.type == "negative")
        .first()
    )
    if negative_row and negative_row.content:
        prompt += f". Negative: {negative_row.content}"
    if preset and preset.negative_prompt:
        prompt += f", {preset.negative_prompt}"

    seed = random.randint(0, 999)  # Agnes seed 范围 -1~999
    urls = agnes.generate_image(prompt, size="2K", ratio=project.aspect_ratio, seed=seed)
    update_progress(db, task, 60)
    remote = urls[0]
    local = storage.save_from_url(remote, "images")
    project.cover_url = local
    db.add(
        models.Asset(
            project_id=project.id,
            type=models.AssetType.image,
            url=local,
            meta={"cover": True, "remote_url": remote},
        )
    )
    db.commit()
    return {"cover_url": local}


def _handle_tts(db: Session, task: models.GenTask) -> dict:
    """分镜配音：台词 → TTS → 音频落盘 → assets(type=audio)。"""
    from .providers import dashscope
    from . import storage

    sb = db.get(models.Storyboard, (task.payload or {}).get("storyboard_id"))
    if sb is None or sb.project_id != task.project_id:
        raise RuntimeError("分镜不存在")
    if not sb.dialogue or not sb.dialogue.strip():
        raise RuntimeError("该分镜没有台词，无法生成配音")
    project = db.get(models.Project, task.project_id)

    # 音色：分镜涉及角色 → 项目默认 → longxiaochun
    voice = None
    speed = None
    characters = (
        db.query(models.Character).filter(models.Character.project_id == project.id).all()
    )
    for c in characters:
        if c.name and (c.name in (sb.dialogue or "") or c.name in (sb.scene or "")):
            voice = c.voice
            speed = c.voice_speed
            break
    if voice is None:
        voice = (project.voice_config or {}).get("voice") or "longxiaochun"

    audio_bytes = dashscope.tts(sb.dialogue.strip(), voice=voice, speed=speed)
    url = storage.save_bytes(audio_bytes, "audio", ".mp3")
    db.add(
        models.Asset(
            project_id=project.id,
            type=models.AssetType.audio,
            url=url,
            meta={"storyboard_id": sb.id, "voice": voice},
        )
    )
    db.commit()
    return {"audio_url": url, "voice": voice}


def _handle_video(db: Session, task: models.GenTask) -> dict:
    """镜头视频：选中版本参考图 → 图生视频 → 轮询 → 下载落盘。"""
    import time as _time

    from .providers import agnes
    from . import storage

    payload = task.payload or {}
    shot = db.get(models.Shot, payload.get("shot_id"))
    if shot is None:
        raise RuntimeError("镜头不存在")
    sb = db.get(models.Storyboard, shot.storyboard_id)
    if sb is None or sb.project_id != task.project_id:
        raise RuntimeError("镜头不存在")

    version = None
    if shot.selected_version_id:
        version = db.get(models.ShotVersion, shot.selected_version_id)
    if version is None:
        version = (
            db.query(models.ShotVersion)
            .filter(models.ShotVersion.shot_id == shot.id)
            .order_by(models.ShotVersion.version_no.desc())
            .first()
        )
    if version is None:
        raise RuntimeError("该镜头没有可用的图片版本，请先生成图片")

    project = db.get(models.Project, task.project_id)
    seconds = str(payload.get("seconds") or "5")
    prompt = payload.get("prompt_override") or _build_video_prompt(db, project, sb)

    # 参考图需要公网可访问地址：优先取出图时记录的远程 URL
    remote_url = None
    assets = (
        db.query(models.Asset)
        .filter(
            models.Asset.project_id == task.project_id,
            models.Asset.type == models.AssetType.image,
        )
        .all()
    )
    for asset in assets:
        if (asset.meta or {}).get("shot_version_id") == version.id:
            remote_url = (asset.meta or {}).get("remote_url")
            break
    image_ref = remote_url or version.image_url

    version.status = models.ShotVersionStatus.running
    db.commit()
    _publish(task)

    video_id = agnes.create_video(
        prompt=prompt,
        images=[image_ref] if image_ref else None,
        mode="reference" if image_ref else "text",
        seconds=seconds,
        aspect_ratio=project.aspect_ratio or "9:16",
    )

    # 轮询：间隔 10s，最长 10 分钟
    start = _time.time()
    deadline = start + 600
    while True:
        check_canceled(db, task.id)
        info = agnes.query_video(video_id)
        status = info["status"]
        if status in agnes.VIDEO_DONE_STATES:
            if not info["video_url"]:
                raise RuntimeError(f"视频生成完成但未返回地址: {str(info['raw'])[:500]}")
            break
        if status in agnes.VIDEO_FAIL_STATES:
            raise RuntimeError(f"视频生成失败: {str(info['raw'])[:500]}")
        if _time.time() > deadline:
            raise RuntimeError("视频生成超时（超过 10 分钟）")
        update_progress(db, task, min(90, 10 + int((_time.time() - start) / 600 * 80)))
        _time.sleep(10)

    remote_video = info["video_url"]
    local_video = storage.save_from_url(remote_video, "videos")
    version.video_url = local_video
    version.status = models.ShotVersionStatus.succeeded
    shot.video_url = local_video
    db.add(
        models.Asset(
            project_id=task.project_id,
            type=models.AssetType.video,
            url=local_video,
            meta={"shot_id": shot.id, "shot_version_id": version.id, "remote_url": remote_video, "video_id": video_id},
        )
    )
    db.commit()
    return {"video_url": local_video, "video_id": video_id}


def _handle_composite(db: Session, task: models.GenTask) -> dict:
    """时间线合成成片。"""
    from . import compositor

    timeline = db.get(models.Timeline, (task.payload or {}).get("timeline_id"))
    if timeline is None or timeline.project_id != task.project_id:
        raise RuntimeError("时间线不存在")
    project = db.get(models.Project, task.project_id)

    timeline.status = models.TimelineStatus.compositing
    db.commit()
    _publish(task)
    try:
        output_url = compositor.composite(project, timeline)
    except Exception:
        timeline.status = models.TimelineStatus.failed
        db.commit()
        _publish(task)
        raise
    timeline.output_url = output_url
    timeline.status = models.TimelineStatus.completed
    db.add(
        models.Asset(
            project_id=task.project_id,
            type=models.AssetType.composite,
            url=output_url,
            meta={"timeline_id": timeline.id},
        )
    )
    db.commit()
    return {"output_url": output_url}


HANDLERS: dict[models.TaskType, callable] = {
    models.TaskType.script: _handle_script,
    models.TaskType.image: _handle_image,
    models.TaskType.ref_image: _handle_ref_image,
    models.TaskType.cover: _handle_cover,
    models.TaskType.tts: _handle_tts,
    models.TaskType.video: _handle_video,
    models.TaskType.composite: _handle_composite,
}
