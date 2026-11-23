"""角色接口：列表 / 编辑 / 生成定妆照 / 试听音色。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.db import get_db
from .. import models, schemas
from ..models import Asset, Character, User
from ..api.routes_projects import get_owned_project
from ..services import storage, task_engine
from ..services.providers import dashscope

router = APIRouter()

AUDITION_TEXT = "你好，欢迎来到 AI 漫剧平台。"


def _get_owned_character(db: Session, user: User, character_id: int) -> Character:
    char = db.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    project = db.get(models.Project, char.project_id)
    if project is None or project.deleted or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="角色不存在")
    return char


@router.post("/projects/{project_id}/characters")
def create_character(
    project_id: int,
    body: schemas.CharacterCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    get_owned_project(db, user, project_id)
    char = Character(project_id=project_id, **body.model_dump())
    db.add(char)
    db.commit()
    db.refresh(char)
    return schemas.character_out(char)


@router.get("/characters")
def list_characters(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    get_owned_project(db, user, project_id)
    items = db.query(Character).filter(Character.project_id == project_id).order_by(Character.id).all()
    return {"items": [schemas.character_out(c) for c in items], "total": len(items)}


@router.get("/characters/{character_id}")
def get_character(
    character_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    char = _get_owned_character(db, user, character_id)
    return schemas.character_out(char)


@router.put("/characters/{character_id}")
def update_character(
    character_id: int,
    body: schemas.CharacterUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    char = _get_owned_character(db, user, character_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(char, field, value)
    db.commit()
    db.refresh(char)
    return schemas.character_out(char)


@router.delete("/characters/{character_id}")
def delete_character(
    character_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    char = _get_owned_character(db, user, character_id)
    db.delete(char)
    db.commit()
    return {"ok": True, "message": "角色已删除"}


@router.post("/characters/{character_id}/generate-ref")
def generate_ref(
    character_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    char = _get_owned_character(db, user, character_id)
    task = task_engine.submit_task(
        db, char.project_id, models.TaskType.ref_image, {"character_id": char.id, "retryable": True}
    )
    return {"task_id": task.id}


@router.get("/characters/{character_id}/audition")
def audition(
    character_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """试听音色：同步合成固定示例句；未配置 DASHSCOPE_API_KEY 时返回 400。"""
    char = _get_owned_character(db, user, character_id)
    voice = char.voice or "longxiaochun"
    try:
        audio = dashscope.tts(AUDITION_TEXT, voice=voice, speed=char.voice_speed)
    except Exception as exc:  # noqa: BLE001
        # 配置缺失属用户可修复问题（400），其余上游异常不对外暴露原文（503）
        msg = str(exc)
        if isinstance(exc, RuntimeError) and ("DASHSCOPE" in msg or "未配置" in msg or "api_key" in msg.lower()):
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=503, detail="语音服务暂不可用，请稍后重试")
    url = storage.save_bytes(audio, "audio", ".mp3")
    db.add(
        Asset(
            project_id=char.project_id,
            type=models.AssetType.audio,
            url=url,
            meta={"character_id": char.id, "audition": True, "text": AUDITION_TEXT},
        )
    )
    db.commit()
    return {"audio_url": url, "voice": voice}
