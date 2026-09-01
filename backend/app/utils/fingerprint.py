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
        cipher=parsed.cipher,
        network=parsed.network,
        security=parsed.security,
        path=parsed.path,
        host=parsed.host,
        sni=parsed.sni,
    )
