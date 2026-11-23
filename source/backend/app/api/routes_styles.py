"""风格预设接口：CRUD、启用/停用切换。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas
from ..core.deps import get_current_user
from ..core.db import get_db
from ..models import StylePreset, User
from ..services.style_seed import ensure_default_styles

router = APIRouter()


def get_owned_preset(db: Session, user: User, preset_id: int) -> StylePreset:
    """按归属校验风格预设，不存在或非本人返回 404（避免资源探测）。"""
    preset = db.get(StylePreset, preset_id)
    if preset is None or preset.user_id != user.id:
        raise HTTPException(status_code=404, detail="风格预设不存在")
    return preset


@router.get("")
def list_presets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # 懒 seed：已注册用户首次访问时补默认风格
    ensure_default_styles(db, user.id)
    query = db.query(StylePreset).filter(StylePreset.user_id == user.id)
    if not include_inactive:
        query = query.filter(StylePreset.is_active.is_(True))
    total = query.count()
    items = (
        query.order_by(StylePreset.sort_order.asc(), StylePreset.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": [schemas.style_preset_out(p) for p in items], "total": total}


@router.post("")
def create_preset(
    body: schemas.StylePresetCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    dup = (
        db.query(StylePreset)
        .filter(StylePreset.user_id == user.id, StylePreset.name == body.name)
        .first()
    )
    if dup is not None:
        raise HTTPException(status_code=400, detail="风格名称已存在")
    preset = StylePreset(user_id=user.id, **body.model_dump())
    db.add(preset)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="风格名称已存在")
    db.refresh(preset)
    return schemas.style_preset_out(preset)


@router.get("/{preset_id}")
def get_preset(
    preset_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    preset = get_owned_preset(db, user, preset_id)
    return schemas.style_preset_out(preset)


@router.put("/{preset_id}")
def update_preset(
    preset_id: int,
    body: schemas.StylePresetUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    preset = get_owned_preset(db, user, preset_id)
    data = body.model_dump(exclude_unset=True)
    new_name = data.get("name")
    if new_name and new_name != preset.name:
        dup = (
            db.query(StylePreset)
            .filter(
                StylePreset.user_id == user.id,
                StylePreset.name == new_name,
                StylePreset.id != preset.id,
            )
            .first()
        )
        if dup is not None:
            raise HTTPException(status_code=400, detail="风格名称已存在")
    for field, value in data.items():
        setattr(preset, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="风格名称已存在")
    db.refresh(preset)
    return schemas.style_preset_out(preset)


@router.patch("/{preset_id}/toggle")
def toggle_preset(
    preset_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    preset = get_owned_preset(db, user, preset_id)
    preset.is_active = not preset.is_active
    db.commit()
    db.refresh(preset)
    return schemas.style_preset_out(preset)


@router.delete("/{preset_id}")
def delete_preset(
    preset_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    preset = get_owned_preset(db, user, preset_id)
    db.delete(preset)
    db.commit()
    return {"ok": True, "message": "风格已删除"}
