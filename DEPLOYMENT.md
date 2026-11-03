# 天窗天幕 CRM · Docker 部署

镜像内包含 FastAPI、静态前端和运行时目录，一个容器即可提供完整服务：

- 页面：`http://<服务器IP>:8010/crm/`
- 健康检查：`http://<服务器IP>:8010/health`
- 数据：SQLite 数据库、附件和备份统一保存在命名卷 `sunshine-crm-data`

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

在 Compose 文件所在目录准备密钥：

```bash
cp .env.example .env
chmod 600 .env
# 编辑 .env，至少把 ADMIN_PASSWORD 改为高强度密码
docker compose up -d
```

首次启动会自动建表、执行数据库迁移，并在数据库没有用户时创建管理员。
之后修改 `ADMIN_PASSWORD` 不会覆盖数据库里已有账号的密码。

如果已有旧数据，先把备份恢复为命名卷内的
`/opt/data/crm/crm.db` 和 `/opt/data/crm/uploads/`，再启动新容器。

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

容器内部固定使用：

```text
CRM_DB=/opt/data/crm/crm.db
CRM_UPLOADS=/opt/data/crm/uploads
```

如只允许本机 nginx 访问容器，可把 `.env` 中
`CRM_BIND_ADDRESS` 改成 `127.0.0.1`。

## 6. 数据备份与恢复

容器内已有备份脚本，可生成 SQLite 一致快照和附件归档：

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

数据卷不会因替换镜像而删除。只有明确执行 `docker compose down -v` 才会删除数据卷。

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
```

HTTP 状态码为 `307` 且 Location 是 `/crm/` 时属于正常重定向。
