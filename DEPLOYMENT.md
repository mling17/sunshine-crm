# 天窗天幕 CRM · 部署与数据库切换

镜像包含 FastAPI、静态前端和运行时目录。默认仍是 SQLite，也可以连接外部 MySQL 8.0，或使用 Compose 内置的 MySQL 8.0 服务。

- 页面：`http://<服务器IP>:8010/crm/`
- 健康检查：`http://<服务器IP>:8010/health`
- 默认数据库：SQLite，位于 `/opt/data/crm/crm.db`
- MySQL 模式：`CRM_DB_ENGINE=mysql`
- 附件：`/opt/data/crm/uploads`
- SQLite 数据卷：`sunshine-crm-data`
- 内置 MySQL 数据卷：`sunshine-crm-mysql-data`

数据库迁移和备份手册：

- [SQLite 数据迁移到 MySQL](docs/DATABASE-SQLITE-TO-MYSQL.md)
- [MySQL 数据备份及恢复](docs/DATABASE-MYSQL-BACKUP-RESTORE.md)
- [SQLite 数据备份及恢复](docs/DATABASE-SQLITE-BACKUP-RESTORE.md)

## 1. 构建镜像

在项目根目录（本文件所在目录）执行：

```bash
docker build --pull -t sunshine-crm:1.0.0 .
```

如果在 x86_64 Windows/macOS 上为 Ubuntu x86_64 服务器构建，可明确指定架构：

```bash
docker build --pull --platform linux/amd64 -t sunshine-crm:1.0.0 .
```

## 2. 离线传输镜像

在构建机导出：

```bash
docker save sunshine-crm:1.0.0 | gzip -1 > sunshine-crm-1.0.0-amd64.tar.gz
```

把 `sunshine-crm-1.0.0-amd64.tar.gz` 和项目中的
`docker-compose.yml`、`.env.example` 上传到 Ubuntu 服务器。服务器导入：

```bash
gzip -dc sunshine-crm-1.0.0-amd64.tar.gz | docker load
```

也可以把源码直接上传服务器，在服务器执行第 1 节的 `docker build`，不传输镜像文件。

## 3. 启动

Ubuntu 需要 Docker Engine 与 Compose 插件：

```bash
docker --version
docker compose version
```

使用内置 MySQL 的可选依赖需要 Docker Compose **2.20.0 或更高版本**。

### 3.1 默认 SQLite

在 Compose 文件所在目录准备配置：

```bash
cp .env.example .env
chmod 600 .env
# 编辑 .env，至少把 ADMIN_PASSWORD 改为高强度密码
docker compose up -d
```

首次启动会自动建表、执行数据库迁移，并在数据库没有用户时创建管理员。
之后修改 `ADMIN_PASSWORD` 不会覆盖数据库里已有账号的密码。

默认 `CRM_DB_ENGINE=sqlite`。如果已有旧数据，先把备份恢复为命名卷内的 `/opt/data/crm/crm.db` 和 `/opt/data/crm/uploads/`，再启动容器。

### 3.2 使用 Compose 内置 MySQL

先设置 `.env`：

```dotenv
CRM_DB_ENGINE=mysql
CRM_MYSQL_HOST=mysql
CRM_MYSQL_PORT=3306
CRM_MYSQL_USER=crm
CRM_MYSQL_PASSWORD=替换为强密码
CRM_MYSQL_DATABASE=sunshine_crm
CRM_MYSQL_CHARSET=utf8mb4
CRM_MYSQL_SSL_DISABLED=true
MYSQL_ROOT_PASSWORD=替换为另一条强密码
```

启动应用和内置 MySQL：

```bash
docker compose --profile mysql up -d
```

`mysql` 使用 MySQL 8.0.36、`utf8mb4_unicode_ci`、`+08:00` 时区，数据保存在命名卷 `sunshine-crm-mysql-data`。首次启动自动建表并播种字典、产品主档和管理员。

### 3.3 使用外部 MySQL

外部 MySQL 必须是 8.0 及以上。`.env` 示例：

```dotenv
CRM_DB_ENGINE=mysql
CRM_MYSQL_HOST=10.0.0.20
CRM_MYSQL_PORT=3306
CRM_MYSQL_USER=crm
CRM_MYSQL_PASSWORD=替换为强密码
CRM_MYSQL_DATABASE=sunshine_crm
CRM_MYSQL_CHARSET=utf8mb4
CRM_MYSQL_SSL_DISABLED=false
```

不要填写 `127.0.0.1` 指向 Docker 容器自身。外部数据库账号只授权对应数据库；跨网连接应启用 TLS，并在防火墙中限制应用服务器 IP。

启动：

```bash
docker compose up -d crm
```

传统 systemd 部署时，把数据库配置写到权限为 `600` 的
`/opt/data/crm/crm.env`；`crm-api.service` 会自动读取该文件：

```bash
sudo install -m 600 /dev/null /opt/data/crm/crm.env
sudoedit /opt/data/crm/crm.env
sudo systemctl restart crm-api
```

