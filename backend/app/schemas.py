"""Pydantic 请求模型与响应序列化函数。"""
import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import models
from .core.security import (
    LOGIN_USERNAME_RE,
    PASSWORD_RE,
    REGISTER_USERNAME_RE,
)


# ---------------- Auth ----------------
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8, max_length=20)
    confirm_password: str | None = Field(default=None, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    agree_terms: bool = Field(default=False)

    @field_validator("username")
    @classmethod
    def _username_format(cls, v: str) -> str:
        if not REGISTER_USERNAME_RE.match(v):
            raise ValueError("用户名须为 3-20 位字母或数字")
        return v

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not PASSWORD_RE.match(v):
            raise ValueError("密码须为 8-20 位，包含大写、小写字母和数字，且不含空格")
        return v

    @field_validator("email")
    @classmethod
    def _email_format(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.strip()
        if v and "@" not in v:
            raise ValueError("邮箱格式不正确")
        return v or None

    @field_validator("confirm_password")
    @classmethod
    def _confirm(cls, v: str | None, info) -> str | None:
        if v is not None and info.data.get("password") and v != info.data["password"]:
            raise ValueError("两次输入的密码不一致")
        return v


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False

    @field_validator("username")
    @classmethod
    def _username_format(cls, v: str) -> str:
        if not LOGIN_USERNAME_RE.match(v):
            raise ValueError("用户名须为 3-20 位字母、数字、下划线或中文")
        return v


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=2048)


class VerifyUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class SendCodeRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class VerifyCodeRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=4, max_length=8)


class ResetPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=4, max_length=8)
    new_password: str = Field(min_length=8, max_length=20)
    confirm_password: str = Field(min_length=8, max_length=20)

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not PASSWORD_RE.match(v):
            raise ValueError("密码须为 8-20 位，包含大写、小写字母和数字，且不含空格")
        return v

    @field_validator("confirm_password")
    @classmethod
    def _confirm(cls, v: str, info) -> str:
        if info.data.get("new_password") and v != info.data["new_password"]:
            raise ValueError("两次输入的密码不一致")
        return v


class ProfileUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("nickname")
    @classmethod
    def _nickname_not_blank(cls, v: str | None) -> str | None:
        # min_length 只看原始长度，纯空格能绕过，必须 strip 后再判空
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("昵称不能为空")
        return stripped


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=20)

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not PASSWORD_RE.match(v):
            raise ValueError("密码须为 8-20 位，包含大写、小写字母和数字，且不含空格")
        return v


# ---------------- Project ----------------
class ProjectCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    genre: str | None = Field(default=None, max_length=64)
    style: str | None = Field(default=None, max_length=64)
    aspect_ratio: str = "9:16"
    inspiration: str = ""
    voice_config: dict | None = None


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    genre: str | None = Field(default=None, max_length=64)
    style: str | None = Field(default=None, max_length=64)
    aspect_ratio: str | None = Field(default=None, max_length=16)
    inspiration: str | None = None
    voice_config: dict | None = None
    status: str | None = Field(default=None, max_length=32)
    cover_url: str | None = Field(default=None, max_length=500)


class BatchImageRequest(BaseModel):
    storyboard_ids: list[int] | None = None
    count: int = Field(default=2, ge=1, le=6)


class BatchVideoRequest(BaseModel):
    storyboard_ids: list[int] | None = None
    seconds: str = Field(default="5", pattern=r"^[0-9]+$")


class GenerateScriptRequest(BaseModel):
    inspiration: str | None = None


# ---------------- Episode ----------------
class EpisodeCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    synopsis: str | None = None
    inspiration: str | None = None


class EpisodeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    synopsis: str | None = None
    inspiration: str | None = None
    status: str | None = Field(default=None, max_length=32)


# ---------------- StylePreset ----------------
class StylePresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=256)
    negative_prompt: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, max_length=32)
    is_active: bool = True
    sort_order: int = 0


class StylePresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    prompt: str | None = Field(default=None, min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=256)
    negative_prompt: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    sort_order: int | None = None


# ---------------- Storyboard ----------------
class StoryboardCreate(BaseModel):
    episode_id: int | None = None
    shot_size: str | None = Field(default=None, max_length=32)
    scene: str | None = None
    dialogue: str | None = None
    emotion: str | None = Field(default=None, max_length=32)
    duration_sec: int = Field(default=5, ge=1, le=60)
    image_prompt: str | None = None


class StoryboardUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # seq 不在此暴露：排序必须走 reorder 接口，否则直写 seq 会与其它分镜撞号
    shot_size: str | None = Field(default=None, max_length=32)
    scene: str | None = None
    dialogue: str | None = None
    emotion: str | None = Field(default=None, max_length=32)
    duration_sec: int | None = Field(default=None, ge=1, le=60)
    image_prompt: str | None = None


class ReorderRequest(BaseModel):
    ordered_ids: list[int]


class GenerateImageRequest(BaseModel):
    count: int = Field(default=2, ge=1, le=6)
    prompt_override: str | None = None
    seed: int | None = Field(default=None, ge=0)


# ---------------- Character ----------------
class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None
    prompt_template: str | None = None
    voice: str = Field(default="longxiaochun", max_length=64)
    voice_emotion: str | None = Field(default=None, max_length=32)
    voice_speed: float | None = Field(default=None, ge=0.5, le=2.0)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = None
    prompt_template: str | None = None
    ref_image_url: str | None = Field(default=None, max_length=500)
    voice: str | None = Field(default=None, max_length=64)
    voice_emotion: str | None = Field(default=None, max_length=32)
    voice_speed: float | None = Field(default=None, ge=0.5, le=2.0)


# ---------------- Shot ----------------
class SelectVersionRequest(BaseModel):
    version_id: int


class GenerateVideoRequest(BaseModel):
    seconds: str = Field(default="5", pattern=r"^[0-9]+$")
    prompt_override: str | None = None


class ShotRegenerateRequest(BaseModel):
    prompt_override: str | None = None
    seed: int | None = Field(default=None, ge=0)


class ShotVersionUpdate(BaseModel):
    prompt: str | None = None
    seed: int | None = Field(default=None, ge=0)


# ---------------- Timeline ----------------
class TimelineItem(BaseModel):
    shot_id: int | None = None
    version_id: int | None = None
    media_url: str = Field(min_length=1, max_length=500)
    # 与合成器一致：单段 0.5~600 秒
    duration_sec: float = Field(default=5, ge=0.5, le=600)
    subtitle: str | None = None
    audio_url: str | None = Field(default=None, max_length=500)


class TimelineCreate(BaseModel):
    episode_id: int | None = None
    items: list[TimelineItem] | None = None
    composite_config: dict | None = None


class TimelineUpdate(BaseModel):
    items: list[TimelineItem] | None = None
    composite_config: dict | None = None


# ---------------- 序列化 ----------------
def _v(x):
    """枚举 → 原始字符串值。"""
    return x.value if isinstance(x, enum.Enum) else x


def _dt(x: datetime | None) -> str | None:
    return x.isoformat(timespec="seconds") if x else None


def user_out(user: models.User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "email": user.email,
        "is_active": user.is_active,
        "roles": [r.name for r in (user.roles or [])],
        "created_at": _dt(user.created_at),
    }


def project_out(p: models.Project, stats: dict | None = None) -> dict:
    data = {
        "id": p.id,
        "user_id": p.user_id,
        "title": p.title,
        "genre": p.genre,
        "style": p.style,
        "aspect_ratio": p.aspect_ratio,
        "inspiration": p.inspiration,
        "voice_config": p.voice_config,
        "cover_url": p.cover_url,
        "status": _v(p.status),
        "created_at": _dt(p.created_at),
        "updated_at": _dt(p.updated_at),
    }
    if stats is not None:
        data["stats"] = stats
    return data


