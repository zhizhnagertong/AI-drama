"""编剧智能体：调用 Agnes 文本模型生成结构化剧本 JSON。

deepagents 为可选增强（尽力导入，缺失不影响功能），
核心实现直接走 agnes.chat，保证任何环境下可用。
"""
import json
import re

from .. import models
from ..services.providers import agnes

# ---------------- 可选依赖：deepagents ----------------
try:  # 新版 API
    from deepagents import create_agent as _deepagents_factory  # type: ignore

    DEEPAGENTS_AVAILABLE = True
except Exception:  # noqa: BLE001
    try:  # 旧版 API
        from deepagents import create_deep_agent as _deepagents_factory  # type: ignore

        DEEPAGENTS_AVAILABLE = True
    except Exception:  # noqa: BLE001
        _deepagents_factory = None
        DEEPAGENTS_AVAILABLE = False

SYSTEM_PROMPT = """你是一位专业的 AI 漫剧编剧，擅长创作短小精悍、有戏剧张力的竖屏短剧。
请根据用户的创意输出**严格合法的 JSON**（不要输出任何解释文字或 Markdown 代码块之外的内容），结构如下：
{
  "title": "短剧标题",
  "logline": "一句话故事梗概",
  "characters": [
    {"name": "角色名", "description": "角色性格与背景简介（中文）", "prompt_template": "用于图像生成的角色固定外貌描述（英文，包含发型、服装、体型、年龄感等，保持一致性）", "voice": "longxiaochun"}
  ],
  "storyboards": [
    {"seq": 1, "shot_size": "景别（远/全/中/近/特写）", "scene": "画面内容描述（中文，具体到人物动作与环境）", "dialogue": "台词（中文，没有则为空字符串）", "emotion": "角色情绪", "duration_sec": 5, "image_prompt": "本镜头画面提示词（英文，详细描述构图、光线、氛围）"}
  ]
}
要求：
1. storyboards 数量 6-10 个，节奏紧凑，最后要有收尾镜头；
2. characters 1-3 个，voice 只能从 longxiaochun/longwan/longcheng/longhua/longxiaoxia 中选择；
3. image_prompt 用英文书写，确保画面可直接用于图像模型；
4. 用户提供的"创意/灵感"若是故事梗概或剧情大纲，剧本必须严格围绕其展开，不得自行改写主线剧情；
5. characters 的 prompt_template 只描述外貌特征（发型、发色、服装、体型、年龄感等），禁止包含任何画风/艺术风格词（如 anime、photorealistic、3D、oil painting 等），画风由系统统一指定；
6. prompt_template 与 image_prompt 必须通过图像内容安全审核：避免血腥、伤口、疤痕、骨骼、尸体、残忍表情等直白血腥描写，反派气质用眼神、姿态、服装色调等含蓄表达。"""


def _extract_json(text: str) -> dict:
    """剥离 ```json 围栏与前后杂文本，解析首个 JSON 对象。"""
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    start = stripped.find("{")
    if start == -1:
        raise ValueError("响应中未找到 JSON 内容")
    obj, _ = json.JSONDecoder().raw_decode(stripped[start:])
    if not isinstance(obj, dict):
        raise ValueError("JSON 顶层不是对象")
    return obj


def _validate(data: dict) -> None:
    storyboards = data.get("storyboards")
    if not isinstance(storyboards, list) or not storyboards:
        raise ValueError("缺少 storyboards 列表")
    # 限制 6-10 个：超出截断，过少照用（由模型保证）
    data["storyboards"] = storyboards[:10]
    if not isinstance(data.get("characters"), list):
        data["characters"] = []


def _record_run(
    db,
    project: models.Project,
    input_summary: str,
    output: dict | None,
    error: str | None,
    attempts: int,
) -> None:
    db.add(
        models.AgentRun(
            project_id=project.id,
            agent="writer",
            stage="script",
            input_summary=(input_summary or "")[:1000],
            output_summary=(json.dumps(output, ensure_ascii=False)[:4000] if output else f"失败: {error}（尝试 {attempts} 次）"),
        )
    )
    db.commit()


def generate_script(db, project: models.Project, inspiration: str) -> dict:
    """生成剧本 JSON；首次失败自动降温（0.3）重试一次。"""
    topic = (inspiration or project.inspiration or "").strip() or "一个引人入胜的短剧故事"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"题材：{project.genre or '不限'}\n"
                f"画面风格：{project.style or '不限'}\n"
                f"创意/灵感：{topic}\n"
                "请按系统要求输出剧本 JSON。"
            ),
        },
    ]

    last_error: Exception | None = None
    attempts = 0
    for attempt, temperature in enumerate((0.7, 0.3), start=1):
        attempts = attempt
        try:
            raw = agnes.chat(messages, model=agnes.TEXT_MODEL, temperature=temperature)
        except Exception as exc:  # noqa: BLE001  API 调用失败：记录后降温重试
            last_error = exc
            continue
        try:
            data = _extract_json(raw)
            _validate(data)
            _record_run(db, project, topic, data, None, attempt)
            return data
        except Exception as exc:  # noqa: BLE001  JSON 解析失败：降温重试一次
            last_error = exc
    _record_run(db, project, topic, None, str(last_error), attempts)
    raise RuntimeError(f"剧本生成失败: {last_error}")


EXTRACT_PROMPT = """你是短剧资产分析师。阅读以下剧本分镜文本，提取其中出现的全部角色。
输出**严格合法的 JSON**（不要任何解释文字），结构：
{"characters": [{"name": "角色名", "description": "性格与背景简介（中文）", "prompt_template": "图像生成用固定外貌描述（英文，含发型/服装/体型/年龄感，保持跨镜头一致）", "voice": "longxiaochun"}]}
要求：characters 1-5 个；voice 只能从 longxiaochun/longwan/longcheng/longhua/longxiaoxia 中选择。"""


def extract_characters(db, project: models.Project, script_text: str) -> dict:
    """按现有分镜文本重新提取角色（不重建分镜）；失败降温重试一次。"""
    messages = [
        {"role": "system", "content": EXTRACT_PROMPT},
        {"role": "user", "content": f"题材：{project.genre or '不限'}\n剧本：\n{script_text[:6000]}"},
    ]
    last_error: Exception | None = None
    for attempt, temperature in enumerate((0.5, 0.2), start=1):
        try:
            raw = agnes.chat(messages, model=agnes.TEXT_MODEL, temperature=temperature)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        try:
            data = _extract_json(raw)
            if not isinstance(data.get("characters"), list):
                raise ValueError("缺少 characters 列表")
            _record_run(db, project, "重提角色", data, None, attempt)
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    _record_run(db, project, "重提角色", None, str(last_error), 2)
    raise RuntimeError(f"角色提取失败: {last_error}")
