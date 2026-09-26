"""节点去重指纹生成。"""

from __future__ import annotations

import hashlib


def build_node_fingerprint(
    *,
    node_type: str,
    server: str,
    port: int,
    uuid: str | None = None,
    password: str | None = None,
    username: str | None = None,
    cipher: str | None = None,
    network: str | None = None,
    security: str | None = None,
    path: str | None = None,
    host: str | None = None,
    sni: str | None = None,
) -> str:
    """基于连接关键信息生成 SHA-256 指纹，相同节点只保留一份。"""

    parts = [
        node_type.strip().lower(),
        server.strip().lower(),
        str(port),
        (uuid or "").strip(),
        (password or "").strip(),
        (username or "").strip(),
        (cipher or "").strip().lower(),
        (network or "").strip().lower(),
        (security or "").strip().lower(),
        (path or "").strip(),
        (host or "").strip().lower(),
        (sni or "").strip().lower(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fingerprint_for_parsed(parsed: object) -> str:
    """根据 ParsedNode 生成指纹，避免业务层重复拼字段。"""

    return build_node_fingerprint(
        node_type=parsed.type,
        server=parsed.server,
        port=parsed.port,
        uuid=parsed.uuid,
        password=parsed.password,
        username=parsed.username,
        cipher=parsed.cipher,
        network=parsed.network,
        security=parsed.security,
        path=parsed.path,
        host=parsed.host,
        sni=parsed.sni,
    )


def build_source_node_key(
    *,
    node_type: str,
    uuid: str | None = None,
    password: str | None = None,
    cipher: str | None = None,
    original_name: str | None = None,
) -> str | None:
    """基于明确的协议稳定字段生成来源内节点标识。"""

    normalized_type = node_type.strip().lower()
    normalized_uuid = (uuid or "").strip().lower()
    if normalized_uuid and normalized_type in {"vless", "vmess", "tuic"}:
        identity = f"{normalized_type}|uuid|{normalized_uuid}"
    elif (
        normalized_type in {"shadowsocks", "trojan", "anytls"}
        and password
        and original_name
    ):
        identity = "|".join(
            [
                normalized_type,
                "credential",
                password.strip(),
                (cipher or "").strip().lower(),
                original_name.strip().lower(),
            ]
        )
    else:
        return None
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def source_node_key_for_parsed(parsed: object) -> str | None:
    """根据解析结果生成来源内节点标识。"""

    return build_source_node_key(
        node_type=parsed.type,
        uuid=parsed.uuid,
        password=parsed.password,
        cipher=parsed.cipher,
        original_name=parsed.original_name,
    )


def source_node_key_for_node(node: object) -> str | None:
    """根据旧节点字段生成来源内节点标识，兼容迁移前数据。"""

    return build_source_node_key(
        node_type=node.type,
        uuid=node.uuid,
        password=node.password,
        cipher=node.cipher,
        original_name=node.original_name,
    )
