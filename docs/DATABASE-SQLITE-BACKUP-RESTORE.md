# SQLite 数据备份及恢复

SQLite 模式的数据由两部分组成：

```text
/opt/data/crm/crm.db     数据库
/opt/data/crm/uploads/   照片、产品下单表、报价附件
```

备份必须覆盖两者。不要在应用运行时直接 `cp crm.db`，写入中的数据库可能拿到不完整页；必须使用 SQLite 在线备份 API 或停服务后备份。

> 适用范围：CRM 使用默认 SQLite 模式时的日常备份、故障恢复和恢复演练。
>
> 一次有效备份必须同时包含 `crm.db` 和 `uploads/`，通过数据库完整性检查与归档校验，并且至少完成过一次隔离恢复演练。只有压缩文件存在，不代表可以恢复。

## 0. 数据范围与成功标准

备份内容包括：

- 28 张 CRM 表及其索引、触发器和最终迁移状态；
- `CRM_UPLOADS` 下的跟进照片、产品下单表、报价附件等物理文件；
- 最终迁移版本 `schema_migrations.version = 'v2_019'`；
- 每张表的标准字段 `create_time`、`update_time`、`is_delete`。

备份成功至少满足：

1. 本地备份成功：`backup.py --no-offsite` 退出码为 `0`；启用异机上传时完整成功也应为 `0`；
2. 快照 `PRAGMA integrity_check` 输出 `ok`；
3. 归档可以完整解压，且同时包含 `crm.db` 和 `uploads/`；
4. 归档的 SHA-256 已写入备份日志，并与同一时间点的文件记录一致；
5. 解包后的数据库仍存在最终迁移版本和完整标准字段；
6. 恢复演练中可以登录、查看业务数据并打开附件。

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

项目脚本会把归档 SHA-256 写入 `backup.py` 的标准输出和日志，不额外生成 `.sha256` 文件。请把日志中的摘要与归档大小一起登记；若执行成功但归档缺少数据库、附件或摘要，不要继续依赖这份备份。

### 1.1 定时任务

systemd 部署使用项目自带单元：

```bash
systemctl enable --now crm-backup.timer
systemctl list-timers crm-backup.timer
systemctl start crm-backup.service
journalctl -u crm-backup.service -n 30
```

默认每天 03:10，`Persistent=true`，关机错过会在开机后补跑。

安装或切换数据库后先手工执行一次：

```bash
systemctl start crm-backup.service
systemctl show crm-backup.service -p Result -p ExecMainStatus
journalctl -u crm-backup.service -n 50 --no-pager
```

应看到 `Result=success`、`ExecMainStatus=0`，并在备份目录看到完整归档。随后从 `journalctl` 记录归档路径、大小和 SHA-256；只有本地备份成功并通过完整性检查后，才启用定时器。

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
tar -czf "$dest/crm-$stamp.tar.gz" \
  -C "$dest" crm.db \
  -C /opt/data/crm uploads
sha256sum "$dest/crm-$stamp.tar.gz" > "$dest/crm-$stamp.sha256"
```

期望完整性检查输出 `ok`。随后删除单独快照：

```bash
rm "$dest/crm.db"
```

如果应用必须持续运行，优先使用项目脚本的在线备份 API；手工 `cp` 只能作为停服务后的最后手段。

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

继续检查迁移版本和审计结构：

```bash
sqlite3 /tmp/crm-restore/crm.db \
  "SELECT version, applied_at FROM schema_migrations WHERE version = 'v2_019';"

sqlite3 /tmp/crm-restore/crm.db <<'SQL'
SELECT m.name AS table_name,
       SUM(CASE WHEN p.name = 'create_time' THEN 1 ELSE 0 END) AS has_create_time,
       SUM(CASE WHEN p.name = 'update_time' THEN 1 ELSE 0 END) AS has_update_time,
       SUM(CASE WHEN p.name = 'is_delete' THEN 1 ELSE 0 END) AS has_is_delete
FROM sqlite_master AS m
JOIN pragma_table_info(m.name) AS p
WHERE m.type = 'table'
  AND m.name NOT LIKE 'sqlite_%'
GROUP BY m.name
ORDER BY m.name;
SQL
```

三列必须都为 `1`。同时核对关键表行数和附件数量，并在备份记录中写明检查结果：

```bash
sqlite3 /tmp/crm-restore/crm.db \
  "SELECT 'customers', COUNT(*) FROM customers
   UNION ALL SELECT 'deals', COUNT(*) FROM deals
   UNION ALL SELECT 'orders', COUNT(*) FROM orders
   UNION ALL SELECT 'products', COUNT(*) FROM products
   UNION ALL SELECT 'follow_ups', COUNT(*) FROM follow_ups;"

find /tmp/crm-restore/uploads -type f | wc -l
du -sh /tmp/crm-restore/uploads
```

## 4. 恢复步骤

恢复会覆盖正式数据，先停止应用并保留当前库：

```bash
systemctl stop crm-api
stamp=$(date +%Y%m%d-%H%M%S)
cp -a /opt/data/crm/crm.db "/opt/data/crm/crm.db.before-restore-$stamp"
mv /opt/data/crm/uploads "/opt/data/crm/uploads.before-restore-$stamp"
```

停服务后先做一次当前库的最终快照，确认回滚目标仍可用：

```bash
sqlite3 "/opt/data/crm/crm.db.before-restore-$stamp" "PRAGMA integrity_check;"
```

预期输出 `ok`。如果当前库已经损坏，也不要覆盖原文件；记录损坏状态并转入故障分析。

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

确认服务确实指向恢复后的 SQLite 文件，并检查目录权限：

```bash
systemctl show crm-api.service -p Environment
ls -l /opt/data/crm/crm.db
du -sh /opt/data/crm/uploads
journalctl -u crm-api.service -n 50 --no-pager
```

恢复完成不等于问题结束。将使用的备份文件、SHA-256、恢复前保护副本、`integrity_check` 结果、关键表行数和附件抽查结果写入故障记录，并立即生成一份新的全量备份。

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

## 6. 备份保留与演练

- 本地默认保留 14 天，至少保留最近 7 个完整日备份；
- 异地备份与本地副本分开保存，避免同时受主机磁盘或误删除影响；
- 至少每季度执行一次隔离恢复演练；
- 每次应用升级、数据库迁移和重要大批量导入前后，各做一次手工备份；
- 清理过期备份前先确认最近一份备份已完成校验和恢复演练。

如果发现归档中只有 `crm.db` 而没有 `uploads/`，应检查当时附件目录是否为空、是否挂载正确，并立刻重新执行一次完整备份。不要用该归档覆盖正式数据。
