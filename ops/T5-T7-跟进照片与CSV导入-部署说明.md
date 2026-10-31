# T5–T7 部署说明（跟进/照片、看板、CSV 导入）

> 适用版本：CRM V1 · commit `a0acf6b`(T5) / `d517a1c`(T6) / `7342a5f`(T7)
> 本文件只记录这三个任务带来的**增量**部署要点；完整上线/回滚流程见
> `ops/OPS-部署与运维手册.md`（T9 已写好，不用重写）。

## 1. 变更清单

| 文件 | 说明 |
|---|---|
| `app/routers/followups.py` | 跟进 CRUD（multipart）：建/列表/删 + 照片 ≤3 + 带 stage 顺手改商机阶段 |
| `app/routers/attachments.py` | `GET /api/crm/attachments/{id}`：登录 + 路径穿越校验 + `FileResponse` 流式 |
| `app/storage.py` | 落盘/取盘唯一出口：`storage_key=YYYY/MM/DD/<uuid>.<ext>`、图片白名单、`resolve()` 越界校验 |
| `app/routers/dashboard.py` | 首页看板：今日待跟进 / 本月成交 / 统计 |
| `app/routers/csvimport.py` | CSV preview + commit（stdlib `csv`，`.xlsx` 友好提示） |
| `app/models.py` | 上述接口的 Pydantic 出参/入参 |
| `app/main.py` | 挂载 4 个新 router（auth/customers/deals 行为未改） |
| `app/schema.py` | 仅订正 `attachments.storage_key` 注释（相对 `CRM_UPLOADS` 根），**DDL 无变化** |
| `tests/test_followups.py` `tests/test_dashboard.py` `tests/test_csvimport.py` | 44 个用例 |

**无数据库迁移**：`follow_ups/attachments/import_log` 三张表在 T1 的 `ENSURE_SQL` 里早已建好，
重启即生效；`crm.db` 不需要手工改。

## 2. 新增接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/crm/follow-ups` | multipart：`customer_id*, content*, deal_id?, next_date?(YYYY-MM-DD), stage?, photos[≤3]` |
| GET | `/api/crm/follow-ups?customer_id=&deal_id=` | 列表（新的在前，每条含 `photo_count` + `photos[]`） |
| DELETE | `/api/crm/follow-ups/{id}` | 删跟进 + 级联删 `attachments` 行（**物理文件保留**） |
| GET | `/api/crm/attachments/{id}` | 图片流（登录；`Cache-Control: private`） |
| GET | `/api/crm/dashboard` | `{today_followups, month_won, stats}` |
| POST | `/api/crm/import/preview` | multipart `file`：表头/前 5 行/建议映射/`file_ref`；`.xlsx` 返回 `kind=xlsx_unsupported` |
| POST | `/api/crm/import/commit` | JSON `{file_ref, column_mapping?, source_name?}` 或 multipart `file + column_mapping(JSON 串)` |

错误口径：业务校验一律 **400**（非法阶段/日期/超 3 张/映射缺失/映射列不存在），
资源不存在 **404**，未登录 **401**，前端统一按 `detail` 文案提示即可。

## 3. 存储与磁盘

```
/opt/data/crm/uploads/
├── 2026/10/29/<uuid>.png        # 跟进照片，按服务器本地日期分目录
└── _import_cache/<token>.csv    # CSV 预览缓存，2h TTL，每次 preview/commit 自动清过期
```
- `attachments.storage_key` 存 **相对 `CRM_UPLOADS` 的路径**（不带 `uploads/` 前缀），
  换根目录（迁移/测试）时不用改数据；
- 单张限 20MB、单条跟进 3 张；nginx 片段已是 `client_max_body_size 100M`（无需改）；
- 新增写盘都在 `/opt/data/crm` 下，systemd 的 `ReadWritePaths=/opt/data/crm` 已覆盖；
- 备份：`ops/backup.py` 原本就打包整个 `uploads/`，照片与导入缓存自动进备份，无需改配置。
  按 3 张/跟进 × 2–8MB 估算，**每天 10 条跟进 ≈ 100MB/月**，注意 `backups/` 保留策略。

### 物理文件清理（可选，手工）
删跟进只删 DB 行，照片留在盘上（误删可从备份捞回）。需要定期瘦身时：

```bash
# 只清 90 天前的照片（先确认备份可用！）
find /opt/data/crm/uploads -type f -name '*.png' -mtime +90 -print
```

## 4. 上线步骤（增量）

```bash
cd /opt/data/crm
git log --oneline -3                      # 确认 a0acf6b / d517a1c / 7342a5f
systemctl restart crm-api                 # 只重启，无迁移
curl -s http://<内网服务器IP>:8010/health    # {"status":"ok",...}
# 经 nginx 验收（登录后）
curl -s -o /dev/null -w '%{http_code}\n' http://<内网服务器IP>:8000/crm/api/crm/dashboard   # 404/401 均说明路由通
```

前端（T8）调用注意：
- 附件 URL 用后端路径 `/api/crm/attachments/{id}`，对外要拼 `/crm` 前缀 →
  `/crm/api/crm/attachments/{id}`；
- 图片用 `<img src>` 直连即可（Cookie 自动带），不要用 fetch 转 blob；
- 跟进表单 `<input type="file" accept="image/*" capture="environment" multiple>`，
  前端也要卡 3 张（后端已硬校验，超了 400）。

## 5. 验证命令

```bash
# 本任务验收（44 例）
cd /opt/data/crm && ADMIN_PASSWORD=test123 CRM_DB=/tmp/crm-t3.db CRM_UPLOADS=/tmp/crm-t3-up \
  env -u PYTHONPATH -u VIRTUAL_ENV /usr/bin/python3 -m unittest \
  tests.test_followups tests.test_dashboard tests.test_csvimport -v

# 全量回归（87 例）
cd /opt/data/crm && ADMIN_PASSWORD=test123 CRM_DB=/tmp/crm-all.db CRM_UPLOADS=/tmp/crm-all-up \
  env -u PYTHONPATH -u VIRTUAL_ENV /usr/bin/python3 -m unittest discover -s tests
```

生产库自检（应无输出）：`ls /opt/data/crm/crm.db` 只在服务真实启动后才会出现；
测试一律用 `/tmp` 下的临时库，`tests/_bootstrap.py` 会拒绝指向生产库。

## 6. 回滚

```bash
cd /opt/data/crm
git revert --no-edit 7342a5f   # T7
git revert --no-edit d517a1c   # T6
git revert --no-edit a0acf6b   # T5
systemctl restart crm-api
```
- 回滚代码即可：**表结构没动**，多出来的 `attachments`/`import_log` 数据无害；
- `uploads/` 里的照片与缓存可以保留（旧代码不读它们），也可以按 §3 清理。

## 7. 已知边界（V1 明确不做）

- `.xlsx` 直传不解析（提示另存为 CSV），V1.5 才上 `openpyxl`；
- 删跟进不删物理文件；无可视化清理工具；
- 无缩略图/EXIF 纠正，原图直出（内网、单人，够用）；
- 兼容性：iPhone HEIC 能存（`image/heic`），但**浏览器 `<img>` 不一定能解码**，
  V1.5 再按机型决定是否转码。
