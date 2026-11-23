"""DashScope TTS Provider（CosyVoice）。

实现选择：使用 DashScope 原生接口 POST /api/v1/services/audio/tts，
原因是角色默认音色 longxiaochun 属于 CosyVoice 音色体系，
仅在原生接口可用；OpenAI 兼容接口 /compatible-mode/v1/audio/speech
主要覆盖 qwen-tts 系列音色，二者不可互换。
响应处理：SSE 已禁用（X-DashScope-SSE: disable），
返回 JSON 时从 output.audio.url 下载音频；直接返回音频流时原样取字节。
"""
import httpx

from ...core.config import get_settings

DASHSCOPE_TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts"


class ConfigError(RuntimeError):
    """配置缺失类错误：自动重试无意义，任务引擎不应重试。"""


def tts(text: str, voice: str = "longxiaochun", speed: float | None = None, audio_format: str = "mp3") -> bytes:
    """合成语音，返回音频字节。未配置 API Key 时抛 ConfigError。"""
    key = get_settings().DASHSCOPE_API_KEY
    if not key:
        raise ConfigError("未配置 DASHSCOPE_API_KEY，请在 backend/.env 中配置后重启后端")
    if not text or not text.strip():
        raise RuntimeError("TTS 文本不能为空")

    model = "cosyvoice-v2" if voice.endswith("_v2") else "cosyvoice-v1"
    body: dict = {
        "model": model,
        "input": {"text": text, "voice": voice},
        "parameters": {"format": audio_format},
    }
    if speed:
        body["parameters"]["speed"] = speed

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "disable",
        "X-DashScope-DataInspection": "enable",
    }
    try:
        resp = httpx.post(DASHSCOPE_TTS_URL, json=body, headers=headers, timeout=120)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"DashScope TTS 网络错误: {exc}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"DashScope TTS 失败[{resp.status_code}]: {resp.text[:500]}")

    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        data = resp.json()
        url = ((data.get("output") or {}).get("audio") or {}).get("url")
        if not url:
            raise RuntimeError(f"DashScope TTS 响应缺少音频 URL: {str(data)[:500]}")
        audio = httpx.get(url, timeout=120)
        audio.raise_for_status()
        return audio.content
    return resp.content
