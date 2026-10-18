"""节点国家/地区识别与服务器地址解析工具。"""

from __future__ import annotations

import re
import ipaddress
import socket


# 常见国家代码映射。未知国家保留上游返回的国家名称，避免把新地区误判为空。
COUNTRY_CODE_NAMES: dict[str, str] = {
    "AU": "澳大利亚", "BR": "巴西", "CA": "加拿大", "CH": "瑞士",
    "CN": "中国", "DE": "德国", "ES": "西班牙", "FI": "芬兰",
    "FR": "法国", "GB": "英国", "HK": "香港", "ID": "印尼",
    "IN": "印度", "IT": "意大利", "JP": "日本", "KR": "韩国",
    "MY": "马来西亚", "NL": "荷兰", "NO": "挪威", "NZ": "新西兰",
    "PH": "菲律宾", "PL": "波兰", "PT": "葡萄牙", "RU": "俄罗斯",
    "SE": "瑞典", "SG": "新加坡", "TH": "泰国", "TR": "土耳其",
    "TW": "台湾", "UA": "乌克兰", "US": "美国", "VN": "越南",
}

# 顺序敏感：更具体的关键词必须排在前面，避免被短关键词误匹配
COUNTRY_RULES: list[tuple[tuple[str, ...], str]] = [
    (("hong kong", "香港", "hk", "xianggang"), "香港"),
    (("taiwan", "台湾", "tw", "taipei", "台北"), "台湾"),
    (("japan", "日本", "jp", "tokyo", "东京", "osaka", "大阪"), "日本"),
    (("korea", "韩国", "kr", "seoul", "首尔"), "韩国"),
    (("singapore", "新加坡", "sg", "狮城"), "新加坡"),
    (("united states", "美国", "usa", "us", "america"), "美国"),
    (("united kingdom", "英国", "uk", "britain"), "英国"),
    (("germany", "德国", "de"), "德国"),
    (("france", "法国", "fr"), "法国"),
    (("malaysia", "马来西亚", "my"), "马来西亚"),
    (("mexico", "墨西哥", "mx"), "墨西哥"),
    (("russia", "俄罗斯", "ru", "moscow", "莫斯科"), "俄罗斯"),
    (("australia", "澳大利亚", "au", "澳洲"), "澳大利亚"),
    (("canada", "加拿大", "ca"), "加拿大"),
    (("thailand", "泰国", "th", "曼谷"), "泰国"),
    (("vietnam", "越南", "vn"), "越南"),
    (("india", "印度", "in"), "印度"),
    (("netherlands", "荷兰", "nl"), "荷兰"),
    (("indonesia", "印尼", "印度尼西亚", "id"), "印尼"),
    (("philippines", "菲律宾", "ph"), "菲律宾"),
]

# 用于节点重命名：国家中文名 → 地区缩写
COUNTRY_ABBR: dict[str, str] = {
    "香港": "HK",
    "台湾": "TW",
    "日本": "JP",
    "韩国": "KR",
    "新加坡": "SG",
    "美国": "US",
    "英国": "UK",
    "德国": "DE",
    "法国": "FR",
    "马来西亚": "MY",
    "墨西哥": "MX",
    "俄罗斯": "RU",
    "澳大利亚": "AU",
    "加拿大": "CA",
    "泰国": "TH",
    "越南": "VN",
    "印度": "IN",
    "荷兰": "NL",
    "印尼": "ID",
    "菲律宾": "PH",
}


def detect_country(name: str) -> str | None:
    """从节点名称中识别国家；无法识别时返回 None。"""

    lowered = name.lower()
    for keywords, country in COUNTRY_RULES:
        for keyword in keywords:
            if keyword.isascii() and keyword.isalpha():
                matched = re.search(
                    rf"(?<![a-z]){re.escape(keyword)}(?![a-z])",
                    lowered,
                )
            else:
                matched = keyword in lowered
            if matched:
                return country
    return None


def normalize_host(value: str | None) -> str | None:
    """清理节点服务器字段，兼容 IPv6 方括号和误带端口的输入。"""

    if not value:
        return None
    host = value.strip()
    if host.startswith("[") and "]" in host:
        host = host[1:host.index("]")]
    return host or None


def is_public_ip(value: str | None) -> bool:
    """只允许查询公网地址，避免把私网或保留地址发送给地理服务。"""

    try:
        address = ipaddress.ip_address(normalize_host(value) or "")
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def resolve_public_ip(server: str | None) -> str | None:
    """把 IP 或域名解析为一个公网 IP；解析失败时返回 None。"""

    host = normalize_host(server)
    if not host:
        return None
    if is_public_ip(host):
        return host
    try:
        addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror):
        return None
    for item in addresses:
        sockaddr = item[4]
        candidate = sockaddr[0] if sockaddr else None
        if is_public_ip(candidate):
            return normalize_host(candidate)
    return None


def country_name_from_code(code: str | None, fallback: str | None = None) -> str | None:
    """把地理服务返回的国家代码转换为界面使用的国家名称。"""

    normalized = (code or "").strip().upper()
    return COUNTRY_CODE_NAMES.get(normalized) or (fallback.strip() if fallback and fallback.strip() else None)
