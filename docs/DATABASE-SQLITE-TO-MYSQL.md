# SQLite 数据迁移到 MySQL

本文用于把现有 `crm.db` 切换到 MySQL 8.0。迁移工具只读取 SQLite，保留原主键、业务时间、软删除状态和密码哈希；`crm.db` 不会被修改，可作为回滚副本。

> 适用范围：单实例 CRM 从 SQLite 切换到 MySQL 8.0，或在专用 MySQL 库上做一次完整数据搬迁。
>
> 本文只迁移数据库记录。`CRM_UPLOADS` 下的照片、产品下单表和报价附件必须单独同步，两者都完成并通过验收后，迁移才算完成。

## 0. 迁移范围与完成标准

迁移工具复制代码定义的 29 张表，并保留原主键、业务时间、软删除状态和密码哈希。目标库不会建立数据库外键；客户、商机、订单、售后等引用关系由业务代码维护。

每一张表都必须具备：

- `create_time`：记录创建时间；
- `update_time`：记录最后更新时间；
- `is_delete`：`0` 表示有效，`1` 表示已软删除。

迁移完成必须同时满足以下条件：

1. 迁移工具最后输出 `migration OK: 29 tables / N rows`，且没有按表行数不一致；
2. 原管理员账号可以登录，客户、线索、商机、订单、售后数量与源库一致；
3. 照片、产品下单表和报价附件均可打开或下载；
4. `/health` 返回 `db_engine=mysql`，且响应中不含数据库密码；
5. 抽查新增跟进、看板统计和订单详情，确认读写与历史时间口径正常；
6. 原 SQLite 库和附件目录在验收结束前保持只读保留，不删除、不覆盖。

## 1. 迁移前准备

必须同时满足：

- MySQL 版本为 **8.0 及以上**（统计页面使用窗口函数）；
- 当前程序已启动过 SQLite，`schema_migrations` 中存在 `v2_019`；
- 已完成 SQLite 和 `uploads/` 的完整备份；
- 迁移期间停止写入 CRM。建议停应用后做最终迁移。

先按 [SQLite 数据备份及恢复](DATABASE-SQLITE-BACKUP-RESTORE.md) 做一份备份。

先在 SQLite 模式下备份，再停止应用和 SQLite 备份定时器，避免备份归档与最终迁移源不一致：

```bash
python3 /opt/data/crm/ops/backup.py --no-offsite
sudo systemctl stop crm-api
sudo systemctl disable --now crm-backup.timer
```

如果继续使用 Docker 中的 SQLite 模式，则先执行容器内备份，再停止 CRM 容器：

```bash
docker exec sunshine-crm python ops/backup.py --no-offsite
docker compose stop crm
```

迁移期间不要让页面、脚本、定时任务或其他进程继续写 `crm.db`。

检查源库已完成最终迁移，并且标准审计字段、软删除字段齐全：

```bash
sqlite3 "$CRM_DB" \
  "SELECT version, applied_at FROM schema_migrations WHERE version = 'v2_019';"

sqlite3 "$CRM_DB" <<'SQL'
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

`has_create_time`、`has_update_time`、`has_is_delete` 都必须为 `1`。任何一行出现 `0`，先用当前版本启动一次 SQLite，让 V2 迁移完成后再重试。

## 2. 创建 MySQL 数据库和账号

用管理员账号登录 MySQL 后执行。字符集必须使用 `utf8mb4`：

```sql
CREATE DATABASE sunshine_crm
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER 'crm'@'%' IDENTIFIED BY '替换为强密码';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP,
      REFERENCES, TRIGGER
  ON sunshine_crm.* TO 'crm'@'%';
FLUSH PRIVILEGES;
```

生产环境应把 `'crm'@'%'` 收窄为实际应用服务器地址，例如 `'crm'@'10.0.0.25'`。

目标库必须是一个独立数据库。不要复用其他系统的库，也不要给应用账号授予全实例权限。若迁移后需要做 `mysqldump` 备份，备份账号还应具备读取表结构和触发器的权限。

## 3. 配置迁移环境

在项目根目录设置环境变量。不要把真实密码写进 Git：

```bash
export CRM_DB=/opt/data/crm/crm.db
export CRM_DB_ENGINE=mysql
export CRM_MYSQL_HOST=127.0.0.1
export CRM_MYSQL_PORT=3306
export CRM_MYSQL_USER=crm
export CRM_MYSQL_PASSWORD='替换为密码'
export CRM_MYSQL_DATABASE=sunshine_crm
export CRM_MYSQL_CHARSET=utf8mb4
export CRM_MYSQL_SSL_DISABLED=false
```

本机或隔离内网测试连接时，可按实际驱动/证书情况使用
`CRM_MYSQL_SSL_DISABLED=true`；跨网连接应启用 TLS，并通过防火墙限制来源 IP。

systemd 部署可把同一组变量写入权限为 `600` 的 `/opt/data/crm/crm.env`。手工执行迁移时明确加载该文件，避免终端里的旧配置混入：

```bash
set -a
. /opt/data/crm/crm.env
set +a
```

先确认迁移工具实际连接的是预期实例和库，不执行任何写操作：

```bash
python ops/migrate_sqlite_to_mysql.py \
  --source "$CRM_DB" \
  --dry-run
