"""3x-ui 服务器、转发任务和本地转发节点业务服务。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.cache import cache_service
from app.core.security import encrypt_secret, token_prefix
from app.db import SessionLocal
from app.integrations.three_xui.adapter import (
    ThreeXUIAdapter,
    ThreeXUIError,
    normalize_api_url,
)
from app.models.base import utcnow
from app.models.node import Node
from app.models.three_xui import ForwardTask, ForwardedNodeMapping, ThreeXUIServer
from app.models.user import User
from app.parsers.base import ParseError, ParsedNode, validate_parsed_node
from app.parsers.uri_parser import parse_uri_line
from app.repositories.log_repo import LogRepository
from app.utils.fingerprint import fingerprint_for_parsed
from app.utils.node_code import allocate_node_code
from app.utils.country import detect_country
from app.schemas.three_xui import (
    ForwardBatchCreate,
    ForwardBatchResponse,
    ForwardBatchSkipped,
    ForwardTaskCreate,
    ThreeXUIInboundTestCreate,
    ThreeXUIInboundTestResponse,
    ThreeXUIServerCreate,
    ThreeXUIServerUpdate,
)

logger = logging.getLogger(__name__)


class ThreeXUIService:
    """封装 3x-ui 服务器管理和异步转发任务执行。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.log_repo = LogRepository(db)

    def list_servers(self) -> list[ThreeXUIServer]:
        """按启用状态和名称返回服务器列表。"""

        return list(
            self.db.scalars(
                select(ThreeXUIServer).order_by(
                    ThreeXUIServer.enabled.desc(), ThreeXUIServer.name.asc()
                )
            ).all()
        )

    def get_server(self, server_id: int) -> ThreeXUIServer | None:
        return self.db.get(ThreeXUIServer, server_id)

    def create_server(
        self, payload: ThreeXUIServerCreate, admin: User
    ) -> ThreeXUIServer:
        """创建服务器并只把 API Token 密文保存到数据库。"""

        self._validate_api_url(payload.api_url)
        server = ThreeXUIServer(
            name=payload.name.strip(),
            ip=payload.ip.strip() if payload.ip else None,
            domain=payload.domain.strip() if payload.domain else None,
            api_url=normalize_api_url(payload.api_url),
            api_token_encrypted=encrypt_secret(payload.api_token),
            api_token_prefix=token_prefix(payload.api_token),
            version=payload.version.strip(),
            note=payload.note.strip() if payload.note else None,
            expires_at=payload.expires_at,
            enabled=payload.enabled,
        )
        self.db.add(server)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise BusinessError("3x-ui 服务器名称已存在") from exc
        self.log_repo.create_admin_log(admin.id, "create_three_xui_server", "three_xui_server", server.name)
        self.db.commit()
        self.db.refresh(server)
        return server

    def update_server(
        self,
        server: ThreeXUIServer,
        payload: ThreeXUIServerUpdate,
        admin: User,
    ) -> ThreeXUIServer:
        """更新服务器；未提交新 Token 时保留原密文。"""

        data = payload.model_dump(exclude_unset=True)
        if "api_url" in data and data["api_url"]:
            data["api_url"] = normalize_api_url(data["api_url"])
        if "name" in data and data["name"]:
            data["name"] = data["name"].strip()
        if "api_token" in data:
            raw_token = (data.pop("api_token") or "").strip()
            if raw_token:
                server.api_token_encrypted = encrypt_secret(raw_token)
                server.api_token_prefix = token_prefix(raw_token)
        for field in ("ip", "domain", "version", "note"):
            if field in data and isinstance(data[field], str):
                data[field] = data[field].strip() or None
        for key, value in data.items():
            setattr(server, key, value)
        if not (server.ip or server.domain):
            raise BusinessError("服务器 IP 或域名至少填写一个")
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise BusinessError("3x-ui 服务器名称已存在") from exc
        self.log_repo.create_admin_log(admin.id, "update_three_xui_server", "three_xui_server", server.name)
        self.db.commit()
        self.db.refresh(server)
        return server

    def check_server(
        self, server: ThreeXUIServer, actor: User | None = None
    ) -> tuple[str, int | None, str]:
        """调用适配器检测服务器，并保存脱敏后的检测结果。"""

        checked_at = utcnow()
        try:
            inbound_count = self._adapter(server, actor.id if actor else None).check()
        except ThreeXUIError as exc:
            server.last_api_check_at = checked_at
            server.last_api_status = "failed"
            server.last_error = str(exc)[:240]
            self.db.commit()
            return "failed", None, server.last_error
        server.last_api_check_at = checked_at
        server.last_api_status = "healthy"
        server.last_error = None
        self.db.commit()
        return "healthy", inbound_count, "3x-ui API 连接正常"

    def create_test_inbound(
        self,
        server: ThreeXUIServer,
        payload: ThreeXUIInboundTestCreate,
        actor: User | None = None,
    ) -> ThreeXUIInboundTestResponse:
        """创建一个真实测试入站，验证 Token、入站新增和 Xray 重载链路。"""

        if not server.enabled:
            raise BusinessError("目标 3x-ui 服务器已停用")
        if server.expires_at and _utc(server.expires_at) <= _utc(utcnow()):
            raise BusinessError("目标 3x-ui 服务器已到期")
        address = self._target_address(server)
        if not address:
            raise BusinessError("目标服务器缺少 IP 或域名")
        listen_port = payload.port or self._allocate_listen_port(server.id)
        remark = (payload.remark or "").strip() or f"测试入站-{listen_port}"
        try:
            provision = self._adapter(server, actor.id if actor else None).create_test_inbound(
                template=payload.template,
                listen_port=listen_port,
                remark=remark,
                target_address=address,
            )
        except ThreeXUIError as exc:
            server.last_api_check_at = utcnow()
            server.last_api_status = "failed"
            server.last_error = str(exc)[:240]
            self.db.commit()
            raise BusinessError(f"测试创建入站失败：{exc}", status_code=502) from exc
        server.last_api_check_at = utcnow()
        server.last_api_status = "healthy"
        server.last_error = None
        self.db.commit()
        return ThreeXUIInboundTestResponse(
            server_id=server.id,
            inbound_id=provision.inbound_id,
            template=payload.template,
            protocol=provision.protocol,
            port=provision.port,
            remark=provision.inbound_remark,
            message="测试入站已创建并已请求重载 Xray；如仅用于测试，请在 3x-ui 面板中手动删除。",
        )

    def delete_server(self, server: ThreeXUIServer, admin: User) -> None:
        """仅删除没有任务或映射的服务器，避免留下远端转发资源。"""

        mapping_exists = self.db.scalar(
            select(ForwardedNodeMapping.id).where(
                ForwardedNodeMapping.target_server_id == server.id
            ).limit(1)
        )
        task_exists = self.db.scalar(
            select(ForwardTask.id).where(ForwardTask.target_server_id == server.id).limit(1)
        )
        if mapping_exists is not None or task_exists is not None:
            raise BusinessError("该服务器仍有关联的转发任务或映射，不能直接删除")
        self.db.delete(server)
        self.log_repo.create_admin_log(admin.id, "delete_three_xui_server", "three_xui_server", server.name)
        self.db.commit()

    def list_tasks(self, limit: int = 100) -> list[ForwardTask]:
        safe_limit = max(1, min(limit, 200))
        return list(
            self.db.scalars(
                select(ForwardTask)
                .order_by(ForwardTask.created_at.desc(), ForwardTask.id.desc())
                .limit(safe_limit)
            ).all()
        )

    def list_mappings(self, limit: int = 100) -> list[ForwardedNodeMapping]:
        safe_limit = max(1, min(limit, 200))
        return list(
            self.db.scalars(
                select(ForwardedNodeMapping)
                .order_by(ForwardedNodeMapping.updated_at.desc(), ForwardedNodeMapping.id.desc())
                .limit(safe_limit)
            ).all()
        )

    def create_batch(
        self, payload: ForwardBatchCreate, admin: User
    ) -> ForwardBatchResponse:
        """为多个外部节点分配端口并分别入队，单个节点失败不影响其他节点。"""

        unique_ids = list(dict.fromkeys(payload.source_node_ids))
        occupied = set(
            self.db.scalars(
                select(ForwardTask.listen_port).where(
                    ForwardTask.target_server_id == payload.target_server_id,
                )
            ).all()
        )
        tasks: list[ForwardTask] = []
        skipped: list[ForwardBatchSkipped] = []
        next_port = payload.listen_port_start
        for source_id in unique_ids:
            while next_port in occupied and next_port <= payload.listen_port_end:
                next_port += 1
            if next_port > payload.listen_port_end:
                skipped.append(
                    ForwardBatchSkipped(source_node_id=source_id, reason="可用端口不足")
                )
                continue
            try:
                task = self.create_task(
                    ForwardTaskCreate(
                        source_node_id=source_id,
                        target_server_id=payload.target_server_id,
                        template=payload.template,
                        forward_mode=payload.forward_mode,
                        inbound_remark=payload.inbound_remark,
                        listen_port=next_port,
                    ),
                    admin,
                )
            except BusinessError as exc:
                skipped.append(
                    ForwardBatchSkipped(source_node_id=source_id, reason=exc.message)
                )
                continue
            tasks.append(task)
            occupied.add(next_port)
            next_port += 1
        return ForwardBatchResponse(tasks=tasks, skipped=skipped)

    def retry_task(self, task: ForwardTask) -> ForwardTask:
        """重新排队失败任务，避免重复创建仍在运行的远端资源。"""

        if task.status != "failed":
            raise BusinessError("只有失败任务可以重试")
        source = self.db.get(Node, task.source_node_id)
        target = self.db.get(ThreeXUIServer, task.target_server_id)
        if source is None or target is None:
            raise BusinessError("源节点或目标服务器不存在", status_code=404)
        if source.node_category != "external":
            raise BusinessError("只有外部节点可以创建转发")
        if not target.enabled:
            raise BusinessError("目标 3x-ui 服务器已停用")
        task.status = "pending"
        task.progress = 0
        task.stage = "等待后台处理"
        task.error_message = None
        task.started_at = None
        task.finished_at = None
        self.db.commit()
        self.db.refresh(task)
        return task

    def cleanup_mapping(self, mapping: ForwardedNodeMapping, admin: User) -> None:
        """先清理远端资源，再删除本地转发节点和映射。"""

        target = self.db.get(ThreeXUIServer, mapping.target_server_id)
        forwarded = self.db.get(Node, mapping.forwarded_node_id)
        if target is None or forwarded is None:
            raise BusinessError("转发映射关联数据不存在", status_code=404)
        metadata = mapping.metadata_json if isinstance(mapping.metadata_json, dict) else {}
        inbound_tag = str(metadata.get("inbound_tag") or f"submgr-in-{mapping.id}")
        task_id = metadata.get("task_id")
        outbound_tag = str(
            metadata.get("outbound_tag")
            or (f"submgr-out-{task_id}" if task_id else f"submgr-out-map-{mapping.id}")
        )
        try:
            adapter = self._adapter(target, admin.id)
            if mapping.forward_mode == "port_forward":
                adapter.cleanup_forward(mapping.inbound_id, inbound_tag, outbound_tag, "port_forward")
            else:
                # 保持旧版本适配器和已有测试替身的三参数兼容性。
                adapter.cleanup_forward(mapping.inbound_id, inbound_tag, outbound_tag)
        except ThreeXUIError as exc:
            self.db.rollback()
            current = self.db.get(ForwardedNodeMapping, mapping.id)
            if current is not None:
                current.status = "cleanup_failed"
                current.last_error = str(exc)[:240]
                self.db.commit()
            raise BusinessError("远端 3x-ui 资源清理失败，请稍后重试", status_code=409) from exc

        # 远端删除成功后才删除本地记录，避免本地仍可交付一个失效线路。
        self.db.expunge(mapping)
        self.db.execute(
            delete(ForwardedNodeMapping).where(ForwardedNodeMapping.id == mapping.id)
        )
        from app.services.node_service import NodeService

        NodeService(self.db)._remove_owner_node(forwarded, allow_forwarded=True)
        self.log_repo.create_admin_log(
            admin.id,
            "delete_three_xui_forward",
            "node",
            forwarded.name,
        )
        self.db.commit()
        cache_service.invalidate_all()

    def cleanup_forwarded_node(self, node: Node, admin: User) -> None:
        """按本地转发节点查找映射，并执行远端清理。"""

        mapping = self.db.scalar(
            select(ForwardedNodeMapping).where(
                ForwardedNodeMapping.forwarded_node_id == node.id
            )
        )
        if mapping is None:
            raise BusinessError("转发节点缺少资源映射，不能直接删除", status_code=409)
        self.cleanup_mapping(mapping, admin)

    def create_task(
        self, payload: ForwardTaskCreate, admin: User
    ) -> ForwardTask:
        """校验源节点后入队；HTTP 请求本身不连接目标 3x-ui。"""

        source = self.db.get(Node, payload.source_node_id)
        if source is None:
            raise BusinessError("源节点不存在", status_code=404)
        if source.node_category != "external":
            raise BusinessError("只有导入外部节点可以作为 3x-ui 转发源")
        target = self.db.get(ThreeXUIServer, payload.target_server_id)
        if target is None:
            raise BusinessError("目标 3x-ui 服务器不存在", status_code=404)
        if not target.enabled:
            raise BusinessError("目标 3x-ui 服务器已停用")
        if target.expires_at and _utc(target.expires_at) <= _utc(utcnow()):
            raise BusinessError("目标 3x-ui 服务器已到期")
        if self._target_address(target) is None:
            raise BusinessError("目标服务器缺少 IP 或域名")

        mapping = self.db.scalar(
            select(ForwardedNodeMapping).where(
                ForwardedNodeMapping.source_node_id == source.id,
                ForwardedNodeMapping.target_server_id == target.id,
                ForwardedNodeMapping.template == payload.template,
                ForwardedNodeMapping.forward_mode == payload.forward_mode,
                ForwardedNodeMapping.status == "active",
            )
        )
        if mapping is not None:
            existing = self.db.get(ForwardTask, mapping.metadata_json.get("task_id")) if isinstance(mapping.metadata_json, dict) and mapping.metadata_json.get("task_id") else None
            if existing is not None:
                return existing
            raise BusinessError("相同源节点、目标服务器和模板已经存在转发")

        pending = self.db.scalar(
            select(ForwardTask).where(
                ForwardTask.source_node_id == source.id,
                ForwardTask.target_server_id == target.id,
                ForwardTask.template == payload.template,
                ForwardTask.forward_mode == payload.forward_mode,
                ForwardTask.status.in_(("pending", "running")),
            ).order_by(ForwardTask.id.desc())
        )
        if pending is not None:
            return pending
        task = ForwardTask(
            source_node_id=source.id,
            target_server_id=target.id,
            template=payload.template,
            forward_mode=payload.forward_mode,
            inbound_remark=payload.inbound_remark.strip() if payload.inbound_remark else None,
            listen_port=payload.listen_port or self._allocate_listen_port(target.id),
            auto_port=payload.listen_port is None,
            status="pending",
            created_by_user_id=admin.id,
        )
        self.db.add(task)
        self.log_repo.create_admin_log(admin.id, "create_three_xui_forward_task", "forward_task", source.name)
        self.db.commit()
        self.db.refresh(task)
        return task

    def process_pending(self, limit: int = 3) -> int:
        """认领并执行一批待处理任务；每个任务独立提交结果。"""

        stale_before = utcnow().timestamp() - 1800
        stale_running = list(
            self.db.scalars(
                select(ForwardTask).where(ForwardTask.status == "running")
            ).all()
        )
        for stale in stale_running:
            if stale.started_at is not None and _utc(stale.started_at).timestamp() < stale_before:
                stale.status = "pending"
                stale.error_message = "上次 worker 中断，任务已重新排队"
                stale.progress = 0
                stale.stage = "等待后台处理"
        if stale_running:
            self.db.commit()
        tasks = list(
            self.db.scalars(
                select(ForwardTask)
                .where(ForwardTask.status == "pending")
                .order_by(ForwardTask.created_at.asc(), ForwardTask.id.asc())
                .limit(max(1, min(limit, 20)))
            ).all()
        )
        processed = 0
        for task in tasks:
            task.status = "running"
            task.started_at = utcnow()
            task.error_message = None
            task.progress = 5
            task.stage = "准备执行"
            self.db.commit()
            self._execute_task(task.id)
            processed += 1
        return processed

    def _execute_task(self, task_id: int) -> None:
        task = self.db.get(ForwardTask, task_id)
        if task is None:
            return
        source = self.db.get(Node, task.source_node_id)
        target = self.db.get(ThreeXUIServer, task.target_server_id)
        if source is None or target is None:
            self._fail_task(task, "源节点或目标服务器不存在", "校验资源")
            return
        adapter: ThreeXUIAdapter | None = None
        provision = None
        stage = "初始化 3x-ui 适配器"
        try:
            self._set_task_progress(task, 10, stage)
            if not target.enabled:
                raise ThreeXUIError("目标 3x-ui 服务器已停用")
            if target.expires_at and _utc(target.expires_at) <= _utc(utcnow()):
                raise ThreeXUIError("目标 3x-ui 服务器已到期")
            address = self._target_address(target)
            if not address:
                raise ThreeXUIError("目标服务器缺少 IP 或域名")
            adapter = self._adapter(target, task.created_by_user_id)
            if task.auto_port:
                task.listen_port = self._resolve_remote_port(adapter, task.listen_port)
                self.db.commit()
            inbound_tag = f"submgr-in-{task.id}"
            outbound_tag = f"submgr-out-{task.id}"
            region = source.country or detect_country(source.name) or detect_country(address) or "节点"
            remark = (task.inbound_remark or "").strip() or f"{region}-{address}"
            stage = "创建 3x-ui 转发资源"
            self._set_task_progress(task, 20, "检查目标服务器")
            self._set_task_progress(task, 30, stage)
            provision = adapter.provision_forward(
                source,
                template=task.template,
                listen_port=task.listen_port,
                remark=remark,
                target_address=address,
                inbound_tag=inbound_tag,
                outbound_tag=outbound_tag,
                forward_mode=task.forward_mode,
            )
            if task.forward_mode == "port_forward":
                parsed = self._build_port_forward_node(source, address, task.listen_port)
            else:
                stage = "读取 3x-ui 入站分享链接"
                self._set_task_progress(task, 55, stage)
                links = adapter.get_inbound_links(provision.inbound_id)
                stage = "解析 3x-ui 入站分享链接"
                self._set_task_progress(task, 70, stage)
                parsed = self._parse_generated_link(links, task.template, task.listen_port)
            stage = "保存本地已转发节点"
            self._set_task_progress(task, 85, stage)
            node = self._save_forwarded_node(parsed, source, target, task, provision)
            mapping = ForwardedNodeMapping(
                source_node_id=source.id,
                forwarded_node_id=node.id,
                target_server_id=target.id,
                inbound_id=provision.inbound_id,
                client_id=parsed.uuid or parsed.password or provision.client_id,
                inbound_remark=provision.inbound_remark,
                template=task.template,
                forward_mode=task.forward_mode,
                status="active",
                last_synced_at=utcnow(),
                metadata_json={
                    "task_id": task.id,
                    "inbound_tag": provision.inbound_tag,
                    "outbound_tag": f"submgr-out-{task.id}",
                    "forward_mode": task.forward_mode,
                },
            )
            self.db.add(mapping)
            task.progress = 95
            task.stage = "写入转发映射"
            task.result_node_id = node.id
            task.status = "succeeded"
            task.progress = 100
            task.stage = "转发完成"
            task.finished_at = utcnow()
            target.last_api_check_at = utcnow()
            target.last_api_status = "healthy"
            target.last_error = None
            self.db.commit()
            cache_service.invalidate_all()
        except (BusinessError, ThreeXUIError, ParseError, ValueError) as exc:
            if adapter is not None and provision is not None:
                try:
                    adapter.cleanup_forward(
                        provision.inbound_id,
                        provision.inbound_tag,
                        f"submgr-out-{task.id}",
                        task.forward_mode,
                    )
                except ThreeXUIError:
                    logger.warning("3x-ui 转发回滚失败，任务=%s", task.id)
            message = _safe_error(exc)
            self._fail_task(task, f"{stage}失败：{message}", stage)
        except Exception:
            logger.exception("3x-ui 转发任务执行异常，任务=%s", task.id)
            if adapter is not None and provision is not None:
                try:
                    adapter.cleanup_forward(
                        provision.inbound_id,
                        provision.inbound_tag,
                        f"submgr-out-{task.id}",
                        task.forward_mode,
                    )
                except ThreeXUIError:
                    logger.warning("3x-ui 转发回滚失败，任务=%s", task.id)
            self._fail_task(task, f"{stage}失败：转发任务执行失败", stage)

    def _save_forwarded_node(
        self,
        parsed: ParsedNode,
        source: Node,
        target: ThreeXUIServer,
        task: ForwardTask,
        provision,
    ) -> Node:
        fingerprint = fingerprint_for_parsed(parsed)
        existing = self.db.scalar(select(Node).where(Node.node_fingerprint == fingerprint))
        if existing is not None and existing.node_category != "forwarded":
            raise BusinessError("生成的转发节点与现有非转发节点重复")
        if existing is None:
            node = Node(
                node_code=allocate_node_code(self.db),
                source_name=f"3x-ui:{target.name}",
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
                country=parsed.country or detect_country(parsed.original_name),
                source_type="forwarded",
                source_subtype="three_xui",
                node_category="forwarded",
                enabled=True,
                node_fingerprint=fingerprint,
                metadata_json={"source_node_id": source.id, "target_server_id": target.id, "task_id": task.id},
                note=f"3x-ui 转发源：{source.name}",
                last_seen_at=utcnow(),
            )
            self.db.add(node)
            self.db.flush()
            return node
        node.name = parsed.original_name
        node.enabled = True
        node.last_seen_at = utcnow()
        node.note = f"3x-ui 转发源：{source.name}"
        node.metadata_json = {"source_node_id": source.id, "target_server_id": target.id, "task_id": task.id}
        return node

    @staticmethod
    def _build_port_forward_node(source: Node, target_address: str, listen_port: int) -> ParsedNode:
        """端口转发不生成新协议凭证，只替换客户端实际连接的地址和端口。"""

        return ParsedNode(
            original_name=source.name,
            type=source.type,
            server=target_address,
            port=listen_port,
            uuid=source.uuid,
            password=source.password,
            username=source.username,
            cipher=source.cipher,
            network=source.network,
            security=source.security,
            tls=source.tls,
            sni=source.sni,
            fingerprint=source.fingerprint,
            public_key=source.public_key,
            short_id=source.short_id,
            path=source.path,
            host=source.host,
            country=source.country or detect_country(source.name),
            metadata=dict(source.metadata_json) if isinstance(source.metadata_json, dict) else {},
        )

    @staticmethod
    def _parse_generated_link(
        links: list[str], template: str, listen_port: int | None = None
    ) -> ParsedNode:
        expected = {
            "vless_tcp": "vless",
            "vless_ws_tls": "vless",
            "vmess_ws_tls": "vmess",
            "trojan_tcp_tls": "trojan",
            "shadowsocks_tcp": "shadowsocks",
        }.get(template)
        errors: list[str] = []
        for link in links:
            try:
                parsed = parse_uri_line(link)
                validate_parsed_node(parsed)
                if expected and parsed.type != expected:
                    continue
                if listen_port is not None and parsed.port != listen_port:
                    continue
                return parsed
            except (ParseError, TypeError, ValueError) as exc:
                errors.append(str(exc))
        raise ParseError("3x-ui 返回的分享链接无法解析")

    @staticmethod
    def _target_address(server: ThreeXUIServer) -> str | None:
        return (server.domain or server.ip or "").strip() or None

    def _allocate_listen_port(self, target_server_id: int, start: int = 12900) -> int:
        """从指定起始端口开始，避开本地已有任务后顺序分配端口。"""

        occupied = {
            int(port)
            for port in self.db.scalars(
                select(ForwardTask.listen_port).where(
                    ForwardTask.target_server_id == target_server_id
                )
            ).all()
            if port is not None
        }
        for port in range(max(1, start), 65536):
            if port not in occupied:
                return port
        raise BusinessError("12900 之后没有可用监听端口", status_code=409)

    @staticmethod
    def _resolve_remote_port(adapter: ThreeXUIAdapter, initial_port: int) -> int:
        """自动端口任务执行前避开目标面板已有入站。"""

        occupied = {
            int(item.get("port") or 0)
            for item in adapter.list_inbounds()
            if isinstance(item, dict) and item.get("port") is not None
        }
        port = initial_port
        while port in occupied and port < 65535:
            port += 1
        if port in occupied:
            raise ThreeXUIError("目标服务器没有可用监听端口")
        return port

    @staticmethod
    def _validate_api_url(value: str) -> None:
        try:
            normalize_api_url(value)
        except ValueError as exc:
            raise BusinessError(str(exc)) from exc

    def _adapter(
        self, server: ThreeXUIServer, actor_user_id: int | None = None
    ) -> ThreeXUIAdapter:
        """创建带审计回调的适配器，统一记录每次面板 API 调用。"""

        return ThreeXUIAdapter(
            server,
            request_logger=lambda event: self._record_api_request(
                server, actor_user_id, event
            ),
        )

    def _record_api_request(
        self,
        server: ThreeXUIServer,
        actor_user_id: int | None,
        event: dict,
    ) -> None:
        """写入脱敏的 3x-ui API 审计日志，不保存请求体和认证头。"""

        detail = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        # 转发失败时业务事务会回滚，审计日志必须独立提交，才能保留真实失败原因。
        audit_db = SessionLocal()
        try:
            LogRepository(audit_db).create_admin_log(
                actor_user_id,
                "three_xui_api_request",
                "three_xui_server",
                server.name,
                detail,
            )
            audit_db.commit()
        except Exception:
            audit_db.rollback()
            logger.exception("写入 3x-ui API 审计日志失败")
        finally:
            audit_db.close()

    def _set_task_progress(self, task: ForwardTask, progress: int, stage: str) -> None:
        """提交任务当前进度，让前端轮询时能看到真实阶段。"""

        task.progress = max(0, min(progress, 100))
        task.stage = stage[:64]
        self.db.commit()
        self.db.refresh(task)

    def _fail_task(self, task: ForwardTask, message: str, stage: str | None = None) -> None:
        # 任务执行中可能已经写入了未提交的节点或映射，失败时先回滚再保存失败状态。
        self.db.rollback()
        task = self.db.get(ForwardTask, task.id)
        if task is None:
            return
        task.status = "failed"
        if stage:
            task.stage = f"{stage}失败"[:64]
        task.error_message = message[:240]
        task.finished_at = utcnow()
        self.db.commit()


def _utc(value: datetime) -> datetime:
    """把 SQLite 返回的无时区时间按 UTC 解释。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_error(exc: Exception) -> str:
    """只保留适合后台展示的错误，不回显 Token、链接或底层请求内容。"""

    if isinstance(exc, BusinessError):
        return exc.message
    if isinstance(exc, (ThreeXUIError, ParseError)):
        return str(exc)[:240]
    return "转发任务执行失败"
