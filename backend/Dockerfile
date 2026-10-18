FROM python:3.12-slim

ARG SING_BOX_VERSION=1.14.2
ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tar \
    && rm -rf /var/lib/apt/lists/* \
    && case "${TARGETARCH:-amd64}" in amd64) SB_ARCH=amd64 ;; arm64) SB_ARCH=arm64 ;; *) echo "不支持的容器架构" >&2; exit 1 ;; esac \
    && mkdir -p /tmp/sing-box \
    && curl --fail --silent --show-error --location \
      "https://github.com/SagerNet/sing-box/releases/download/v${SING_BOX_VERSION}/sing-box-${SING_BOX_VERSION}-linux-${SB_ARCH}.tar.gz" \
      --output /tmp/sing-box.tar.gz \
    && tar -xzf /tmp/sing-box.tar.gz -C /tmp/sing-box \
    && install /tmp/sing-box/sing-box-${SING_BOX_VERSION}-linux-${SB_ARCH}/sing-box /usr/local/bin/sing-box \
    && rm -rf /tmp/sing-box /tmp/sing-box.tar.gz \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