```

输出第一行应显示只读的 SQLite 源文件，`target=` 应显示预期的 MySQL 主机和库名。如果目标地址或库名不符合预期，立即停止，先修正环境配置。

## 4. 预检和正式迁移

先只读预检，不写 MySQL：

```bash
python ops/migrate_sqlite_to_mysql.py \
  --source "$CRM_DB" \
  --dry-run
```

正式迁移要求 MySQL 中对应项目的业务表为空。工具会建表、复制全部 29 张表并按表比较源/目标行数：

```bash
python ops/migrate_sqlite_to_mysql.py --source "$CRM_DB"
```

正式执行前，把 dry-run 输出的表名与行数留存到变更记录中。迁移输出会逐表打印 `[copy] <table>: N rows`，最后再输出总计；逐表数字应与 dry-run 一致。

如果该 MySQL 库已有测试数据，并确认可以全部清空，才能加 `--replace`：

```bash
python ops/migrate_sqlite_to_mysql.py --source "$CRM_DB" --replace
```

`--replace` 会先删除目标业务表数据。不要把生产库当作试验目标，也不要在迁移期间继续写 SQLite。

工具在同一个事务内写入业务数据并在提交前做按表行数校验。失败时会回滚已写入业务数据，但已经创建的表结构会保留。处理失败原因后，可直接重试空库迁移；不要手工复制部分表来“补数据”。

## 5. 同步附件

数据库迁移不会移动 `uploads/` 中的照片、下单表和报价附件。使用可校验的目录同步：

```bash
rsync -a --checksum \
  /opt/data/crm/uploads/ \
  /opt/data/crm/uploads-mysql/
```

如果应用和附件仍放在同一台服务器，可以直接继续使用原 `/opt/data/crm/uploads/`，只需保证 `CRM_UPLOADS` 不变。若改为另一台机器，则先完整同步，再切换应用。

同步后比对文件数量和大小：

```bash
rsync -ani --checksum \
  /opt/data/crm/uploads/ \
  /opt/data/crm/uploads-mysql/

find /opt/data/crm/uploads -type f | wc -l
find /opt/data/crm/uploads-mysql -type f | wc -l
du -sh /opt/data/crm/uploads /opt/data/crm/uploads-mysql
```

`rsync -ani` 预检不应再输出待传输文件。文件数量必须一致；大小不一致时，至少抽查最近上传的照片和最近修改的报价附件。

## 6. 切换应用

确认迁移输出最后为 `migration OK` 后，修改运行配置：

```dotenv
CRM_DB_ENGINE=mysql
CRM_MYSQL_HOST=127.0.0.1
CRM_MYSQL_PORT=3306
CRM_MYSQL_USER=crm
CRM_MYSQL_PASSWORD=...
CRM_MYSQL_DATABASE=sunshine_crm
CRM_MYSQL_CHARSET=utf8mb4
CRM_MYSQL_SSL_DISABLED=false
```

重启应用：

```bash
systemctl restart crm-api
# 或
docker compose up -d
```

启动时会幂等创建/校准表结构与触发器，不会覆盖已有用户密码和业务数据。

如果迁移期间停用了应用，现在重新启动；不要同时启动旧 SQLite 进程和 MySQL 进程，避免两个实例都接受写入：

```bash
sudo systemctl enable --now crm-api
sudo systemctl --no-pager --full status crm-api
```

Docker 模式：

```bash
docker compose up -d crm
docker compose ps
docker inspect --format '{{.State.Health.Status}}' sunshine-crm
```

使用 systemd 且已切换到 MySQL 时，停用只支持 SQLite 的旧备份定时器，改按 MySQL 文档配置备份：

```bash
sudo systemctl disable --now crm-backup.timer
```

## 7. 验收

至少检查以下项目：

```bash
curl -fsS http://127.0.0.1:8010/health
```

预期：

```json
{
  "status": "ok",
  "db": "mysql://crm@127.0.0.1:3306/sunshine_crm",
  "db_engine": "mysql"
}
```

然后在页面中检查：

1. 原管理员账号可以登录；
2. 客户、线索、商机、订单、售后数量与原库一致；
3. 最近一条跟进、看板统计和统计图正常；
4. 任意产品下单表仍能下载；
5. 新建一条测试跟进，确认成功后再删除测试数据（删业务记录时按页面规则操作，避免 `DELETE` 绕过软删除）。

再做一份 MySQL 全量备份：

```bash
mysqldump --single-transaction --triggers \
  --default-character-set=utf8mb4 \
  -h 127.0.0.1 -P 3306 -u crm -p sunshine_crm \
  | gzip -1 > sunshine_crm-after-migration.sql.gz
