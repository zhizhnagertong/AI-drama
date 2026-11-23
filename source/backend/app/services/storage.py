"""产物文件存储：backend/storage/{images,videos,audio,composites}，URL 以 /static/... 暴露。"""
import uuid
from pathlib import Path

import httpx

from ..core.config import get_settings

SUBDIRS = ("images", "videos", "audio", "composites")

DEFAULT_EXT = {"images": ".png", "videos": ".mp4", "audio": ".mp3", "composites": ".mp4"}

KNOWN_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg",
}


def ensure_dirs() -> None:
    for sub in SUBDIRS:
        (get_settings().storage_path / sub).mkdir(parents=True, exist_ok=True)


def local_path(url: str) -> Path:
    """把 /static/... URL 映射回本地文件路径；非 /static 输入原样拼接。"""
    base = get_settings().storage_path
    if "/static/" in url:
        rel = url.split("/static/", 1)[1].lstrip("/")
        return base / rel
    return base / url.lstrip("/")


def save_bytes(data: bytes, subdir: str, ext: str | None = None) -> str:
    """字节数组落盘，返回 /static/{subdir}/{name} URL。"""
    ensure_dirs()
    ext = (ext or DEFAULT_EXT.get(subdir, ".bin")).lower()
    if not ext.startswith("."):
        ext = "." + ext
    name = f"{uuid.uuid4().hex}{ext}"
    path = get_settings().storage_path / subdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"/static/{subdir}/{name}"


def save_from_url(url: str, subdir: str) -> str:
    """下载远程 URL 到本地存储并返回 /static URL；若已是本地 /static 地址则原样返回。"""
    if url.startswith("/static/"):
        return url
    ext = Path(httpx.URL(url).path).suffix.lower()
    if ext not in KNOWN_EXTS:
        ext = DEFAULT_EXT.get(subdir, ".bin")
    last_exc: Exception | None = None
    # 先直连（系统代理常会掐断 CDN 的 TLS 连接），失败再回退走代理
    for trust_env in (False, True):
        try:
            with httpx.Client(timeout=180, follow_redirects=True, trust_env=trust_env) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return save_bytes(resp.content, subdir, ext)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise last_exc
