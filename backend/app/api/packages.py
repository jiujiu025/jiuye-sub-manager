"""套餐管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.config import get_settings
from app.db import get_db
from app.models.user import User
from app.repositories.package_repo import PackageRepository
from app.schemas.package import (
    PackageCreate,
    PackageCreateResponse,
    PackageDetail,
    PackageSummary,
    PackageTokenResponse,
    PackageUpdate,
    PreviewNode,
)
from app.services.package_service import (
    PackageService,
    display_subscription_name,
    subscription_url,
    subscription_url_for_package,
)

router = APIRouter(prefix="/packages", tags=["packages"])


def _get_package_or_404(db: Session, package_id: int):
    package = PackageRepository(db).get(package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="套餐不存在")
    return package


def _subscription_url(token: str) -> str:
    return subscription_url(token)


@router.get("", response_model=list[PackageSummary])
def list_packages(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[PackageSummary]:
    """套餐列表。"""

    packages = PackageRepository(db).list()
    summaries = []
    for package in packages:
        summary = PackageSummary.model_validate(package)
        summary.subscription_url = subscription_url_for_package(package)
        summary.subscription_name = display_subscription_name(package)
        summaries.append(summary)
    return summaries


@router.post("", response_model=PackageCreateResponse, status_code=status.HTTP_201_CREATED)
def create_package(
    payload: PackageCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> PackageCreateResponse:
    """创建套餐，返回一次性明文 Token。"""

    service = PackageService(db)
    package, token = service.create(payload, admin)
    detail = service.to_detail(package)
    return PackageCreateResponse(
        **detail.model_dump(),
        token=token,
    )


@router.get("/{package_id}", response_model=PackageDetail)
def get_package(
    package_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> PackageDetail:
    """套餐详情与规则。"""

    package = _get_package_or_404(db, package_id)
    return PackageService(db).to_detail(package)


@router.put("/{package_id}", response_model=PackageDetail)
def update_package(
    package_id: int,
    payload: PackageUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> PackageDetail:
    """修改套餐名称、状态与规则。"""

    package = _get_package_or_404(db, package_id)
    service = PackageService(db)
    updated = service.update(package, payload, admin)
    return service.to_detail(updated)


@router.post("/{package_id}/regenerate-token", response_model=PackageTokenResponse)
def regenerate_token(
    package_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> PackageTokenResponse:
    """重生成订阅 Token，旧 Token 立即失效。"""

    package = _get_package_or_404(db, package_id)
    token = PackageService(db).regenerate_token(package, admin)
    return PackageTokenResponse(
        package_id=package.id,
        token=token,
        subscription_url=_subscription_url(token),
    )


@router.post("/{package_id}/toggle", response_model=PackageDetail)
def toggle_package(
    package_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> PackageDetail:
    """启用/禁用套餐。"""

    package = _get_package_or_404(db, package_id)
    service = PackageService(db)
    updated = service.toggle(package, admin)
    return service.to_detail(updated)


@router.get("/{package_id}/preview", response_model=list[PreviewNode])
def preview_package(
    package_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[PreviewNode]:
    """预览套餐规则当前命中的节点。"""

    package = _get_package_or_404(db, package_id)
    return PackageService(db).preview(package)


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_package(
    package_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> None:
    """删除套餐。"""

    package = _get_package_or_404(db, package_id)
    PackageService(db).delete(package, admin)
