"""测试公共夹具。"""
import pytest

from app.api import routes_auth


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """每个用例前清空认证限流计数。

    send-code / verify-user 等接口按 IP+用户名做了分钟级限流，
    计数是进程级状态，会让连续运行的用例互相影响。
    """
    routes_auth._limiter.reset()
    yield
    routes_auth._limiter.reset()