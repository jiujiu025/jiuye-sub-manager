"""节点健康探测、状态收敛和外部告警。"""

from __future__ import annotations

import logging
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.node import Node
from app.exporters.singbox import SingboxExporter
from app.services.notification_writer import create_admin_notifications
from app.services.subscription_state import active_subscription_clause
from app.models.subscription import CustomerSubscription
from app.models.user import User
from app.services.manager_scope import effective_manager_id
from app.services.package_service import PackageService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NodeProbeTarget:
    """线程中探测节点所需的最小字段集合。"""

    node_id: int
    name: str
    node_type: str
    server: str
    port: int
    outbound: dict


@dataclass(frozen=True)
class ProbeResult:
    status: str
    detail: str
    latency_ms: int | None
    tcp_status: str = "unknown"
    tls_status: str = "unknown"
    tcp_latency_ms: int | None = None
    tls_latency_ms: int | None = None


@dataclass(frozen=True)
class HealthAlert:
    node_name: str
    node_id: int
    title: str
    content: str
    dedupe_key: str
    priority: str


def _is_udp_node(node_type: str) -> bool:
    return node_type in {"hysteria", "hysteria2", "tuic"}


def _error_detail(exc: Exception) -> str:
    """把底层网络异常转换成适合展示和通知的中文。"""

    if isinstance(exc, socket.gaierror):
        return "DNS 解析失败"
    if isinstance(exc, socket.timeout) or isinstance(exc, TimeoutError):
        return "连接超时"
    if isinstance(exc, ConnectionRefusedError):
        return "目标端口拒绝连接"
    if isinstance(exc, ConnectionResetError):
        return "连接被目标端重置"
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "TLS 证书验证失败"
    if isinstance(exc, ssl.SSLError):
        return "TLS 握手失败"
    return "连接失败"


