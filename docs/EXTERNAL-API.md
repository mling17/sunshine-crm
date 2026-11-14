# 外部 API

外部 API 供服务器之间调用，使用数据库中长期保存的完整 Bearer Token。当前版本提供新增线索、按手机号新增跟进和批量手机号校验。

生产更新、审计、Token 初始化和回滚边界见 `ops/ROLLOUT-EXTERNAL-API.md`。第三方集成只需阅读本文；运维执行以该上线手册为准。

## 认证

请求头：

```http
Authorization: Bearer <token>
```

- 只接受该请求头，不接受 Cookie、查询参数或其他自定义请求头。
- 不限制来源 IP。
- Token 必须未软删除、未撤销，且满足有效期；绑定用户必须存在并处于启用状态。
- 缺失、格式错误、未知、过期、撤销和绑定用户停用统一返回 401：

```json
{"detail": "认证失败", "code": "unauthorized"}
```

Token 明文保存在 `api_tokens.token`，数据库读取权限等同于凭据读取权限。风险和取舍见 `docs/adr/0002-plaintext-api-token-no-ip-allowlist.md`。

## 幂等重试

新增线索和新增跟进支持可选的请求头：

```http
Idempotency-Key: <client-generated-key>
```

- Key 由客户端生成，最长 255 个字符；空白 Key 返回 400 `invalid_idempotency_key`。
- 幂等身份由 Token、端点和 Key 共同确定；不同 Token 或不同端点可以复用同一个 Key。
- 相同 Key 和相同业务请求返回首次的原始状态码与 JSON，不重复创建线索、跟进、附件行或文件。
- 相同身份但请求内容不同返回 409 `idempotency_conflict`。
- 跟进请求的附件文件名、类型、大小和内容摘要参与请求比较。
- 幂等记录保留 30 天；过期记录会在后续幂等请求前清理，清理后 Key 可以重新使用。
- 手机号批量校验是只读接口，不需要 `Idempotency-Key`。

## 新增线索

`POST /api/external/v1/leads`

成功返回 201 和创建后的线索。服务端固定写入：

- `source = "api"`
- `status = "new"`
- `created_by = Token 绑定用户 ID`

手机号会去除空格、短横线、括号和 `+86` / `86` 前缀，并校验为 11 位中国大陆手机号。未填 `lead_type` 时默认 `other`；其他未填字段保持 `null`，标签默认为空数组。

### 请求字段

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `phone` | 是 | 中国大陆手机号，允许常见分隔符和 `+86` / `86` 前缀 |
| `name` | 否 | 最长 64 |
| `wechat` | 否 | 最长 64 |
| `lead_type` | 否 | `personal` / `company` / `other`，默认 `other` |
| `company_name` | 否 | 最长 100 |
| `source_other` | 否 | 最长 100 |
| `location` | 否 | 最长 200 |
| `note` | 否 | 最长 500 |
| `intent_level` | 否 | 使用现有意向字典 key |
| `owner` | 否 | 最长 32 |
| `tags` | 否 | 字符串数组，最多 20 个；去重并保留首次顺序 |

未知字段和服务端字段（例如 `id`、`status`、`source`、`created_by`、时间戳）会整单拒绝。

### 示例

```bash
curl -X POST https://crm.example.com/api/external/v1/leads \
  -H 'Authorization: Bearer <token>' \
  -H 'Idempotency-Key: lead-20261114-001' \
  -H 'Content-Type: application/json' \
  -d '{
    "phone": "+86 (138) 0013-8000",
    "name": "王经理",
    "lead_type": "company",
    "company_name": "海景装饰",
    "tags": ["重点", "展会"]
  }'
```

## 新增跟进

`POST /api/external/v1/follow-ups`

请求类型为 `multipart/form-data`，使用同一套 Bearer Token。服务端先按规范手机号查找有效客户，再查找有效线索：

- 客户优先；客户命中时不检查同号线索。
- 无客户时使用未被删除的线索。
- 同一目标表存在多条匹配返回 409 `ambiguous_phone`，不任意选择。
- 唯一线索已转化或已失效时返回 409 `lead_closed`。
- 无任何匹配时返回 404 `phone_not_found`，`detail` 为 `<规范手机号>手机号不存在`。

### 请求字段

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `phone` | 是 | 按大陆手机号规则规范化后匹配 |
| `content` | 是 | 去首尾空格后 1～2000 字 |
| `method` | 否 | 与页面跟进方式使用相同字典值 |
| `next_date` | 否 | `YYYY-MM-DD` |
| `attachments` | 否 | 重复 multipart 字段；最多 10 个，每个不超过 20MB |

附件类型沿用页面白名单：图片、PDF、Excel、Word、CSV、CAD、ZIP 和 TXT；HTML、SVG、JS 等类型拒绝。所有字段和附件先完成校验，随后才写入文件、跟进和附件记录。数据库写入失败会回滚跟进、业务状态和附件行，并删除该请求已经写入的文件。

### 响应与状态变化

