# 订阅聚合与节点分发系统

私有的「订阅聚合 + 节点管理 + 套餐分发」系统。支持多个合法授权的上游订阅、统一节点池、自有 VLESS/SS 节点、套餐筛选规则、独立订阅 Token，以及 Clash/Mihomo 订阅输出。

## 核心原则

- 上游订阅只是数据源
- 统一节点池是核心数据
- 套餐只是节点池上的筛选规则
- 订阅 URL 只是套餐规则的对外访问入口
- 最终订阅绝不包含上游订阅 URL

## 功能

- 多上游订阅管理：新增、修改、删除、启用/禁用、手动/定时同步
- 订阅解析：Base64、Clash YAML、VLESS URI、Shadowsocks URI，自动格式检测
- 同步安全：staging → validate → commit，失败保留旧节点，空订阅默认视为异常
- 统一节点池：标准化 Node Model、节点指纹去重、来源优先级
- 自有节点：VLESS、Shadowsocks
- 套餐规则：来源/地区/类型/关键词筛选、重命名、排序
- 独立订阅 Token：高强度随机、数据库只存 SHA-256 哈希、可重生成
- Clash/Mihomo 输出：只输出解析后的 `proxies`
- 缓存：订阅 YAML TTL 缓存，同步/规则变更后主动清理
- 后台：概览、上游订阅、节点池、套餐管理、系统日志

## 技术栈

- 后端：Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic
- 数据库：SQLite（WAL 模式）
- 认证：bcrypt + JWT
- 前端：Vue3 + Vite + Element Plus + Pinia
- 部署：Docker Compose + Nginx

## 目录

```text
backend/            FastAPI 后端
frontend/           Vue3 后台
deploy/nginx/       Nginx HTTP/HTTPS 配置
docs/               架构与设计文档
```

## Windows 本地开发（无需 Docker）

### 1. 启动后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env：设置 JWT_SECRET_KEY 和 ADMIN_PASSWORD
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

首次启动若未设置 `ADMIN_PASSWORD`，会生成一次性临时密码并打印到控制台，请尽快登录后台修改。

### 2. 启动前端

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

访问 `http://localhost:5173`。Vite 已配置 `/api`、`/sub` 代理到 `http://127.0.0.1:8000`。

## Ubuntu VPS Docker Compose 部署

```bash
git clone <your-repo-url>
cd sub项目
cp .env.example .env
nano .env   # 修改 JWT_SECRET_KEY、ADMIN_PASSWORD、PUBLIC_BASE_URL
docker compose up -d --build
```

访问 `http://服务器IP`，后台默认路径为 `/`。API 文档在 `http://服务器IP/api/docs`。

## HTTPS

1. 将 `deploy/nginx/ssl-example.conf` 复制为正式 Nginx 配置并替换域名
2. 使用 Certbot 或云厂商证书生成 `fullchain.pem`、`privkey.pem`
3. 挂载证书到 nginx 容器 `/etc/nginx/certs/`，启用 443 监听
4. 将 `.env` 中的 `PUBLIC_BASE_URL` 改为 `https://你的域名`

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/sub_manager.db` | 数据库连接 |
| `JWT_SECRET_KEY` | 随机生成（仅本地） | 生产必须配置固定密钥 |
| `JWT_EXPIRE_MINUTES` | `720` | 后台会话有效期 |
| `ADMIN_USERNAME` | `admin` | 首次启动创建的管理员 |
| `ADMIN_PASSWORD` | 随机生成（仅首次） | 生产必须配置强密码 |
| `SYNC_INTERVAL_MINUTES` | `5` | 自动同步周期 |
| `SYNC_ENABLED` | `true` | 是否启动定时同步 |
| `CACHE_TTL_SECONDS` | `300` | 订阅缓存 TTL |
| `HTTP_TIMEOUT_SECONDS` | `15` | 上游拉取超时 |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | 订阅 URL 展示基础地址 |

## 已记录的默认行为

- 同步失败、返回 HTML、空订阅：保留旧节点，只更新失败状态和日志
- `allow_empty_override=true` 时才允许空订阅覆盖旧节点
- 去重优先级：自有节点最高，其余来源按 `dedup_source_priority` 或创建顺序
- 国家识别基于节点名称关键词，后续可扩展 GeoIP
- 订阅 Token 仅在创建/重生成时显示一次，数据库只保存哈希
- 生产环境日志会过滤 UUID、密码、完整 VLESS URL、上游 URL、Token

## 系统设置

后台「系统设置」页面可修改：

- 自动同步间隔（分钟）
- 定时同步开关
- 订阅缓存 TTL（秒）
- 节点来源去重优先级（自有节点始终最高）

以上设置保存后立即生效。JWT 密钥、管理员密码、HTTP 超时等配置需要修改 `.env` 后重启服务。

## 数据库备份与恢复

备份（自动带时间戳，输出到 `data/backups/`）：

```powershell
cd backend
python scripts/backup_db.py
```

Docker 环境：

```bash
docker compose exec api python scripts/backup_db.py
```

恢复（恢复前会自动备份一次当前数据库）：

```powershell
cd backend
python scripts/restore_db.py data/backups/sub_manager_20260901_120000.db
```

Docker 环境（建议先 `docker compose stop api` 再恢复）：

```bash
docker compose exec api python scripts/restore_db.py /app/data/backups/sub_manager_20260901_120000.db
docker compose start api
```

日志文件已启用滚动轮转（单个 5MB，保留 5 份），Docker 部署时 `logs/` 目录挂载在命名卷中，容器重建不会丢失。

## 测试

```powershell
cd backend
python -m pytest -q
```

测试覆盖：VLESS/SS 解析、Base64/Clash 解析、节点去重与优先级、筛选/关键词/重命名/排序、套餐规则、Token 校验与重生成、Clash 输出、同步失败保留旧节点、空订阅策略、端到端订阅自动更新。

## 最终验收流程

1. 登录后台
2. 添加机场 A、机场 B 订阅并同步
3. 添加自有 VLESS、SS 节点
4. 创建套餐 A（香港/日本/自有）与套餐 B（美国/新加坡/机场 B）
5. 分别获得两个订阅 URL
6. 修改上游节点，等待自动同步
7. 原订阅 URL 自动返回新节点，且无法看到上游订阅 URL

详细架构见 [docs/01-architecture.md](docs/01-architecture.md)。
