FROM python:3.12-slim-bookworm

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    CRM_DB=/opt/data/crm/crm.db \
    CRM_UPLOADS=/opt/data/crm/uploads

WORKDIR /app

# 项目使用 datetime.now() 生成业务日期，容器必须有业务时区数据。
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_GID}" crm \
    && useradd --uid "${APP_UID}" --gid crm --create-home --shell /usr/sbin/nologin crm

# 先复制依赖清单，让代码变更尽量复用依赖层缓存。
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY --chown=crm:crm app ./app
COPY --chown=crm:crm static ./static
COPY --chown=crm:crm ops/backup.py ./ops/backup.py
COPY --chown=crm:crm ops/migrate_sqlite_to_mysql.py ./ops/migrate_sqlite_to_mysql.py

RUN mkdir -p /opt/data/crm/uploads /opt/data/crm/backups \
    && chown -R crm:crm /opt/data/crm /app

# 应用与数据目录均不需要 root；Docker 卷自动继承该目录所有者。
USER crm

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=4).read()"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*", "--no-access-log"]
