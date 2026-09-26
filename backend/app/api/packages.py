"""套餐管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.models.user import User
from app.repositories.package_repo import PackageRepository
from app.schemas.package import (
    PackageCreate,
    PackageCreateResponse,
    PackageDetail,
    PackageSubscriptionUrlResponse,
    PackageTokenResponse,
    PackageTokenUpdate,
    PackageUpdate,
    PreviewNode,
)
from app.services.package_service import (
    PackageService,
    subscription_url,
)

router = APIRouter(prefix="/packages", tags=["packages"])


def _get_package_or_404(db: Session, package_id: int):
    package = PackageRepository(db).get(package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="套餐不存在")
    return package


def _subscription_url(token: str) -> str:
    return subscription_url(token)


@router.get("", response_model=list[PackageDetail])
def list_packages(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[PackageDetail]:
    """套餐列表。"""

    packages = PackageRepository(db).list()
    service = PackageService(db)
    return [service.to_detail(package) for package in packages]


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
        **detail.model_dump(exclude={"subscription_url"}),
        token=token,
        subscription_url=_subscription_url(token),
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


@router.get("/{package_id}/subscription-url", response_model=PackageSubscriptionUrlResponse)
def get_subscription_url(
    package_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> PackageSubscriptionUrlResponse:
    """管理员按需获取当前套餐订阅地址，不随列表返回。"""

    package = _get_package_or_404(db, package_id)
    url = PackageService.subscription_url(package)
    if url is None:
        raise HTTPException(status_code=404, detail="当前套餐没有可用订阅 Token")
    return PackageSubscriptionUrlResponse(package_id=package.id, subscription_url=url)


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


@router.patch("/{package_id}/token", response_model=PackageDetail)
def rename_token(
    package_id: int,
    payload: PackageTokenUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> PackageDetail:
    """修改当前订阅 Token 的后台显示名称。"""

    package = _get_package_or_404(db, package_id)
    return PackageService(db).rename_token(package, payload.token_name, admin)


@router.post("/{package_id}/revoke-token", response_model=PackageDetail)
def revoke_token(
    package_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> PackageDetail:
    """吊销当前订阅 Token；需要重新生成 Token 才能恢复访问。"""

    package = _get_package_or_404(db, package_id)
    service = PackageService(db)
    service.revoke_token(package, admin)
    return service.to_detail(package)


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
