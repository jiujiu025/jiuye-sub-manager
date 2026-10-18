"""节点公网 IP 地区识别服务。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.geo import GeoIPCache
from app.models.node import Node
from app.utils.country import (
    country_name_from_code,
    detect_country,
    resolve_public_ip,
)

logger = logging.getLogger(__name__)


class GeoIPService:
    """异步任务和管理员手动操作共用的地区识别服务。"""

    def __init__(self, db: Session, http_client: Any | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(
            timeout=self.settings.geoip_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            headers={"Accept": "application/json", "User-Agent": "Sub-Manager/1.0"},
        )

    def close(self) -> None:
        """释放默认 HTTP 客户端。"""

        if self._owns_client:
            self.client.close()

    def resolve_nodes(
        self,
        *,
        node_ids: list[int] | None = None,
        limit: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """批量识别节点地区；单个 IP 只访问一次地理服务。"""

        safe_limit = max(1, min(limit or self.settings.geoip_batch_size, 500))
        statement = select(Node).order_by(Node.id.asc()).limit(safe_limit)
        if node_ids:
            statement = select(Node).where(Node.id.in_(node_ids)).order_by(Node.id.asc()).limit(safe_limit)
        elif not force:
            statement = statement.where(Node.country.is_(None))
        nodes = list(self.db.scalars(statement).all())
        result: dict[str, Any] = {
            "processed": 0,
            "resolved": 0,
            "name_resolved": 0,
            "cached": 0,
            "skipped": 0,
            "failed": 0,
            "remaining": 0,
            "errors": [],
        }
        for node in nodes:
            result["processed"] += 1
            status, detail = self.resolve_node(node, force=force)
            if status == "resolved":
                result["resolved"] += 1
                if detail == "name":
                    result["name_resolved"] += 1
                elif detail == "cache":
                    result["cached"] += 1
            elif status == "skipped":
                result["skipped"] += 1
            else:
                result["failed"] += 1
                if detail and len(result["errors"]) < 20:
                    result["errors"].append(detail)
        self.db.commit()
        if not node_ids:
            result["remaining"] = self.db.scalar(
                select(Node.id).where(Node.country.is_(None)).limit(1)
            ) is not None
        return result

    def resolve_node(self, node: Node, *, force: bool = False) -> tuple[str, str | None]:
        """识别单个节点；返回 resolved/skipped/failed 和非敏感原因。"""

        if node.country and not force:
            return "skipped", "已有地区"
        named_country = detect_country(node.name or node.original_name or "")
        if named_country and not force:
            node.country = named_country
            return "resolved", "name"
        if not self.settings.geoip_enabled:
            return "skipped", "地区识别服务已禁用"
        ip_address = resolve_public_ip(node.server)
        if not ip_address:
            return "skipped", "服务器不是可识别的公网 IP"
        cached = self.db.scalar(
            select(GeoIPCache).where(GeoIPCache.ip_address == ip_address)
        )
        now = utcnow()
        if cached is not None and not force and self._as_utc(cached.expires_at) > now:
            if cached.status == "success" and cached.country:
                node.country = cached.country
                return "resolved", "cache"
            return "failed", cached.last_error or "IP 地区识别失败"
        try:
            payload = self._fetch(ip_address)
            country, country_code, region, city = self._parse_payload(payload)
            if not country:
                raise ValueError("地理服务未返回国家信息")
            self._save_cache(
                cached,
                ip_address,
                country=country,
                country_code=country_code,
                region=region,
                city=city,
                status="success",
                error=None,
            )
            node.country = country
            return "resolved", "api"
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # 第三方服务失败不能阻断节点导入、同步或其他节点识别。
            message = self._safe_error(exc)
            self._save_cache(
                cached,
                ip_address,
                country=None,
                country_code=None,
                region=None,
                city=None,
                status="error",
                error=message,
            )
            logger.warning("节点地区识别失败：%s", message)
            return "failed", message

    def _fetch(self, ip_address: str) -> dict[str, Any]:
        template = self.settings.geoip_api_url.strip()
        if "{ip}" not in template:
            raise ValueError("GEOIP_API_URL 必须包含 {ip} 占位符")
        url = template.replace("{ip}", quote(ip_address, safe=":"))
        response = self.client.get(url, timeout=self.settings.geoip_timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("地理服务响应格式无效")
        return payload

    @staticmethod
    def _parse_payload(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
        """兼容 ipwho.is、ip-api 和常见自建 JSON 地理接口字段。"""

        if payload.get("success") is False or str(payload.get("status", "")).lower() == "fail":
            raise ValueError("地理服务返回失败")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        location = data.get("location") if isinstance(data.get("location"), dict) else {}
        country = data.get("country") or data.get("country_name") or location.get("country")
        code = data.get("country_code") or data.get("countryCode") or location.get("country_code")
        country = country_name_from_code(str(code) if code else None, str(country) if country else None)
        region = data.get("region") or data.get("regionName") or location.get("region")
        city = data.get("city") or location.get("city")
        return (
            country,
            str(code).upper() if code else None,
            str(region) if region else None,
            str(city) if city else None,
        )

    def _save_cache(
        self,
        cached: GeoIPCache | None,
        ip_address: str,
        *,
        country: str | None,
        country_code: str | None,
        region: str | None,
        city: str | None,
        status: str,
        error: str | None,
    ) -> None:
        now = utcnow()
        minutes = (
            self.settings.geoip_cache_ttl_hours * 60
            if status == "success"
            else self.settings.geoip_error_retry_minutes
        )
        if cached is None:
            cached = GeoIPCache(ip_address=ip_address)
            self.db.add(cached)
        cached.country = country
        cached.country_code = country_code
        cached.region = region
        cached.city = city
        cached.status = status
        cached.last_error = error[:200] if error else None
        cached.checked_at = now
        cached.expires_at = now + timedelta(minutes=max(1, minutes))
        # 测试会话和应用会话均关闭 autoflush，立即刷入可保证同一批次的相同 IP 只请求一次。
        self.db.flush()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        """兼容 SQLite 返回的无时区时间。"""

        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        text = str(exc).strip()
        return text[:200] if text else "地理服务请求失败"
