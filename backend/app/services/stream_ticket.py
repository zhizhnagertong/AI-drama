"""SSE 一次性短时票据。

EventSource 无法自定义 Header，过去只能把 access token 放进查询串，
导致令牌进入浏览器历史与反向代理访问日志。现在改为：
1. 前端用 Authorization 头调 POST /stream-ticket 换取一次性 ticket（60 秒有效）；
2. EventSource 只带 ticket，泄露也只在 60 秒内、且用一次即失效。
"""
import secrets
import threading
import time

TTL_SECONDS = 60

_tickets: dict[str, tuple[int, int, float]] = {}
_lock = threading.Lock()


def issue(project_id: int, user_id: int) -> tuple[str, int]:
    """签发一次性票据，返回 (ticket, 有效期秒数)。"""
    token = secrets.token_urlsafe(24)
    with _lock:
        _gc_locked()
        _tickets[token] = (project_id, user_id, time.monotonic() + TTL_SECONDS)
    return token, TTL_SECONDS


def consume(token: str) -> tuple[int, int] | None:
    """核销票据，返回 (project_id, user_id)；无效/过期/已用过返回 None。"""
    if not token:
        return None
    with _lock:
        record = _tickets.pop(token, None)
    if record is None:
        return None
    project_id, user_id, expires_at = record
    if expires_at < time.monotonic():
        return None
    return project_id, user_id


def _gc_locked() -> None:
    now = time.monotonic()
    expired = [k for k, v in _tickets.items() if v[2] < now]
    for key in expired:
        _tickets.pop(key, None)