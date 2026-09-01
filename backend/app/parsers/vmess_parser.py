"""VMess URI 解析。"""

from __future__ import annotations

import json

from app.parsers.base import ParseError, ParsedNode
from app.parsers.detector import decode_base64
from app.utils.country import detect_country


def parse_vmess_uri(uri: str) -> ParsedNode:
    """把 vmess://base64(JSON) 链接解析为 ParsedNode。"""

    if not uri.startswith("vmess://"):
        raise ParseError("不是有效的 VMess 链接")
    payload = uri.removeprefix("vmess://")
    decoded = decode_base64(payload)
    if decoded is None:
        raise ParseError("VMess 链接 Base64 解码失败")
    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ParseError("VMess 配置 JSON 无效") from exc
    server = data.get("add")
    port = data.get("port")
    if not server or not port:
        raise ParseError("VMess 配置缺少服务器或端口")
    name = str(data.get("ps") or server)
    tls = str(data.get("tls", "")).lower() == "true"
    return ParsedNode(
        original_name=name,
        type="vmess",
        server=str(server),
        port=int(port),
        uuid=data.get("id"),
        cipher=str(data.get("scy") or "auto"),
        network=data.get("net"),
        tls=tls,
        sni=data.get("sni") or data.get("host"),
        host=data.get("host"),
        path=data.get("path"),
        fingerprint=data.get("fp"),
        public_key=data.get("pbk"),
        short_id=data.get("sid"),
        country=detect_country(name),
        metadata=data,
    )
