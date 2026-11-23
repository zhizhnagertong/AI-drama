"""进程内滑动窗口限流（单实例够用，多实例需换 Redis）。

用于未鉴权接口的防刷：找回密码 send-code / verify-user、登录等，
避免被批量探测用户名或刷验证码。
"""
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_gc = time.monotonic()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        """记录一次命中；超过窗口内限额返回 False。"""
        now = time.monotonic()
        deadline = now - window_seconds
        with self._lock:
            self._gc(now)
            bucket = self._hits[key]
            while bucket and bucket[0] <= deadline:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def retry_after(self, key: str, window_seconds: int) -> int:
        """距离窗口内最早一次命中的剩余秒数（用于 Retry-After 提示）。"""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.get(key)
            if not bucket:
                return 0
            return max(1, int(window_seconds - (now - bucket[0])))

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    def _gc(self, now: float) -> None:
        """每 10 分钟清理一次空桶，避免 key 无限增长。"""
        if now - self._last_gc < 600:
            return
        self._last_gc = now
        empty = [k for k, v in self._hits.items() if not v]
        for k in empty:
            self._hits.pop(k, None)