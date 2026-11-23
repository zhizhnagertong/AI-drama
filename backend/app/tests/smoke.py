"""端到端冒烟测试：注册 → 登录 → 创建项目 → generate-script → 轮询任务 → 任务列表。

用法：python tests/smoke.py [base_url]
默认 base_url=http://localhost:8010（与 start.ps1 启动的后端端口一致）。
"""
import json
import sys
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010"
API = f"{BASE}/api/v1"

USERNAME = f"smoke{uuid.uuid4().hex[:8]}"
PASSWORD = "SmokePass123"


def main() -> int:
    client = httpx.Client(timeout=60)

    print(f"[1] 注册 {USERNAME}: ", end="")
    r = client.post(
        f"{API}/auth/register",
        json={"username": USERNAME, "password": PASSWORD, "confirm_password": PASSWORD, "agree_terms": True},
    )
    print(r.status_code, r.json() if r.status_code != 201 else "ok")
    assert r.status_code == 201, f"注册失败: {r.text}"

    print("[2] 登录: ", end="")
    r = client.post(f"{API}/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert r.status_code == 200, f"登录失败: {r.text}"
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("ok")

    print("[3] /auth/me: ", end="")
    r = client.get(f"{API}/auth/me", headers=headers)
    assert r.status_code == 200, f"me 失败: {r.text}"
    print(r.json()["username"], r.json()["roles"])

    print("[4] 创建项目: ", end="")
    r = client.post(
        f"{API}/projects",
        headers=headers,
        json={
            "title": "霓虹侦探",
            "genre": "科幻悬疑",
            "style": "赛博朋克动画风",
            "aspect_ratio": "9:16",
            "inspiration": "2088 年的新京市，侦探林霄在雨夜追查一起记忆芯片失窃案，发现凶手竟是自己失散多年的妹妹。",
        },
    )
    assert r.status_code == 200, f"创建项目失败: {r.text}"
    project_id = r.json()["id"]
    print(f"ok id={project_id}")

    # SSE 订阅验证（后台监听 20 秒，收集事件）
    events: list[dict] = []

    def listen():
        try:
            with httpx.Client(timeout=30) as sse_client:
                with sse_client.stream(
                    "GET", f"{API}/projects/{project_id}/stream", params={"token": token}
                ) as resp:
                    for line in resp.iter_lines():
                        if line.startswith("data: "):
                            events.append(json.loads(line[6:]))
                            if len(events) >= 3:
                                return
        except Exception:
            pass

    import threading

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(1)

    print("[5] 提交 generate-script: ", end="")
    r = client.post(f"{API}/projects/{project_id}/generate-script", headers=headers, json={})
    assert r.status_code == 200, f"提交剧本任务失败: {r.text}"
    task_id = r.json()["task_id"]
    print(f"ok task_id={task_id}")

    # 轮询任务状态（最长 180 秒）
    final = None
    start = time.time()
    while time.time() - start < 180:
        r = client.get(f"{API}/tasks/{task_id}", headers=headers)
        data = r.json()
        if data["status"] in ("succeeded", "failed"):
            final = data
            break
        time.sleep(3)
    assert final is not None, "任务 180 秒内未结束"
    print(f"[6] 任务结束: status={final['status']} progress={final['progress']}")
    if final["status"] == "failed":
        print(f"    error: {final['error']}")
    else:
        print(f"    result: {json.dumps(final['result'], ensure_ascii=False)}")

    print("[7] 任务列表: ", end="")
    r = client.get(f"{API}/tasks", headers=headers, params={"project_id": project_id})
    assert r.status_code == 200, f"任务列表失败: {r.text}"
    print(f"total={r.json()['total']}")

    print(f"[8] SSE 事件数: {len(events)}", ("示例: " + json.dumps(events[0], ensure_ascii=False)) if events else "(未收到)")

    print("[9] 项目详情统计: ", end="")
    r = client.get(f"{API}/projects/{project_id}", headers=headers)
    print(json.dumps(r.json().get("stats"), ensure_ascii=False))

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
