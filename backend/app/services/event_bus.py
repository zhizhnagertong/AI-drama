"""进程内 SSE 事件总线：每个订阅者一个 asyncio.Queue。

publish 可能来自 worker 线程（asyncio.to_thread 内），
因此统一通过主事件循环 call_soon_threadsafe 投递，保证线程安全；
订阅表本身由 threading.Lock 保护（subscribe/unsubscribe 在事件循环线程，
publish 可能在工作线程，直接 list(set) 会触发 "Set changed size during iteration"）。
"""
import asyncio
import threading

_subscribers: dict[int, set[asyncio.Queue]] = {}
_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None

MAX_QUEUE = 500


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """在 FastAPI startup 中记录主事件循环。"""
    global _loop
    _loop = loop


def subscribe(project_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
    with _lock:
        _subscribers.setdefault(project_id, set()).add(q)
    return q


def unsubscribe(project_id: int, q: asyncio.Queue) -> None:
    with _lock:
        subs = _subscribers.get(project_id)
        if subs is None:
            return
        subs.discard(q)
        if not subs:
            _subscribers.pop(project_id, None)


def _safe_put(q: asyncio.Queue, event: dict) -> None:
    # 队列满时丢最旧的一条：终态事件（succeeded/failed）比中间进度更重要
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        pass  # 竞态下仍可能满，丢弃本条避免阻塞任务线程


def publish(project_id: int, event: dict) -> None:
    with _lock:
        queues = list(_subscribers.get(project_id, ()))
    if not queues:
        return
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    for q in queues:
        try:
            if _loop is not None and current_loop is not _loop:
                # 跨线程（worker 线程）投递
                _loop.call_soon_threadsafe(_safe_put, q, event)
            else:
                _safe_put(q, event)
        except RuntimeError:
            # 事件循环已关闭（服务关停中）：丢弃事件，不影响业务
            return