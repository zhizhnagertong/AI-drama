"""真实环境验证：项目→集→分镜 三层接口冒烟（不触发付费模型调用）。"""
import random

import httpx

BASE = "http://localhost:8010/api/v1"
SUFFIX = random.randint(10000, 99999)
USERNAME = f"epv{SUFFIX}"
PASSWORD = "Epv123456"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def main():
    c = httpx.Client(timeout=30, trust_env=False)
    r = c.post(f"{BASE}/auth/register", json={"username": USERNAME, "password": PASSWORD, "confirm_password": PASSWORD, "agree_terms": True})
    print("register:", r.status_code, r.text[:200])
    r = c.post(f"{BASE}/auth/login", json={"username": USERNAME, "password": PASSWORD})
    print("login:", r.status_code, r.text[:200])
    token = r.json()["access_token"]

    # 1) 创建项目 → 自动第 1 集
    pr = c.post(f"{BASE}/projects", json={"title": "多集验证项目", "inspiration": "点子", "style": "日系动漫"}, headers=auth(token))
    print("create project:", pr.status_code, pr.text[:300])
    p = pr.json()
    pid = p["id"]
    eps = c.get(f"{BASE}/projects/{pid}/episodes", headers=auth(token)).json()
    assert eps["total"] == 1 and eps["items"][0]["episode_number"] == 1, eps
    ep1 = eps["items"][0]["id"]
    print("1) 创建项目自动建第1集 OK", "detail.episodes:", len(c.get(f"{BASE}/projects/{pid}", headers=auth(token)).json()["episodes"]))

    # 2) 新增第 2 集（带梗概）
    e2 = c.post(f"{BASE}/projects/{pid}/episodes", json={"title": "反转", "synopsis": "第二集梗概"}, headers=auth(token)).json()
    assert e2["episode_number"] == 2 and e2["style"] == "日系动漫", e2
    print("2) 新增第2集 + 配置快照 OK", e2["id"], e2["title"])

    # 3) 集详情 / 更新 / 统计
    d = c.get(f"{BASE}/episodes/{e2['id']}", headers=auth(token)).json()
    assert d["stats"]["storyboard_count"] == 0 and d["storyboards"] == []
    u = c.put(f"{BASE}/episodes/{e2['id']}", json={"status": "completed"}, headers=auth(token)).json()
    assert u["status"] == "completed"
    print("3) 集详情/更新 OK")

    # 4) 手动分镜归属集
    sb = c.post(f"{BASE}/episodes/{e2['id']}/storyboards", json={"scene": "测试一幕", "duration_sec": 5}, headers=auth(token)).json()
    assert sb["episode_id"] == e2["id"] and sb["seq"] == 1, sb
    lst = c.get(f"{BASE}/episodes/{e2['id']}/storyboards", headers=auth(token)).json()
    assert lst["total"] == 1
    print("4) 按集新增/列出分镜 OK")

    # 5) 项目级分镜缺省归属默认集
    sb2 = c.post(f"{BASE}/projects/{pid}/storyboards", json={"scene": "默认集一幕"}, headers=auth(token)).json()
    assert sb2["episode_id"] == ep1, sb2
    print("5) 项目级分镜回退默认集 OK")

    # 6) 删除集保护 + 软删（两集时删其一成功，剩最后一集时禁止删除）
    r2 = c.delete(f"{BASE}/episodes/{e2['id']}", headers=auth(token))
    assert r2.status_code == 200, r2.text
    r3 = c.delete(f"{BASE}/episodes/{ep1}", headers=auth(token))
    assert r3.status_code == 400, "最后一集应禁止删除"
    print("6) 软删集 + 最后一集保护 OK")

    # 7) 时间线按集：ep1 有分镜但无已选版本 → 400；items 显式传入 → 成功
    tl = c.post(f"{BASE}/projects/{pid}/timelines", json={"episode_id": ep1, "items": [{"shot_id": None, "media_url": "/static/x.png", "duration_sec": 3}]}, headers=auth(token)).json()
    assert tl["episode_id"] == ep1, tl
    ex = c.get(f"{BASE}/projects/{pid}/export", params={"episode_id": 999999}, headers=auth(token))
    assert ex.status_code == 404
    print("7) 时间线按集 / 导出过滤 OK")

    # 8) 越权 404
    c.post(f"{BASE}/auth/register", json={"username": f"epv_o_{SUFFIX}", "password": PASSWORD})
    t2 = c.post(f"{BASE}/auth/login", json={"username": f"epv_o_{SUFFIX}", "password": PASSWORD}).json()["access_token"]
    assert c.get(f"{BASE}/episodes/{ep1}", headers=auth(t2)).status_code == 404
    print("8) 跨用户越权 404 OK")

    # 9) 存量项目回填检查：任意一个非本次创建的项目详情应含 episodes 且分镜已归集
    old = [x for x in c.get(f"{BASE}/projects?page_size=100", headers=auth(token)).json()["items"] if x["id"] != pid]
    if old:
        oid = old[0]["id"]
        od = c.get(f"{BASE}/projects/{oid}", headers=auth(token)).json()
        assert len(od["episodes"]) >= 1, od
        assert all(sb.get("episode_id") for sb in od["storyboards"]), "存量分镜应已回填 episode_id"
        print(f"9) 存量项目 {oid} 回填 OK（{len(od['episodes'])} 集，{len(od['storyboards'])} 分镜已归集）")
    else:
        print("9) 无其他存量项目可查（跳过）")

    print("\nALL EPISODE VERIFICATION PASSED")


if __name__ == "__main__":
    main()
