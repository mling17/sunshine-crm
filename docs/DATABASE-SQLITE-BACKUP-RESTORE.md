# SQLite 数据备份及恢复

SQLite 模式的数据由两部分组成：

```text
/opt/data/crm/crm.db     数据库
/opt/data/crm/uploads/   照片、产品下单表、报价附件
```

备份必须覆盖两者。不要在应用运行时直接 `cp crm.db`，写入中的数据库可能拿到不完整页；必须使用 SQLite 在线备份 API 或停服务后备份。

## 1. 使用项目备份脚本

项目自带 `ops/backup.py`，会：

- 使用 SQLite `.backup` API 生成事务一致快照；
- 对快照执行 `PRAGMA integrity_check`；
- 将数据库与 `uploads/` 打包；
- 生成 SHA-256；
- 默认保留本地 14 天，可选上传 MinIO。

手工执行：

```bash
cd /opt/data/crm
python3 ops/backup.py --no-offsite
```

输出目录：

```text
/opt/data/crm/backups/YYYY-MM-DD/crm-YYYYMMDD-HHMMSS.tar.gz
```

### 1.1 定时任务

systemd 部署使用项目自带单元：

```bash
systemctl enable --now crm-backup.timer
systemctl list-timers crm-backup.timer
systemctl start crm-backup.service
journalctl -u crm-backup.service -n 30
```

默认每天 03:10，`Persistent=true`，关机错过会在开机后补跑。

### 1.2 异地备份

在 `ops/backup.env` 配置 MinIO，权限设为 `600`：

```dotenv
CRM_MINIO_ENDPOINT=备份机地址:9000
CRM_MINIO_BUCKET=crm-backups
CRM_MINIO_ACCESS=...
CRM_MINIO_SECRET=...
```

再执行不带 `--no-offsite` 的备份：

```bash
python3 ops/backup.py
```

退出码含义：

- `0`：完整成功；
- `1`：本地快照或完整性校验失败，必须告警；
- `2`：本地成功、异机上传失败，本地备份仍可用。

## 2. 手工在线备份

没有项目脚本时，可使用 SQLite CLI 的 `.backup`：

```bash
stamp=$(date +%Y%m%d-%H%M%S)
dest=/opt/data/crm/backups/manual/$(date +%F)
mkdir -p "$dest"
sqlite3 /opt/data/crm/crm.db ".timeout 10000" ".backup '$dest/crm.db'"
sqlite3 "$dest/crm.db" "PRAGMA integrity_check;"
tar -C /opt/data/crm -czf "$dest/crm-$stamp.tar.gz" crm.db uploads
sha256sum "$dest/crm-$stamp.tar.gz" > "$dest/crm-$stamp.sha256"
```

期望完整性检查输出 `ok`。随后删除单独快照：

```bash
rm "$dest/crm.db"
```

## 3. 校验备份

```bash
gzip -t /path/to/crm-YYYYMMDD-HHMMSS.tar.gz
tar -tzf /path/to/crm-YYYYMMDD-HHMMSS.tar.gz | head
sha256sum -c /path/to/crm-YYYYMMDD-HHMMSS.sha256
```

恢复演练建议每季度一次。先在 `/tmp/crm-restore` 解包，再对文件做检查：

```bash
mkdir -p /tmp/crm-restore
tar -xzf /path/to/crm-YYYYMMDD-HHMMSS.tar.gz -C /tmp/crm-restore
sqlite3 /tmp/crm-restore/crm.db "PRAGMA integrity_check;"
ls -la /tmp/crm-restore/uploads
```

## 4. 恢复步骤

恢复会覆盖正式数据，先停止应用并保留当前库：

```bash
systemctl stop crm-api
stamp=$(date +%Y%m%d-%H%M%S)
cp -a /opt/data/crm/crm.db "/opt/data/crm/crm.db.before-restore-$stamp"
mv /opt/data/crm/uploads "/opt/data/crm/uploads.before-restore-$stamp"
```

解包备份：

```bash
mkdir -p /tmp/crm-restore
tar -xzf /path/to/crm-YYYYMMDD-HHMMSS.tar.gz -C /tmp/crm-restore
sqlite3 /tmp/crm-restore/crm.db "PRAGMA integrity_check;"
```

检查结果为 `ok` 后安装：

```bash
install -o crm -g crm -m 600 /tmp/crm-restore/crm.db /opt/data/crm/crm.db
rsync -a /tmp/crm-restore/uploads/ /opt/data/crm/uploads/
chown -R crm:crm /opt/data/crm/uploads
```

启动并验收：

```bash
systemctl start crm-api
curl -fsS http://127.0.0.1:8010/health
```

验证管理员登录、客户/商机/订单数量、统计页面、一张跟进照片和产品下单表。

## 5. Docker Compose 场景

SQLite 数据库和附件都在命名卷 `sunshine-crm-data`。在线生成备份：

```bash
docker exec sunshine-crm python ops/backup.py --no-offsite
docker cp sunshine-crm:/opt/data/crm/backups ./backups
```

恢复前停止容器，并导出当前数据：

```bash
docker compose stop crm
docker cp sunshine-crm:/opt/data/crm ./crm-data-before-restore
```

将备份中的 `crm.db` 和 `uploads/` 解包到宿主机目录，再复制回已停止容器的
`/opt/data/crm/`。不要在 SQLite 服务运行中覆盖数据库文件：

```bash
docker cp ./restore/crm.db sunshine-crm:/opt/data/crm/crm.db
docker cp ./restore/uploads/. sunshine-crm:/opt/data/crm/uploads/
docker compose start crm
```

只有确认不再需要卷内数据后，才允许执行 `docker compose down -v`；该命令会删除命名卷。
