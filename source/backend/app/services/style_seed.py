"""默认风格预设种子：新用户注册 / 老用户首次拉取列表时懒初始化。"""
from sqlalchemy.orm import Session

from ..models import StylePreset

# 与前端 Create.vue 风格选项对应的 6 条默认预设
DEFAULT_STYLES: list[dict] = [
    {
        "name": "赛博朋克",
        "prompt": "cyberpunk, neon lights, futuristic city, high contrast, cyan and magenta color grading",
        "description": "霓虹光效、未来都市",
        "color": "#00E5FF",
        "sort_order": 1,
    },
    {
        "name": "水墨国风",
        "prompt": "Chinese ink wash painting, traditional shuimo style, soft brush strokes, misty mountains, elegant oriental aesthetic",
        "description": "水墨笔触、东方意境",
        "color": "#546E7A",
        "sort_order": 2,
    },
    {
        "name": "日系动漫",
        "prompt": "Japanese anime style, clean line art, vibrant saturated colors, cel shading, expressive eyes",
        "description": "清新线条、高饱和",
        "color": "#FF6B9D",
        "sort_order": 3,
    },
    {
        "name": "美式漫画",
        "prompt": "American comic book style, bold outlines, high contrast shading, halftone dots, dynamic heroic composition",
        "description": "强对比块面、硬派",
        "color": "#F4511E",
        "sort_order": 4,
    },
    {
        "name": "3D卡通",
        "prompt": "3D cartoon render, Pixar style, rounded soft shapes, toy-like texture, bright cheerful lighting",
        "description": "圆润立体、玩具质感",
        "color": "#FFB300",
        "sort_order": 5,
    },
    {
        "name": "写实",
        "prompt": "photorealistic, cinematic lighting, fine details, shallow depth of field, film grain, 8k quality",
        "description": "电影感光影、细节",
        "color": "#8D6E63",
        "sort_order": 6,
    },
]


def ensure_default_styles(db: Session, user_id: int) -> None:
    """该用户尚无任何风格预设时，插入 6 条默认风格（幂等，内部自行 commit）。"""
    exists = (
        db.query(StylePreset.id)
        .filter(StylePreset.user_id == user_id)
        .first()
    )
    if exists is not None:
        return
    for item in DEFAULT_STYLES:
        db.add(StylePreset(user_id=user_id, **item))
    db.commit()
