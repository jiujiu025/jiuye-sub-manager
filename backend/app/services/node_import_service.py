"""自有节点批量导入：文本 → 协议识别 → 解析 → 去重 → 统一节点池。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.cache import cache_service
from app.models.node import Node
from app.models.user import User
from app.parsers import parse_content
from app.parsers.base import ParseError, ParsedNode
from app.parsers.detector import decode_base64, detect_format
from app.parsers.uri_parser import parse_uri_line
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.source_repo import SourceRepository
from app.schemas.node import ImportFailure, NodeImportResult
from app.utils.fingerprint import fingerprint_for_parsed
from app.utils.priority import SELF_SOURCE_NAME

_FORCED_URI_FORMATS = (
    "vless",
    "vmess",
    "ss",
    "trojan",
    "socks",
    "http",
    "hysteria",
    "hysteria2",
    "tuic",
)


def _to_custom_node(
    parsed: ParsedNode, source_subtype: str, fingerprint: str
) -> Node:
    return Node(
        source_id=None,
        source_name=SELF_SOURCE_NAME,
        original_name=parsed.original_name,
        name=parsed.original_name,
        type=parsed.type,
        server=parsed.server,
        port=parsed.port,
        uuid=parsed.uuid,
        password=parsed.password,
        username=parsed.username,
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
        source_type="custom",
        source_subtype=source_subtype,
        node_fingerprint=fingerprint,
        metadata_json=parsed.metadata or None,
    )


class NodeImportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.node_repo = NodeRepository(db)
        self.source_repo = SourceRepository(db)
        self.log_repo = LogRepository(db)

    def import_content(
        self,
        content: str,
        source_subtype: str,
        fmt: str,
        admin: User,
    ) -> NodeImportResult:
        """导入节点内容；单个节点失败不影响其他节点。"""

        entries, failures = self._parse_entries(content, fmt)
        seen: set[str] = set()
        success = 0
        duplicate = 0

        for _index, parsed in entries:
            fingerprint = fingerprint_for_parsed(parsed)
            if fingerprint in seen:
                duplicate += 1
                continue
            existing = self.node_repo.get_by_fingerprint(fingerprint)
            if existing is not None:
                if existing.source_name == SELF_SOURCE_NAME:
                    duplicate += 1
                    continue
                # 自有节点优先级最高，替换低优先级的上游节点
                if existing.source_id is not None:
                    owner = self.source_repo.get(existing.source_id)
                    if owner is not None:
                        owner.node_count = max(0, owner.node_count - 1)
                self.node_repo.delete(existing)
            seen.add(fingerprint)
            self.db.add(_to_custom_node(parsed, source_subtype, fingerprint))
            success += 1

        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="import_nodes",
            target_type="node",
            target_value=SELF_SOURCE_NAME,
            detail=(
                f"total={success + duplicate + len(failures)} "
                f"success={success} duplicate={duplicate} failed={len(failures)}"
            ),
        )
        self.db.commit()
        cache_service.invalidate_all()
        return NodeImportResult(
            total=success + duplicate + len(failures),
            success=success,
            duplicate=duplicate,
            failed=len(failures),
            failures=failures,
        )

    def _parse_entries(
        self, content: str, fmt: str
    ) -> tuple[list[tuple[int, ParsedNode]], list[ImportFailure]]:
        actual_format = fmt if fmt != "auto" else detect_format(content)
        if actual_format == "base64":
            decoded = decode_base64(content)
            if decoded is None:
                return [], [ImportFailure(index=1, reason="Base64 解码失败")]
            return self._parse_lines(decoded.splitlines())
        if actual_format == "uri":
            return self._parse_lines(content.splitlines())
        if actual_format in _FORCED_URI_FORMATS:
            return self._parse_lines(content.splitlines(), forced=actual_format)
        if actual_format in ("clash", "singbox"):
            try:
                nodes = parse_content(content, actual_format)
            except ParseError as exc:
                return [], [ImportFailure(index=1, reason=str(exc))]
            return [(index, node) for index, node in enumerate(nodes, start=1)], []
        return [], [ImportFailure(index=1, reason="无法识别输入格式")]

    @staticmethod
    def _parse_lines(
        lines: list[str], forced: str | None = None
    ) -> tuple[list[tuple[int, ParsedNode]], list[ImportFailure]]:
        entries: list[tuple[int, ParsedNode]] = []
        failures: list[ImportFailure] = []
        for index, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                entries.append((index, parse_uri_line(line, forced)))
            except ParseError as exc:
                failures.append(ImportFailure(index=index, reason=str(exc)))
            except ValueError:
                failures.append(ImportFailure(index=index, reason="节点链接的服务器或端口无效"))
        return entries, failures
