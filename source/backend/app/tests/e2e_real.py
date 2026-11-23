"""真实模型端到端验证：灵感→剧本→角色参考图→分镜抽卡→选定→图生视频→合成→导出。

依赖有效的 Agnes API key（backend/.env）。视频生成耗时较长（数分钟），请耐心等待。
"""
import random
import sys
import time

import httpx

BASE = "http://localhost:8010/api/v1"
SUFFIX = random.randint(1000, 9999)
USERNAME = f"real{SUFFIX}"
PASSWORD = "Real123456"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def req_json(client, method, url, token=None, body=None, tries=5):
    """带重试的请求（本机偶发连接中断 10053 时自动恢复）。"""
    last = None
    for i in range(tries):
        try:
            headers = auth(token) if token else {}
            r = client.request(method, url, headers=headers, json=body)
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 * (i + 1))
    raise last


def post_json(client, url, token, body=None):
    """POST 并解析 JSON，非 JSON 响应时打印原始内容便于排查。"""
    r = client.post(url, headers=auth(token), json=body or {})
    try:
        return r.json()
    except Exception:
        print(f"  !! {url} -> {r.status_code}: {r.text[:200]}")
        raise


def wait_task(client, token, task_id, timeout=900, label=""):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = req_json(client, "GET", f"{BASE}/tasks/{task_id}", token)
        st, prog = r.get("status"), r.get("progress")
        cur = f"{st} {prog}%"
        if cur != last:
            print(f"  [{label}] {cur}", flush=True)
            last = cur
        if st in ("succeeded", "failed", "canceled"):
            return r
        time.sleep(5)
    return {"status": "timeout"}


def main():
    c = httpx.Client(timeout=60)
    print("== 1. 注册登录 ==")
    req_json(c, "POST", f"{BASE}/auth/register", body={"username": USERNAME, "password": PASSWORD, "confirm_password": PASSWORD, "agree_terms": True, "nickname": "RealE2E"})
    token = req_json(c, "POST", f"{BASE}/auth/login", body={"username": USERNAME, "password": PASSWORD})["access_token"]

    print("== 2. 创建项目 ==")
    pid = req_json(
        c, "POST", f"{BASE}/projects", token,
        {
            "title": f"真实全流程验证 {SUFFIX}",
            "genre": "科幻",
            "style": "赛博朋克",
            "aspect_ratio": "9:16",
            "inspiration": "2089年的雨夜，失去记忆的女侦探在霓虹都市中追查一个会做梦的AI，却发现AI梦到的正是她自己消失的过去。",
        },
    )["id"]
    print("  project:", pid)

    print("== 3. 生成剧本（agnes-2.5-flash）==")
    tid = req_json(c, "POST", f"{BASE}/projects/{pid}/generate-script", token, {})["task_id"]
    task = wait_task(c, token, tid, timeout=300, label="script")
    print("  result:", task.get("status"), str(task.get("error"))[:150] if task.get("error") else "")
    if task.get("status") != "succeeded":
        sys.exit(1)

    detail = req_json(c, "GET", f"{BASE}/projects/{pid}", token)
    sbs = detail["storyboards"]
    chars = detail["characters"]
    print(f"  分镜 {len(sbs)} 条 / 角色 {len(chars)} 个: {[ch['name'] for ch in chars][:5]}")
    print(f"  首条分镜: 景别={sbs[0]['shot_size']} 台词={(sbs[0]['dialogue'] or '')[:30]}")

    print("== 4. 角色参考图（agnes-image-2.1-flash）==")
    if chars:
        tid = post_json(c, f"{BASE}/characters/{chars[0]['id']}/generate-ref", token)["task_id"]
        task = wait_task(c, token, tid, timeout=300, label="ref")
        print("  result:", task.get("status"), str(task.get("error"))[:150] if task.get("error") else "")

    print("== 5. 分镜抽卡（2 版本）==")
    tid = post_json(c, f"{BASE}/storyboards/{sbs[0]['id']}/generate-image", token, {"count": 2})["task_id"]
    task = wait_task(c, token, tid, timeout=600, label="image")
    print("  result:", task.get("status"), str(task.get("error"))[:150] if task.get("error") else "")
    if task.get("status") != "succeeded":
        sys.exit(1)

    detail = req_json(c, "GET", f"{BASE}/projects/{pid}", token)
    shot = detail["storyboards"][0]["shots"][0]
    versions = shot["versions"]
    print(f"  版本数: {len(versions)}  首图: {versions[0]['image_url'][:60]}")

    print("== 6. 选定版本 ==")
    req_json(c, "POST", f"{BASE}/shots/{shot['id']}/select-version", token, {"version_id": versions[0]["id"]})

    print("== 7. 图生视频（agnes-video-2.5-flash，可能耗时数分钟）==")
    tid = post_json(c, f"{BASE}/shots/{shot['id']}/generate-video", token, {"seconds": "4"})["task_id"]
    task = wait_task(c, token, tid, timeout=900, label="video")
    print("  result:", task.get("status"), str(task.get("error"))[:150] if task.get("error") else "")

    print("== 8. 时间线 + 合成成片 ==")
    tl = req_json(c, "POST", f"{BASE}/projects/{pid}/timelines", token)
    print("  timeline:", tl.get("id"), "items:", len(tl.get("items") or []))
    tid = post_json(c, f"{BASE}/timelines/{tl['id']}/composite", token)["task_id"]
    task = wait_task(c, token, tid, timeout=600, label="composite")
    print("  result:", task.get("status"), str(task.get("error"))[:200] if task.get("error") else "")

    print("== 9. 导出 ==")
    print("  export:", req_json(c, "GET", f"{BASE}/projects/{pid}/export", token))

    print("\n== 全流程完成 ==")
    print(f"项目 ID: {pid}（可在前端 http://localhost:5173 创作-作品管理 中查看）")


if __name__ == "__main__":
    main()
