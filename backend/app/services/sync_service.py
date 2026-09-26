"""上游同步业务逻辑：staging → validate → commit。"""

from __future__ import annotations

import logging
import ipaddress
import time
from io import BytesIO
import socket
from urllib.parse import urljoin, urlparse

import httpx
from curl_cffi import Curl, CurlError, CurlInfo, CurlOpt
from curl_cffi import requests as curl_requests
from curl_cffi.requests import Headers
from curl_cffi.requests import errors as curl_errors
from sqlalchemy.orm import Session

from app.core.cache import cache_service
from app.core.config import get_settings
from app.models.base import utcnow
from app.models.node import Node
from app.models.source import Source
from app.parsers import parse_content
from app.parsers.base import ParseError, ParsedNode, validate_parsed_node
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.source_repo import SourceRepository
from app.schemas.source import SyncResult
from app.services.subscription_service import SubscriptionService
from app.utils.fingerprint import (
    fingerprint_for_parsed,
    source_node_key_for_node,
    source_node_key_for_parsed,
)
from app.utils.priority import build_source_priority

logger = logging.getLogger(__name__)

_MAX_UPSTREAM_BYTES = 10 * 1024 * 1024
_MAX_REDIRECTS = 3


class _UpstreamStatusError(Exception):
    """上游返回非 2xx 状态码。"""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def _is_blocked_address(address: str) -> bool:
    """判断解析结果是否属于本机、内网或其他不应访问的地址。"""

    parsed = ipaddress.ip_address(address)
    return not parsed.is_global


def _resolve_public_addresses(hostname: str, port: int) -> list[str]:
    """解析并校验目标地址，返回本次请求需要固定的公网地址。"""

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            resolved = {
                result[4][0]
                for result in socket.getaddrinfo(
                    hostname, port, type=socket.SOCK_STREAM
                )
            }
        except socket.gaierror as exc:
            raise ParseError("上游域名解析失败") from exc
        if not resolved:
            raise ParseError("上游域名解析失败")
        if any(_is_blocked_address(item) for item in resolved):
            raise ParseError("上游地址解析到了内网或保留地址")
        return sorted(resolved)
    if _is_blocked_address(str(address)):
        raise ParseError("上游地址不允许指向内网或保留地址")
    return [str(address)]


def _validate_fetch_target(url: str) -> list[str]:
    """在每次请求前解析并校验目标，覆盖 DNS 和重定向后的地址。"""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ParseError("上游重定向目标必须是有效的 http/https 地址")
    if parsed.username or parsed.password:
        raise ParseError("上游地址不允许携带用户信息")
    try:
        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ParseError("上游地址端口无效") from exc
    if not hostname or not 0 < port < 65536:
        raise ParseError("上游地址无效")

    return _resolve_public_addresses(hostname, port)


def _parse_response_headers(raw_headers: bytes) -> Headers:
    """提取最后一个响应头块，避免中间代理信息覆盖最终响应。"""

    blocks = raw_headers.split(b"\r\n\r\n")
    header_block = next(
        (block for block in reversed(blocks) if block.lstrip().startswith(b"HTTP/")),
        b"",
    )
    lines: list[str] = []
    for line in header_block.splitlines()[1:]:
        try:
            decoded = line.decode("iso-8859-1")
        except UnicodeDecodeError:
            continue
        if ":" in decoded:
            lines.append(decoded)
    return Headers(lines)


def _pinned_curl_get(
    url: str,
    resolved_addresses: list[str],
    timeout_seconds: float,
    user_agent: str,
    request_headers: dict[str, str] | None = None,
) -> curl_requests.Response:
    """使用 CURLOPT_RESOLVE 固定已校验解析结果，阻断 DNS rebinding。"""

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolve_entries = []
    for address in resolved_addresses:
        formatted = f"[{address}]" if ":" in address else address
        resolve_entries.append(f"{hostname}:{port}:{formatted}")

    body = BytesIO()
    raw_headers = BytesIO()
    too_large = False

    def write_body(chunk: bytes) -> int:
        nonlocal too_large
        if body.tell() + len(chunk) > _MAX_UPSTREAM_BYTES:
            too_large = True
            return 0
        body.write(chunk)
        return len(chunk)

    curl = Curl()
    try:
        curl.setopt(CurlOpt.URL, url)
        curl.setopt(CurlOpt.WRITEFUNCTION, write_body)
        curl.setopt(CurlOpt.HEADERDATA, raw_headers)
        headers = [f"User-Agent: {user_agent}"]
        headers.extend(f"{key}: {value}" for key, value in (request_headers or {}).items())
        curl.setopt(CurlOpt.HTTPHEADER, headers)
        curl.setopt(CurlOpt.TIMEOUT_MS, max(1, int(timeout_seconds * 1000)))
        curl.setopt(CurlOpt.CONNECTTIMEOUT_MS, max(1, int(timeout_seconds * 1000)))
        curl.setopt(CurlOpt.FOLLOWLOCATION, False)
        curl.setopt(CurlOpt.SSL_VERIFYPEER, 1)
        curl.setopt(CurlOpt.SSL_VERIFYHOST, 2)
        curl.setopt(CurlOpt.RESOLVE, resolve_entries)
        try:
            curl.perform()
        except CurlError as exc:
            if too_large:
                raise ParseError("上游订阅内容超过 10MB 限制") from exc
            raise

        response = curl_requests.Response(curl)
        response.url = url
        response.status_code = int(curl.getinfo(CurlInfo.RESPONSE_CODE))
        response.ok = 200 <= response.status_code < 400
        response.content = body.getvalue()
        response.headers = _parse_response_headers(raw_headers.getvalue())
        return response
    finally:
        curl.close()


