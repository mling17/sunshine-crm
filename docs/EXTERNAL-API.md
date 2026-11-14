# 外部 API

外部 API 供服务器之间调用，使用数据库中长期保存的完整 Bearer Token。当前版本提供新增线索和批量手机号校验；同一套 Token 鉴权将复用于后续外部接口。

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
  -H 'Content-Type: application/json' \
  -d '{
    "phone": "+86 (138) 0013-8000",
    "name": "王经理",
    "lead_type": "company",
    "company_name": "海景装饰",
    "tags": ["重点", "展会"]
  }'
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
- 每个值按新增线索的手机号规则规范化。
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

任一值非法时整批返回 400，不查询或返回部分结果。`invalid_positions` 使用从 0 开始的输入数组下标：

```json
{
  "detail": "手机号格式不正确",
  "code": "invalid_phone",
  "invalid_positions": [1, 3]
}
```

## 错误

| HTTP | code | 含义 |
| --- | --- | --- |
| 401 | `unauthorized` | Token 或绑定用户无效 |
| 400 | `invalid_phone` | 新增线索手机号非法，或校验批次包含非法值；批次错误带 `invalid_positions` |
| 400 | `validation_failed` | 字段、长度或未知字段校验失败 |
| 409 | `duplicate_contact` | 有效线索或客户已占用该手机号 |

重复响应包含不含 Token 的最小 `duplicate_hint`：对象类型、ID、名称、规范手机号和业务状态。

## Token 初始化

数据库更新脚本和一次性模板位于 `ops/sql/`：

- `v2_023_external_lead_api.sqlite.sql`
- `v2_023_external_lead_api.mysql.sql`
- `api_token_init.sqlite.template.sql`
- `api_token_init.mysql.template.sql`

模板必须替换 Token 名称、Token 值、绑定用户名和可选过期时间后再执行。不要把真实 Token 写入仓库、日志、工单或文档。
