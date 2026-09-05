FROM node:22-alpine AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

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
