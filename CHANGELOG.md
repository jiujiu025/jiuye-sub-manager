# 更新记录

## Unreleased

- 完善上游同步的公网 DNS 校验、重定向校验和请求大小限制。
- 同步失败时保留上一次成功的节点状态。
- 修复容器无 IPv6 出口时混合 DNS 结果导致的同步失败。
- 支持 Clash/Mihomo YAML、sing-box JSON 和 URI 订阅输出。
- 增加订阅 Token 重生成、撤销和格式隔离缓存。
- 增加生产部署 HTTPS、安全响应头和健康检查配置。

## 现有能力

- 来源、节点、套餐、Token 和订阅管理。
- VLESS Reality/TLS、Shadowsocks、VMess、Trojan 等节点解析与导出。
- Alembic 数据库迁移和 Docker Compose 部署。
