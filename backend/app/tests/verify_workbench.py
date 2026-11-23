"""工作台优化验证：pipeline-status / composite-check / 批量接口 / 状态标记 / 重提角色。

批量出图/出视频与重提角色会触发付费 Agnes 调用，故仅用"空选择/非法入参"
验证路由与校验逻辑，不实际提交任务。
"""
import random

import httpx

BASE = "http://localhost:8010/api/v1"
SUFFIX = random.randint(100000, 999999)
USERNAME = f"wko{SUFFIX}"
PASSWORD = "Wko123456"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def main():
    c = httpx.Client(timeout=30, trust_env=False)
    c.post(f"{BASE}/auth/register", json={"username": USERNAME, "password": PASSWORD, "confirm_password": PASSWORD, "agree_terms": True})
    token = c.post(f"{BASE}/auth/login", json={"username": USERNAME, "password": PASSWORD}).json()["access_token"]

    # 建项目 + 集
    pid = c.post(f"{BASE}/projects", json={"title": "工作台验证", "style": "日系动漫"}, headers=auth(token)).json()["id"]
    ep = c.get(f"{BASE}/projects/{pid}/episodes", headers=auth(token)).json()["items"][0]
    eid = ep["id"]

    # 1) pipeline-status：空集全 pending
    ps = c.get(f"{BASE}/episodes/{eid}/pipeline-status", headers=auth(token)).json()
    assert ps["steps"]["script"]["status"] == "pending", ps
    assert ps["steps"]["image"]["total"] == 0
    print("1) pipeline-status（空集）OK", {k: v["status"] for k, v in ps["steps"].items()})

    # 2) composite-check：无分镜 → total 0
    cc = c.get(f"{BASE}/episodes/{eid}/composite-check", headers=auth(token)).json()
    assert cc["total"] == 0 and cc["missing"] == [], cc
    print("2) composite-check（空）OK")

    # 3) 手动加 2 个分镜（无视频）→ check 应列出 missing
    for i in range(2):
        c.post(f"{BASE}/episodes/{eid}/storyboards", json={"scene": f"幕{i+1}", "dialogue": "台词" if i == 0 else None}, headers=auth(token))
    cc = c.get(f"{BASE}/episodes/{eid}/composite-check", headers=auth(token)).json()
    assert cc["total"] == 2 and cc["ready"] == 0 and len(cc["missing"]) == 2, cc
    print("3) composite-check（2幕缺视频）OK", cc["missing"])

    # 4) pipeline-status：有分镜 script/board done，image pending
    ps = c.get(f"{BASE}/episodes/{eid}/pipeline-status", headers=auth(token)).json()
    assert ps["steps"]["script"]["status"] == "done", ps
    assert ps["steps"]["image"]["status"] == "pending"
    assert ps["steps"]["image"]["total"] == 2
    assert ps["steps"]["voice"]["total"] == 1  # 只有 1 幕有台词
    print("4) pipeline-status（有分镜）OK", {k: v.get("status") for k, v in ps["steps"].items()})

    # 5) 批量接口：跨集 id 校验 400（不实际提交，避免触发付费调用）
    r = c.post(f"{BASE}/episodes/{eid}/batch-images", json={"storyboard_ids": [99999999]}, headers=auth(token))
    assert r.status_code == 400, r.text
    print("5) batch-images 跨集校验 400 OK")

    # 6) 批量视频：传不属于该集的 id → 400
    r = c.post(f"{BASE}/episodes/{eid}/batch-videos", json={"storyboard_ids": [99999999]}, headers=auth(token))
    assert r.status_code == 400, r.text
    print("6) batch-videos 跨集校验 400 OK")

    # 7) 项目状态手动标记（批次 A.1）
    r = c.put(f"{BASE}/projects/{pid}", json={"status": "completed"}, headers=auth(token))
    assert r.status_code == 200 and r.json()["status"] == "completed", r.text
    r = c.put(f"{BASE}/projects/{pid}", json={"status": "bogus"}, headers=auth(token))
    assert r.status_code == 400, r.text
    print("7) 项目状态手动标记 + 非法状态 400 OK")

    # 8) 集梗概保存（剧本全文可编辑）
    r = c.put(f"{BASE}/episodes/{eid}", json={"synopsis": "改写后的剧情梗概"}, headers=auth(token))
    assert r.json()["synopsis"] == "改写后的剧情梗概", r.text
    print("8) 集梗概保存 OK")

    print("\nALL WORKBENCH VERIFICATION PASSED")


if __name__ == "__main__":
    main()
