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

> 适用范围：CRM 已切换到 MySQL 8.0 后的日常备份、故障恢复和恢复演练。
>
> 一次有效备份必须同时满足：数据库导出成功、附件归档成功、校验和生成成功、至少能在隔离环境恢复并读取业务数据。只看 `.sql.gz` 文件存在不算备份成功。

## 0. 备份范围内与恢复目标

需要覆盖的数据：

- MySQL 中的 29 张 CRM 表，包括 `schema_migrations` 和业务配置；
- `CRM_UPLOADS` 下的跟进照片、产品下单表、报价附件等文件；
- 当前备份应记录生成时间、数据库版本、最终迁移版本和校验和。

恢复完成后应达到：

1. MySQL 可以正常启动并完成导入；
2. 原管理员账号可以登录；
3. 关键业务表行数与备份基线一致；
4. 每张表都有 `create_time`、`update_time`、`is_delete`；
5. 数据库中没有外键，引用关系由业务层维护；
6. 至少一张照片、一个产品下单表和一个报价附件可以打开；
7. `/health` 返回 `db_engine=mysql`，应用日志没有启动或查询错误。

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

记录当次版本和关键表行数，便于恢复后对照：

```bash
mysql -h 127.0.0.1 -P 3306 -u crm -p sunshine_crm <<'SQL' \
  > "$dest/table-counts-$stamp.txt"
SELECT version, applied_at, note
FROM schema_migrations
ORDER BY applied_at;

SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL SELECT 'deals', COUNT(*) FROM deals
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'follow_ups', COUNT(*) FROM follow_ups
UNION ALL SELECT 'aftersales', COUNT(*) FROM aftersales;
SQL

printf 'backup_time=%s\ndatabase=sunshine_crm\n' "$stamp" \
  > "$dest/MANIFEST-$stamp.txt"
ls -lh "$dest"
```

生产记录中至少保留备份时间、文件大小、SHA-256、最终迁移版本和关键表行数。不要只记录“已备份”。

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

恢复演练后确认最终迁移版本存在：

```sql
SELECT version, applied_at, note
FROM schema_migrations
WHERE version = 'v2_018';
```

同时检查所有表都有标准字段，并且没有外键：

```sql
-- 列出标准字段不足 3 个的表；结果必须为空
SELECT t.TABLE_NAME,
       COUNT(DISTINCT c.COLUMN_NAME) AS standard_column_count
FROM information_schema.TABLES AS t
LEFT JOIN information_schema.COLUMNS AS c
  ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
 AND c.TABLE_NAME = t.TABLE_NAME
 AND c.COLUMN_NAME IN ('create_time', 'update_time', 'is_delete')
WHERE t.TABLE_SCHEMA = DATABASE()
  AND t.TABLE_TYPE = 'BASE TABLE'
GROUP BY t.TABLE_NAME
HAVING COUNT(DISTINCT c.COLUMN_NAME) <> 3;

-- 结果必须为空
SELECT TABLE_NAME, CONSTRAINT_NAME
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE();
```

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

备份账号应通过 `/etc/mysql/crm-backup.cnf` 或备份用户自己的 `~/.my.cnf` 提供连接信息，文件权限设为 `600`。cron 默认不会加载交互式 shell 的配置；安装后必须手工运行一次并检查退出码、文件大小和校验和，再等待下一次定时执行。

建议在监控中至少检查：

- 最近一次备份是否在 24 小时内生成；
- `.sql.gz`、附件归档和校验文件是否同时存在；
- 最近一次恢复演练是否在 30 天内完成；
- 磁盘剩余空间是否能容纳至少两份完整备份。

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

恢复前还要从当前库导出表行数，作为恢复后的基线：

```bash
mysql -h 127.0.0.1 -P 3306 -u crm -p sunshine_crm <<'SQL'
SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL SELECT 'deals', COUNT(*) FROM deals
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'follow_ups', COUNT(*) FROM follow_ups
UNION ALL SELECT 'aftersales', COUNT(*) FROM aftersales;
SQL
```

## 5. 恢复数据库

优先恢复到新库 `sunshine_crm_restore`，验证无误后再切换应用：

```sql
CREATE DATABASE sunshine_crm_restore
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP,
      REFERENCES, TRIGGER
  ON sunshine_crm_restore.* TO 'crm'@'<应用主机>';
FLUSH PRIVILEGES;
```

`<应用主机>` 必须与迁移文档中实际创建的应用账号主机部分保持一致；如果账号是 `'crm'@'%'`，这里也使用 `%`。

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

继续检查全部业务表，而不仅检查 `customers`：

```sql
-- 结果必须为空
SELECT t.TABLE_NAME,
       COUNT(DISTINCT c.COLUMN_NAME) AS standard_column_count
FROM information_schema.TABLES AS t
LEFT JOIN information_schema.COLUMNS AS c
  ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
 AND c.TABLE_NAME = t.TABLE_NAME
 AND c.COLUMN_NAME IN ('create_time', 'update_time', 'is_delete')
WHERE t.TABLE_SCHEMA = DATABASE()
  AND t.TABLE_TYPE = 'BASE TABLE'
GROUP BY t.TABLE_NAME
HAVING COUNT(DISTINCT c.COLUMN_NAME) <> 3;

-- 标准字段必须为 NOT NULL，结果必须为空
SELECT TABLE_NAME, COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_NAME IN ('create_time', 'update_time', 'is_delete')
  AND IS_NULLABLE <> 'NO';
```

两段查询的结果都必须为空。恢复库中出现的任何外键也应视为结构异常；项目按规则通过业务层维护引用一致性。

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

附件恢复还要核对文件数量和目录大小：

```bash
find /opt/data/crm/restore/uploads -type f | wc -l
find /opt/data/crm/uploads-before-restore-$stamp -type f | wc -l
du -sh /opt/data/crm/restore/uploads
du -sh /opt/data/crm/uploads-before-restore-$stamp
```

数量或大小差异较大时，先保留恢复目录并重新检查归档，不要继续覆盖正式目录。

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

全部检查通过后，记录以下结果：

- 使用的备份文件、SHA-256 和生成时间；
- 导入耗时、应用重启时间；
- 关键业务表行数；
- `schema_migrations` 最后版本；
- 照片、产品下单表、报价附件抽查结果；
- 固化为一次恢复演练记录，保留到下一次演练完成。

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

## 9. 无法恢复时的止损

如果备份无法通过压缩检查、SQL 尾部不完整或 `SHA256SUMS` 校验失败：

1. 不导入正式库，保留失败文件及原始报错；
2. 回退到上一份已完成恢复演练的备份；
3. 优先恢复到新库验证，不要直接覆盖唯一可用的正式库；
4. 同时确认附件归档与数据库备份时间对应，避免数据库和附件来自不同时间点；
5. 恢复完成后重新生成一份全量备份，确认新的恢复链可用。
