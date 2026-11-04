# MySQL 数据备份及恢复

备份必须覆盖两部分：MySQL 数据库和 `CRM_UPLOADS` 附件目录。只备份数据库会导致照片、产品下单表和报价附件丢失。

以下示例使用：

```text
数据库：sunshine_crm
账号：crm
主机：127.0.0.1:3306
附件：/opt/data/crm/uploads
备份目录：/opt/data/crm/backups
```

## 1. 手工全量备份

创建当天目录并生成一致性快照。`--single-transaction` 适用于 InnoDB，不锁全表：

```bash
stamp=$(date +%Y%m%d-%H%M%S)
day=$(date +%F)
dest="/opt/data/crm/backups/$day"
mkdir -p "$dest"

mysqldump \
  --single-transaction \
  --triggers \
  --default-character-set=utf8mb4 \
  --set-gtid-purged=OFF \
  -h 127.0.0.1 -P 3306 -u crm -p \
  sunshine_crm \
  | gzip -1 > "$dest/mysql-$stamp.sql.gz"

tar -C /opt/data/crm -czf "$dest/uploads-$stamp.tar.gz" uploads
sha256sum "$dest/mysql-$stamp.sql.gz" \
          "$dest/uploads-$stamp.tar.gz" \
  > "$dest/SHA256SUMS-$stamp"
```

建议通过 MySQL 配置文件或 `~/.my.cnf` 提供密码，避免密码出现在 shell 历史和进程列表：

```ini
[client]
host=127.0.0.1
port=3306
user=crm
password=替换为密码
default-character-set=utf8mb4
```

文件权限设为 `600`。使用 `mysql` 组只允许备份账号读取。

## 2. 校验备份

检查压缩包、校验和和 SQL 尾部：

```bash
gzip -t "$dest/mysql-$stamp.sql.gz"
tar -tzf "$dest/uploads-$stamp.tar.gz" >/dev/null
cd "$dest" && sha256sum -c "SHA256SUMS-$stamp"
gzip -dc "$dest/mysql-$stamp.sql.gz" | tail -n 20
```

至少每月在独立测试库执行一次恢复演练，不能只看文件是否存在。

## 3. 定时备份

Ubuntu 可添加 `/usr/local/sbin/crm-mysql-backup.sh`，保留 14 天，并通过 cron 每天 03:20 执行：

```bash
#!/usr/bin/env bash
set -euo pipefail

keep_days=14
stamp=$(date +%Y%m%d-%H%M%S)
day=$(date +%F)
root=/opt/data/crm
dest="$root/backups/$day"
mkdir -p "$dest"

mysqldump --single-transaction --triggers \
  --default-character-set=utf8mb4 --set-gtid-purged=OFF \
  sunshine_crm | gzip -1 > "$dest/mysql-$stamp.sql.gz"
tar -C "$root" -czf "$dest/uploads-$stamp.tar.gz" uploads
sha256sum "$dest/mysql-$stamp.sql.gz" "$dest/uploads-$stamp.tar.gz" \
  > "$dest/SHA256SUMS-$stamp"

find "$root/backups" -mindepth 1 -maxdepth 1 -type d \
  -mtime +"$keep_days" -exec rm -rf -- {} +
```

安装后执行：

```bash
sudo install -m 700 crm-mysql-backup.sh /usr/local/sbin/crm-mysql-backup.sh
sudo /usr/local/sbin/crm-mysql-backup.sh
```

异地备份建议把 `.sql.gz`、附件包和校验文件同步到另一台机器，不能只保留同盘副本。

## 4. 恢复前保护当前数据

恢复会覆盖目标库。先停应用，禁止新写入，并对当前库再做一次备份：

```bash
sudo systemctl stop crm-api
stamp=$(date +%Y%m%d-%H%M%S)
mysqldump --single-transaction --triggers \
  --default-character-set=utf8mb4 --set-gtid-purged=OFF \
  sunshine_crm | gzip -1 > "/opt/data/crm/mysql-before-restore-$stamp.sql.gz"
```

同时备份当前附件目录：

```bash
sudo mv /opt/data/crm/uploads /opt/data/crm/uploads-before-restore-$stamp
```

## 5. 恢复数据库

优先恢复到新库 `sunshine_crm_restore`，验证无误后再切换应用：

```sql
CREATE DATABASE sunshine_crm_restore
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

导入：

```bash
gzip -dc /opt/data/crm/backups/2026-11-04/mysql-20261104-032000.sql.gz \
  | mysql -h 127.0.0.1 -P 3306 -u crm sunshine_crm_restore
```

检查关键表行数和审计字段：

```sql
SELECT COUNT(*) FROM customers;
SELECT COUNT(*) FROM deals;
SELECT COUNT(*) FROM orders;
SELECT COUNT(*) FROM products;
SELECT COUNT(*) FROM follow_ups;
SELECT version, applied_at, note FROM schema_migrations ORDER BY applied_at;
SELECT COUNT(*) FROM customers WHERE create_time = '' OR update_time = '';
```

最后一项应为 `0`。如不为 0，先查清是否为历史数据，再决定是否修复；不要把空审计字段当作新表结构的正常结果。

## 6. 恢复附件

选择备份中的附件目录解包到新位置：

```bash
mkdir -p /opt/data/crm/restore
tar -xzf /opt/data/crm/backups/2026-11-04/uploads-20261104-032000.tar.gz \
  -C /opt/data/crm/restore
sudo chown -R crm:crm /opt/data/crm/restore/uploads
```

验证几张附件能打开后，再替换正式目录：

```bash
sudo rsync -a --delete \
  /opt/data/crm/restore/uploads/ \
  /opt/data/crm/uploads/
```

`--delete` 前必须确认恢复目录完整，且恢复前旧目录已经另存。

## 7. 切换并验收

先在 `CRM_MYSQL_DATABASE` 指向恢复库时启动应用，确认登录、客户列表、订单、统计和附件下载都正常，再把数据库名切回 `sunshine_crm` 或做受控改名。

```bash
sudo systemctl start crm-api
curl -fsS http://127.0.0.1:8010/health
```

恢复后至少抽查：

1. 管理员能登录；
2. 客户/商机/订单/售后数量和备份前登记数量一致；
3. 今日待跟进与本月成交口径正常；
4. 产品 Excel 下单表可下载；
5. 随便打开一张跟进照片。

## 8. Docker Compose 场景

内置 MySQL 的数据在命名卷 `sunshine-crm-mysql-data`。备份可从宿主机执行：

```bash
docker compose exec -T mysql sh -c \
  'exec mysqldump --single-transaction --triggers \
   --default-character-set=utf8mb4 --set-gtid-purged=OFF \
   -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  | gzip -1 > mysql-backup.sql.gz

docker run --rm \
  -v sunshine-crm-data:/data:ro \
  -v "$PWD":/backup \
  alpine tar -C /data -czf /backup/uploads-backup.tar.gz uploads
```

恢复 MySQL 时先停止 CRM，再导入：

```bash
docker compose stop crm
gzip -dc mysql-backup.sql.gz | \
  docker compose exec -T mysql sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
docker compose start crm
```

不要在容器运行中复制 `/var/lib/mysql`。逻辑备份用 `mysqldump`，物理卷只可作为整机级快照。
