# sunshine-crm · 天窗天幕销售 CRM

面向定制阳光房 / 天窗天幕（含遮阳篷）销售的单用户 CRM。业务链路：
**线索 → 客户 → 产品 → 商机 → 订单 → 售后 → 物流**，配套工作台、统计与数据字典。

产品主档按“一份 Excel 对应一个产品”管理；每份下单表随产品归档、可下载，商机和订单保存产品配置快照。

> 单用户、内网自用；客户档案由线索转化产生，商机只能由线索或客户「转商机」发起。

## 技术栈

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 后端 | Python + FastAPI + Pydantic | REST API，前缀 `/api/crm`，SQLite 存储 |
| 前端 | 原生 JS SPA（无构建） | `static/` 目录直出，hash 路由 `#/leads` 等 |
| 存储 | SQLite + 本地 `uploads/` | 附件（跟进照片、报价单）落盘 |
| 部署 | systemd + nginx 反代 | 静态文件由 nginx 托管，API 由 `crm-api.service` 提供 |

## 目录

```
app/                 后端
  main.py            入口，挂载 /api/crm
  models.py          请求/响应模型
  schema.py          建表与迁移
  services.py        业务编排（线索转商机等）
  timeline.py        系统履历 add_entry()（创建/编辑/转化/失效）
  dicts.py           数据字典种子与读写
  enums.py labels.py 枚举与中文标签
  storage.py         附件存储
  routers/           按模块拆的接口
    leads.py customers.py deals.py orders.py aftersales.py
    carriers.py dicts.py followups.py csvimport.py auth.py
    dashboard.py stats.py attachments.py
static/              前端
  index.html app.js app.css sw.js
  views/             每页一个文件（leads.js 线索、deals.js 商机、...）
  demo/              设计稿（对照用，不参与发版）
  icons/ manifest.json
docs/                设计与测试文档
  TC-LEADS.md/.csv   线索页测试用例（85 条，含执行结果）
  gen_lead_testcases.py  用例生成器
  BUSINESS-ARCH-V2.md PAGES-V2.md PLANNER-V2.md PLANNER-V3.md
ops/                 部署运维
  deploy-frontend.sh 前端发版（拷 static 到 nginx 并自检）
  crm-api.service    systemd 单元
  nginx-crm-location.conf
  backup.py backup.env crm-backup.service/.timer
  OPS-部署与运维手册.md
tests/               pytest 用例
```

## 本地跑起来

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install fastapi "uvicorn[standard]" pydantic python-multipart

# 管理员账号（首次登录用，库为空时自动建）
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=change-me

uvicorn app.main:app --host 127.0.0.1 --port 8010
# 打开 http://127.0.0.1:8010/crm/
```

环境变量（可写进 `.env`，**不要提交**）：

| 变量 | 说明 |
| --- | --- |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | 管理员登录名与口令 |
| `CRM_DB` | SQLite 路径，默认 `crm.db` |
| `CRM_UPLOADS` | 附件目录，默认 `uploads/` |
| `CRM_MINIO_ENDPOINT` / `_BUCKET` / `_ACCESS` / `_SECRET` | 可选，异地备份用 |

## 部署要点

1. 后端：`ops/crm-api.service` 拷到 `/etc/systemd/system/` → `systemctl daemon-reload && systemctl restart crm-api`
2. 前端：`bash ops/deploy-frontend.sh`（把 `static/` 同步到 nginx 目录并自检）
3. **改前端必须同步升版本号**：`static/index.html` 里所有 `?v=` 与 `static/sw.js` 的缓存名一起升，否则浏览器混版会让页面报 `dictOptions is not defined`（表现为「点按钮没反应」）
4. 反向代理：`ops/nginx-crm-location.conf`（把 `/crm/` 静态与 `/crm/api/` → `127.0.0.1:8010` 一起配好）

## 数据与安全

- 入库排除：`crm.db`、`crm.db.bak-*`、`uploads/`、`backups/`、`logs/`、`.env`（见 `.gitignore`）
- 备份：`backup.py` + `crm-backup.timer`，支持本机与 MinIO 异地；口令一律走 `ops/backup.env`（不入库）
- 搜索接口统一转义 `LIKE` 通配符（`%`、`_`、`\` 按字面匹配），别直接拼 `'%{kw}%'`

## 测试

- 手工回归：`docs/TC-LEADS.md`（线索页 85 条，分 12 个模块；同内容另有 `.csv` 便于导入表格工具）
- 自动化：`pytest tests/`

## License

私有业务系统，未附开源许可；如需二次分发请先联系作者。
