# Ubuntu 部署

## 系统准备

建议使用受支持的 Ubuntu LTS，并完成系统更新、SSH 防护和防火墙配置。只开放必要的 SSH、HTTP 和 HTTPS 端口。

安装 Docker 官方组件后验证：

```bash
docker --version
docker compose version
```

## 域名与 HTTPS

将域名解析到服务器。生产配置使用 Nginx：

- HTTP 80 用于跳转 HTTPS 和 ACME challenge。
- HTTPS 443 提供前端、`/api/`、`/sub/` 和 `/healthz`。
- API 8000 只通过 Compose 网络暴露，不映射到宿主机。

证书文件通过只读挂载提供给 Nginx。证书目录和 ACME webroot 应使用服务器自己的路径，不要把证书文件放进仓库。

## 启动与检查

```bash
cp .env.example .env
# 编辑 .env
docker compose up -d --build
docker compose ps
curl -fsS https://你的域名/healthz
```

生产环境必须设置 `APP_ENV=production`、固定的 `JWT_SECRET_KEY`、强 `ADMIN_PASSWORD`、HTTPS `PUBLIC_BASE_URL` 和明确的 `CORS_ORIGINS`。

## 数据与升级

SQLite 数据保存在 Compose 命名卷中。升级前先备份数据库，升级时执行：

```bash
docker compose exec api alembic upgrade head
docker compose up -d --build
```

不要删除数据卷来解决应用问题。
