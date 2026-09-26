"""统一节点池业务逻辑：自有节点、去重优先级、批量操作。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import cache_service
from app.core.exceptions import BusinessError
from app.models.node import Node
from app.models.package import PackageRule
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.source_repo import SourceRepository
from app.schemas.node import NodeCreate, NodeUpdate
from app.utils.country import detect_country
from app.utils.fingerprint import build_node_fingerprint
from app.utils.priority import SELF_SOURCE_NAME

SUPPORTED_NODE_TYPES = {
    "vless",
    "vmess",
    "shadowsocks",
    "trojan",
    "socks",
    "http",
    "hysteria",
    "hysteria2",
    "tuic",
    "anytls",
}

SUPPORTED_SS_CIPHERS = {
    "aes-128-gcm",
    "aes-192-gcm",
    "aes-256-gcm",
    "chacha20-ietf-poly1305",
    "xchacha20-ietf-poly1305",
    "2022-blake3-aes-128-gcm",
    "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
}


def _validate_self_node(
    node_type: str,
    uuid: str | None,
    password: str | None,
    cipher: str | None,
) -> None:
    """校验自有节点必须携带对应协议的关键字段。"""

    if node_type not in SUPPORTED_NODE_TYPES:
        raise BusinessError(f"不支持的自有节点协议：{node_type}")
    if node_type in ("vless", "vmess", "tuic"):
        if not uuid or not uuid.strip():
            raise BusinessError(f"{node_type.upper()} 节点缺少 UUID")
        try:
            UUID(uuid.strip())
        except (AttributeError, ValueError):
            raise BusinessError(f"{node_type.upper()} 节点 UUID 格式无效") from None
    if node_type == "shadowsocks":
        if not password or not password.strip():
            raise BusinessError("Shadowsocks 节点缺少密码")
        normalized_cipher = (cipher or "").strip().lower()
        if not normalized_cipher:
            raise BusinessError("Shadowsocks 节点缺少加密方式")
        if normalized_cipher not in SUPPORTED_SS_CIPHERS:
            raise BusinessError(f"Shadowsocks 不支持的加密方式：{cipher}")
    if node_type in {"trojan", "anytls"} and (not password or not password.strip()):
        raise BusinessError(f"{node_type.upper()} 节点缺少密码")
    if node_type in ("hysteria", "hysteria2") and (
        not password or not password.strip()
    ):
        raise BusinessError(f"{node_type.upper()} 节点缺少认证密码")


def _fingerprint_from_fields(
    *,
    node_type: str,
    server: str,
    port: int,
    uuid: str | None,
    password: str | None,
    username: str | None,
    cipher: str | None,
    network: str | None,
    security: str | None,
    path: str | None,
    host: str | None,
    sni: str | None,
) -> str:
    return build_node_fingerprint(
        node_type=node_type,
        server=server,
        port=port,
        uuid=uuid,
        password=password,
        username=username,
        cipher=cipher,
        network=network,
        security=security,
        path=path,
        host=host,
        sni=sni,
    )


class NodeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = NodeRepository(db)
        self.source_repo = SourceRepository(db)
        self.log_repo = LogRepository(db)

    def create(self, payload: NodeCreate, admin: User) -> Node:
        """创建自有节点；与上游节点同指纹时按优先级替换。"""

        _validate_self_node(payload.type, payload.uuid, payload.password, payload.cipher)
        fingerprint = _fingerprint_from_fields(
            node_type=payload.type,
            server=payload.server,
            port=payload.port,
            uuid=payload.uuid,
            password=payload.password,
            username=payload.username,
            cipher=payload.cipher,
            network=payload.network,
            security=payload.security,
            path=payload.path,
            host=payload.host,
            sni=payload.sni,
        )
        existing = self.repo.get_by_fingerprint(fingerprint)
        if existing is not None:
            if existing.source_name == SELF_SOURCE_NAME:
                raise BusinessError("相同自有节点已存在")
            # 自有节点优先级最高，替换低优先级的上游节点
            self._remove_owner_node(existing)

        node = Node(
            source_id=None,
            source_name=SELF_SOURCE_NAME,
            original_name=payload.name,
            name=payload.name,
            type=payload.type,
            server=payload.server,
            port=payload.port,
            uuid=payload.uuid,
            password=payload.password,
            username=payload.username,
            cipher=payload.cipher,
            network=payload.network,
            security=payload.security,
            tls=payload.tls,
            sni=payload.sni,
            fingerprint=payload.fingerprint,
            public_key=payload.public_key,
            short_id=payload.short_id,
            path=payload.path,
            host=payload.host,
            country=payload.country or detect_country(payload.name),
            source_type="custom",
            source_subtype=payload.source_subtype,
            enabled=payload.enabled,
            node_fingerprint=fingerprint,
        )
        self.db.add(node)
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="create_node",
            target_type="node",
            target_value=payload.name,
        )
        self.db.commit()
        self.db.refresh(node)
        cache_service.invalidate_all()
        return node

    def update(self, node: Node, payload: NodeUpdate, admin: User) -> Node:
        """更新节点并重新计算指纹；与其他节点冲突时拒绝。"""

        data = payload.model_dump(exclude_unset=True)
        if "enabled" in data and data["enabled"] is None:
            raise BusinessError("节点字段 enabled 不能为 null")
        if node.source_id is not None or node.source_type == "upstream":
            editable_fields = set(data) - {"enabled"}
            if editable_fields:
                raise BusinessError("上游节点不支持直接编辑，请复制为自有节点后修改")
            if not data:
                raise BusinessError("至少需要提交一个可修改字段")
            node.enabled = data["enabled"]
            self.log_repo.create_admin_log(
                admin_user_id=admin.id,
                action="update_node_status",
                target_type="node",
                target_value=node.name,
            )
            self.db.commit()
            self.db.refresh(node)
            cache_service.invalidate_all()
            return node
        for key in ("name", "server", "port"):
            if key in data and data[key] is None:
                raise BusinessError(f"节点字段 {key} 不能为 null")
        final_type = data.get("type", node.type)
        _validate_self_node(
            final_type,
            data.get("uuid", node.uuid),
            data.get("password", node.password),
            data.get("cipher", node.cipher),
        )
        for key, value in data.items():
            setattr(node, key, value)
        if "country" not in data:
            node.country = node.country or detect_country(node.name)
        new_fingerprint = _fingerprint_from_fields(
            node_type=node.type,
            server=node.server,
            port=node.port,
            uuid=node.uuid,
            password=node.password,
            username=node.username,
            cipher=node.cipher,
            network=node.network,
            security=node.security,
            path=node.path,
            host=node.host,
            sni=node.sni,
        )
        other = self.repo.get_by_fingerprint(new_fingerprint)
        if other is not None and other.id != node.id:
            raise BusinessError("修改后与现有节点重复")
        node.node_fingerprint = new_fingerprint
        node.source_type = "custom"
        node.source_subtype = payload.source_subtype or node.source_subtype
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="update_node",
            target_type="node",
            target_value=node.name,
        )
        self.db.commit()
        self.db.refresh(node)
        cache_service.invalidate_all()
        return node

    def delete(self, node: Node, admin: User) -> None:
        """删除节点，并同步修正来源节点计数。"""

        self._remove_owner_node(node)
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="delete_node",
            target_type="node",
            target_value=node.name,
        )
        self.db.commit()
        cache_service.invalidate_all()

    def batch(self, ids: list[int], action: str, admin: User) -> int:
        """批量启用/禁用/删除节点。"""

        processed = 0
        for node_id in ids:
            node = self.repo.get(node_id)
            if node is None:
                continue
            if action == "enable":
                node.enabled = True
            elif action == "disable":
                node.enabled = False
            elif action == "delete":
                self._remove_owner_node(node)
            processed += 1
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action=f"batch_{action}_nodes",
            target_type="node",
            target_value=f"{len(ids)} ids",
        )
        self.db.commit()
        cache_service.invalidate_all()
        return processed

    def _remove_owner_node(self, node: Node) -> None:
        """删除节点并同步更新其来源的 node_count。"""

        for rule in self.db.scalars(select(PackageRule)).all():
            if not isinstance(rule.node_ids, list):
                continue
            remaining_ids = [
                value
                for value in rule.node_ids
                if not (str(value).isdigit() and int(value) == node.id)
            ]
            if remaining_ids != rule.node_ids:
                rule.node_ids = remaining_ids
        if node.source_id is not None:
            owner = self.source_repo.get(node.source_id)
            if owner is not None:
                owner.node_count = max(0, owner.node_count - 1)
        self.repo.delete(node)