## 4. 验证

```bash
docker compose ps
docker inspect --format '{{.State.Health.Status}}' sunshine-crm
curl -fsS http://127.0.0.1:8010/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/crm/
docker compose logs --tail=100 crm
```

预期容器状态为 `running`、健康状态为 `healthy`，两个 HTTP 检查均返回 `200`。

## 5. 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `ADMIN_USERNAME` | 首次建库时的管理员账号 | `admin` |
| `ADMIN_PASSWORD` | 首次建库时的管理员密码，Compose 强制要求设置 | 无 |
| `CRM_IMAGE` | 镜像名 | `sunshine-crm:latest` |
| `CRM_BIND_ADDRESS` | 宿主机监听地址 | `0.0.0.0` |
| `CRM_PORT` | 宿主机端口 | `8010` |
| `COOKIE_SECURE` | HTTPS 下设为 `1`；仅 HTTP 时保持 `0` | `0` |
| `TZ` | 业务时区 | `Asia/Shanghai` |
| `CRM_DB_ENGINE` | `sqlite` 或 `mysql` | `sqlite` |
| `CRM_MYSQL_HOST` | MySQL 主机；内置服务使用 `mysql` | `mysql` |
| `CRM_MYSQL_PORT` | MySQL 端口 | `3306` |
| `CRM_MYSQL_USER` | MySQL 用户 | `crm` |
| `CRM_MYSQL_PASSWORD` | MySQL 密码 | 空 |
| `CRM_MYSQL_DATABASE` | 数据库名 | `sunshine_crm` |
| `CRM_MYSQL_CHARSET` | 连接字符集，必须是 `utf8mb4` | `utf8mb4` |
| `CRM_MYSQL_SSL_DISABLED` | 内网可设 `true`；跨网应设 `false` | `true` |
| `MYSQL_ROOT_PASSWORD` | 仅 Compose 内置 MySQL root 密码 | 空 |

容器内部固定使用：

```text
CRM_DB=/opt/data/crm/crm.db
CRM_UPLOADS=/opt/data/crm/uploads
```

如只允许本机 nginx 访问容器，可把 `.env` 中
`CRM_BIND_ADDRESS` 改成 `127.0.0.1`。

## 6. 数据备份与恢复

### 6.1 SQLite

容器内备份脚本生成 SQLite 一致快照和附件归档：

```bash
docker exec sunshine-crm python ops/backup.py --no-offsite
docker cp sunshine-crm:/opt/data/crm/backups ./backups
```

建议用宿主机 cron 每天执行一次，并把导出的 `backups/` 同步到另一台机器。

恢复前先停止服务，并保留当前数据卷备份：

```bash
docker compose stop crm
docker cp sunshine-crm:/opt/data/crm ./crm-data-before-restore
```

将旧备份解包后，用 `docker cp` 覆盖停止状态容器内的
`/opt/data/crm/crm.db` 与 `/opt/data/crm/uploads/`，再执行
`docker compose up -d`。不要在服务运行时用 `docker cp` 或 `cp` 覆盖 SQLite 数据库。

### 6.2 MySQL

Compose 内置 MySQL 的逻辑备份：

```bash
docker compose exec -T mysql sh -c \
  'exec mysqldump --single-transaction --triggers \
   --default-character-set=utf8mb4 --set-gtid-purged=OFF \
   -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  | gzip -1 > "mysql-$(date +%Y%m%d-%H%M%S).sql.gz"
```

附件单独从 CRM 数据卷打包。完整命令、校验和恢复演练见
[MySQL 数据备份及恢复](docs/DATABASE-MYSQL-BACKUP-RESTORE.md)。

## 7. 升级与回滚

升级：

```bash
# 先把新版本构建/导入为新标签，例如 sunshine-crm:1.0.1
sed -i 's#^CRM_IMAGE=.*#CRM_IMAGE=sunshine-crm:1.0.1#' .env
docker compose up -d --no-build
```

回滚：

```bash
sed -i 's#^CRM_IMAGE=.*#CRM_IMAGE=sunshine-crm:1.0.0#' .env
docker compose up -d --no-build
```

数据卷不会因替换镜像而删除。只有明确执行 `docker compose down -v` 才会删除 SQLite/附件和内置 MySQL 两个数据卷。

## 8. 常见问题

```bash
# 查看配置和环境变量是否符合预期
docker compose config

# 查看启动、迁移和错误日志
docker compose logs -f crm

# 检查端口占用
sudo ss -lntp | grep ':8010'

# 确认数据卷位置
docker volume inspect sunshine-crm-data
docker volume inspect sunshine-crm-mysql-data
```

HTTP 状态码为 `307` 且 Location 是 `/crm/` 时属于正常重定向。

`/health` 在 MySQL 模式返回的 `db` 字段形如：

```json
{
  "status": "ok",
  "db": "mysql://crm@mysql:3306/sunshine_crm",
  "db_engine": "mysql"
}
```

响应不会包含数据库密码。
