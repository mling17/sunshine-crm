# 客户只由线索转化产生且手机号不可变

Status: accepted

客户必须由线索关联首个商机后，在同一事务中转化产生。直接客户创建、CSV 客户导入和客户手机号编辑都会制造没有来源线索或手机号与来源不一致的客户，因此这三个旁路永久关闭。

## Consequences

- `POST /api/crm/customers` 固定返回 405 `customer_create_forbidden`。
- CSV 导入固定写线索池；省略目标时默认导入线索，显式选择客户返回 400 `customer_import_forbidden`。
- 客户更新请求包含 `phone` 时返回 409 `customer_phone_immutable`，整条请求不修改记录；客户编辑页电话只读且不提交。
- 历史异常数据不在迁移中伪造来源线索或改写手机号，由上线前审计报告交人工处理。
