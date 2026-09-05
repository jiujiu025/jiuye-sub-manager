# 快速开始

## Docker Compose

1. 安装 Docker Engine 和 Docker Compose Plugin。
2. 准备一个域名，并将 DNS A/AAAA 记录指向服务器。
3. 复制环境变量模板：

```bash
cp .env.example .env
```

4. 编辑 `.env`，至少设置：

- `APP_ENV=production`
- `JWT_SECRET_KEY`：至少 32 个字符的随机值
- `ADMIN_PASSWORD`：强管理员密码
- `PUBLIC_BASE_URL=https://你的域名`
- `CORS_ORIGINS=https://你的域名`

5. 启动：

```bash
docker compose up -d --build
docker compose ps
```

API 只在 Compose 网络内监听 8000，公网入口由 Nginx 提供 80/443。

## 首次使用

1. 打开网站首页并登录。
2. 在“来源管理”添加合法授权的上游订阅。
3. 点击同步，确认来源状态为成功。
4. 在“节点管理”检查节点、协议和启用状态。
5. 在“套餐管理”创建套餐并配置来源、国家、类型、关键词、重命名和排序规则。
6. 复制创建响应中一次性返回的订阅地址。
7. 在客户端中导入订阅地址。

本地开发命令和 HTTPS 证书配置见 `docs/Ubuntu部署.md` 与 `docs/Docker部署.md`。
