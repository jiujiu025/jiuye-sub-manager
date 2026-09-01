"""健康检查接口。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """容器编排与本地健康检查。"""

    return {"status": "ok"}
