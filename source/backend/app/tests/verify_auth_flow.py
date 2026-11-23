"""登录注册流程端到端验证（真实 MySQL，端口 8011）。

覆盖：注册 201 / 重名 409 / 弱密码 422 / 条款 422 / 登录双令牌 / 记住我 7 天 /
无 token 401 / refresh 轮换 / 连续失败锁定 423 / 找回密码三步 / 重置后旧令牌失效 / 登出撤销。
"""
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8011/api/v1"
API = f"{BASE}/auth"
PWD = "Abcd1234"
NEW_PWD = "NewPwd5678"

passed = 0


def ok(name):
    global passed
    passed += 1
    print(f"  ✓ {name}")


def check(cond, name, extra=""):
    if not cond:
        print(f"  ✗ {name} {extra}")
        sys.exit(1)
    ok(name)


def main():
    c = httpx.Client(timeout=30, trust_env=False)
    u = f"flow{uuid.uuid4().hex[:6]}"

    print("== 注册 ==")
    r = c.post(f"{API}/register", json={"username": u, "password": PWD, "confirm_password": PWD, "agree_terms": True, "email": f"{u}@ex.com"})
    check(r.status_code == 201 and "user_id" in r.json(), "注册 201", r.text)

    r = c.post(f"{API}/register", json={"username": u, "password": PWD, "confirm_password": PWD, "agree_terms": True})
    check(r.status_code == 409 and r.json()["biz_code"] == "USERNAME_TAKEN", "重名 409", r.text)

    r = c.post(f"{API}/register", json={"username": "weak" + uuid.uuid4().hex[:4], "password": "alllower1", "confirm_password": "alllower1", "agree_terms": True})
    check(r.status_code == 422 and "password" in r.json().get("field_errors", {}), "弱密码 422 字段级回显", r.text)

    r = c.post(f"{API}/register", json={"username": "mism" + uuid.uuid4().hex[:4], "password": PWD, "confirm_password": "Abcd9999", "agree_terms": True})
    check(r.status_code == 422, "确认密码不一致 422", r.text)

    r = c.post(f"{API}/register", json={"username": "terms" + uuid.uuid4().hex[:4], "password": PWD, "confirm_password": PWD, "agree_terms": False})
    check(r.status_code == 422 and r.json().get("biz_code") == "TERMS_NOT_AGREED", "未勾选条款 422", r.text)

    print("== 登录 ==")
    r = c.post(f"{API}/login", json={"username": u, "password": PWD})
    d = r.json()
    check(r.status_code == 200 and d["access_token"] and d["refresh_token"] and d["expires_in"] == 900 and d["refresh_expires_in"] == 12 * 3600, "登录双令牌（会话级 12h）", r.text)
    access, refresh = d["access_token"], d["refresh_token"]

    r = c.post(f"{API}/login", json={"username": u, "password": PWD, "remember": True})
    check(r.json()["refresh_expires_in"] == 7 * 24 * 3600, "记住我 refresh 7 天", r.text)

    r = c.post(f"{API}/login", json={"username": u, "password": "Wrong12345"})
    check(r.status_code == 401 and r.json()["biz_code"] == "BAD_CREDENTIALS", "密码错误 401", r.text)

    r = c.post(f"{API}/login", json={"username": "ghost" + uuid.uuid4().hex[:4], "password": PWD})
    check(r.status_code == 401 and r.json()["biz_code"] == "BAD_CREDENTIALS", "防枚举：不存在用户同提示", r.text)

    r = c.get(f"{API}/me")
    check(r.status_code == 401, "无 token 401", r.text)
    r = c.get(f"{API}/me", headers={"Authorization": f"Bearer {access}"})
    check(r.status_code == 200 and r.json()["username"] == u and r.json()["email"] == f"{u}@ex.com", "/me 返回用户信息", r.text)

    print("== 刷新 ==")
    r = c.post(f"{API}/refresh", json={"refresh_token": refresh})
    d2 = r.json()
    check(r.status_code == 200 and d2["access_token"] and d2["refresh_token"] != refresh, "refresh 换发新对", r.text)
    r = c.post(f"{API}/refresh", json={"refresh_token": refresh})
    check(r.status_code == 401, "旧 refresh 轮换后作废", r.text)
    refresh = d2["refresh_token"]
    access = d2["access_token"]

    print("== 锁定 ==")
    u2 = f"lock{uuid.uuid4().hex[:6]}"
    c.post(f"{API}/register", json={"username": u2, "password": PWD, "confirm_password": PWD, "agree_terms": True})
    for i in range(4):
        r = c.post(f"{API}/login", json={"username": u2, "password": "Wrong12345"})
        check(r.status_code == 401 and "剩余" in r.json()["message"], f"第 {i+1} 次失败提示剩余次数", r.text)
    r = c.post(f"{API}/login", json={"username": u2, "password": "Wrong12345"})
    check(r.status_code == 423 and r.json()["biz_code"] == "ACCOUNT_LOCKED", "第 5 次失败触发锁定 423", r.text)
    r = c.post(f"{API}/login", json={"username": u2, "password": PWD})
    check(r.status_code == 423 and r.json()["biz_code"] == "ACCOUNT_LOCKED", "锁定期间正确密码也被拒", r.text)

    print("== 找回密码 ==")
    r = c.post(f"{API}/verify-user", json={"username": u})
    check(r.json()["exists"] is True and "*" in r.json()["masked_contact"], "Step1 用户存在 + 邮箱脱敏", r.text)
    r = c.post(f"{API}/verify-user", json={"username": "ghost999"})
    check(r.json()["exists"] is False, "Step1 用户不存在", r.text)

    r = c.post(f"{API}/password/send-code", json={"username": u})
    check(r.status_code == 200 and r.json()["code_hint"], "Step2 下发验证码", r.text)
    code = r.json()["code_hint"]
    r = c.post(f"{API}/password/send-code", json={"username": u})
    check(r.status_code == 429, "重发冷却 429", r.text)

    r = c.post(f"{API}/password/verify-code", json={"username": u, "code": "000000"})
    check(r.status_code == 400 and r.json()["biz_code"] == "CODE_INVALID", "错误验证码 400", r.text)
    r = c.post(f"{API}/password/verify-code", json={"username": u, "code": code})
    check(r.json()["valid"] is True, "验证码校验通过", r.text)

    r = c.post(f"{API}/password/reset", json={"username": u, "code": code, "new_password": PWD, "confirm_password": PWD})
    check(r.status_code == 400 and r.json()["biz_code"] == "PASSWORD_REUSED", "密码复用被拒", r.text)
    r = c.post(f"{API}/password/reset", json={"username": u, "code": code, "new_password": NEW_PWD, "confirm_password": NEW_PWD})
    check(r.status_code == 200 and r.json()["username"] == u, "重置成功", r.text)

    r = c.post(f"{API}/refresh", json={"refresh_token": refresh})
    check(r.status_code == 401, "重置后旧 refresh 全部失效", r.text)
    r = c.post(f"{API}/login", json={"username": u, "password": NEW_PWD})
    check(r.status_code == 200, "新密码可登录", r.text)
    tokens = r.json()

    print("== 登出 ==")
    r = c.post(f"{API}/logout", json={"refresh_token": tokens["refresh_token"]}, headers={"Authorization": f"Bearer {tokens['access_token']}"})
    check(r.status_code == 200 and r.json()["revoked"] is True, "登出撤销 refresh", r.text)
    r = c.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
    check(r.status_code == 401, "登出后 refresh 不可用", r.text)

    print(f"\n✅ 全部通过（{passed} 项）")


if __name__ == "__main__":
    main()
