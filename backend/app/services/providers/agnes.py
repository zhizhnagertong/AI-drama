"""Agnes AI Provider：文本 / 图像 / 视频（全部 httpx 直连，OpenAI 兼容）。"""
import base64
import threading
import time

import httpx

from ...core.config import get_settings
from .. import storage

_settings = get_settings()

# 模型名优先取 .env 中的配置，未配置时回退到内置默认值（无需改代码即可换模型）
TEXT_MODEL = _settings.AGNES_TEXT_MODEL or "agnes-2.5-flash"
IMAGE_MODEL = _settings.AGNES_IMAGE_MODEL or "agnes-image-2.1-flash"
VIDEO_MODEL = _settings.AGNES_VIDEO_MODEL or "agnes-video-2.5-flash"

VIDEO_DONE_STATES = {"completed", "succeed", "succeeded", "success", "done", "finish", "finished"}
VIDEO_FAIL_STATES = {"failed", "error", "canceled", "cancelled", "terminated"}

# 免费档速率限制：图像/视频创建调用全局串行化 + 429 指数退避
_IMAGE_SEM = threading.Semaphore(2)
_VIDEO_SEM = threading.Semaphore(1)
_RATE_RETRIES = 4


class AgnesError(RuntimeError):
    """Agnes API 调用失败（带响应体摘要）。"""


class AgnesRateLimitError(AgnesError):
    """免费档速率限制（429）：应退避重试而非立即失败。"""


class AgnesContentBlockedError(AgnesError):
    """提示词被内容安全审核拒绝（400）：需改写提示词而非原样重试。"""


def _settings():
    return get_settings()


def _headers() -> dict:
    key = _settings().AGNES_API_KEY
    if not key:
        raise AgnesError("未配置 AGNES_API_KEY，请在 backend/.env 中配置后重试")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _raise_for(resp: httpx.Response, label: str) -> None:
    if resp.status_code >= 400:
        if resp.status_code == 429 or "rate_limit" in resp.text:
            raise AgnesRateLimitError(f"Agnes {label} 接口触发免费档速率限制(429)，稍后自动重试")
        if "content_policy_violation" in resp.text or "Unable to generate this content" in resp.text:
            raise AgnesContentBlockedError(
                f"Agnes {label} 接口拒绝该提示词（内容安全审核 content_policy_violation）"
            )
        raise AgnesError(f"Agnes {label} 接口失败[{resp.status_code}]: {resp.text[:200]}")


def _post_with_rate_backoff(
    url: str, label: str, *, sem: threading.Semaphore, json_body: dict, timeout: float
) -> httpx.Response:
    """信号量限并发 + 429 指数退避重试（10/20/40s，最后一次尝试后不再等待）。"""
    last_exc: Exception | None = None
    for attempt in range(_RATE_RETRIES):
        with sem:
            try:
                resp = httpx.post(url, headers=_headers(), json=json_body, timeout=timeout, trust_env=False)
            except httpx.HTTPError as exc:
                raise AgnesError(f"Agnes {label} 接口网络错误: {exc}") from exc
            try:
                _raise_for(resp, label)
                return resp
            except AgnesRateLimitError as exc:
                last_exc = exc
        if attempt < _RATE_RETRIES - 1:  # 最后一次失败直接抛出，不再无效等待
            time.sleep(10 * (2**attempt))
    raise last_exc or AgnesError(f"Agnes {label} 接口速率限制重试耗尽")


# ---------------- 文本 ----------------
def chat(
    messages: list[dict],
    model: str = TEXT_MODEL,
    temperature: float = 0.7,
    response_format: dict | None = None,
) -> str:
    """OpenAI 兼容 chat/completions，返回 choices[0].message.content。"""
    body: dict = {"model": model, "messages": messages, "temperature": temperature}
    if response_format is not None:
        body["response_format"] = response_format
    url = f"{_settings().AGNES_BASE_URL}/v1/chat/completions"
    try:
        resp = httpx.post(url, headers=_headers(), json=body, timeout=300)
    except httpx.HTTPError as exc:
        raise AgnesError(f"Agnes 文本接口网络错误: {exc}") from exc
    _raise_for(resp, "文本")
    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AgnesError(f"Agnes 文本接口响应格式异常: {str(data)[:500]}") from exc
    return content


# ---------------- 图像 ----------------
def _blocked_fallbacks(prompt: str) -> list[str]:
    """内容审核被拒时的降级提示词：逐级剥离可能触发审核的片段。"""
    out = []
    # 1) 去掉 Negative 段与超长尾部
    simplified = prompt.split(". Negative:")[0].strip()
    if simplified and simplified != prompt:
        out.append(simplified[:300])
    # 2) 只保留开头画风段（本项目提示词以风格前缀开头），配通用安全描述
    head = simplified.split("，")[0].split(",")[0].strip() or "cinematic lighting"
    out.append(
        f"{head}, character design sheet, clean solid background, "
        "high quality, detailed, safe for work"
    )
    return out


