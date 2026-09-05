"""套餐相关请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PackageRulesPayload(BaseModel):
    """套餐规则：套餐不保存节点副本，只保存筛选与展示规则。"""

    source_filter: list[str] = Field(default_factory=list)
    node_ids: list[int] = Field(default_factory=list)
    country_filter: list[str] = Field(default_factory=list)
    type_filter: list[str] = Field(default_factory=list)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    rename_rules: list[dict[str, Any]] = Field(default_factory=list)
    sort_rules: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("include_keywords", "exclude_keywords", mode="before")
    @classmethod
    def remove_empty_keywords(cls, value: object) -> object:
        """去掉空白关键词，避免空字符串匹配全部或排除全部节点。"""

        if not isinstance(value, list):
            return value
        return [
            item.strip() if isinstance(item, str) else item
            for item in value
            if not isinstance(item, str) or item.strip()
        ]


class PackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    subscription_name: str | None = Field(default=None, max_length=128)
    enabled: bool = True
    description: str | None = None
    rules: PackageRulesPayload = Field(default_factory=PackageRulesPayload)


class PackageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    subscription_name: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
    description: str | None = None
    rules: PackageRulesPayload | None = None


class PackageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    subscription_name: str | None = None
    enabled: bool
    description: str | None
    token_prefix: str
    subscription_url: str | None = None
    created_at: datetime
    updated_at: datetime
    rules: PackageRulesPayload = Field(default_factory=PackageRulesPayload)


class PackageDetail(PackageSummary):
    pass


class PackageCreateResponse(PackageDetail):
    """创建套餐时返回一次明文 Token，后续不再返回。"""

    token: str
    subscription_url: str


class PackageTokenResponse(BaseModel):
    package_id: int
    token: str
    subscription_url: str


class PreviewNode(BaseModel):
    """套餐预览节点（应用规则后的展示结果）。"""

    id: int
    source_name: str
    original_name: str
    name: str
    type: str
    server: str
    port: int
    country: str | None
