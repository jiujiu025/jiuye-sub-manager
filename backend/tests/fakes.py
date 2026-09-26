"""测试用伪 HTTP 客户端，避免同步测试访问互联网。"""

from __future__ import annotations


class FakeResponse:
    def __init__(
        self, status_code: int = 200, text: str = "", headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.ok = 200 <= status_code < 400


class FakeClient:
    """记录调用参数并返回由 handler 决定的结果。"""

    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.handler(url, kwargs)

    def close(self) -> None:
        pass
