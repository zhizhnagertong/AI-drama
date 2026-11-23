"""应用配置：从 backend/.env 读取（pydantic-settings）。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend 根目录（本文件位于 backend/app/core/ 下）
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 数据库
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "ai_manga_studio2"

    # Agnes AI（文本/图像与视频分属两个域名）
    AGNES_API_KEY: str = ""
    AGNES_BASE_URL: str = "https://apihub.agnes-ai.com"
    AGNES_VIDEO_BASE_URL: str = "https://api.agnes-ai.cn"

    # DashScope TTS（留空则 TTS 相关功能报 400）
    DASHSCOPE_API_KEY: str = ""

    # JWT（双令牌：access 短期 + refresh 长期，对齐登录注册流程规范）
    JWT_SECRET: str = "change-me"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_REMEMBER_DAYS: int = 7
    REFRESH_TOKEN_EXPIRE_SESSION_HOURS: int = 12

    # 登录安全策略
    LOGIN_MAX_FAILS: int = 5
    LOGIN_LOCK_MINUTES: int = 30

    # 找回密码验证码
    RESET_CODE_TTL_MINUTES: int = 10
    RESET_CODE_RESEND_SECONDS: int = 60
    RESET_CODE_MAX_ATTEMPTS: int = 5
    # 仅本地调试开启：把验证码打到服务端日志（生产必须为 false，否则日志泄露即可重置任意账号）
    LOG_RESET_CODE: bool = False

    # 产物存储目录（相对 backend）
    STORAGE_DIR: str = "storage"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def database_url_no_db(self) -> str:
        """不带库名的连接串，仅用于启动时自动 CREATE DATABASE。"""
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/?charset=utf8mb4"
        )

    @property
    def storage_path(self) -> Path:
        p = Path(self.STORAGE_DIR)
        return p if p.is_absolute() else (BACKEND_DIR / p)


@lru_cache
def get_settings() -> Settings:
    return Settings()
