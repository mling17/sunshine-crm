# SQLite 数据迁移到 MySQL

本文用于把现有 `crm.db` 切换到 MySQL 8.0。迁移工具只读取 SQLite，保留原主键、业务时间、软删除状态和密码哈希；`crm.db` 不会被修改，可作为回滚副本。

## 1. 迁移前准备

必须同时满足：

- MySQL 版本为 **8.0 及以上**（统计页面使用窗口函数）；
- 当前程序已启动过 SQLite，`schema_migrations` 中存在 `v2_018`；
- 已完成 SQLite 和 `uploads/` 的完整备份；
- 迁移期间停止写入 CRM。建议停应用后做最终迁移。

先按 [SQLite 数据备份及恢复](DATABASE-SQLITE-BACKUP-RESTORE.md) 做一份备份。

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

如果该 MySQL 库已有测试数据，并确认可以全部清空，才能加 `--replace`：

```bash
python ops/migrate_sqlite_to_mysql.py --source "$CRM_DB" --replace
```

`--replace` 会先删除目标业务表数据。不要把生产库当作试验目标，也不要在迁移期间继续写 SQLite。

## 5. 同步附件

数据库迁移不会移动 `uploads/` 中的照片、下单表和报价附件。使用可校验的目录同步：

```bash
rsync -a --checksum \
  /opt/data/crm/uploads/ \
  /opt/data/crm/uploads-mysql/
```

如果应用和附件仍放在同一台服务器，可以直接继续使用原 `/opt/data/crm/uploads/`，只需保证 `CRM_UPLOADS` 不变。若改为另一台机器，则先完整同步，再切换应用。

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

## 8. 回滚

回滚期间继续停止写入。保留原 SQLite 文件和 `uploads/`，把配置改回：

```dotenv
CRM_DB_ENGINE=sqlite
CRM_DB=/opt/data/crm/crm.db
```

再重启应用。迁移工具没有删除或改写 SQLite，因此无需把 MySQL 数据反向导回即可恢复迁移前状态。

## 9. 已知边界

- MySQL 结构按项目规则不建立外键；SQLite 中的外键约束在 MySQL 由业务层保证。
- MySQL 用生成列实现“未删除记录唯一”索引，包含线索手机号、产品编码、已确认报价和常用短语。
- 业务时间继续以字符串保存：UTC 时间带 `Z`，本地业务日期保持原格式，避免迁移后改变统计口径。
- 自动迁移不负责复制物理附件；必须单独同步 `CRM_UPLOADS`。
- 表结构由 `app/mysql_schema.py` 管理。以后新增字段时必须同时更新 SQLite 迁移和 MySQL 定稿结构。
