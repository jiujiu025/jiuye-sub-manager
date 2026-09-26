#!/bin/sh
set -eu

# 生产环境必须使用证书；开发环境保留 HTTP 便于本地启动。
normalized_app_env=$(printf '%s' "${APP_ENV:-development}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
if [ "$normalized_app_env" = "production" ] || [ "$normalized_app_env" = "prod" ]; then
    if [ ! -f /etc/nginx/certs/fullchain.pem ] || [ ! -f /etc/nginx/certs/privkey.pem ]; then
        echo "生产环境缺少 /etc/nginx/certs/fullchain.pem 或 privkey.pem" >&2
        exit 1
    fi
    cp /opt/sub-manager/nginx-https.conf /etc/nginx/conf.d/default.conf
else
    cp /opt/sub-manager/nginx-http.conf /etc/nginx/conf.d/default.conf
fi
