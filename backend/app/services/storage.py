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
    """把 /static/... URL 映射回本地文件路径；非 /static 输入按相对路径拼接。

    安全：结果必须落在 storage 目录内，防止 `../../` 路径穿越读取任意本地文件。
    """
    base = get_settings().storage_path.resolve()
    if "/static/" in url:
        rel = url.split("/static/", 1)[1].lstrip("/")
    else:
        rel = url.lstrip("/")
    path = (base / rel).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"非法存储路径: {url}")
    return path


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
    """下载远程 URL 到本地存储并返回 /static URL；若已是本地 /static 地址则原样返回。

    - 流式落盘：整段视频读进内存再写会在多 worker 并发时打爆内存；
    - 只对网络/HTTP 错误重试：磁盘写失败（OSError）重试没有意义，直接抛出。
    """
    if url.startswith("/static/"):
        return url
    ext = Path(httpx.URL(url).path).suffix.lower()
    if ext not in KNOWN_EXTS:
        ext = DEFAULT_EXT.get(subdir, ".bin")

    ensure_dirs()
    name = f"{uuid.uuid4().hex}{ext}"
    path = get_settings().storage_path / subdir / name
    path.parent.mkdir(parents=True, exist_ok=True)

    last_exc: Exception | None = None
    # 先直连（系统代理常会掐断 CDN 的 TLS 连接），失败再回退走代理
    for trust_env in (False, True):
        try:
            with httpx.Client(timeout=180, follow_redirects=True, trust_env=trust_env) as client:
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    with path.open("wb") as fh:
                        for chunk in resp.iter_bytes(1024 * 1024):
                            fh.write(chunk)
            return f"/static/{subdir}/{name}"
        except httpx.HTTPError as exc:
            last_exc = exc
            path.unlink(missing_ok=True)
        except OSError:
            path.unlink(missing_ok=True)
            raise
    assert last_exc is not None
    raise last_exc
