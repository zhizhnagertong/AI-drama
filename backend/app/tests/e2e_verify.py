"""端到端验证：注册登录→建项目→剧本任务→本地素材合成→导出。

剧本/图像/视频依赖 Agnes API（当前 key 无效返回 401，属环境问题），
故用本地生成的素材图片直接驱动合成链路，验证任务引擎与 FFmpeg 成片。
"""
import random
import struct
import sys
import time
import zlib

import httpx

BASE = "http://localhost:8010/api/v1"
SUFFIX = random.randint(1000, 9999)
USERNAME = f"e2e_{SUFFIX}"
PASSWORD = "e2e123456"


def make_png(path: str, rgb=(64, 120, 220), w=64, h=64) -> str:
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    raw = b""
    for _ in range(h):
        raw += b"\x00" + bytes(rgb) * w
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as f:
        f.write(png)
    return path


def wait_task(client, token, task_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"{BASE}/tasks/{task_id}", headers=auth(token)).json()
        st = r.get("status")
        if st in ("succeeded", "failed", "canceled"):
            return r
        time.sleep(2)
    return {"status": "timeout"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def main():
    c = httpx.Client(timeout=30)
    # 1) 注册/登录
    r = c.post(f"{BASE}/auth/register", json={"username": USERNAME, "password": PASSWORD, "confirm_password": PASSWORD, "agree_terms": True, "nickname": "E2E"})
    print("register:", r.status_code)
    r = c.post(f"{BASE}/auth/login", json={"username": USERNAME, "password": PASSWORD})
    token = r.json()["access_token"]
    print("login ok")

    # 2) 创建项目
    r = c.post(
        f"{BASE}/projects",
        headers=auth(token),
        json={
            "title": f"E2E 验证项目 {SUFFIX}",
            "genre": "科幻",
            "style": "赛博朋克",
            "aspect_ratio": "9:16",
            "inspiration": "未来城市中，一名侦探追查失踪 AI 的下落。",
        },
    )
    pid = r.json()["id"]
    print("project:", pid)

    # 3) 剧本任务（Agnes key 失效应 graceful failed 并带错误信息）
    r = c.post(f"{BASE}/projects/{pid}/generate-script", headers=auth(token), json={})
    tid = r.json()["task_id"]
    task = wait_task(c, token, tid, timeout=180)
    print("script task:", task.get("status"), "| error:", str(task.get("error"))[:120])

    # 4) 本地素材直接驱动合成链（绕开外部 API）
    from app.core.db import SessionLocal
    from app import models
    from app.services.storage import save_bytes

    make_png("storage/images/e2e_keyframe.png")
    with open("storage/images/e2e_keyframe.png", "rb") as f:
        img_rel = save_bytes(f.read(), "images", ".png")
    db = SessionLocal()
    sb = models.Storyboard(
        project_id=pid, seq=1, shot_size="中景",
        scene="雨夜街道，侦探眺望霓虹深处", dialogue="真相就在前面。",
        emotion="紧张", duration_sec=2, status="ready",
    )
    db.add(sb)
    db.flush()
    shot = models.Storyboard.shot.property.mapper.class_ if False else models.Shot(
        storyboard_id=sb.id, status="ready"
    )
    db.add(shot)
    db.flush()
    ver = models.ShotVersion(
        shot_id=shot.id, version_no=1, image_url=img_rel, prompt="e2e", is_selected=True, status="succeeded"
    )
    db.add(ver)
    db.commit()
    shot.selected_version_id = ver.id
    db.commit()
    print("seeded storyboard/shot/version:", sb.id, shot.id, ver.id, img_rel)

    # 5) 自动时间线 + 合成
    r = c.post(f"{BASE}/projects/{pid}/timelines", headers=auth(token))
    tl = r.json()
    print("timeline:", tl.get("id"), "items:", len(tl.get("items") or []))
    r = c.post(f"{BASE}/timelines/{tl['id']}/composite", headers=auth(token))
    ctid = r.json()["task_id"]
    task = wait_task(c, token, ctid, timeout=180)
    print("composite task:", task.get("status"), "| error:", str(task.get("error"))[:200])

    # 6) 导出
    r = c.get(f"{BASE}/projects/{pid}/export", headers=auth(token))
    print("export:", r.status_code, r.json())

    # 7) SSE 可连接性（读首帧）
    with httpx.stream("GET", f"{BASE}/projects/{pid}/stream", params={"token": token}, timeout=10) as s:
        print("sse status:", s.status_code)
    db.close()


if __name__ == "__main__":
    sys.exit(main())
