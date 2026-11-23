"""FastAPI 依赖：当前登录用户。"""
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..models import User
from .db import get_db
from .security import decode_token

# tokenUrl 仅用于 OpenAPI 文档展示
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="未登录或缺少访问令牌")
    user_id = decode_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")
    return user


def get_optional_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User | None:
    """登出等场景：令牌缺失/无效时返回 None 而非 401。"""
    if not token:
        return None
    user_id = decode_token(token)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user
