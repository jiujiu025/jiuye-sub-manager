# 固定 Node 20 构建环境，避免 Node 22 Alpine 中 npm ci 的内部退出异常。
FROM node:20-bookworm-slim AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --progress=false

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY deploy/nginx/nginx.conf /opt/sub-manager/nginx-http.conf
COPY deploy/nginx/nginx-https.conf /opt/sub-manager/nginx-https.conf
COPY frontend/docker-entrypoint.d/40-select-nginx-config.sh /docker-entrypoint.d/40-select-nginx-config.sh
RUN chmod +x /docker-entrypoint.d/40-select-nginx-config.sh

EXPOSE 80
EXPOSE 443
