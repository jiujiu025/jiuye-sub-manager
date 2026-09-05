"""根据节点名称识别国家/地区。"""

from __future__ import annotations

import re

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
