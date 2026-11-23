"""进程内 SSE 事件总线：每个订阅者一个 asyncio.Queue。

publish 可能来自 worker 线程（asyncio.to_thread 内），
因此统一通过主事件循环 call_soon_threadsafe 投递，保证线程安全。
"""
import asyncio

_subscribers: dict[int, set[asyncio.Queue]] = {}
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """在 FastAPI startup 中记录主事件循环。"""
    global _loop
    _loop = loop


def subscribe(project_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.setdefault(project_id, set()).add(q)
    return q


def unsubscribe(project_id: int, q: asyncio.Queue) -> None:
    _subscribers.get(project_id, set()).discard(q)
    if not _subscribers.get(project_id):
        _subscribers.pop(project_id, None)


def _safe_put(q: asyncio.Queue, event: dict) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        pass  # 丢弃溢出事件，避免阻塞任务线程


def publish(project_id: int, event: dict) -> None:
    queues = list(_subscribers.get(project_id, ()))
    if not queues:
        return
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    for q in queues:
        if _loop is not None and current_loop is not _loop:
            # 跨线程（worker 线程）投递
            _loop.call_soon_threadsafe(_safe_put, q, event)
        else:
            _safe_put(q, event)