def episode_out(e: models.Episode, stats: dict | None = None) -> dict:
    data = {
        "id": e.id,
        "project_id": e.project_id,
        "episode_number": e.episode_number,
        "title": e.title,
        "synopsis": e.synopsis,
        "logline": e.logline,
        "inspiration": e.inspiration,
        "status": _v(e.status),
        "style": e.style,
        "aspect_ratio": e.aspect_ratio,
        "voice_config": e.voice_config,
        "created_at": _dt(e.created_at),
        "updated_at": _dt(e.updated_at),
    }
    if stats is not None:
        data["stats"] = stats
    return data


def character_out(c: models.Character) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "name": c.name,
        "description": c.description,
        "prompt_template": c.prompt_template,
        "ref_image_url": c.ref_image_url,
        "voice": c.voice,
        "voice_emotion": c.voice_emotion,
        "voice_speed": c.voice_speed,
        "created_at": _dt(c.created_at),
        "updated_at": _dt(c.updated_at),
    }


def shot_version_out(v: models.ShotVersion) -> dict:
    return {
        "id": v.id,
        "shot_id": v.shot_id,
        "version_no": v.version_no,
        "image_url": v.image_url,
        "video_url": v.video_url,
        "prompt": v.prompt,
        "seed": v.seed,
        "is_selected": v.is_selected,
        "status": _v(v.status),
        "created_at": _dt(v.created_at),
    }


def shot_out(shot: models.Shot | None) -> dict | None:
    if shot is None:
        return None
    return {
        "id": shot.id,
        "storyboard_id": shot.storyboard_id,
        "selected_version_id": shot.selected_version_id,
        "video_url": shot.video_url,
        "qc_score": shot.qc_score,
        "status": _v(shot.status),
        "versions": [shot_version_out(v) for v in (shot.versions or [])],
        "created_at": _dt(shot.created_at),
    }


def storyboard_out(sb: models.Storyboard) -> dict:
    return {
        "id": sb.id,
        "project_id": sb.project_id,
        "episode_id": sb.episode_id,
        "seq": sb.seq,
        "shot_size": sb.shot_size,
        "scene": sb.scene,
        "dialogue": sb.dialogue,
        "emotion": sb.emotion,
        "duration_sec": sb.duration_sec,
        "status": _v(sb.status),
        "image_prompt": sb.image_prompt,
        "shot": shot_out(sb.shot),
        "shots": [shot_out(sb.shot)] if sb.shot else [],
        "created_at": _dt(sb.created_at),
    }


def asset_out(a: models.Asset) -> dict:
    return {
        "id": a.id,
        "project_id": a.project_id,
        "type": _v(a.type),
        "url": a.url,
        "meta": a.meta,
        "created_at": _dt(a.created_at),
    }


def task_out(t: models.GenTask) -> dict:
    return {
        "id": t.id,
        "project_id": t.project_id,
        "type": _v(t.type),
        "status": _v(t.status),
        "progress": t.progress,
        "payload": t.payload,
        "result": t.result,
        "error": t.error,
        "retries": t.retries,
        "created_at": _dt(t.created_at),
        "updated_at": _dt(t.updated_at),
    }


def style_preset_out(p: models.StylePreset) -> dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "name": p.name,
        "prompt": p.prompt,
        "description": p.description,
        "negative_prompt": p.negative_prompt,
        "color": p.color,
        "is_active": p.is_active,
        "sort_order": p.sort_order,
        "created_at": _dt(p.created_at),
        "updated_at": _dt(p.updated_at),
    }


def timeline_out(t: models.Timeline) -> dict:
    return {
        "id": t.id,
        "project_id": t.project_id,
        "episode_id": t.episode_id,
        "items": t.items,
        "composite_config": t.composite_config,
        "output_url": t.output_url,
        "status": _v(t.status),
        "created_at": _dt(t.created_at),
        "updated_at": _dt(t.updated_at),
    }