def generate_image(
    prompt: str,
    size: str = "2K",
    ratio: str = "9:16",
    seed: int | None = None,
    image: str | None = None,
) -> list[str]:
    """文生图 / 图生图，返回图片 URL 列表（b64_json 解码后经 storage 落盘为 /static 地址）。

    提示词被内容审核（content_policy_violation）拒绝时自动逐级简化重试。
    """
    body: dict = {"model": IMAGE_MODEL, "prompt": prompt, "size": size, "ratio": ratio}
    if seed is not None:
        body["seed"] = max(-1, min(999, int(seed)))  # Agnes 限制 seed ∈ [-1, 999]
    if image:
        body["image"] = image
    url = f"{_settings().AGNES_BASE_URL}/v1/images/generations"
    candidates = [prompt, *_blocked_fallbacks(prompt)]
    data = None
    for i, candidate in enumerate(candidates):
        body["prompt"] = candidate
        try:
            resp = _post_with_rate_backoff(url, "图像", sem=_IMAGE_SEM, json_body=body, timeout=300)
            data = resp.json()
            break
        except AgnesContentBlockedError:
            if i == len(candidates) - 1:
                raise AgnesContentBlockedError(
                    "提示词被图像接口内容安全审核拒绝，请修改角色描述/画面描述中的敏感词后重试"
                )
    items = data.get("data") or data.get("images") or []
    if isinstance(items, dict):
        items = [items]
    urls: list[str] = []
    for item in items:
        if isinstance(item, str):
            urls.append(item)
            continue
        remote = item.get("url")
        b64 = item.get("b64_json")
        if remote:
            urls.append(remote)
        elif b64:
            urls.append(storage.save_bytes(base64.b64decode(b64), "images"))
    if not urls:
        raise AgnesError(f"Agnes 图像接口未返回图片: {str(data)[:500]}")
    return urls


# ---------------- 视频（异步任务） ----------------
def create_video(
    prompt: str,
    images: list[str] | None = None,
    mode: str = "reference",
    seconds: str = "5",
    aspect_ratio: str = "9:16",
) -> str:
    """创建视频生成任务，返回 video_id。

    按文档约定：参考图模式下需在 prompt 末尾追加 "<Picture N>" 占位。
    """
    body: dict = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        "mode": mode,
        "seconds": str(seconds),
        "aspect_ratio": aspect_ratio,
    }
    if images:
        body["images"] = list(images)
        placeholders = " ".join(f"<Picture {i + 1}>" for i in range(len(images)))
        if "<Picture" not in prompt:
            body["prompt"] = f"{prompt} {placeholders}"
    url = f"{_settings().AGNES_VIDEO_BASE_URL}/v1/videos"
    # 视频创建是 429 重灾区：全局串行 + 指数退避
    resp = _post_with_rate_backoff(url, "视频", sem=_VIDEO_SEM, json_body=body, timeout=120)
    data = resp.json()
    video_id = (
        data.get("video_id")
        or data.get("id")
        or data.get("task_id")
        or ((data.get("output") or {}) if isinstance(data.get("output"), dict) else {}).get("video_id")
    )
    if not video_id:
        raise AgnesError(f"Agnes 视频接口未返回 video_id: {str(data)[:500]}")
    return str(video_id)


def query_video(video_id: str) -> dict:
    """查询视频任务状态，返回 {status, video_url, raw}。

    429 / 网络抖动视为"仍在生成"返回 processing，避免误杀任务导致重建视频。
    """
    url = f"{_settings().AGNES_VIDEO_BASE_URL}/agnesapi"
    params = {"video_id": video_id, "model_name": VIDEO_MODEL}
    try:
        resp = httpx.get(url, headers=_headers(), params=params, timeout=60, trust_env=False)
    except httpx.HTTPError:
        return {"status": "processing", "video_url": None, "raw": {"note": "查询网络抖动，稍后重试"}}
    if resp.status_code == 429 or "rate_limit" in resp.text:
        return {"status": "processing", "video_url": None, "raw": {"note": "查询触发速率限制，稍后重试"}}
    _raise_for(resp, "视频查询")
    data = resp.json()
    status = str(data.get("status") or data.get("state") or "").lower()
    video_url = (
        data.get("video_url")
        or data.get("url")
        or ((data.get("output") or {}) if isinstance(data.get("output"), dict) else {}).get("video_url")
    )
    return {"status": status, "video_url": video_url, "raw": data}