def _classify_error(exc: Exception) -> str:
    """把网络异常转换为人类可读的错误信息。"""

    if isinstance(exc, _UpstreamStatusError):
        return f"上游返回 HTTP {exc.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "上游请求超时"
    if isinstance(exc, httpx.ConnectError):
        message = str(exc).lower()
        if "unexpected_eof" in message:
            return "TLS 握手失败（上游中断连接）"
        if "certificate_verify_failed" in message:
            return "SSL 证书验证失败"
        if "self-signed certificate" in message:
            return "SSL 证书为自签名证书"
        if "unable to get local issuer certificate" in message:
            return "SSL 证书链验证失败"
        if "ssl" in message:
            return "TLS/SSL 连接错误"
        return "上游连接失败（DNS 或网络不可达）"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"上游返回 HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.HTTPError):
        return "上游 HTTP 请求失败"
    if isinstance(exc, (curl_errors.RequestsError, curl_errors.CurlError)):
        message = str(exc).lower()
        if "timed out" in message or "timeout" in message or "curl(28)" in message:
            return "上游请求超时"
        if "unexpected_eof" in message:
            return "TLS 握手失败（上游中断连接）"
        if "ssl" in message or "certificate" in message:
            return "TLS/SSL 连接错误"
        return "上游 HTTP 请求失败"
    return "同步失败"