```

用只读 SQL 核对迁移后的数据库结构：

```sql
-- 缺少任一标准字段的表，结果必须为空
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

-- MySQL 按项目规则不应存在外键，结果必须为空
SELECT TABLE_NAME, CONSTRAINT_NAME
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE();

-- 标准字段必须为 NOT NULL，结果必须为空
SELECT TABLE_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_NAME IN ('create_time', 'update_time', 'is_delete')
  AND IS_NULLABLE <> 'NO';

-- 应存在最终迁移版本
SELECT version, applied_at, note
FROM schema_migrations
WHERE version = 'v2_019';
```

第一段 SQL 直接列出标准字段数量不等于 `3` 的表；第二段列出所有外键；第三段列出可空的标准字段。三段查询的结果都必须为空，最后一段必须返回 `v2_019`。

最后核对健康检查、页面读写和附件访问。全部通过后，把 `/health` 输出、迁移表数/行数、备份文件名和验收时间写入变更记录。

## 8. 回滚

回滚期间继续停止写入。保留原 SQLite 文件和 `uploads/`，把配置改回：

```dotenv
CRM_DB_ENGINE=sqlite
CRM_DB=/opt/data/crm/crm.db
```

再重启应用。迁移工具没有删除或改写 SQLite，因此无需把 MySQL 数据反向导回即可恢复迁移前状态。

回滚顺序：

1. 停止 CRM 服务，确认没有进程继续连接 MySQL；
2. 把 `crm.env` 或 `.env` 中的 `CRM_DB_ENGINE` 改回 `sqlite`，并把 `CRM_DB`、`CRM_UPLOADS` 指向迁移前路径；
3. 重启服务并检查 `/health`、登录和最近一条业务记录；
4. 原 SQLite 备份和附件归档保留到业务确认稳定后再按保留策略清理。

回滚后不要重新启用旧的 SQLite 备份定时器，直到确认这次 MySQL 切换已被放弃。若仍准备再次迁移，先重新停写、重新备份并重新执行 dry-run，不能沿用上一次迁移后的 MySQL 行数作为基线。

## 9. 已知边界

- MySQL 结构按项目规则不建立外键；SQLite 中的外键约束在 MySQL 由业务层保证。
- MySQL 用生成列实现“未删除记录唯一”索引，包含线索手机号、产品编码、已确认报价和常用短语。
- 业务时间继续以字符串保存：UTC 时间带 `Z`，本地业务日期保持原格式，避免迁移后改变统计口径。
- 自动迁移不负责复制物理附件；必须单独同步 `CRM_UPLOADS`。
- 表结构由 `app/mysql_schema.py` 管理。以后新增字段时必须同时更新 SQLite 迁移和 MySQL 定稿结构。

## 10. 常见失败与处理

| 现象 | 含义 | 处理 |
|---|---|---|
| `源库尚未完成 v2_019 迁移` | SQLite 不是当前最终结构 | 用当前版本以 SQLite 模式启动一次，确认迁移完成后重新备份 |
| `源库缺少标准字段` | 数据库没有完成审计列补齐 | 不要手工补列后直接迁移；先让当前应用完成 V2 迁移 |
| `目标 MySQL 不是空库` | 防止误覆盖非空库 | 核对目标库；只有确认为可清空测试库时才使用 `--replace` |
| 某表写入失败 | 字段类型、字符集或数据内容不兼容 | 保留完整报错；修正目标环境后重试，不要跳过该表 |
| 行数校验失败 | 源表在迁移中发生变化或复制不完整 | 重新停写、重新备份并从头迁移 |
| 页面可用但附件 404 | 数据库迁移成功，附件未同步或 `CRM_UPLOADS` 路径错误 | 核对目录、文件数量和容器挂载路径 |