- 成功返回 201，包含规范化后的对象类型、目标 ID、跟进内容、附件元数据和 `created_by`。
- 客户命中创建客户跟进。
- 线索命中创建线索跟进；`new` 线索在同一事务内进入 `following`。
- 外部跟进写入 Token 绑定用户 ID，页面 Cookie 跟进写入当前登录用户 ID；历史跟进保持空值。
- 支持 `Idempotency-Key`；附件摘要参与请求比较，重试不会重复保存文件。

```bash
curl -X POST https://crm.example.com/api/external/v1/follow-ups \
  -H 'Authorization: Bearer <token>' \
  -H 'Idempotency-Key: follow-up-20261114-001' \
  -F 'phone=+86 138-0013-8000' \
  -F 'content=已电话确认安装时间' \
  -F 'method=phone' \
  -F 'next_date=2026-12-01' \
  -F 'attachments=@报价单.pdf' \
  -F 'attachments=@现场照片.png'
```

## 批量校验线索手机号

`POST /api/external/v1/leads/phone-check`

在推送前检查一批规范手机号是否已被未删除线索占用。请求使用与新增线索相同的 Bearer Token，不接受 Cookie。

```json
{
  "phones": [
    "+86 (138) 0013-8000",
    "139 0013 9000",
    "13700137000"
  ]
}
```

规则：

- `phones` 必须包含 1 到 500 个值。
- 每个值按新增线索的手机号规则规范化；`null`、数字、对象等非字符串项也按非法手机号处理。
- 规范化后的重复值会删除，保留第一次出现的顺序。
- 只查询未删除线索；已转化和已失效但未删除的线索仍算存在。
- 不返回客户信息、线索状态、名称、ID 或其他敏感字段。

成功返回 200：

```json
{
  "items": [
    {"phone": "13800138000", "exists": true},
    {"phone": "13900139000", "exists": false},
    {"phone": "13700137000", "exists": false}
  ]
}
```

任一值非法（包括非字符串项）时整批返回 400，不查询或返回部分结果。`invalid_positions` 使用从 0 开始的输入数组下标：

```json
{
  "detail": "手机号格式不正确",
  "code": "invalid_phone",
  "invalid_positions": [1, 3]
}
```

## 错误

HTTP 状态约定：

| HTTP | 场景 |
| --- | --- |
| 200 | 手机号批量校验成功 |
| 201 | 新增线索或新增跟进成功 |
| 400 | Token 之外的请求参数、手机号、日期、正文、附件或幂等 Key 不合法 |
| 401 | Bearer Token 或绑定用户无效 |
| 404 | 按手机号新增跟进时没有匹配对象 |
| 409 | 重复联系方式、目标歧义、线索终态、幂等 Key 冲突或并发占用 |
| 500 | 服务端事务或幂等状态写入失败；响应不包含 Token 或数据库细节 |

稳定业务错误码：

| HTTP | code | 含义 |
| --- | --- | --- |
| 401 | `unauthorized` | Token 或绑定用户无效 |
| 400 | `invalid_phone` | 新增线索手机号非法，或校验批次包含非法值；批次错误带 `invalid_positions` |
| 400 | `invalid_idempotency_key` | Idempotency-Key 为空或超长 |
| 400 | `validation_failed` | 字段、长度或未知字段校验失败 |
| 409 | `duplicate_contact` | 有效线索或客户已占用该手机号 |
| 409 | `idempotency_conflict` | 同一幂等身份被不同请求复用 |
| 409 | `idempotency_in_progress` | 同一幂等身份的首个请求尚未完成 |
| 404 | `phone_not_found` | 手机号没有对应客户或线索 |
| 409 | `ambiguous_phone` | 客户或线索目标表存在多条同号记录 |
| 409 | `lead_closed` | 唯一匹配线索已转化或已失效 |

重复响应包含不含 Token 的最小 `duplicate_hint`：对象类型、ID、名称、规范手机号和业务状态。

## Token 初始化

生产库应从 `v2_022` 执行合并更新脚本，并由应用启动确认迁移到 `v2_025`：

- `v2_022_to_v2_025.sqlite.sql`
- `v2_022_to_v2_025.mysql.sql`

分阶段脚本作为审计历史保留在 `ops/sql/`：

- `v2_023_external_lead_api.sqlite.sql`
- `v2_023_external_lead_api.mysql.sql`
- `v2_024_external_followups.sqlite.sql`
- `v2_024_external_followups.mysql.sql`
- `v2_025_external_idempotency.sqlite.sql`
- `v2_025_external_idempotency.mysql.sql`
- `api_token_init.sqlite.template.sql`
- `api_token_init.mysql.template.sql`

模板必须替换 Token 名称、Token 值、绑定用户名和可选过期时间后再执行，且只执行一次。不要把真实 Token 写入仓库、日志、工单或文档。完整执行顺序、preflight/postcheck 和回滚边界见 `ops/ROLLOUT-EXTERNAL-API.md`。
