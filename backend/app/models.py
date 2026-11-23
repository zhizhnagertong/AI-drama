"""SQLAlchemy 数据模型（13 张表）。

全部表含 id（自增主键）与 created_at/updated_at（DATETIME）。
枚举统一用 native_enum=False（VARCHAR 存储），便于后续扩展。
"""
import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.db import Base


def _enum(e: type[enum.Enum]) -> SAEnum:
    return SAEnum(e, native_enum=False, length=32)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )


# ---------------- 枚举 ----------------
class ProjectStatus(str, enum.Enum):
    draft = "draft"
    script_ready = "script_ready"
    producing = "producing"
    completed = "completed"
    failed = "failed"


class EpisodeStatus(str, enum.Enum):
    draft = "draft"
    script_ready = "script_ready"
    producing = "producing"
    completed = "completed"
    failed = "failed"


class StoryboardStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    ready = "ready"


class ShotStatus(str, enum.Enum):
    pending = "pending"
    ready = "ready"


class ShotVersionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class AssetType(str, enum.Enum):
    image = "image"
    audio = "audio"
    video = "video"
    subtitle = "subtitle"
    composite = "composite"


class TaskType(str, enum.Enum):
    script = "script"
    ref_image = "ref_image"
    cover = "cover"
    image = "image"
    video = "video"
    tts = "tts"
    composite = "composite"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class TimelineStatus(str, enum.Enum):
    draft = "draft"
    compositing = "compositing"
    completed = "completed"
    failed = "failed"


# ---------------- 用户与角色 ----------------
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 登录安全：连续失败计数与锁定截止时间（ER 图 status 列由 is_active 等价承担）
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary="user_roles", lazy="selectin", viewonly=True
    )


class RefreshToken(TimestampMixin, Base):
    """refresh 令牌表：支持登出撤销与重置密码后全量失效。"""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class LoginLog(TimestampMixin, Base):
    """登录日志：1 登录成功 2 登出 3 登录失败。"""

    __tablename__ = "login_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PasswordResetCode(TimestampMixin, Base):
    """找回密码验证码（TTL 字段方案，替代文档中的 Redis）。"""

    __tablename__ = "password_reset_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="email")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)


class UserRole(TimestampMixin, Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)


# ---------------- 项目 ----------------
class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    genre: Mapped[str | None] = mapped_column(String(64), nullable=True)
    style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aspect_ratio: Mapped[str] = mapped_column(String(16), nullable=False, default="9:16")
    inspiration: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        _enum(ProjectStatus), nullable=False, default=ProjectStatus.draft
    )
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    characters: Mapped[list["Character"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    storyboards: Mapped[list["Storyboard"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )
    tasks: Mapped[list["GenTask"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )
    timelines: Mapped[list["Timeline"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )


# ---------------- 剧集（一个项目下的多集） ----------------
class Episode(TimestampMixin, Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="第1集")
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)
    logline: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspiration: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EpisodeStatus] = mapped_column(
        _enum(EpisodeStatus), nullable=False, default=EpisodeStatus.draft
    )
    # 生成配置快照：建集时锁定，避免后续改全局配置导致历史集重生成风格漂移
    style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aspect_ratio: Mapped[str | None] = mapped_column(String(16), nullable=True)
    voice_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    project: Mapped[Project] = relationship(back_populates="episodes")
    storyboards: Mapped[list["Storyboard"]] = relationship(
        back_populates="episode", cascade="all, delete-orphan", lazy="noload"
    )


# ---------------- 角色（剧中人物） ----------------
class Character(TimestampMixin, Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    voice: Mapped[str] = mapped_column(String(64), nullable=False, default="longxiaochun")
    voice_emotion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voice_speed: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped[Project] = relationship(back_populates="characters")


# ---------------- 分镜 / 镜头 / 版本 ----------------
class Storyboard(TimestampMixin, Base):
    __tablename__ = "storyboards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    episode_id: Mapped[int | None] = mapped_column(
        ForeignKey("episodes.id"), nullable=True, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    shot_size: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scene: Mapped[str | None] = mapped_column(Text, nullable=True)
    dialogue: Mapped[str | None] = mapped_column(Text, nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    status: Mapped[StoryboardStatus] = mapped_column(
        _enum(StoryboardStatus), nullable=False, default=StoryboardStatus.pending
    )
    # 编剧智能体输出的画面提示词（供出图使用）；相对表结构的补充字段
    image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="storyboards")
    episode: Mapped["Episode | None"] = relationship(back_populates="storyboards")
    shot: Mapped["Shot | None"] = relationship(
        uselist=False, back_populates="storyboard", cascade="all, delete-orphan"
    )


class Shot(TimestampMixin, Base):
    __tablename__ = "shots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    storyboard_id: Mapped[int] = mapped_column(ForeignKey("storyboards.id"), nullable=False, index=True)
    selected_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 不加 FK 避免循环引用
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qc_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ShotStatus] = mapped_column(
        _enum(ShotStatus), nullable=False, default=ShotStatus.pending
    )

    storyboard: Mapped[Storyboard] = relationship(back_populates="shot")
    versions: Mapped[list["ShotVersion"]] = relationship(
        back_populates="shot",
        cascade="all, delete-orphan",
        order_by="ShotVersion.version_no",
        lazy="selectin",
    )


class ShotVersion(TimestampMixin, Base):
    __tablename__ = "shot_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shot_id: Mapped[int] = mapped_column(ForeignKey("shots.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[ShotVersionStatus] = mapped_column(
        _enum(ShotVersionStatus), nullable=False, default=ShotVersionStatus.pending
    )

    shot: Mapped[Shot] = relationship(back_populates="versions")


# ---------------- 资产 / 任务 / 智能体运行 / 提示词 / 时间线 ----------------
class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    type: Mapped[AssetType] = mapped_column(_enum(AssetType), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    project: Mapped[Project] = relationship(back_populates="assets")


class GenTask(TimestampMixin, Base):
    __tablename__ = "gen_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    type: Mapped[TaskType] = mapped_column(_enum(TaskType), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        _enum(TaskStatus), nullable=False, default=TaskStatus.queued
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)

    project: Mapped[Project] = relationship(back_populates="tasks")


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    project: Mapped[Project] = relationship(back_populates="agent_runs")


class Prompt(TimestampMixin, Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Timeline(TimestampMixin, Base):
    __tablename__ = "timelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    episode_id: Mapped[int | None] = mapped_column(
        ForeignKey("episodes.id"), nullable=True, index=True
    )
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    composite_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[TimelineStatus] = mapped_column(
        _enum(TimelineStatus), nullable=False, default=TimelineStatus.draft
    )

    project: Mapped[Project] = relationship(back_populates="timelines")


# ---------------- 风格预设 ----------------
class StylePreset(TimestampMixin, Base):
    __tablename__ = "style_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_style_presets_user_name"),)
