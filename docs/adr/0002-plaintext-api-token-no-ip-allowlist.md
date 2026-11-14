# 外部 API Token 明文保存且不限制来源 IP

Status: accepted

外部 API 需要一个可由数据库初始化、便于服务端集成且不依赖浏览器 Cookie 的长期凭据。项目明确选择在 `api_tokens.token` 中保存完整 Token，并要求通过数据库管理控制读取权限；同时不增加 IP 白名单，使集成部署可以在合法服务器之间迁移。

## Consequences

- 任何能读取 `api_tokens` 表的人都可取得可用凭据，因此数据库备份、只读账号和日志必须按凭据级别保护。
- Token 泄露后应通过 `revoked_at` 撤销；多行设计允许新旧 Token 轮换重叠。
- 鉴权统一通过 `Authorization: Bearer <token>`，不使用 Cookie、查询参数或其他请求头。
- 来源 IP 不受限制；请求速率限制、WAF 和网络边界不属于本版本 Token 鉴权逻辑。