def probe_node(target: NodeProbeTarget, timeout_seconds: float) -> ProbeResult:
    """启动临时 sing-box，通过本地代理验证节点是否真正可用。"""

    settings = get_settings()
    executable = shutil.which(settings.sing_box_path) or settings.sing_box_path
    if not shutil.which(executable) and not os.path.isfile(executable):
        return ProbeResult("unknown", "完整检测内核未安装，请安装 sing-box", None)

    started = time.perf_counter()
    deadline = started + max(float(timeout_seconds), 1.0)
    with tempfile.TemporaryDirectory(prefix="sub-health-") as temp_dir:
        config_path = os.path.join(temp_dir, "config.json")
        local_port = _free_local_port()
        config = {
            "log": {"level": "error"},
            "inbounds": [
                {
                    "type": "mixed",
                    "tag": "health-in",
                    "listen": "127.0.0.1",
                    "listen_port": local_port,
                }
            ],
            "outbounds": [
                {**target.outbound, "tag": "health-node"},
                {"type": "direct", "tag": "direct"},
            ],
            "route": {"final": "health-node"},
        }
        with open(config_path, "w", encoding="utf-8") as config_file:
            json.dump(config, config_file, ensure_ascii=False)

        try:
            remaining = _remaining_seconds(deadline)
            if remaining <= 0:
                return ProbeResult("degraded", "节点检测总超时", None)
            checked = subprocess.run(
                [executable, "check", "-c", config_path],
                capture_output=True,
                text=True,
                timeout=remaining,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ProbeResult("degraded", "协议配置校验超时", None)
        except OSError:
            return ProbeResult("degraded", "完整检测内核无法启动", None)
        if checked.returncode != 0:
            return ProbeResult(
                "degraded",
                f"协议配置校验失败：{_classify_process_error(checked.stderr)}",
                None,
            )

        # 使用系统分配的本地端口，避免多节点并发检测时端口冲突。
        try:
            process = subprocess.Popen(
                [executable, "run", "-c", config_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError:
            return ProbeResult("degraded", "完整检测内核无法启动", None)
        try:
            remaining = _remaining_seconds(deadline)
            if remaining <= 0:
                return ProbeResult("offline", "节点检测总超时", None)
            ready, startup_error = _wait_for_proxy(process, local_port, remaining)
            if not ready:
                return ProbeResult("degraded", startup_error, None)
            remaining = _remaining_seconds(deadline)
            if remaining <= 0:
                return ProbeResult("offline", "节点检测总超时", None)
            with httpx.Client(
                proxy=f"http://127.0.0.1:{local_port}",
                timeout=remaining,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                response = client.get(settings.health_test_url)
            if response.status_code >= 400:
                return ProbeResult(
                    "degraded",
                    f"代理已建立，但测试网址返回 HTTP {response.status_code}",
                    _latency_ms(started),
                    "passed",
                    _tls_probe_status(target.outbound),
                    None,
                    _latency_ms(started),
                )
            latency_ms = _latency_ms(started)
            return ProbeResult(
                "healthy",
                f"完整代理访问成功，HTTP {response.status_code}",
                latency_ms,
                "passed",
                _tls_probe_status(target.outbound),
                None,
                latency_ms,
            )
        except httpx.TimeoutException:
            return ProbeResult("offline", "代理已启动，但访问测试网址超时", None)
        except httpx.ProxyError:
            return ProbeResult("degraded", "本地代理已启动，但代理请求失败", None)
        except httpx.HTTPError as exc:
            return ProbeResult("degraded", f"代理请求失败：{_short_error(str(exc))}", None)
        except OSError as exc:
            return ProbeResult("offline", f"检测进程启动失败：{_short_error(str(exc))}", None)
        finally:
            _terminate_process(process)


def probe_basic_node(target: NodeProbeTarget, timeout_seconds: float) -> ProbeResult:
    """执行不启动代理内核的基础连通性探测。"""

    if _is_udp_node(target.node_type):
        return ProbeResult(
            "unknown",
            "UDP 节点暂未执行 TCP/TLS 探测",
            None,
            "unknown",
            "unknown",
        )

    started = time.perf_counter()
    try:
        addresses = socket.getaddrinfo(
            target.server,
            target.port,
            type=socket.SOCK_STREAM,
        )
    except Exception as exc:
        return ProbeResult("offline", _error_detail(exc), None, "failed", "unknown")

    last_error: Exception | None = None
    last_tcp_latency: int | None = None
    last_tls_latency: int | None = None
    last_tls_status = "unknown"
    for family, socktype, protocol, _, sockaddr in addresses:
        sock: socket.socket | None = None
        connected = False
        requires_tls = False
        reality_enabled = False
        connected_at = 0.0
        try:
            sock = socket.socket(family, socktype, protocol)
            sock.settimeout(timeout_seconds)
            sock.connect(sockaddr)
            connected = True
            connected_at = time.perf_counter()

            tls_config = target.outbound.get("tls")
            requires_tls = target.node_type in {"trojan", "anytls"} or bool(
                isinstance(tls_config, dict) and tls_config.get("enabled")
            )
            reality_enabled = bool(
                isinstance(tls_config, dict)
                and isinstance(tls_config.get("reality"), dict)
                and tls_config["reality"].get("enabled")
            )
            tcp_latency = max(1, round((connected_at - started) * 1000))
            if requires_tls and not reality_enabled:
                context = ssl.create_default_context()
                server_name = (
                    tls_config.get("server_name")
                    if isinstance(tls_config, dict)
                    else None
                ) or target.server
                tls_started = time.perf_counter()
                sock = context.wrap_socket(sock, server_hostname=server_name)
                last_tls_latency = max(1, round((time.perf_counter() - tls_started) * 1000))
                last_tls_status = "passed"
            elif reality_enabled:
                last_tls_status = "unknown"
            else:
                last_tls_status = "not_applicable"

            latency_ms = max(1, round((time.perf_counter() - started) * 1000))
            detail = "TCP 连接成功"
            if last_tls_status == "passed":
                detail += "，TLS 握手成功"
            elif last_tls_status == "unknown" and reality_enabled:
                detail += "，Reality 握手需完整模式验证"
            return ProbeResult(
                "healthy",
                detail,
                latency_ms,
                "passed",
                last_tls_status,
                tcp_latency,
                last_tls_latency,
            )
        except Exception as exc:
            last_error = exc
            if connected:
                last_tcp_latency = max(1, round((connected_at - started) * 1000))
                last_tls_status = "failed" if requires_tls and not reality_enabled else last_tls_status
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

    detail = _error_detail(last_error or OSError())
    status = "degraded" if isinstance(last_error, ssl.SSLError) else "offline"
    return ProbeResult(
        status,
        detail,
        last_tcp_latency,
        "passed" if last_tcp_latency is not None else "failed",
        last_tls_status,
        last_tcp_latency,
        last_tls_latency,
    )


def _tls_probe_status(outbound: dict) -> str:
    """根据完整探测配置标记 TLS 是否属于本线路。"""

    tls_config = outbound.get("tls") if isinstance(outbound, dict) else None
    if not isinstance(tls_config, dict) or not tls_config.get("enabled"):
        return "not_applicable"
    return "passed"


def _free_local_port() -> int:
    """申请一个当前可用的本地 TCP 端口。"""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _remaining_seconds(deadline: float) -> float:
    """返回探测总截止时间的剩余秒数。"""

    return max(0.0, deadline - time.perf_counter())


def _wait_for_proxy(
    process: subprocess.Popen, port: int, timeout_seconds: float
) -> tuple[bool, str]:
    """等待 sing-box 入站监听，进程提前退出时返回诊断信息。"""

    deadline = time.monotonic() + max(timeout_seconds, 0)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            error = process.stderr.read() if process.stderr else ""
            return False, f"协议进程启动失败：{_classify_process_error(error)}"
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True, ""
        except OSError:
            time.sleep(0.05)
    return False, "协议进程启动超时，可能是配置错误或节点握手异常"


def _terminate_process(process: subprocess.Popen) -> None:
    """无论检测结果如何都清理临时 sing-box 进程。"""

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    if process.stderr:
        process.stderr.close()


def _latency_ms(started: float) -> int:
    return max(1, round((time.perf_counter() - started) * 1000))


def _short_error(message: str) -> str:
    return " ".join(message.strip().split())[:240] or "未知错误"


def _classify_process_error(message: str) -> str:
    """隐藏 sing-box 日志中的路径和凭证，只保留可诊断信息。"""

    text = _short_error(message)
    lowered = text.lower()
    if "authentication" in lowered or "unauthorized" in lowered:
        return "认证失败（UUID、密码或用户信息错误）"
    if "tls" in lowered or "reality" in lowered or "certificate" in lowered:
        return "TLS/Reality 握手失败（SNI、证书或 Reality 参数错误）"
    if "websocket" in lowered or "transport" in lowered or "grpc" in lowered:
        return "传输层握手失败（Path、Host 或传输参数错误）"
    if "timeout" in lowered or "timed out" in lowered:
        return "节点连接超时"
    return "协议进程异常退出，请检查节点协议参数"


class HealthAlertDispatcher:
    """按环境变量配置发送 Telegram 和企业微信告警。"""

    def dispatch(self, content: str) -> None:
        settings = get_settings()
        has_telegram = bool(settings.telegram_bot_token and settings.telegram_chat_id)
        has_wecom = bool(settings.wecom_bot_webhook)
        if not has_telegram and not has_wecom:
            return
        with httpx.Client(timeout=10, trust_env=False) as client:
            if has_telegram:
                try:
                    response = client.post(
                        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                        json={"chat_id": settings.telegram_chat_id, "text": content},
                    )
                    response.raise_for_status()
                except Exception:
                    logger.exception("Telegram 节点健康告警发送失败")
            if settings.wecom_bot_webhook:
                try:
                    response = client.post(
                        settings.wecom_bot_webhook,
                        json={"msgtype": "text", "text": {"content": content}},
                    )
                    response.raise_for_status()
                except Exception:
                    logger.exception("企业微信节点健康告警发送失败")


class NodeHealthService:
    """从自有节点池探测启用节点，并维护故障状态。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def run_node(self, node: Node) -> Node:
        settings = SettingsService(self.db).get()
        try:
            target = self._target(node)
        except (AttributeError, TypeError, ValueError) as exc:
            result = ProbeResult(
                "degraded",
                f"节点配置无效：{_short_error(str(exc))}",
                None,
            )
        else:
            result = self._probe(target, settings)
        alerts = self._apply_result(node, result, settings)
        self.db.commit()
        self._dispatch(alerts)
        self.db.refresh(node)
        return node

    def run_all(self, *, include_all: bool = False) -> int:
        """批量检测节点；定时任务默认只检测自有节点，手动操作可检测全部启用节点。"""

        settings = SettingsService(self.db).get()
        conditions = [Node.enabled.is_(True)]
        if not include_all:
            conditions.append(Node.source_type == "custom")
        nodes = list(self.db.scalars(select(Node).where(*conditions)).all())
        targets: dict[int, NodeProbeTarget] = {}
        results: dict[int, ProbeResult] = {}
        for node in nodes:
            try:
                targets[node.id] = self._target(node)
            except (AttributeError, TypeError, ValueError) as exc:
                results[node.id] = ProbeResult(
                    "degraded",
                    f"节点配置无效：{_short_error(str(exc))}",
                    None,
                )
        if targets:
            with ThreadPoolExecutor(
                max_workers=max(1, min(settings.health_probe_concurrency, 100))
            ) as pool:
                results.update(
                    zip(
                        targets,
                        pool.map(
                            lambda target: self._probe(target, settings),
                            targets.values(),
                        ),
                    )
                )

        alerts: list[HealthAlert] = []
        for node in nodes:
            alerts.extend(self._apply_result(node, results[node.id], settings))
        self.db.commit()
        self._dispatch(alerts)
        scope_label = "全部启用节点" if include_all else "启用自有节点"
        logger.info("本次节点健康检测完成，共检测 %s 个%s", len(nodes), scope_label)
        return len(nodes)

    def _target(self, node: Node) -> NodeProbeTarget:
        return NodeProbeTarget(
            node_id=node.id,
            name=node.name,
            node_type=node.type,
            server=node.server,
            port=node.port,
            outbound=SingboxExporter._to_outbound(node, "health-node"),
        )

    @staticmethod
    def _probe(target: NodeProbeTarget, settings) -> ProbeResult:
        if settings.health_probe_mode == "basic":
            return probe_basic_node(target, settings.health_timeout_seconds)
        return probe_node(target, settings.health_timeout_seconds)

    def _apply_result(self, node: Node, result: ProbeResult, settings) -> list[HealthAlert]:
        """连续失败/成功达到阈值后才切换状态并生成告警。"""

        now = utcnow()
        previous_status = node.health_status or "unknown"
        node.health_checked_at = now
        node.health_latency_ms = result.latency_ms
        node.health_detail = result.detail
        node.health_tcp_status = result.tcp_status
        node.health_tls_status = result.tls_status
        node.health_tcp_latency_ms = result.tcp_latency_ms
        node.health_tls_latency_ms = result.tls_latency_ms
        alerts: list[HealthAlert] = []

        if result.status == "unknown":
            node.health_status = "unknown"
            node.health_failure_count = 0
            node.health_success_count = 0
            node.health_incident_started_at = None
            return alerts

        if result.status == "healthy":
            node.health_failure_count = 0
            node.health_success_count += 1
            if previous_status in {"offline", "degraded"}:
                if node.health_success_count < settings.health_recovery_threshold:
                    node.health_detail = (
                        f"恢复检测 {node.health_success_count}/"
                        f"{settings.health_recovery_threshold}：{result.detail}"
                    )
                    return alerts
                node.health_status = "healthy"
                incident = node.health_incident_started_at or now
                alerts.append(
                    self._alert(
                        node,
                        "线路已恢复",
                        f"线路「{node.name}」已恢复，连续成功 {node.health_success_count} 次，耗时 {result.latency_ms or '-'} ms。",
                        f"node_health:{node.id}:recovered:{incident.isoformat()}",
                        "normal",
                    )
                )
                node.health_incident_started_at = None
            else:
                node.health_status = "healthy"
            return alerts

        node.health_success_count = 0
        node.health_failure_count += 1
        if node.health_failure_count < settings.health_failure_threshold:
            return alerts

        node.health_status = result.status
        if previous_status != result.status or previous_status == "unknown":
            if node.health_incident_started_at is None:
                node.health_incident_started_at = now
            label = "离线" if result.status == "offline" else "异常"
            alerts.append(
                self._alert(
                    node,
                    f"线路{label}",
                    f"线路「{node.name}」[{node.type}] 检测为{label}，连续失败 {node.health_failure_count} 次。\n"
                    f"服务器：{node.server}:{node.port}\n原因：{result.detail}",
                    f"node_health:{node.id}:{result.status}:{node.health_incident_started_at.isoformat()}",
                    "high",
                )
            )
        return alerts

    def _alert(
        self,
        node: Node,
        title: str,
        content: str,
        dedupe_key: str,
        priority: str,
    ) -> HealthAlert:
        recipients = list(
            self.db.scalars(
                select(User.id).where(User.role == "admin", User.is_active.is_(True))
            ).all()
        )
        subscriptions = self.db.scalars(
            select(CustomerSubscription)
            .options(
                joinedload(CustomerSubscription.customer),
                joinedload(CustomerSubscription.package),
                joinedload(CustomerSubscription.token),
            )
            .join(CustomerSubscription.customer)
            .outerjoin(CustomerSubscription.token)
            .where(active_subscription_clause(datetime.now(timezone.utc)))
        ).all()
        package_service = PackageService(self.db)
        for subscription in subscriptions:
            manager_id = effective_manager_id(subscription)
            if manager_id is None or manager_id in recipients:
                continue
            if any(item.id == node.id for item in package_service.preview(subscription.package)):
                recipients.append(manager_id)
        create_admin_notifications(
            self.db,
            kind="node_health",
            title=title,
            content=content,
            dedupe_key=dedupe_key,
            priority=priority,
            target_type="node",
            target_id=node.id,
            recipient_user_ids=recipients,
        )
        return HealthAlert(node.name, node.id, title, content, dedupe_key, priority)

    def _dispatch(self, alerts: list[HealthAlert]) -> None:
        if not alerts:
            return
        dispatcher = HealthAlertDispatcher()
        for alert in alerts:
            dispatcher.dispatch(f"【{alert.title}】\n{alert.content}")
