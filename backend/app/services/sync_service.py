"""上游同步业务逻辑：staging → validate → commit。"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.core.cache import cache_service
from app.core.config import get_settings
from app.models.base import utcnow
from app.models.node import Node
from app.models.source import Source
from app.parsers import parse_content
from app.parsers.base import ParseError, ParsedNode
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.source_repo import SourceRepository
from app.schemas.source import SyncResult
from app.utils.fingerprint import build_node_fingerprint, fingerprint_for_parsed
from app.utils.priority import build_source_priority

logger = logging.getLogger(__name__)


def _classify_error(exc: Exception) -> str:
    """把网络异常转换为人类可读的错误信息。"""

    if isinstance(exc, httpx.TimeoutException):
        return "上游请求超时"
    if isinstance(exc, httpx.ConnectError):
        if "ssl" in str(exc).lower():
            return "上游 SSL 证书错误"
        return "上游连接失败（DNS 或网络不可达）"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"上游返回 HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.HTTPError):
        return "上游 HTTP 请求失败"
    return "同步失败"


class SyncService:
    def __init__(self, db: Session, http_client: httpx.Client | None = None) -> None:
        self.db = db
        self.source_repo = SourceRepository(db)
        self.node_repo = NodeRepository(db)
        self.log_repo = LogRepository(db)
        self.client = http_client or httpx.Client(
            timeout=get_settings().http_timeout_seconds,
            follow_redirects=True,
        )

    def sync_source(self, source: Source) -> SyncResult:
        """同步单个上游；失败时保留旧节点，只更新状态与日志。"""

        try:
            content = self._fetch(source.url)
            if not content.strip():
                # 空内容默认视为异常，除非管理员明确允许空订阅覆盖
                if not source.allow_empty_override:
                    return self._mark_failure(source, "上游返回空内容")
                parsed_nodes = []
            else:
                parsed_nodes = parse_content(content, source.format)
                if not parsed_nodes and not source.allow_empty_override:
                    return self._mark_failure(source, "上游未解析到有效节点")
            return self._commit_success(source, parsed_nodes)
        except ParseError as exc:
            return self._mark_failure(source, str(exc))
        except httpx.HTTPError as exc:
            return self._mark_failure(source, _classify_error(exc))
        except Exception as exc:
            logger.exception("同步上游 %s 时发生未预期错误", source.name)
            return self._mark_failure(source, _classify_error(exc))

    def sync_all_enabled(self) -> list[SyncResult]:
        """同步全部启用源；单个源失败不影响其他源。"""

        results = []
        for source in self.source_repo.list_enabled():
            results.append(self.sync_source(source))
        return results

    def _fetch(self, url: str) -> str:
        response = self.client.get(url)
        response.raise_for_status()
        content = response.text or ""
        lowered = content.strip().lower()
        if lowered.startswith(("<html", "<!doctype html")):
            raise ParseError("上游返回 HTML 页面，不是订阅内容")
        return content

    def _commit_success(
        self, source: Source, parsed_nodes: list[ParsedNode]
    ) -> SyncResult:
        """去重后在同一事务中替换旧节点，任何异常都会回滚。"""

        old_nodes = self.node_repo.list_by_source(source.id)
        old_map = {node.node_fingerprint: node for node in old_nodes}
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
            node = self._to_orm(source, parsed, fingerprint)
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

        try:
            self.node_repo.delete_by_source(source.id)
            self.node_repo.bulk_add(new_nodes)
            source.node_count = len(new_nodes)
            source.version += 1
            source.last_sync_status = "success"
            source.last_sync_at = utcnow()
            source.last_error = None
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

    def _mark_failure(self, source: Source, error: str) -> SyncResult:
        """记录失败状态；不清空已有节点。"""

        source.last_sync_status = "failed"
        source.last_sync_at = utcnow()
        source.last_error = error[:500]
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
    def _to_orm(source: Source, parsed: ParsedNode, fingerprint: str) -> Node:
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
            node_fingerprint=fingerprint,
            metadata_json=parsed.metadata or None,
        )
