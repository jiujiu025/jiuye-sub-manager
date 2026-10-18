"""MHSanaei/3x-ui v3.8.5 API 适配器。

适配器只处理面板 HTTP API 和 Xray 配置格式，业务服务不直接拼接面板请求。
"""

from __future__ import annotations

import json
import logging
import secrets
import uuid
import copy
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

import httpx

from app.core.security import decrypt_secret
from app.models.node import Node
from app.models.three_xui import ThreeXUIServer

logger = logging.getLogger(__name__)


class ThreeXUIError(Exception):
    """已脱敏的 3x-ui 操作错误。"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ForwardProvision:
    inbound_id: int
    client_id: str | None
    inbound_remark: str
    inbound_tag: str
    protocol: str
    server: str
    port: int
    uuid: str | None
    password: str | None
    cipher: str | None
    network: str | None
    tls: bool
    sni: str | None
    path: str | None
    host: str | None
    fingerprint: str | None
    public_key: str | None
    short_id: str | None
    metadata: dict[str, Any]
    forward_mode: str = "inbound_outbound"


def normalize_api_url(value: str) -> str:
    """把面板地址统一为根地址，并保留自定义 WebBasePath。"""

    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("3x-ui API 地址必须是 HTTP 或 HTTPS 地址")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("3x-ui API 地址不能包含账号、密码或查询参数")

    path = parsed.path.rstrip("/")
    for suffix in ("/panel/api-docs/index.html", "/panel/api-docs"):
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    return urlunparse((parsed.scheme.lower(), parsed.netloc, path, "", "", "")).rstrip("/")


class ThreeXUIAdapter:
    """默认 MHSanaei/3x-ui v3.8.5 适配器。"""

    def __init__(
        self,
        server: ThreeXUIServer,
        timeout: float = 15.0,
        request_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.server = server
        self.timeout = timeout
        self.request_logger = request_logger
        try:
            self.token = decrypt_secret(server.api_token_encrypted)
        except Exception as exc:
            raise ThreeXUIError("3x-ui API Token 无法解密") from exc
        try:
            self.base_url = normalize_api_url(server.api_url)
        except ValueError as exc:
            raise ThreeXUIError(str(exc)) from exc

    def _url(self, path: str) -> str:
        # 不能使用 urljoin，否则 /panel/api/... 会覆盖自定义 WebBasePath。
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        # 官方 API Token 只通过 Bearer 头发送，避免把凭证重复暴露到额外请求头。
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        operation = kwargs.pop("operation", None)
        safe_path = f"/{path.lstrip('/')}"
        started = time.perf_counter()

        def finish(status_code: int | None, error: str | None = None) -> None:
            event = {
                "method": method.upper(),
                "path": safe_path,
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "stage": operation or _api_stage(method, safe_path),
                "success": error is None,
            }
            if error:
                event["error"] = _safe_remote_text(error)
            logger.log(
                logging.WARNING if error else logging.INFO,
                "3x-ui API %s %s status=%s duration_ms=%s%s",
                event["method"],
                event["path"],
                status_code if status_code is not None else "network-error",
                event["duration_ms"],
                f" error={event['error']}" if error else "",
            )
            if self.request_logger is not None:
                try:
                    self.request_logger(event)
                except Exception:
                    logger.exception("写入 3x-ui API 审计日志失败")

        headers = {**self._headers(), **kwargs.pop("headers", {})}
        try:
            with httpx.Client(
                timeout=self.timeout,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                response = client.request(method, self._url(path), headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            message = "3x-ui API 请求超时"
            finish(None, message)
            raise ThreeXUIError(message) from exc
        except httpx.HTTPError as exc:
            message = "3x-ui API 网络请求失败"
            finish(None, message)
            raise ThreeXUIError(message) from exc
        if response.status_code in {301, 302, 303, 307, 308}:
            message = "3x-ui API 禁止未校验的重定向"
            finish(response.status_code, message)
            raise ThreeXUIError(message)
        if response.status_code == 401:
            message = f"3x-ui API 请求失败：{method.upper()} {safe_path}，HTTP 401，Token 无效或已过期"
            finish(response.status_code, message)
            raise ThreeXUIError(message, status_code=response.status_code)
        if response.status_code == 403:
            message = f"3x-ui API 请求失败：{method.upper()} {safe_path}，HTTP 403，Token 权限不足，转发需要 admin 作用域"
            finish(response.status_code, message)
            raise ThreeXUIError(message, status_code=response.status_code)
        if response.status_code >= 400:
            remote_message = _response_message(response)
            message = f"3x-ui API 请求失败：{method.upper()} {safe_path}，HTTP {response.status_code}"
            if remote_message:
                message += f"，面板返回：{remote_message}"
            finish(response.status_code, message)
            raise ThreeXUIError(message, status_code=response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            message = f"3x-ui API 请求失败：{method.upper()} {safe_path}，返回格式无效"
            finish(response.status_code, message)
            raise ThreeXUIError(message) from exc
        if not isinstance(payload, dict):
            message = f"3x-ui API 请求失败：{method.upper()} {safe_path}，返回结构无效"
            finish(response.status_code, message)
            raise ThreeXUIError(message)
        if payload.get("success") is False:
            remote_message = _safe_remote_text(payload.get("msg") or "3x-ui API 操作失败")
            message = f"3x-ui API 操作失败：{method.upper()} {safe_path}，面板返回：{remote_message}"
            finish(response.status_code, message)
            raise ThreeXUIError(message)
        finish(response.status_code)
        return payload

    def check(self) -> int:
        """验证 API Token 并返回当前入站数量。"""

        return len(self.list_inbounds())

    def list_inbounds(self) -> list[dict[str, Any]]:
        last_error: ThreeXUIError | None = None
        for path in ("/panel/api/inbounds/list", "/panel/api/inbounds/list/slim"):
            try:
                payload = self._request("GET", path)
            except ThreeXUIError as exc:
                if any(marker in str(exc) for marker in ("HTTP 404", "HTTP 405")):
                    last_error = exc
                    continue
                raise
            value = payload.get("obj")
            if isinstance(value, dict):
                value = value.get("inbounds") or value.get("items")
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            # 某些版本直接把数组放在 data/result 下。
            for key in ("data", "result", "inbounds", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        if last_error is not None:
            raise ThreeXUIError("3x-ui 未提供入站列表接口") from last_error
        return []

    def get_xray_setting(self) -> tuple[dict[str, Any], str | None]:
        """读取不同 3x-ui 版本返回的 Xray 配置模板。"""

        last_error: ThreeXUIError | None = None
        checked_paths: list[str] = []
        endpoints = (
            ("GET", "/panel/api/server/getConfigJson"),
            ("POST", "/panel/api/server/getConfigJson"),
            ("GET", "/panel/api/xray/getConfigJson"),
            ("POST", "/panel/api/xray/getConfigJson"),
            ("GET", "/panel/api/xray/config"),
            ("POST", "/panel/api/xray/config"),
            ("POST", "/panel/api/xray/"),
            ("GET", "/panel/api/xray/"),
        )
        for method, path in endpoints:
            checked_paths.append(f"{method} {path}")
            try:
                payload = self._request(method, path)
            except ThreeXUIError as exc:
                if any(marker in str(exc) for marker in ("HTTP 404", "HTTP 405")):
                    last_error = exc
                    continue
                raise
            config = _extract_xray_config(payload)
            if config is not None:
                return config, _extract_outbound_test_url(payload)
        if last_error is not None:
            checked = ", ".join(checked_paths)
            raise ThreeXUIError(f"3x-ui 未提供兼容的 Xray 配置接口（已检查 {checked}）") from last_error
        raise ThreeXUIError("3x-ui API 返回成功但不含有效 Xray 配置（需要 outbounds 或 routing）")

    def get_inbound_links(self, inbound_id: int) -> list[str]:
        """读取面板为入站生成的真实分享链接。"""

        # 优先读取指定入站，避免 allLinks 在多入站面板上拿到别人的线路。
        candidates = [
            ("GET", f"/panel/api/inbounds/get/{inbound_id}"),
            ("GET", "/panel/api/inbounds/allLinks"),
            ("GET", "/panel/api/inbounds/allLink"),
            ("POST", "/panel/api/inbounds/allLinks"),
        ]
        for method, path in candidates:
            try:
                payload = self._request(method, path)
            except ThreeXUIError as exc:
                if not any(marker in str(exc) for marker in ("HTTP 404", "HTTP 405")):
                    raise
                continue
            value = payload.get("obj")
            links = _extract_links_for_inbound(value, inbound_id)
            if not links and path.endswith("/get/" + str(inbound_id)):
                links = _extract_links(value)
            if not links and (path.endswith("allLinks") or path.endswith("allLink")):
                candidates_in_payload = _extract_links(value)
                if len(candidates_in_payload) == 1:
                    links = candidates_in_payload
            if links:
                return links
        raise ThreeXUIError("3x-ui 未返回当前入站的可用分享链接")

    def update_xray_setting(self, config: dict[str, Any], test_url: str | None) -> None:
        fields = {"xraySetting": json.dumps(config, ensure_ascii=False)}
        if test_url:
            fields["outboundTestUrl"] = test_url
        self._request(
            "POST",
            "/panel/api/xray/update",
            data=fields,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def add_inbound(self, payload: dict[str, Any]) -> dict[str, Any]:
        # 最新官方 API 推荐 application/json，嵌套配置直接传对象。
        result = self._request(
            "POST",
            "/panel/api/inbounds/add",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        obj = result.get("obj")
        return obj if isinstance(obj, dict) else payload

    def create_test_inbound(
        self,
        *,
        template: str,
        listen_port: int,
        remark: str,
        target_address: str,
    ) -> ForwardProvision:
        """直接调用面板新增一个测试入站，用于隔离验证入站 API。"""

        inbounds = self.list_inbounds()
        if any(int(item.get("port") or 0) == listen_port for item in inbounds):
            raise ThreeXUIError(f"目标服务器端口 {listen_port} 已被其他入站占用")
        inbound_tag = f"submgr-test-{secrets.token_hex(6)}"
        inbound, provision = self._build_inbound(
            None,
            template=template,
            listen_port=listen_port,
            remark=remark,
            target_address=target_address,
            inbound_tag=inbound_tag,
        )
        created = self._add_inbound_with_unique_email(inbound, inbound_tag)
        inbound_id = _int_value(created.get("id")) or _int_value(inbound.get("id"))
        if inbound_id is None:
            raise ThreeXUIError("3x-ui 创建测试入站后未返回入站 ID")
        actual_tag = str(created.get("tag") or inbound_tag)
        try:
            self.restart_xray()
        except Exception:
            try:
                self.delete_inbound(inbound_id)
                self.restart_xray()
            except ThreeXUIError:
                pass
            raise
        return ForwardProvision(
            **{**provision.__dict__, "inbound_id": inbound_id, "inbound_tag": actual_tag}
        )

    def _add_inbound_with_unique_email(
        self, payload: dict[str, Any], inbound_tag: str
    ) -> dict[str, Any]:
        """兼容面板历史残留 email；仅在明确重复时重新生成一次。"""

        try:
            return self.add_inbound(payload)
        except ThreeXUIError as exc:
            if "duplicate email" not in str(exc).lower():
                raise
            retry_payload = copy.deepcopy(payload)
            settings = retry_payload.get("settings")
            if not isinstance(settings, dict):
                raise
            clients = settings.get("clients")
            if not isinstance(clients, list):
                raise
            for client in clients:
                if isinstance(client, dict):
                    client["email"] = _build_client_email(inbound_tag)
            return self.add_inbound(retry_payload)

    def restart_xray(self) -> None:
        """让结构性入站和路由变更立即加载到运行中的 Xray。"""

        self._request("POST", "/panel/api/server/restartXrayService")

    def delete_inbound(self, inbound_id: int, *, ignore_missing: bool = False) -> None:
        try:
            self._request("POST", f"/panel/api/inbounds/del/{inbound_id}")
        except ThreeXUIError as exc:
            # 删除是幂等操作：远端已经不存在时，本地清理仍应继续完成。
            if ignore_missing and exc.status_code == 404:
                return
            raise

    def provision_forward(
        self,
        source: Node,
        *,
        template: str,
        listen_port: int,
        remark: str,
        target_address: str,
        inbound_tag: str,
        outbound_tag: str,
        forward_mode: str = "inbound_outbound",
    ) -> ForwardProvision:
        """按选择的模式创建端口转发或入站出站转发资源。"""

        if forward_mode == "port_forward":
            return self.provision_port_forward(
                source,
                listen_port=listen_port,
                remark=remark,
                target_address=target_address,
                inbound_tag=inbound_tag,
            )
        if forward_mode != "inbound_outbound":
            raise ThreeXUIError("不支持的 3x-ui 转发模式")
        inbound, provision = self._build_inbound(
            source,
            template=template,
            listen_port=listen_port,
            remark=remark,
            target_address=target_address,
            inbound_tag=inbound_tag,
        )
        inbounds = self.list_inbounds()
        if any(int(item.get("port") or 0) == listen_port for item in inbounds):
            raise ThreeXUIError(f"目标服务器端口 {listen_port} 已被其他入站占用")
        created = self._add_inbound_with_unique_email(inbound, inbound_tag)
        inbound_id = _int_value(created.get("id")) or _int_value(inbound.get("id"))
        if inbound_id is None:
            raise ThreeXUIError("3x-ui 创建入站后未返回入站 ID")
        actual_tag = str(created.get("tag") or inbound_tag)
        provision = ForwardProvision(
            **{**provision.__dict__, "inbound_id": inbound_id, "inbound_tag": actual_tag}
        )
        original_config: dict[str, Any] | None = None
        original_test_url: str | None = None
        try:
            config, test_url = self.get_xray_setting()
            original_config = copy.deepcopy(config)
            original_test_url = test_url
            outbounds = config.setdefault("outbounds", [])
            if not isinstance(outbounds, list):
                raise ThreeXUIError("3x-ui Xray outbounds 结构无效")
            outbounds[:] = [item for item in outbounds if not isinstance(item, dict) or item.get("tag") != outbound_tag]
            outbounds.append(self._source_outbound(source, outbound_tag))
            routing = config.setdefault("routing", {})
            if not isinstance(routing, dict):
                raise ThreeXUIError("3x-ui Xray routing 结构无效")
            rules = routing.setdefault("rules", [])
            if not isinstance(rules, list):
                raise ThreeXUIError("3x-ui Xray routing.rules 结构无效")
            rules.append(
                {"type": "field", "inboundTag": [actual_tag], "outboundTag": outbound_tag}
            )
            self.update_xray_setting(config, test_url)
            self.restart_xray()
        except Exception:
            if original_config is not None:
                try:
                    self.update_xray_setting(original_config, original_test_url)
                    self.restart_xray()
                except ThreeXUIError:
                    pass
            try:
                self.delete_inbound(inbound_id)
                self.restart_xray()
            except ThreeXUIError:
                pass
            raise
        return provision

    def provision_port_forward(
        self,
        source: Node,
        *,
        listen_port: int,
        remark: str,
        target_address: str,
        inbound_tag: str,
    ) -> ForwardProvision:
        """创建 dokodemo-door 入站，把目标端口直接转到源节点地址。"""

        inbounds = self.list_inbounds()
        if any(int(item.get("port") or 0) == listen_port for item in inbounds):
            raise ThreeXUIError(f"目标服务器端口 {listen_port} 已被其他入站占用")
        inbound = {
            "enable": True,
            "remark": remark,
            "tag": inbound_tag,
            "listen": "",
            "port": listen_port,
            "protocol": "dokodemo-door",
            "expiryTime": 0,
            "total": 0,
            "settings": {
                "address": source.server,
                "port": source.port,
                "network": "tcp",
            },
            "streamSettings": {"network": "tcp", "security": "none"},
            "sniffing": {"enabled": False},
        }
        created = self._add_inbound_with_unique_email(inbound, inbound_tag)
        inbound_id = _int_value(created.get("id")) or _int_value(inbound.get("id"))
        if inbound_id is None:
            raise ThreeXUIError("3x-ui 创建端口转发入站后未返回入站 ID")
        actual_tag = str(created.get("tag") or inbound_tag)
        try:
            self.restart_xray()
        except Exception:
            try:
                self.delete_inbound(inbound_id)
                self.restart_xray()
            except ThreeXUIError:
                pass
            raise
        return ForwardProvision(
            inbound_id=inbound_id,
            client_id=None,
            inbound_remark=remark,
            inbound_tag=actual_tag,
            protocol=source.type,
            server=target_address,
            port=listen_port,
            uuid=source.uuid,
            password=source.password,
            cipher=source.cipher,
            network=source.network,
            tls=source.tls or False,
            sni=source.sni,
            path=source.path,
            host=source.host,
            fingerprint=source.fingerprint,
            public_key=source.public_key,
            short_id=source.short_id,
            metadata={"forward_mode": "port_forward", "inbound_tag": actual_tag},
            forward_mode="port_forward",
        )

    def cleanup_forward(
        self,
        inbound_id: int,
        inbound_tag: str,
        outbound_tag: str,
        forward_mode: str = "inbound_outbound",
    ) -> None:
        """删除远端路由、出站和入站；任一环节失败都会明确报告。"""

        errors: list[ThreeXUIError] = []
        if forward_mode == "port_forward":
            try:
                self.delete_inbound(inbound_id, ignore_missing=True)
                self.restart_xray()
            except ThreeXUIError as exc:
                raise ThreeXUIError("3x-ui 端口转发资源清理失败") from exc
            return
        try:
            config, test_url = self.get_xray_setting()
            outbounds = config.get("outbounds")
            if isinstance(outbounds, list):
                config["outbounds"] = [
                    item for item in outbounds
                    if not isinstance(item, dict) or item.get("tag") != outbound_tag
                ]
            routing = config.get("routing")
            rules = routing.get("rules") if isinstance(routing, dict) else None
            if isinstance(rules, list):
                config["routing"]["rules"] = [
                    rule for rule in rules
                    if not (
                        isinstance(rule, dict)
                        and outbound_tag == rule.get("outboundTag")
                        and inbound_tag in (rule.get("inboundTag") or [])
                    )
                ]
            self.update_xray_setting(config, test_url)
            self.restart_xray()
        except ThreeXUIError as exc:
            errors.append(exc)
        try:
            self.delete_inbound(inbound_id, ignore_missing=True)
        except ThreeXUIError as exc:
            errors.append(exc)
        if not errors:
            try:
                self.restart_xray()
            except ThreeXUIError as exc:
                errors.append(exc)
        if errors:
            raise ThreeXUIError("3x-ui 转发资源清理失败") from errors[0]

    @staticmethod
    def _build_inbound(
        source: Node | None,
        *,
        template: str,
        listen_port: int,
        remark: str,
        target_address: str,
        inbound_tag: str,
    ) -> tuple[dict[str, Any], ForwardProvision]:
        client_uuid = str(uuid.uuid4())
        # email 不是展示名称，必须保证在同一面板内唯一；任务重试也不能复用旧 email。
        client_email = _build_client_email(inbound_tag)
        network = "tcp"
        tls = False
        sni = target_address
        path = None
        host = None
        protocol = "vless"
        password = None
        cipher = None
        if template == "vless_tcp":
            clients: list[dict[str, Any]] = [{"id": client_uuid, "email": client_email, "flow": ""}]
        elif template == "vless_ws_tls":
            network, tls, path = "ws", True, "/"
            clients = [{"id": client_uuid, "email": client_email, "flow": ""}]
        elif template == "vmess_ws_tls":
            protocol, network, tls, path = "vmess", "ws", True, "/"
            clients = [{"id": client_uuid, "alterId": 0, "email": client_email}]
        elif template == "trojan_tcp_tls":
            protocol, tls, password = "trojan", True, secrets.token_urlsafe(24)
            client_uuid = None
            clients = [{"password": password, "email": client_email}]
        elif template == "shadowsocks_tcp":
            protocol, password, cipher = "shadowsocks", secrets.token_urlsafe(24), "aes-256-gcm"
            client_uuid = None
            clients = []
        else:
            raise ThreeXUIError("不支持的 3x-ui 转发模板")

        settings: dict[str, Any] = {"clients": clients}
        if protocol == "vless":
            settings["decryption"] = "none"
        if protocol == "shadowsocks":
            settings.update({"method": cipher, "password": password, "network": "tcp"})
        stream: dict[str, Any] = {"network": network, "security": "tls" if tls else "none"}
        if network == "ws":
            stream["wsSettings"] = {"path": path or "/", "headers": {"Host": target_address}}
        if tls:
            stream["tlsSettings"] = {"serverName": target_address, "alpn": ["h2", "http/1.1"]}
        inbound = {
            "enable": True,
            "remark": remark,
            # 路由规则按此 tag 匹配；不传 tag 时面板可能自动生成不同的 tag，导致线路无法命中出站。
            "tag": inbound_tag,
            "listen": "",
            "port": listen_port,
            "protocol": protocol,
            "expiryTime": 0,
            "total": 0,
            "settings": settings,
            "streamSettings": stream,
            "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
        }
        provision = ForwardProvision(
            inbound_id=0,
            client_id=client_uuid or password,
            inbound_remark=remark,
            inbound_tag=inbound_tag,
            protocol=protocol,
            server=target_address,
            port=listen_port,
            uuid=client_uuid,
            password=password,
            cipher=cipher,
            network=network,
            tls=tls,
            sni=sni if tls else None,
            path=path,
            host=host,
            fingerprint=None,
            public_key=None,
            short_id=None,
            metadata={"template": template, "inbound_tag": inbound_tag, "client_email": client_email},
        )
        return inbound, provision

    @staticmethod
    def _source_outbound(source: Node, tag: str) -> dict[str, Any]:
        """将本地节点转换为 Xray outbound；不支持的协议明确失败。"""

        stream = {
            "network": source.network or "tcp",
            "security": source.security or ("tls" if source.tls else "none"),
        }
        if stream["network"] == "ws":
            stream["wsSettings"] = {
                "path": source.path or "/",
                "headers": {"Host": source.host or source.sni or source.server},
            }
        if stream["security"] == "tls":
            stream["tlsSettings"] = {"serverName": source.sni or source.server}
            if source.fingerprint:
                stream["tlsSettings"]["fingerprint"] = source.fingerprint
        if stream["security"] == "reality":
            stream["realitySettings"] = {
                "serverName": source.sni or source.server,
                "fingerprint": source.fingerprint or "chrome",
                "publicKey": source.public_key or "",
                "shortId": source.short_id or "",
            }
        if source.type == "vless":
            user = {"id": source.uuid, "encryption": "none"}
            metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
            if metadata.get("flow"):
                user["flow"] = metadata["flow"]
            return {"tag": tag, "protocol": "vless", "settings": {"vnext": [{"address": source.server, "port": source.port, "users": [user]}]}, "streamSettings": stream}
        if source.type == "vmess":
            return {"tag": tag, "protocol": "vmess", "settings": {"vnext": [{"address": source.server, "port": source.port, "users": [{"id": source.uuid, "alterId": 0, "security": source.cipher or "auto"}]}]}, "streamSettings": stream}
        if source.type == "shadowsocks":
            return {"tag": tag, "protocol": "shadowsocks", "settings": {"servers": [{"address": source.server, "port": source.port, "method": source.cipher, "password": source.password}]}}
        if source.type == "trojan":
            return {"tag": tag, "protocol": "trojan", "settings": {"servers": [{"address": source.server, "port": source.port, "password": source.password}]}, "streamSettings": stream}
        if source.type == "socks":
            server: dict[str, Any] = {
                "address": source.server,
                "port": source.port,
            }
            if source.username or source.password:
                if not source.username or not source.password:
                    raise ThreeXUIError("SOCKS5 源节点必须同时提供用户名和密码")
                server["users"] = [{"user": source.username, "pass": source.password}]
            return {"tag": tag, "protocol": "socks", "settings": {"servers": [server]}}
        raise ThreeXUIError(f"源节点协议 {source.type} 暂不支持 Xray 转发")


def _int_value(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _build_client_email(inbound_tag: str) -> str:
    """生成面板内部使用的唯一 email，不暴露节点名称或凭证。"""

    safe_tag = re.sub(r"[^a-zA-Z0-9._-]+", "-", inbound_tag).strip("-")
    return f"submgr-{safe_tag[:32]}-{secrets.token_hex(8)}"


def _json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _looks_like_xray_config(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return isinstance(value.get("outbounds"), list) or isinstance(value.get("routing"), dict)


def _extract_xray_config(payload: dict[str, Any]) -> dict[str, Any] | None:
    """兼容 obj、data、JSON 字符串和直接配置对象等返回形态。"""

    def visit(value: Any, depth: int = 0) -> dict[str, Any] | None:
        if depth > 5:
            return None
        direct = _json_object(value)
        if direct is None:
            return None
        if _looks_like_xray_config(direct):
            return direct
        for key, nested in direct.items():
            normalized = str(key).replace("_", "").lower()
            if normalized in {"xraysetting", "config", "configuration", "configjson"}:
                candidate = visit(nested, depth + 1)
                if candidate is not None:
                    return candidate
        for key in ("obj", "data", "result", "settings"):
            if key in direct:
                candidate = visit(direct[key], depth + 1)
                if candidate is not None:
                    return candidate
        return None

    return visit(payload)


def _extract_outbound_test_url(payload: dict[str, Any]) -> str | None:
    """读取可选的出站检测地址；缺失时由面板默认值处理。"""

    def visit(value: Any, depth: int = 0) -> str | None:
        if depth > 4 or not isinstance(value, dict):
            return None
        for key, nested in value.items():
            if str(key).replace("_", "").lower() == "outboundtesturl" and isinstance(nested, str):
                return nested
        for key in ("obj", "data", "result"):
            found = visit(value.get(key), depth + 1)
            if found:
                return found
        return None

    return visit(payload)


_LINK_PATTERN = re.compile(
    r"(?:vless|vmess|trojan|ss|socks5?|http|hysteria2?|hy2|tuic|anytls)://[^\s\"']+",
    re.IGNORECASE,
)


def _extract_links(value: Any) -> list[str]:
    """从 3x-ui 不同版本的 obj 结构中提取 URI，不记录或输出凭证。"""

    found: list[str] = []
    if isinstance(value, str):
        found.extend(match.rstrip(",]") for match in _LINK_PATTERN.findall(value))
    elif isinstance(value, list):
        for item in value:
            found.extend(_extract_links(item))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_extract_links(item))
    unique: list[str] = []
    seen: set[str] = set()
    for link in found:
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def _extract_links_for_inbound(value: Any, inbound_id: int) -> list[str]:
    """只从指定入站对象或以入站 ID 为键的结构中提取链接。"""

    if isinstance(value, dict):
        if _int_value(value.get("id")) == inbound_id:
            return _extract_links(value)
        for key, nested in value.items():
            if str(key) == str(inbound_id):
                return _extract_links(nested)
        for nested in value.values():
            links = _extract_links_for_inbound(nested, inbound_id)
            if links:
                return links
    elif isinstance(value, list):
        for item in value:
            links = _extract_links_for_inbound(item, inbound_id)
            if links:
                return links
    return []


def _api_stage(method: str, path: str) -> str:
    """把接口路径映射为便于排查的中文阶段名称。"""

    if path.endswith("/inbounds/add"):
        return "创建入站"
    if "/inbounds/del/" in path:
        return "删除入站"
    if path.endswith("/inbounds/list") or path.endswith("/inbounds/list/slim"):
        return "读取入站列表"
    if "/inbounds/get/" in path:
        return "读取入站分享链接"
    if "allLink" in path:
        return "读取全部分享链接"
    if path.endswith("/xray/update"):
        return "更新 Xray 配置"
    if path.endswith("/restartXrayService"):
        return "重载 Xray"
    if "getConfigJson" in path or path.endswith("/xray/config") or path.endswith("/xray/"):
        return "读取 Xray 配置"
    return f"{method.upper()} {path}"


def _safe_remote_text(value: Any) -> str:
    """清理面板错误文本，避免敏感凭证进入日志或接口响应。"""

    text = str(value or "").replace("\n", " ").replace("\r", " ")
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [已隐藏]", text)
    text = re.sub(
        r"(?i)(token|password|passwd|secret|api[_-]?key|uuid)\s*[:=]\s*[^,;\s]+",
        r"\1=[已隐藏]",
        text,
    )
    text = re.sub(
        r"(?i)(?:vless|vmess|trojan|ss|socks5?|http|hysteria2?|hy2|tuic|anytls)://\S+",
        "[节点链接已隐藏]",
        text,
    )
    text = re.sub(
        r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        "[UUID已隐藏]",
        text,
    )
    return text[:240]


def _response_message(response: httpx.Response) -> str | None:
    """提取 HTTP 错误中的面板消息，不回显整段响应体。"""

    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        for key in ("msg", "message", "error", "detail"):
            if payload.get(key):
                return _safe_remote_text(payload[key])
    return None
