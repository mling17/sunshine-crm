# 外部 API 与客户不变量生产更新包

本更新包把生产数据库从 `v2_022` 升到 `v2_025`，并启用外部线索、外部跟进和手机号批量校验。所有脚本和模板均在 `ops/sql/`；真实 Token **只能**在受控终端中临时替换模板占位符，不得写入仓库、日志或工单。

## 1. 适用范围与前置条件

- 应用代码已包含外部 API、客户来源不变量和幂等写接口。
- 数据库当前为 `v2_022`，`schema_migrations` 中不存在 `v2_023`、`v2_024`、`v2_025`。
- 已确认目标数据库类型，并准备同一版本的独立备份。
- 已安排维护窗口；外部写接口在验证完成前不得开放给第三方。

先运行只读审计：

```bash
# SQLite
sqlite3 /path/to/crm.db < ops/sql/preflight_external_rollout.sqlite.sql

# MySQL 8
mysql --default-character-set=utf8mb4 crm < ops/sql/preflight_external_rollout.mysql.sql
```

审计输出四类：

- `customer_without_source_lead`：无来源线索客户。
- `customer_without_active_opportunity`：无活跃商机客户。
- `source_phone_mismatch`：客户与来源线索手机号不一致。
- `multiple_source_leads`：同一客户有多条来源线索。

任一 `affected_count > 0` 都必须人工复核并记录处理结论。脚本不修改数据，也不会自动伪造来源线索。

## 2. 备份与更新

在确认审计结果后，备份数据库；如本次窗口还会变更附件目录，也应同时保留上传目录快照。

```bash
# SQLite 示例
cp /path/to/crm.db /path/to/crm.db.before-v2_025

# MySQL 示例
mysqldump --single-transaction --routines --triggers crm > crm.before-v2_025.sql
```

执行合并更新脚本。以下脚本是**一次性**的 `v2_022 -> v2_025` 更新，不得在已升级库重复执行：

```bash
# SQLite
sqlite3 /path/to/crm.db < ops/sql/v2_022_to_v2_025.sqlite.sql

# MySQL 8
mysql --default-character-set=utf8mb4 crm < ops/sql/v2_022_to_v2_025.mysql.sql
```

脚本失败时立即停止，不要继续启动应用或开放外部入口。先确认事务是否提交；无法确认时恢复备份。

## 3. 应用启动与一次性 Token 初始化

更新脚本完成后启动应用，由启动迁移确认最终结构已收敛，并检查：

```bash
curl -fsS http://127.0.0.1:8000/health
```

`GET /health` 必须返回成功，且数据库引擎为本次目标引擎。应用启动迁移应当识别 `v2_025`，不得再产生结构变更。

Token 初始化是一次性人工操作。选择 `ops/sql/api_token_init.sqlite.template.sql` 或 `api_token_init.mysql.template.sql`，在受控环境替换：

- `{{TOKEN_NAME}}`
- `{{TOKEN_VALUE}}`
- `{{BOUND_USERNAME}}`
- `{{EXPIRES_AT_SQL_LITERAL_OR_NULL}}`

Token 绑定用户必须存在且 `is_active = 1`。模板只保存占位符；真实 Token 不得提交。执行一次后保存审计记录（不保存 Token 明文）。

## 4. 上线后验证

执行只读 `postcheck_external_rollout`，所有行必须为 `PASS`：

```bash
# SQLite
sqlite3 /path/to/crm.db < ops/sql/postcheck_external_rollout.sqlite.sql

# MySQL 8
mysql --default-character-set=utf8mb4 crm < ops/sql/postcheck_external_rollout.mysql.sql
```

Postcheck 覆盖：

- `v2_023`、`v2_024`、`v2_025` 版本记录。
- `users.is_active`、`leads.created_by`、`follow_ups.created_by`。
- `api_tokens` 与 `api_idempotency_records` 字段、标准审计列和无外键约束。
- `customer_source.api` 字典启用。
- 至少一个未过期、未撤销、绑定启用用户的 Token。
- 客户来源线索、活跃商机、手机号一致性和多来源审计。

任何 `FAIL` 都不得开放第三方流量。修正后重新运行 postcheck；结构或数据问题无法就地确认时，执行回滚。

再使用 `docs/EXTERNAL-API.md` 做一次外部接口冒烟：新增线索、添加跟进、批量手机号校验各一次。第三方的正式开关只应在应用健康检查、postcheck 和冒烟均成功后打开。

## 5. 回滚与恢复边界

本更新包不提供反向删除字段的 down migration。新增字段和表对旧应用通常是可忽略的，但一旦出现结构、数据或启动失败，恢复边界是：

1. 停止外部入口和写流量。
2. 回滚应用代码与静态资源到发布前版本。
3. 恢复更新前的数据库备份；必要时同时恢复上传目录快照。
4. 重新执行 `GET /health` 和旧版本冒烟。
5. Token 随旧库恢复而失效；不得从日志或工单恢复明文，需从受控凭据保管处重新初始化。

不要在未备份的情况下执行 `DROP TABLE`、删除新字段或手工修复客户来源。历史异常客户以审计报告和人工记录为准。
