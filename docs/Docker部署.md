# Docker 部署

## 服务结构

当前 Compose 包含两个服务：

- `api`：FastAPI、SQLAlchemy、Alembic 和 SQLite，内部监听 8000。
- `nginx`：构建前端静态文件并反向代理 API、订阅和健康检查，映射 80/443。

API 使用 `sub_manager_data` 保存数据库，使用 `sub_manager_logs` 保存日志。Nginx 证书目录只读挂载。

## 配置

Docker Compose 从项目根目录的 `.env` 读取配置，并额外将数据库路径设置为容器内的 SQLite 路径。模板中的密钥、密码和域名均为占位符。

生产至少配置：

```dotenv
APP_ENV=production
JWT_SECRET_KEY=替换为本地生成的至少32位随机值
ADMIN_PASSWORD=替换为强密码
PUBLIC_BASE_URL=https://你的域名
CORS_ORIGINS=https://你的域名
```

## 常用命令

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=200 api
docker compose exec api alembic current
```

健康接口是 `/healthz`，不是 `/api/healthz`。

## 证书

将 `deploy/nginx/nginx-https.conf` 中的证书域名模板替换为实际域名，或者在部署层生成对应配置。证书私钥只保存在服务器证书目录，不得复制到工作区或 Git。
