"""ffmpeg 合成器：把 timeline.items 按顺序合成为成片。

- 视频片段：scale + pad 归一化到项目比例（默认 1080x1920）、fps 30、yuv420p；
- 纯图片片段：loop 生成 duration_sec 视频；
- 音轨：item.audio_url 优先，否则补静音轨（保证 concat 流对齐）；
- 字幕：drawtext 尽力烧录，找不到中文字体或参数异常时跳过，不导致失败。
"""
import shutil
import subprocess
import uuid
from pathlib import Path

import ffmpeg

from ..core.config import get_settings
from . import storage

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
)


def _find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:  # 兜底：imageio-ffmpeg 自带 ffmpeg 可执行文件
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("未找到 ffmpeg 可执行文件，请安装 ffmpeg 或 pip install imageio-ffmpeg") from exc


def _find_font() -> str | None:
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return None


def _escape_drawtext(text: str) -> str:
    """drawtext 文本转义（尽力而为）。"""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "‘")
        .replace(",", "\\,")
        .replace("%", "\\%")
    )


def _parse_ratio(ratio: str, base_w: int = 1080) -> tuple[int, int]:
    """把 "9:16" 之类比例解析为 (宽, 高)，宽度固定 1080，高度取偶数。"""
    try:
        a, b = str(ratio).split(":")
        w_ratio, h_ratio = float(a), float(b)
        if w_ratio <= 0 or h_ratio <= 0:
            raise ValueError
    except Exception:
        w_ratio, h_ratio = 9, 16
    height = int(round(base_w * h_ratio / w_ratio / 2) * 2)
    return base_w, max(2, height)


def _resolve_media(url: str, subdir: str) -> Path:
    """本地 /static 路径直接映射；远程 URL 先下载落盘。"""
    if url.startswith("/static/"):
        path = storage.local_path(url)
        if not path.exists():
            raise RuntimeError(f"素材文件不存在: {url}")
        return path
    return Path(storage.local_path(storage.save_from_url(url, subdir)))


def _has_audio(path: Path) -> bool:
    """用 ffmpeg 探测文件是否含音频流（imageio-ffmpeg 不带 ffprobe）。"""
    try:
        proc = subprocess.run(
            [_find_ffmpeg(), "-i", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:  # noqa: BLE001
        return False
    return "Audio:" in (proc.stderr or "")


def composite(project, timeline) -> str:
    """合成 timeline，返回 /static/composites/timeline_{id}.mp4。"""
    items = timeline.items or []
    if not items:
        raise RuntimeError("时间线为空，无法合成")
    # 片段数上限：防止超长时间线把 ffmpeg 命令行撑爆（Windows 单条命令上限 32767 字符）
    if len(items) > 200:
        raise RuntimeError(f"时间线片段过多（{len(items)}），单次最多 200 个片段")

    width, height = _parse_ratio(project.aspect_ratio or "9:16")
    fps = 30
    font = _find_font()

    segment_streams: list = []
    for idx, item in enumerate(items):
        media_url = str(item.get("media_url") or "").strip()
        if not media_url:
            raise RuntimeError(f"第 {idx + 1} 个片段缺少 media_url")
        try:
            duration = float(item.get("duration_sec") or 5)
        except (TypeError, ValueError):
            duration = 5.0
        # 单段时长夹在 0.5~600 秒：脏数据不应让合成跑到超时
        duration = min(600.0, max(0.5, duration))
        is_video = Path(media_url.split("?")[0]).suffix.lower() in VIDEO_EXTS
        src = _resolve_media(media_url, "videos" if is_video else "images")

        if is_video:
            stream = ffmpeg.input(str(src))
            v = stream.video
        else:
            # 纯图片：loop 生成 duration_sec 的视频
            stream = ffmpeg.input(str(src), loop=1, t=duration)
            v = stream.video

        v = (
            v.filter("scale", width, height, force_original_aspect_ratio="decrease")
            .filter("pad", width, height, "(ow-iw)/2", "(oh-ih)/2")
            .filter("setsar", "1")
            .filter("fps", fps)
        )
        if is_video:
            # 视频实际时长可能短于 duration_sec（模型按 seconds 生成，与分镜时长不一致）。
            # 先无限克隆末帧再 trim 到 duration，保证视频段严格等于音频段时长，
            # 否则 concat 双流各自拼接会造成累积性音画漂移。
            v = (
                v.filter("tpad", stop_mode="clone", stop=-1)
                .filter("trim", duration=duration)
                .filter("setpts", "PTS-STARTPTS")
            )

        # 字幕烧录（尽力而为：无中文字体或参数异常时跳过，不失败）
        subtitle = str(item.get("subtitle") or "").strip()
        if subtitle and font:
            try:
                v = v.filter(
                    "drawtext",
                    fontfile=font,
                    text=_escape_drawtext(subtitle),
                    fontsize=48,
                    fontcolor="white",
                    borderw=2,
                    bordercolor="black",
                    x="(w-text_w)/2",
                    y="h*0.85",
                )
            except Exception:
                pass

        # 音轨：优先 item.audio_url（TTS 配音），其次镜头视频自带音轨，最后补静音轨
        audio_url = item.get("audio_url")
        if audio_url:
            asrc = _resolve_media(audio_url, "audio")
            a = (
                ffmpeg.input(str(asrc))
                .audio.filter("aresample", 44100)
                .filter("apad", whole_dur=duration)
                .filter("atrim", duration=duration)
                .filter("asetpts", "PTS-STARTPTS")
            )
        elif is_video and _has_audio(src):
            a = (
                stream.audio.filter("aresample", 44100)
                .filter("apad", whole_dur=duration)
                .filter("atrim", duration=duration)
                .filter("asetpts", "PTS-STARTPTS")
            )
        else:
            a = ffmpeg.input("anullsrc=r=44100:cl=stereo", f="lavfi", t=duration).audio

        # concat 输入顺序：按片段交错（v0, a0, v1, a1, ...）
        segment_streams.extend([v, a])

    joined = ffmpeg.concat(*segment_streams, v=1, a=1)

    # 文件名带随机串：/static 无鉴权，可枚举的 timeline_{id}.mp4 会被跨用户抓取
    out_name = f"timeline_{timeline.id}_{uuid.uuid4().hex[:12]}.mp4"
    out_path = get_settings().storage_path / "composites" / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再原子替换，避免失败时在正式路径留下半截可播放的坏文件
    tmp_path = out_path.with_name(out_path.name + ".part.mp4")

    out = ffmpeg.output(
        joined,
        str(tmp_path),
        vcodec="libx264",
        acodec="aac",
        pix_fmt="yuv420p",
        r=fps,
        ar=44100,
        movflags="+faststart",
    )
    cmd = ffmpeg.compile(out, overwrite_output=True)

    try:
        proc = subprocess.run(
            [_find_ffmpeg()] + cmd[1:],
            capture_output=True,
            text=True,
            timeout=900,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg 合成失败: {proc.stderr[-800:]}")
        tmp_path.replace(out_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return f"/static/composites/{out_name}"