class SyncService:
    def __init__(self, db: Session, http_client: httpx.Client | None = None) -> None:
        self.db = db
        self.source_repo = SourceRepository(db)
        self.node_repo = NodeRepository(db)
        self.log_repo = LogRepository(db)
        self.timeout = get_settings().http_timeout_seconds
        self._uses_default_client = http_client is None
        self.client = http_client or curl_requests.Session(trust_env=False)
        self._last_fetch_status = 200
        self._last_fetch_headers: dict[str, str] = {}

    def sync_source(self, source: Source) -> SyncResult:
        """同步单个上游；失败时保留旧节点，只更新状态与日志。"""

        started = time.perf_counter()
        duration_ms = 0
        try:
            conditional_headers = {}
            if source.etag:
                conditional_headers["If-None-Match"] = source.etag
            if source.last_modified:
                conditional_headers["If-Modified-Since"] = source.last_modified
            content = self._fetch(source.url, conditional_headers)
            duration_ms = int((time.perf_counter() - started) * 1000)
            if self._last_fetch_status == 304:
                return self._mark_not_modified(source, duration_ms)
            if not content.strip():
                # 空内容默认视为异常，除非管理员明确允许空订阅覆盖
                if not source.allow_empty_override:
                    return self._mark_failure(source, "上游返回空内容", duration_ms)
                parsed_nodes = []
            else:
                parsed_nodes = parse_content(content, source.format)
                for parsed_node in parsed_nodes:
                    validate_parsed_node(parsed_node)
                if not parsed_nodes and not source.allow_empty_override:
                    return self._mark_failure(source, "上游未解析到有效节点", duration_ms)
            return self._commit_success(
                source, parsed_nodes, self._last_fetch_headers, duration_ms
            )
        except ParseError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return self._mark_failure(source, str(exc), duration_ms)
        except Exception as exc:
            logger.warning("同步上游 %s 时发生未预期错误：%s", source.name, type(exc).__name__)
            duration_ms = int((time.perf_counter() - started) * 1000)
            return self._mark_failure(source, _classify_error(exc), duration_ms)

    def sync_all_enabled(self) -> list[SyncResult]:
        """同步全部启用源；单个源失败不影响其他源。"""

        results = []
        for source in self.source_repo.list_enabled():
            results.append(self.sync_source(source))
        return results

    def _fetch(self, url: str, request_headers: dict[str, str] | None = None) -> str:
        """抓取订阅内容，并保留响应头供条件请求与同步指标使用。"""

        self._last_fetch_status = 200
        self._last_fetch_headers = {}
        current_url = url
        response = None
        for redirect_count in range(_MAX_REDIRECTS + 1):
            resolved_addresses = _validate_fetch_target(current_url)
            if self._uses_default_client:
                response = _pinned_curl_get(
                    current_url,
                    resolved_addresses,
                    self.timeout,
                    get_settings().upstream_user_agent,
                    request_headers,
                )
            else:
                response = self.client.get(
                    current_url,
                    timeout=self.timeout,
                    allow_redirects=False,
                    verify=True,
                    headers={
                        "User-Agent": get_settings().upstream_user_agent,
                        **(request_headers or {}),
                    },
                )
            if response.status_code not in {301, 302, 303, 307, 308}:
                break
            location = (getattr(response, "headers", {}) or {}).get("location")
            if not location:
                raise ParseError("上游重定向缺少目标地址")
            if redirect_count >= _MAX_REDIRECTS:
                raise ParseError("上游重定向次数过多")
            current_url = urljoin(current_url, location)
        if response is None:
            raise ParseError("上游请求未返回响应")
        self._last_fetch_status = response.status_code
        self._last_fetch_headers = {
            str(key).lower(): str(value)
            for key, value in (getattr(response, "headers", {}) or {}).items()
        }
        if response.status_code == 304:
            return ""
        if not response.ok:
            raise _UpstreamStatusError(response.status_code)
        content_length = (getattr(response, "headers", {}) or {}).get("content-length")
        if content_length:
            try:
                if int(content_length) > _MAX_UPSTREAM_BYTES:
                    raise ParseError("上游订阅内容超过 10MB 限制")
            except ValueError:
                pass
        content = response.text or ""
        if len(content.encode("utf-8")) > _MAX_UPSTREAM_BYTES:
            raise ParseError("上游订阅内容超过 10MB 限制")
        lowered = content.strip().lower()
        if lowered.startswith(("<html", "<!doctype html")):
            raise ParseError("上游返回 HTML 页面，不是订阅内容")
        return content

    def _commit_success(
        self,
        source: Source,
        parsed_nodes: list[ParsedNode],
        response_headers: dict[str, str] | None = None,
        duration_ms: int | None = None,
    ) -> SyncResult:
        """去重后在同一事务中替换旧节点，任何异常都会回滚。"""
        try:
            old_nodes = self.node_repo.list_by_source(source.id)
            old_node_ids = {node.id for node in old_nodes}
            old_map = {node.node_fingerprint: node for node in old_nodes}
            old_identity_map: dict[str, Node] = {}
            ambiguous_identity_keys: set[str] = set()
            for old_node in old_nodes:
                identity = old_node.source_node_key or source_node_key_for_node(old_node)
                if not identity:
                    continue
                if identity in old_identity_map:
                    ambiguous_identity_keys.add(identity)
                else:
                    old_identity_map[identity] = old_node
            for identity in ambiguous_identity_keys:
                old_identity_map.pop(identity, None)
            priority = build_source_priority(self.db)
            current_priority = priority.get(source.name, 1000)

            seen: set[str] = set()
            new_nodes: list[Node] = []
            new_map: dict[str, Node] = {}
            for parsed in parsed_nodes:
                fingerprint = fingerprint_for_parsed(parsed)
                if fingerprint in seen:
                    continue
                existing = self.node_repo.get_by_fingerprint(fingerprint)
                if existing is not None and existing.source_id != source.id:
                    existing_priority = priority.get(existing.source_name, 1000)
                    if current_priority >= existing_priority:
                        # 当前来源优先级不高于现有节点，统一节点池只保留一份
                        continue
                    # 当前来源优先级更高，替换低优先级来源的节点
                    if existing.source_id is not None:
                        owner = self.source_repo.get(existing.source_id)
                        if owner is not None:
                            owner.node_count = max(0, owner.node_count - 1)
                    self.node_repo.delete(existing)
                seen.add(fingerprint)
                source_node_key = source_node_key_for_parsed(parsed)
                old_node = old_map.get(fingerprint)
                if old_node is None and source_node_key:
                    candidate = old_identity_map.get(source_node_key)
                    if candidate is not None:
                        old_node = candidate
                node = self._to_orm(
                    source,
                    parsed,
                    fingerprint,
                    enabled=old_node.enabled if old_node is not None else None,
                    source_node_key=source_node_key,
                )
                new_nodes.append(node)
                new_map[fingerprint] = node

            old_keys = set(old_map)
            new_keys = set(new_map)
            added = len(new_keys - old_keys)
            removed = len(old_keys - new_keys)
            changed = sum(
                1
                for key in old_keys & new_keys
                if old_map[key].name != new_map[key].name
                or old_map[key].country != new_map[key].country
            )

            self.node_repo.delete_by_source(source.id)
            self.node_repo.bulk_add(new_nodes)
            source.node_count = len(new_nodes)
            source.version += 1
            source.last_sync_status = "success"
            source.last_sync_at = utcnow()
            source.last_error = None
            source.etag = (response_headers or {}).get("etag") or source.etag
            source.last_modified = (response_headers or {}).get("last-modified") or source.last_modified
            source.last_success_at = source.last_sync_at
            source.last_success_node_count = len(new_nodes)
            source.last_sync_duration_ms = duration_ms
            source.consecutive_failures = 0
            self.log_repo.create_sync_log(
                source_id=source.id,
                version=source.version,
                status="success",
                node_count=len(new_nodes),
                added_count=added,
                removed_count=removed,
                changed_count=changed,
            )
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.exception("同步上游 %s 事务提交失败", source.name)
            return self._mark_failure(source, _classify_error(exc))

        try:
            SubscriptionService.invalidate_for_source(
                self.db,
                source.name,
                old_node_ids,
                {node.id for node in new_nodes},
            )
        except Exception:
            # 数据已成功提交时，宁可扩大失效范围，也不能继续返回旧订阅。
            logger.exception("同步上游 %s 后更新订阅缓存失败", source.name)
            cache_service.invalidate_all()
        logger.info(
            "上游 %s 同步成功：%s 个节点（新增 %s，删除 %s，修改 %s）",
            source.name,
            len(new_nodes),
            added,
            removed,
            changed,
        )
        return SyncResult(
            source_id=source.id,
            source_name=source.name,
            status="success",
            node_count=len(new_nodes),
            added_count=added,
            removed_count=removed,
            changed_count=changed,
            version=source.version,
        )

    def _mark_not_modified(self, source: Source, duration_ms: int | None) -> SyncResult:
        """处理条件请求命中的 304，不重建节点也不递增版本。"""

        source.last_sync_status = "success"
        source.last_sync_at = utcnow()
        source.last_success_at = source.last_sync_at
        source.last_success_node_count = source.node_count
        source.last_sync_duration_ms = duration_ms
        source.consecutive_failures = 0
        source.last_error = None
        self.log_repo.create_sync_log(
            source_id=source.id,
            version=source.version,
            status="success",
            node_count=source.node_count,
        )
        self.db.commit()
        return SyncResult(
            source_id=source.id,
            source_name=source.name,
            status="success",
            node_count=source.node_count,
            added_count=0,
            removed_count=0,
            changed_count=0,
            version=source.version,
        )

    def _mark_failure(
        self, source: Source, error: str, duration_ms: int | None = None
    ) -> SyncResult:
        """记录失败状态；不清空已有节点。"""

        source.last_sync_status = "failed"
        source.last_sync_at = utcnow()
        source.last_error = error[:500]
        source.last_sync_duration_ms = duration_ms
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        self.log_repo.create_sync_log(
            source_id=source.id,
            version=source.version,
            status="failed",
            node_count=source.node_count,
            error_message=error[:500],
        )
        self.db.commit()
        logger.warning("上游 %s 同步失败：%s", source.name, error)
        return SyncResult(
            source_id=source.id,
            source_name=source.name,
            status="failed",
            node_count=source.node_count,
            added_count=0,
            removed_count=0,
            changed_count=0,
            version=source.version,
            error=error,
        )

    @staticmethod
    def _to_orm(
        source: Source,
        parsed: ParsedNode,
        fingerprint: str,
        enabled: bool | None = None,
        source_node_key: str | None = None,
    ) -> Node:
        return Node(
            source_id=source.id,
            source_name=source.name,
            original_name=parsed.original_name,
            name=parsed.original_name,
            type=parsed.type,
            server=parsed.server,
            port=parsed.port,
            uuid=parsed.uuid,
            password=parsed.password,
            cipher=parsed.cipher,
            network=parsed.network,
            security=parsed.security,
            tls=parsed.tls,
            sni=parsed.sni,
            fingerprint=parsed.fingerprint,
            public_key=parsed.public_key,
            short_id=parsed.short_id,
            path=parsed.path,
            host=parsed.host,
            country=parsed.country,
            source_type="upstream",
            enabled=True if enabled is None else enabled,
            node_fingerprint=fingerprint,
            source_node_key=source_node_key,
            metadata_json=parsed.metadata or None,
        )
