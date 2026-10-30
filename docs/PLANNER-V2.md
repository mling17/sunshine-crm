# CRM V2 技术方案（Planner 定稿）

> 版本：v1.0 · 2026-10-30
> 上游权威输入：`/opt/data/crm/docs/BUSINESS-ARCH-V2.md`（业务定稿，本文不改其一字）
> 基线系统：CRM V1（`/opt/data/crm`，FastAPI + SQLite + H5，8010，systemd `crm-api.service`）
> 本文交付对象：@coder（按 §6 拆卡开工）、@reviewer（按 §5 断言表验收）、@ops（按 §3.5 升级/回滚）
> 状态：**定稿**。§7 列出 8 个业务空白，需用户拍板（不阻塞 T1–T6 开工，仅 T5/T6 的个别校验依赖 Q1/Q4）

---

## 0. 方案总览

### 0.1 一句话技术路线

**增量演进，不重写**：V1 的 9 张表、7 个 router、8 个 H5 视图全部保留；V2 加 9 张新表、扩 4 张旧表、加 7 个 router、加 6 个 H5 视图，零新增第三方依赖。

### 0.2 表清单（迁移后 18 张业务表）

| # | 表 | 来源 | 职责 |
|---|---|---|---|
| 1 | `users` | V1 不变 | 登录账号（单用户） |
| 2 | `sessions` | V1 不变 | 会话（12h 固定过期） |
| 3 | `customers` | V1 **扩 6 列** | 客户档案（个人/公司） |
| 4 | `deals` | V1 **扩 6 列** | 商机 |
| 5 | `follow_ups` | V1 **重建**（放宽 `customer_id`） | 统一跟进（挂 5 类对象） |
| 6 | `attachments` | V1 **重建**（放宽 `follow_up_id`） | 附件（跟进照片 / 订单截图） |
| 7 | `import_log` | V1 不变 | CSV 导入审计 |
| 8 | `tags` | V1 不变 | 标签字典 |
| 9 | `customer_tags` | V1 不变 | 客户↔标签 |
| 10 | `schema_migrations` | **新增** | 迁移版本落账 |
| 11 | `leads` | **新增** | 线索 |
| 12 | `lead_tags` | **新增** | 线索↔标签（转化时搬到客户） |
| 13 | `customer_contacts` | **新增** | 公司客户多联系人（R3） |
| 14 | `carriers` | **新增** | 物流公司主数据（N5） |
| 15 | `orders` | **新增** | 订单（7 态） |
| 16 | `order_status_log` | **新增** | 订单跃迁日志（金额/截图/运单审计） |
| 17 | `aftersales` | **新增** | 售后单 |
| 18 | `aftersale_status_log` | **新增** | 售后状态日志 |

### 0.3 设计取舍（4 条硬决定，理由写死，评审别再翻）

1. **枚举放应用层，不放 DB CHECK**。V1 的 `STAGES` 就是这么做的（非法值返回 400 而非约束异常，前端好提示）。V2 把全部枚举收敛到 `app/enums.py` 单文件，DB 只做 NOT NULL / UNIQUE / FK。理由：SQLite 改 CHECK 要重建表，而业务枚举（尤其售后类型）未来大概率扩项。
2. **两张表必须重建，其余只加列**。`follow_ups.customer_id` 与 `attachments.follow_up_id` 在 V1 是 NOT NULL；线索期还没有客户、订单截图不挂跟进，这两条 NOT NULL 直接堵死 V2 的两个核心场景。重建走 SQLite 官方 12 步（关外键 → 建新表 → 按行复制 → 比对行数 → DROP → RENAME → 开外键），并保留旧列名可空，**V1 代码零改动继续可用**。
3. **金额用 REAL，写入时 `round(x, 2)`**（D9）。V1 `amount/deposit/balance` 已是 REAL，改类型等于推翻 V1 API；单用户单库、金额量级 10^5，REAL 的 15 位有效精度足够。汇总一律 `ROUND(SUM(...), 2)`。
4. **时间字符串两种口径并存**（沿用 V1 既有事实，不新造）：`created_at/updated_at` 用 UTC ISO（`2026-10-30T14:25:25Z`，`security.now_iso()`）；业务日期/成交时间用**本地无时区**（`2026-10-30T22:25:00+08:00` 或 `YYYY-MM-DD`，`security.now_local_iso()`）。统计一律按 `date('now','localtime')`，不许用 UTC 跨零点。

### 0.4 与 V1 的兼容承诺（可被测试证伪）

| 承诺 | 验证手段 |
|---|---|
| V1 的 `/api/crm/customers`、`/deals`、`/follow-ups`、`/dashboard`、`/attachments/{id}`、`/import/*` 出参**只增不改** | §5.2 V1 回归 87 条用例 |
| V1 前端（登录/客户/商机/跟进/统计/导入）继续可用 | 手点冒烟 §5.6 |
| V1 写库路径不写 `object_type/object_id` 也不报错 | 触发器 `trg_fu_object_fill` / `trg_att_object_fill`（§1.6） |
| V1 数据 0 丢失 | 迁移前后 6 张表行数比对（§3.6 实测） |

---

## 1. 表设计

### 1.1 枚举字典（唯一来源 `app/enums.py`）

> 存储值一律英文小写蛇形；中文只出现在 `*_LABELS` 与出参 `*_label` 字段。**任何地方不得出现中文字面量做存储值。**

| 枚举 | 代码值 | 中文 | 用在哪 | 约束来源 |
|---|---|---|---|---|
| `CUSTOMER_TYPE` | `personal` / `company` | 个人 / 公司 | `customers.customer_type`、`leads.lead_type` | D1 |
| `LEAD_STATUS` | `new` / `following` / `converted` / `invalid` | 新线索 / 跟进中 / 已转化 / 已失效 | `leads.status` | §3.1 |
| `LEAD_INVALID_REASON` | `invalid_phone` / `blacklist` / `no_intent` / `duplicate` / `other` | 无效号码 / 黑名单 / 无意向 / 重复 / 其他 | `leads.invalid_reason` | §3.1 |
| `SOURCE` | `wechat` / `phone` / `referral` / `existing` / `stock` / `other` | 微信 / 电话 / 转介绍 / 老客户 / **存量** / 其他 | `leads.source`、`customers.source` | §3.1 + §4（存量） |
| `INTENT_LEVEL` | `high` / `medium` / `low` / `none` | 高 / 中 / 低 / 无意向 | `leads.intent_level`、`customers.intent_level` | §3.1、N1、N2、I3 |
| `DEAL_STAGE` | `confirm` / `quote` / `negotiate` / `won` / `lost` | 需求确认 / 报价 / 成交洽谈 / 赢单 / 流失 | `deals.stage` | §3.3、N3 |
| `DEAL_LOST_REASON` | `price` / `competitor` / `give_up` / `budget` / `other` | 价格 / 竞品 / 客户放弃 / 预算不足 / 其他 | `deals.lost_reason` | §3.3 |
| `ORDER_STATUS` | `pending_payment` / `deposit_paid` / `producing` / `balance_paid` / `ready_to_ship` / `shipped` / `completed` | 待支付 / 已支付押金 / 生产中 / 已支付尾款 / 待发货 / 已发货 / 已完成 | `orders.status`、`order_status_log.*_status` | D3、R1、N4 |
| `LOGISTICS_MODE` | `carrier` / `self` | 物流公司 / 自送 | `orders.logistics_mode` | N5、R2 |
| `AFTERSALE_TYPE` | `return` / `exchange` / `repair` / `complaint` / `other` | 退货 / 换货 / 维修 / 投诉 / 其他 | `aftersales.type` | D7 |
| `AFTERSALE_STATUS` | `pending` / `processing` / `done` / `rejected` | 待处理 / 处理中 / 已完成 / 已拒绝 | `aftersales.status` | §3.5（3 段流程，终态二选一） |
| `FOLLOW_OBJECT` | `lead` / `customer` / `deal` / `order` / `aftersale` | 线索 / 客户 / 商机 / 订单 / 售后 | `follow_ups.object_type` | §3.8 |
| `FOLLOW_METHOD` | `phone` / `wechat` / `visit` / `online` | 电话 / 微信 / 到面 / 线上 | `follow_ups.method` | §3.8 |
| `ATTACH_OBJECT` | `follow_up` / `order_payment` / `aftersale` | 跟进照片 / 支付截图 / 售后凭证 | `attachments.object_type` | §3.4、§3.5 |
| `CUSTOMER_LIFECYCLE` | `potential` / `dealing` / `won` / `repeat` | 潜在客户 / 商机中 / 已成交 / 复购 | **派生，不落库** | §3.2 |

**旧值兼容映射**（迁移一次性完成，代码里不再出现旧值）：

| V1 `deals.stage` | V2 | 说明 |
|---|---|---|
| `lead` | `confirm` | 业务 §4 明确 `lead → 需求确认` |
| `quoted` | `quote` | 同名归一 |
| `confirmed` / `deposit` / `producing` / `balance` / `shipped` | `negotiate` | V1 把这些当商机阶段，V2 归入"成交洽谈"（订单细节移到订单表，N3/D3） |
| `won` | `won` | 保留 |
| `lost` | `lost` | 保留 |

`app/enums.py` 同时提供 `LEGACY_STAGE_MAP`（上表）与 `stage_label(s)`，供 `DealOut.stage_label` 兜底未知旧值时原样返回，避免过渡期前端出空白。

> `SOURCE` 里的 `stock`（存量）**只用于迁移回填**，前端"来源"下拉不展示；后端接受该值（存量客户编辑时不能把来源改没）。

### 1.2 新增表 DDL（可直接执行，全部 `IF NOT EXISTS`）

```sql
-- 迁移版本落账
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL,
  note       TEXT
);

-- 线索
CREATE TABLE IF NOT EXISTS leads (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  name                  TEXT,
  phone                 TEXT,
  wechat                TEXT,
  lead_type             TEXT NOT NULL DEFAULT 'personal',
  company_name          TEXT,
  source                TEXT,
  source_other          TEXT,
  location              TEXT,
  note                  TEXT,
  intent_level          TEXT,
  status                TEXT NOT NULL DEFAULT 'new',
  invalid_reason        TEXT,
  invalid_reason_other  TEXT,
  converted_customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
  converted_deal_id     INTEGER REFERENCES deals(id)     ON DELETE SET NULL,
  owner                 TEXT,
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_tags (
  lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
  UNIQUE(lead_id, tag_id)
);

-- 公司客户多联系人（R3）
CREATE TABLE IF NOT EXISTS customer_contacts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  phone       TEXT,
  wechat      TEXT,
  is_primary  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

-- 物流公司主数据（N5）
CREATE TABLE IF NOT EXISTS carriers (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL UNIQUE,
  contact    TEXT,
  phone      TEXT,
  note       TEXT,
  is_active  INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- 订单（1:1 商机，R4 总额继承）
CREATE TABLE IF NOT EXISTS orders (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  order_no       TEXT NOT NULL UNIQUE,
  customer_id    INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  deal_id        INTEGER NOT NULL UNIQUE REFERENCES deals(id) ON DELETE RESTRICT,
  product_type   TEXT,
  model          TEXT,
  spec           TEXT,
  amount         REAL NOT NULL DEFAULT 0,
  deposit_paid   REAL NOT NULL DEFAULT 0,
  balance_paid   REAL NOT NULL DEFAULT 0,
  logistics_mode TEXT,
  carrier_id     INTEGER REFERENCES carriers(id) ON DELETE RESTRICT,
  tracking_no    TEXT,
  shipped_at     TEXT,
  completed_at   TEXT,
  status         TEXT NOT NULL DEFAULT 'pending_payment',
  note           TEXT,
  owner          TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

-- 订单跃迁日志（每次跃迁一行，不可改不可删）
CREATE TABLE IF NOT EXISTS order_status_log (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id       INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  from_status    TEXT,
  to_status      TEXT NOT NULL,
  deposit_paid   REAL,
  balance_paid   REAL,
  screenshot_ids TEXT,
  logistics_mode TEXT,
  carrier_id     INTEGER REFERENCES carriers(id) ON DELETE SET NULL,
  tracking_no    TEXT,
  note           TEXT,
  created_at     TEXT NOT NULL
);

-- 售后单
CREATE TABLE IF NOT EXISTS aftersales (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  no            TEXT NOT NULL UNIQUE,
  order_id      INTEGER NOT NULL REFERENCES orders(id)    ON DELETE RESTRICT,
  customer_id   INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  type          TEXT NOT NULL,
  type_other    TEXT,
  description   TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'pending',
  result        TEXT,
  reject_reason TEXT,
  closed_at     TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aftersale_status_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  aftersale_id INTEGER NOT NULL REFERENCES aftersales(id) ON DELETE CASCADE,
  from_status  TEXT,
  to_status    TEXT NOT NULL,
  note         TEXT,
  created_at   TEXT NOT NULL
);
```

### 1.3 V1 表扩展 DDL（只加列，不重建）

```sql
-- 客户：类型/来源/意向/公司名/负责人（D5 预留）
ALTER TABLE customers ADD COLUMN customer_type TEXT NOT NULL DEFAULT 'personal';
ALTER TABLE customers ADD COLUMN source            TEXT;
ALTER TABLE customers ADD COLUMN source_other      TEXT;
ALTER TABLE customers ADD COLUMN intent_level      TEXT;
ALTER TABLE customers ADD COLUMN company_name      TEXT;
ALTER TABLE customers ADD COLUMN owner             TEXT;

-- 商机：N3 去预计成交日期/概率，加产品（product_* 已存在）；加标题/流失原因/来源流失商机/订单回指
ALTER TABLE deals ADD COLUMN title              TEXT;
ALTER TABLE deals ADD COLUMN lost_reason        TEXT;
ALTER TABLE deals ADD COLUMN lost_reason_other  TEXT;
ALTER TABLE deals ADD COLUMN source_lost_deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL;
ALTER TABLE deals ADD COLUMN order_id           INTEGER;   -- 应用层保证 = orders.deal_id，不加 FK（避免与 orders.deal_id 成环）
ALTER TABLE deals ADD COLUMN owner              TEXT;
```

**列语义补注（防误用）**

| 列 | 口径 |
|---|---|
| `customers.house_note` | V2 当"备注"用（业务 §3.2 的"备注"不另开列，见 Q8） |
| `customers.location` | 楼盘 / 安装地址（沿用） |
| `customers.name` | 个人=姓名；公司=公司名（`company_name` 同步冗余一份，供列表统一显示） |
| `customers.intent_level` | 客户级意向（I3），线索转化时继承最后值（N2），后续客户/商机跟进可更新 |
| `customers.created_at` | 线索转化时**继承线索的 created_at**（§3.1 第 2 条） |
| `deals.title` | 商机名称（业务 §3.3 必填）；存量商机为 NULL，展示时回退 `${product_type} ${model}` |
| `deals.stage` | **DDL 默认值仍是 `'lead'`（V1 遗留，SQLite 的 ALTER 改不了默认值）**。因此所有 INSERT 必须显式写 `stage`；`DealIn.stage` 的默认值已在 T1 改为 `confirm`。**任何"少写 stage"的插入会落回 `lead` 这个非法枚举值** —— reviewer 用 `SELECT COUNT(*) FROM deals WHERE stage='lead'` 必须为 0 来卡这条 |
| `deals.order_id` | 赢单后回指订单；**由事务内 UPDATE 写入**，DB 不设 FK（`orders.deal_id UNIQUE` 才是唯一性真相） |
| `deals.closed_at` | 沿用 V1：进 `won` 写入本地时间，驱动"本月成交" |

### 1.4 两张表的重建 DDL（`follow_ups` / `attachments`）

> 为什么重建：`follow_ups.customer_id`、`attachments.follow_up_id` 在 V1 是 `NOT NULL`。线索期没有客户、订单截图不挂跟进 → 必须放宽为可空。重建保留旧列名（V1 代码与 V1 测试继续可跑），新增 `object_type/object_id` 作为 V2 的权威挂载键。

```sql
CREATE TABLE follow_ups_new (
  id          INTEGER PRIMARY KEY,
  object_type TEXT NOT NULL DEFAULT 'customer',
  object_id   INTEGER,
  customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
  deal_id     INTEGER REFERENCES deals(id)     ON DELETE CASCADE,
  method      TEXT,
  content     TEXT NOT NULL,
  next_date   TEXT,
  created_at  TEXT NOT NULL
);

INSERT OR IGNORE INTO follow_ups_new
  (id, object_type, object_id, customer_id, deal_id, method, content, next_date, created_at)
SELECT id,
       CASE WHEN deal_id IS NOT NULL THEN 'deal' ELSE 'customer' END,
       COALESCE(deal_id, customer_id),
       customer_id, deal_id, NULL, content, next_date, created_at
  FROM follow_ups;

-- 前置：SELECT COUNT(*) FROM follow_ups_new 必须等于 SELECT COUNT(*) FROM follow_ups，
-- 否则迁移脚本直接抛错退出（不 DROP）。
DROP TABLE follow_ups;
ALTER TABLE follow_ups_new RENAME TO follow_ups;

CREATE TABLE attachments_new (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  object_type  TEXT NOT NULL DEFAULT 'follow_up',
  object_id    INTEGER,
  follow_up_id INTEGER REFERENCES follow_ups(id) ON DELETE CASCADE,
  storage_key  TEXT NOT NULL,
  file_name    TEXT,
  mime_type    TEXT,
  size         INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL
);

INSERT OR IGNORE INTO attachments_new
  (id, object_type, object_id, follow_up_id, storage_key, file_name, mime_type, size, created_at)
SELECT id, 'follow_up', follow_up_id, follow_up_id, storage_key, file_name, mime_type, size, created_at
  FROM attachments;

DROP TABLE attachments;
ALTER TABLE attachments_new RENAME TO attachments;
```

**重建三步的工程约束（照做，别省）**

1. `PRAGMA foreign_keys=OFF` **必须在 `BEGIN` 之前**执行（SQLite 不允许在事务内改这个 pragma）。迁移脚本已按此实现；否则 `DROP TABLE follow_ups` 会按 `attachments.follow_up_id ON DELETE CASCADE` 把照片行一起删掉。
2. `DROP` 前**必须**比对 `COUNT(*)`；不相等就抛错退出（数据保护红线）。
3. 提交后再 `PRAGMA foreign_keys=ON` 并跑 `PRAGMA foreign_key_check`，结果非空即失败。

### 1.5 触发器（V1 兼容的唯一机关）

```sql
-- V1 的 POST /follow-ups 只写 customer_id/deal_id → 自动派生 object_type/object_id
CREATE TRIGGER IF NOT EXISTS trg_fu_object_fill
AFTER INSERT ON follow_ups
WHEN NEW.object_id IS NULL
BEGIN
  UPDATE follow_ups
     SET object_type = CASE WHEN NEW.deal_id IS NOT NULL THEN 'deal' ELSE 'customer' END,
         object_id   = COALESCE(NEW.deal_id, NEW.customer_id)
   WHERE id = NEW.id;
END;

-- V1 的跟进照片只写 follow_up_id → 自动派生 object_type/object_id
CREATE TRIGGER IF NOT EXISTS trg_att_object_fill
AFTER INSERT ON attachments
WHEN NEW.object_id IS NULL AND NEW.follow_up_id IS NOT NULL
BEGIN
  UPDATE attachments
     SET object_type = 'follow_up', object_id = NEW.follow_up_id
   WHERE id = NEW.id;
END;
```

> 实测：V1 写法的 `INSERT INTO follow_ups (customer_id, deal_id, ...)` 插入后 `object_type/object_id` 分别为 `('customer',1)`、`('deal',1)`；`INSERT INTO attachments (follow_up_id, ...)` 后为 `('follow_up',1,1)`。见 §3.6。

### 1.6 外键 / 级联矩阵（写错这里 = 删数据或删不掉）

| 子表.列 | 父表 | ON DELETE | 理由 |
|---|---|---|---|
| `deals.customer_id` | `customers` | CASCADE | V1 原样：删客户连商机一起删 |
| `follow_ups.customer_id` | `customers` | CASCADE | V1 原样：删客户清跟进 |
| `follow_ups.deal_id` | `deals` | CASCADE | V1 原样：删商机清其跟进 |
| `attachments.follow_up_id` | `follow_ups` | CASCADE | V1 原样：删跟进清照片行（磁盘文件留备份） |
| `customer_tags.customer_id / tag_id` | — | CASCADE | V1 原样 |
| `leads.converted_customer_id` | `customers` | SET NULL | 线索是历史凭证，客户没了也不该丢线索 |
| `leads.converted_deal_id` | `deals` | SET NULL | 同上 |
| `customer_contacts.customer_id` | `customers` | CASCADE | 联系人属于客户 |
| `orders.customer_id` | `customers` | **RESTRICT** | 有订单不允许删客户（对账底线） |
| `orders.deal_id` | `deals` | **RESTRICT** | 有订单不允许删商机 |
| `orders.carrier_id` | `carriers` | **RESTRICT** | 被引用的物流公司只能停用不能删（Q7） |
| `order_status_log.order_id` | `orders` | CASCADE | 日志随订单 |
| `order_status_log.carrier_id` | `carriers` | SET NULL | 物流公司停用不影响历史日志 |
| `aftersales.order_id` | `orders` | **RESTRICT** | 有售后不允许删订单 |
| `aftersales.customer_id` | `customers` | **RESTRICT** | 同上 |
| `aftersale_status_log.aftersale_id` | `aftersales` | CASCADE | 日志随售后单 |

**由此产生的 API 侧前置检查**（否则用户会看到 500）：
- `DELETE /customers/{id}`：先查 `orders` / `aftersales`，有则 409 `customer_has_orders`。
- `DELETE /carriers/{id}`：先查 `orders`，有则 409 `carrier_in_use`（引导用 `is_active=0`）。
- 删除售后单：**不提供**（业务无此需求），只允许 `rejected`。

### 1.7 索引清单（迁移后 30 个，全部 `IF NOT EXISTS`）

```sql
-- V1 原有 10 个：customers(name/phone)、deals(customer_id/stage/closed)、follow_ups(customer_id/next_date)、
--   attachments(follow_up_id)、customer_tags(customer_id/tag_id)
CREATE INDEX IF NOT EXISTS idx_leads_status    ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_phone     ON leads(phone);
CREATE INDEX IF NOT EXISTS idx_leads_wechat    ON leads(wechat);
CREATE INDEX IF NOT EXISTS idx_leads_created   ON leads(created_at);
CREATE INDEX IF NOT EXISTS idx_lead_tags_lead  ON lead_tags(lead_id);
CREATE INDEX IF NOT EXISTS idx_cc_customer     ON customer_contacts(customer_id);
CREATE INDEX IF NOT EXISTS idx_deals_order     ON deals(order_id);
CREATE INDEX IF NOT EXISTS idx_carriers_active ON carriers(is_active);
CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_created  ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_osl_order       ON order_status_log(order_id);
CREATE INDEX IF NOT EXISTS idx_as_status       ON aftersales(status);
CREATE INDEX IF NOT EXISTS idx_as_order        ON aftersales(order_id);
CREATE INDEX IF NOT EXISTS idx_as_customer     ON aftersales(customer_id);
CREATE INDEX IF NOT EXISTS idx_as_created      ON aftersales(created_at);
CREATE INDEX IF NOT EXISTS idx_asl_aftersale   ON aftersale_status_log(aftersale_id);
CREATE INDEX IF NOT EXISTS idx_fu_object       ON follow_ups(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_fu_customer     ON follow_ups(customer_id);
CREATE INDEX IF NOT EXISTS idx_fu_deal         ON follow_ups(deal_id);
CREATE INDEX IF NOT EXISTS idx_fu_next_date    ON follow_ups(next_date);
CREATE INDEX IF NOT EXISTS idx_att_obj         ON attachments(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_att_fu          ON attachments(follow_up_id);
```

**唯一索引（业务真相，靠 DB 兜底）**：`orders.deal_id UNIQUE`（商机↔订单 1:1，N6）、`orders.order_no UNIQUE`、`aftersales.no UNIQUE`、`carriers.name UNIQUE`、`users.username UNIQUE`、`tags.name UNIQUE`。

**故意不加的唯一约束**：`customers.phone` / `customers.wechat` **不加 UNIQUE**。D4 的去重是"提示后由用户选"，不是硬拦截（"强制新建"必须允许）；硬约束会直接把业务规则改掉。

### 1.8 派生口径（不落库，避免双写不一致）

| 派生项 | SQL 口径 |
|---|---|
| 客户生命周期 `potential` | 无 `deals` 记录 |
| `dealing` | 存在 `deals.stage IN ('confirm','quote','negotiate')` |
| `won` | 存在 `orders.status='completed'` |
| `repeat` | `orders.status='completed'` 计数 ≥ 2（对同一 `customer_id`） |
| 订单"已收/未收" | `deposit_paid + balance_paid` vs `amount`（差额=未收） |
| 客户 360 时间线 | `follow_ups(object_type,object_id)` ∪ `order_status_log` ∪ `aftersale_status_log`，按 `created_at` 倒序 |

> `potential/dealing/won/repeat` 的**优先级**：`repeat > won > dealing > potential`。判定写成一条 `CASE WHEN` 子查询，`GET /customers` 与 `/customers/{id}/360` 共用同一段 SQL（放 `app/queries.py`，只写一次）。

---

## 2. 状态机与 API

### 2.1 订单 7 态机（D3 / R1 / N4）

```
pending_payment ──押金金额+截图──▶ deposit_paid ──财务确认(系统外)点下一步──▶ producing
      ──尾款金额+截图──▶ balance_paid ──点下一步──▶ ready_to_ship
      ──物流公司+运单号──▶ shipped ──客户确认收货──▶ completed
```

| # | 当前态 | 动作端点 | 必填输入 | 校验（全部不过就整单回滚） | 写入 `order_status_log` | 新态 |
|---|---|---|---|---|---|---|
| 1 | `pending_payment` | `POST /orders/{id}/pay-deposit` | `amount>0`、`screenshots` 1–3 张 | 金额 ≤ `orders.amount`；每张 ≤20MB 且是图片 | `deposit_paid=amount`、`screenshot_ids`、`note` | `deposit_paid` |
| 2 | `deposit_paid` | `POST /orders/{id}/start-production` | 无（可带 `note`） | 仅状态校验（财务确认是系统外操作） | `note` | `producing` |
| 3 | `producing` | `POST /orders/{id}/pay-balance` | `amount>0`、`screenshots` 1–3 张 | 金额 ≤ `amount - deposit_paid`（Q1） | `balance_paid=amount`、`screenshot_ids`、`note` | `balance_paid` |
| 4 | `balance_paid` | `POST /orders/{id}/ready-to-ship` | 无（可带 `note`） | 仅状态校验 | `note` | `ready_to_ship` |
| 5 | `ready_to_ship` | `POST /orders/{id}/ship` | `logistics_mode`、`tracking_no`（R2）；`carrier` 模式还需 `carrier_id` | 运单号非空（自送场景**必须**填 `无`，后端把空串归一成 `无`）；`carrier_id` 必须存在且 `is_active=1` | `logistics_mode`、`carrier_id`、`tracking_no`；同时写 `orders.shipped_at` | `shipped` |
| 6 | `shipped` | `POST /orders/{id}/complete` | 无（可带 `note`） | 仅状态校验 | `note`；同时写 `orders.completed_at` | `completed` |

**跃迁规则（服务端唯一真相，前端不许自己算下一态）**

- 每张订单的"合法下一态"由 `app/enums.py: ORDER_FLOW = {pending_payment: deposit_paid, ..., completed: None}` 定义。请求到达时：`ORDER_FLOW.get(order.status) != to_status` → **409 `illegal_transition`**，消息里带 `current_status` 与 `expected_prev`。**不可越级、不可回退、不可跳态**（R1 无取消分支）。
- 每次跃迁与业务写入必须在**同一事务**（`db_conn()` 上下文）里：`UPDATE orders` + `INSERT order_status_log` + `INSERT attachments`（截图）三者同生同死；任何一步失败整笔回滚，磁盘文件由 `storage.save_photo` 写完后再删（或先落临时名，事务成功再 rename —— 实现取后者，见 §2.8）。
- `order_status_log` 只增不改不删；`OrderDetailOut.status_log` 按 `id ASC` 输出（时间线正序）。
- 截图落库：`attachments(object_type='order_payment', object_id=order_id, follow_up_id=NULL)`；日志里 `screenshot_ids` 存 JSON 数组字符串（如 `"[12,13]"`），出参时解析成 `[{id,url}]`。
- `orders.status` 是唯一权威；`order_status_log.to_status` 必须与它一致（同一事务内写，测试要断言）。

### 2.2 商机：阶段、赢单、流失、冻结（N6 / N7 / N3）

**阶段流**：`confirm`（需求确认）→ `quote`（报价）→ `negotiate`（成交洽谈）→ `won` / `lost`。
`won` / `lost` **不接受** `PUT /deals/{id}` 直接改，只能走 `/win`、`/lose` 两个动作端点（否则订单生成、`closed_at`、冻结都会被绕过）。

**冻结矩阵（N6/N7，服务端逐条强制）**

| 商机状态 | `PUT /deals/{id}` | `POST /follow-ups`(object_type=deal) | `POST /deals/{id}/win` | `POST /deals/{id}/lose` | 客户页新建商机 |
|---|---|---|---|---|---|
| `confirm/quote/negotiate`（进行中） | ✅ 可改 | ✅ 可加 | ✅ | ✅ | — |
| `won`（已绑订单） | ❌ 409 `deal_frozen` | ❌ 409 `deal_frozen` | ❌ 409 `deal_frozen` | ❌ 409 `deal_frozen` | ✅（同一客户可开新商机，D2） |
| `lost`（流失冻结） | ❌ 409 `deal_frozen` | ❌ 409 `deal_frozen` | ❌ 409 `deal_frozen` | ❌ 409 `deal_frozen` | ✅（新商机可带 `source_lost_deal_id` 关联旧单，N7） |

**赢单 `POST /deals/{id}/win`（单事务，7 步，顺序不能换）**

1. `SELECT ... FROM deals WHERE id=?` → 不存在 404 `not_found`；`stage IN ('won','lost')` → 409 `deal_frozen`。
2. `SELECT 1 FROM orders WHERE deal_id=?` → 已存在 409 `order_exists`（双保险，DB 还有 `UNIQUE(deal_id)`）。
3. `deal.amount <= 0` → 400 `invalid_amount`（订单总额继承商机金额，R4；0 元订单无意义）。
4. 生成 `order_no = SO-YYYYMMDD-NNN`（§2.8 发号）。
5. `INSERT INTO orders (order_no, customer_id, deal_id, product_type, model, spec, amount, status='pending_payment', owner, created_at, updated_at)`。
6. `UPDATE deals SET stage='won', closed_at=<本地时间>, order_id=<新订单id>, updated_at=now`。
7. `INSERT INTO order_status_log (order_id, from_status=NULL, to_status='pending_payment', note='商机赢单生成订单')`。

出参：`{"deal": DealOut, "order": OrderDetailOut}`。前端赢单成功后直接跳 `#/orders/{order.id}`。
> 赢单后"所有跟踪在订单上进行"（N6）：订单跟进用 `follow_ups(object_type='order')`，订单详情页的「记沟通」按钮走统一跟进端点。

**流失 `POST /deals/{id}/lose`**

- 入参 `{lost_reason: <DEAL_LOST_REASON>, lost_reason_other?: str}`；`lost_reason='other'` 时 `other` 必填（≤100 字）。
- `stage IN ('won','lost')` → 409 `deal_frozen`（已赢单不能改流失，R1：退款退货走售后单）。
- 动作：`UPDATE deals SET stage='lost', lost_reason=?, lost_reason_other=?, closed_at=NULL, updated_at=?`。
  **注意**：从 `won` 转 `lost` 的路径被冻结规则堵死，所以"清空 `closed_at`"只在历史脏数据修复时用到；仍写上一行以保持幂等。
- **不回写订单**（N7 反向：流失商机无订单）。

**重启（N7）**：不设 `restart` 端点。前端在客户 360 点「新建商机」，`POST /deals` 带 `source_lost_deal_id=<旧流失商机id>`。服务端校验旧商机 `stage='lost'` 且 `customer_id` 相同，否则 409 `source_deal_not_lost`。

### 2.3 线索状态机与转化（D4 / N1 / N2 / I4）

**状态机**：`new → following → converted` / `invalid`（`invalid` 与 `converted` 都是终态，不可回退）。

| 动作 | 端点 | 从 | 到 | 校验 |
|---|---|---|---|---|
| 建线索 | `POST /leads` | — | `new` | 手机/微信至少一个（400 `missing_contact`）；来源必填（400 `invalid_enum`） |
| 记跟进 | `POST /follow-ups`(object_type=lead) | `new` | `following`（自动） | 内容非空；可同时更新 `intent_level` |
| 转化 | `POST /leads/{id}/convert` | `new`/`following` | `converted` | 见下 |
| 置失效 | `POST /leads/{id}/invalidate` | `new`/`following` | `invalid` | 必选原因（`other` 需文本） |
| 改线索 | `PUT /leads/{id}` | `new`/`following` | — | 终态改 → 409 `lead_closed` |

**转化流程（单事务 8 步）**

```
1  取线索，status ∈ (new, following) 否则 409 lead_closed
2  线索手机与微信都为空 → 400 missing_contact
3  去重查询：SELECT id,name,phone,wechat FROM customers
             WHERE (phone = ? AND ? <> '') OR (wechat = ? AND ? <> '')
     命中时：
       mode="link" + link_customer_id ∈ 命中集合        → linked（不建客户）
       mode="new"  + force_new=true                      → forced（强制新建）
       mode="new"  + force_new 非 true                    → 409 duplicate_customer
                                                            （body 带 matches[]，D4 的"提示"）
       mode="link" + link_customer_id 不在命中集合/不存在   → 400 invalid_link_customer
4  mode=link  → customer = 已存在客户（不改其档案，只挂商机）
   mode=new   → INSERT customers(
                  name = lead_type='company' ? company_name : lead.name,
                  company_name = lead.company_name,
                  phone, wechat, location, house_note = lead.note,
                  customer_type = lead.lead_type,
                  source = lead.source, source_other = lead.source_other,
                  intent_level = lead.intent_level,          -- N2 顺延
                  owner = lead.owner,
                  created_at = lead.created_at,              -- 继承线索创建时间
                  updated_at = now)
                mode=new 且 lead_type='company' →
                  INSERT customer_contacts(name=lead.name, phone, wechat, is_primary=1)  -- I4 只带主联系人
5  INSERT deals(customer_id, title, product_type, model, spec, amount,
                 stage='confirm', owner, created_at=now, updated_at=now)
6  档案迁移：
     INSERT OR IGNORE INTO customer_tags(customer_id, tag_id)
       SELECT ?, tag_id FROM lead_tags WHERE lead_id = ?
     UPDATE follow_ups SET object_type='customer', object_id=<customer_id>,
            customer_id=<customer_id>
      WHERE object_type='lead' AND object_id=<lead_id>      -- 历史跟进全部搬到客户名下
7  UPDATE leads SET status='converted', converted_customer_id=?, converted_deal_id=?,
        updated_at=? WHERE id=?
8  COMMIT
```

**入参**

```json
{
  "mode": "new",                       // new | link
  "force_new": false,                  // mode=new 且已有匹配客户时必须 true
  "link_customer_id": null,            // mode=link 必填
  "deal": {
    "title": "王先生-天窗首单",          // 必填，≤64
    "product_type": "天窗",             // 天窗 | 天幕（沿用 V1 自由文本，字典未定）
    "model": "平移",
    "spec": "1200*1400",
    "amount": 12800.00                 // 必填，>0，两位小数
  }
}
```

**出参**：`{"lead": LeadOut, "customer": CustomerOut, "deal": DealOut, "dedupe": "none"|"linked"|"forced"}`

**预检端点**（前端弹"客户已存在"用）：`GET /leads/convert-check?phone=&wechat=` → `{"has_match": true, "matches": [{"customer_id": 3, "name": "陈明", "phone": "...", "wechat": null, "deals_total": 1, "lifecycle": "dealing"}]}`

> N1 显式落地点：**转化不校验意向等级**。`intent_level=none` 的线索照样能建商机、能转化。

### 2.4 售后 3 态流（D7 / I2 / N8）

```
pending ──开始处理──▶ processing ──完成(填处理结果)──▶ done
                              └────拒绝(填拒绝原因)──▶ rejected
```

| 动作 | 端点 | 从 → 到 | 必填 | 副作用 |
|---|---|---|---|---|
| 建售后单 | `POST /aftersales` | — → `pending` | `order_id`、`type`、`description`（≤2000） | 发号 `AS-YYYYMMDD-NNN`；`customer_id` 从订单取 |
| 开始处理 | `POST /aftersales/{id}/start` | `pending` → `processing` | 无 | 写 `aftersale_status_log` |
| 完成 | `POST /aftersales/{id}/finish` | `processing` → `done` | `result`（≤1000） | 写 `result`、`closed_at`、日志 |
| 拒绝 | `POST /aftersales/{id}/reject` | `pending`/`processing` → `rejected` | `reject_reason`（≤500） | 写 `reject_reason`、`closed_at`、日志 |

- **售后不回写订单状态**（I2）：退款/换货完成与否只记在售后单，`orders.status` 永远是 `completed` 或更早的态。
- 终态（`done`/`rejected`）再操作 → 409 `aftersale_closed`（Q4：不提供重开）。
- 售后沟通走统一跟进：`object_type='aftersale'`，`customer_id` 冗余写订单客户。

**SLA（N8）**：`pending` 且 `julianday(date('now','localtime')) - julianday(date(created_at)) > 3` → 工作台红色提醒。SQL：

```sql
SELECT a.id, a.no, a.type, a.created_at,
       CAST(julianday(date('now','localtime')) - julianday(date(a.created_at)) AS INTEGER) AS days_pending,
       o.order_no, c.name AS customer_name
  FROM aftersales a
  JOIN orders o    ON o.id = a.order_id
  JOIN customers c ON c.id = a.customer_id
 WHERE a.status = 'pending'
   AND julianday(date('now','localtime')) - julianday(date(a.created_at)) > 3
 ORDER BY a.created_at ASC;
```

> 阈值 3 是常量 `AFTERSALE_SLA_DAYS = 3`（`app/enums.py`），不写死在 SQL 里（用参数绑定）。

### 2.5 统一跟进模型（§3.8）

| 项 | 规则 |
|---|---|
| 挂载键 | `follow_ups(object_type, object_id)`；`object_type ∈ FOLLOW_OBJECT` |
| 冗余列 | `customer_id`（客户 360 聚合用，线索期为空）、`deal_id`（V1 兼容与商机页筛选） |
| 一条只挂一个对象 | 端点只接受一组 `object_type + object_id`；传了 `customer_id` 但没 `object_type` → 归一成 `('customer', customer_id)`（V1 兼容） |
| 可加跟进的对象状态 | `lead`: new/following；`deal`: confirm/quote/negotiate；`customer`/`order`/`aftersale`: 任何时候（终态也可补记沟通） |
| 商机冻结后 | 409 `deal_frozen`（N6/N7） |
| 线索转化后 | 409 `lead_closed`（跟进已迁到客户，见 §2.3 第 6 步） |
| 照片 | ≤3 张、单张 ≤20MB、仅图片（复用 `app/storage.py` 的 `ext_and_mime/MAX_PHOTO_BYTES`） |
| 意向等级 | `object_type=customer` 或 `lead` 时带 `intent_level` → 顺带更新对应表的 `intent_level`（I3） |
| 下次跟进 | `next_date` 只收 `YYYY-MM-DD`；过期日期允许（补录昨天拜访） |
| 订单/售后的跟进 | 是"状态跃迁日志 + 沟通备注"，不参与 `next_date` 待办聚合（业务 §3.8 末条） |

### 2.6 API 通用约定

| 项 | 定稿 |
|---|---|
| 前缀 | `/api/crm`（沿用 V1；nginx 既有 `location /api/crm/` 反代到 `127.0.0.1:8010`，不新增 location） |
| 鉴权 | HttpOnly Cookie `crm_sid`，12h 固定过期，`SameSite=Lax`；除 `/health`、`/login` 外全部 `Depends(require_auth)` |
| 出参 | JSON；时间字段一律字符串；金额 `round(x, 2)` 的 float；`*_label` 字段给中文 |
| 分页 | `page`（≥1，默认 1）+ `size`（1–100，默认 20），出参 `{items, total, page, size}`。**例外**：`GET /deals`、`GET /follow-ups`、`GET /tags`、`GET /carriers` 保持 V1 的"直接返回数组"，避免破坏 V1 前端 |
| 枚举校验 | 非法枚举 → **400** `invalid_enum`（不是 pydantic 的 422），消息里列出合法值（沿用 V1 `deals.py` 的做法） |
| 错误体 | `{"detail": "<中文人话>", "code": "<机器码>"}`，`detail` 仍是字符串 → V1 前端的 toast 逻辑不用改 |

**错误码目录**（`code` 全表，前端按它分支，别再解析中文）

| HTTP | `code` | 触发场景 |
|---|---|---|
| 400 | `invalid_enum` | 枚举值非法 |
| 400 | `validation_failed` | 长度/格式/必填不满足 |
| 400 | `missing_contact` | 线索手机与微信都为空 |
| 400 | `invalid_amount` | 金额 ≤0 或超上限 |
| 400 | `amount_exceeds_total` | 押金 > 订单总额 |
| 400 | `amount_exceeds_remaining` | 尾款 > 总额 − 已收押金 |
| 400 | `screenshot_required` | 押金/尾款跃迁没带截图 |
| 400 | `tracking_required` | 发货没填运单号 |
| 400 | `carrier_required` | 物流模式=carrier 却没选物流公司 |
| 400 | `result_required` / `reject_reason_required` | 售后完成/拒绝缺必填 |
| 400 | `invalid_link_customer` | 转化时 `link_customer_id` 不在去重命中集合 |
| 400 | `fill_required` | 其它"必须填 X"（消息写清哪个字段） |
| 401 | `unauthenticated` | 无/过期会话 |
| 404 | `not_found` | 对象不存在 |
| 405 | `order_create_forbidden` | 直接 `POST /orders`（N6：只能由商机赢单生成） |
| 409 | `illegal_transition` | 订单/售后状态不允许该动作（带 `current_status`） |
| 409 | `deal_frozen` | 商机已赢单/流失 |
| 409 | `lead_closed` | 线索已转化/已失效 |
| 409 | `order_exists` | 该商机已有订单 |
| 409 | `duplicate_customer` | 转化去重命中且未明确选择（带 `matches[]`） |
| 409 | `customer_has_orders` | 删客户但名下有订单/售后 |
| 409 | `carrier_in_use` | 删被订单引用的物流公司 |
| 409 | `carrier_exists` | 物流公司重名 |
| 409 | `aftersale_closed` | 售后单已终态 |
| 409 | `source_deal_not_lost` | 关联的"来源流失商机"不是流失态/不属同一客户 |
| 413/400 | `file_too_large` / `not_image` | 上传超 20MB / 非图片 |

**实现方式**（`app/errors.py`，新增，约 25 行）：

```python
class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, **extra):
        super().__init__(status_code=status_code, detail=message)
        self.code, self.extra = code, extra

def install_error_handler(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handler(_request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code,
                            content={"detail": exc.detail, "code": exc.code, **exc.extra})
```

### 2.7 端点清单（47 个新增/变更 + V1 原样保留 8 个）

> 标注 `[V1]` = 出参只增不改；`[新]` = V2 新增；`[改]` = 行为收紧（错误码变了，成功路径不变）。

#### 线索（7）

| 方法 | 路径 | 入参 | 出参 | 主要错误 |
|---|---|---|---|---|
| GET | `/leads` [新] | `status?`,`source?`,`intent_level?`,`search?`(手机/微信/姓名/地址),`page`,`size` | `{items:[LeadOut],total,page,size}` | 400 |
| POST | `/leads` [新] | `{name?,phone?,wechat?,lead_type,company_name?,source,source_other?,location?,note?,intent_level?,tags[]}` | `LeadOut` | 400 `missing_contact`/`invalid_enum` |
| GET | `/leads/{id}` [新] | — | `LeadDetailOut`（含 `tags[]`、`follow_ups[]`） | 404 |
| PUT | `/leads/{id}` [新] | 同 POST，全可选 | `LeadOut` | 404 / 409 `lead_closed` |
| POST | `/leads/{id}/invalidate` [新] | `{invalid_reason, invalid_reason_other?}` | `LeadOut` | 404 / 409 `lead_closed` / 400 |
| GET | `/leads/convert-check` [新] | `phone?`,`wechat?` | `{has_match,matches[]}` | 400 `missing_contact` |
| POST | `/leads/{id}/convert` [新] | 见 §2.3 | `{lead,customer,deal,dedupe}` | 400 / 404 / 409 `lead_closed`/`duplicate_customer` |

#### 客户（10，其中 5 个 V1 变更）

| 方法 | 路径 | 入参 | 出参 | 主要错误 |
|---|---|---|---|---|
| GET | `/customers` [V1] | 原 `search/tag/page/size` + `customer_type?`,`source?`,`lifecycle?`,`intent_level?` | 原 `{items,total,page,size}`，item 加 `customer_type/company_name/source/intent_level/lifecycle/contacts_count` | 400 |
| POST | `/customers` [V1] | 原入参 + `customer_type?`,`company_name?`,`source?`,`source_other?`,`intent_level?`,`contacts[]?` | `CustomerOut`（加列） | 400 |
| GET | `/customers/{id}` [V1] | — | `CustomerDetailOut`（V1 的 `deals[]`/`follow_ups[]` 保留 + `contacts[]`） | 404 |
| PUT | `/customers/{id}` [V1] | 原入参 + 新列 | `CustomerOut` | 400/404 |
| DELETE | `/customers/{id}` [改] | — | `{ok,id}` | 404 / **409 `customer_has_orders`** |
| GET | `/customers/{id}/360` [新] | — | `Customer360Out` | 404 |
| GET/POST | `/customers/{id}/contacts` [新] | POST `{name,phone?,wechat?,is_primary?}` | `list[ContactOut]` / `ContactOut` | 400/404 |
| PUT/DELETE | `/contacts/{id}` [新] | 同上 | `ContactOut` / `{ok}` | 404 |

`Customer360Out` 结构（前端一页看全的唯一数据源）：

```json
{
  "customer": { "...": "CustomerOut 全部字段" },
  "lifecycle": "dealing",
  "contacts": [{"id":1,"name":"王先生","phone":"139...","wechat":null,"is_primary":1}],
  "deals": [{"id":2,"title":"王先生-天窗首单","stage":"won","stage_label":"赢单","amount":12800.0,"order_id":1}],
  "orders": [{"id":1,"order_no":"SO-20261030-001","status":"completed","status_label":"已完成","amount":12800.0}],
  "aftersales": [{"id":1,"no":"AS-20261030-001","type":"repair","type_label":"维修","status":"done"}],
  "timeline": [{"kind":"order_status","at":"2026-10-30T22:40:00+08:00","title":"已支付押金","ref":{"order_id":1}}],
  "stats": {"deal_count":2,"won_amount":17800.0,"order_count":2,"completed_amount":12800.0,"aftersale_open":1}
}
```

#### 商机（6，其中 2 个 V1 变更）

| 方法 | 路径 | 入参 | 出参 | 主要错误 |
|---|---|---|---|---|
| GET | `/deals` [V1] | 原 `customer_id/stage` + `limit?` | **`list[DealOut]`**（保持数组，V1 前端依赖） | 400 `invalid_stage` |
| POST | `/deals` [V1] | 原入参 + `title?`,`source_lost_deal_id?`；`stage` 默认 `confirm` | `DealOut` | 400/404/409 `source_deal_not_lost` |
| GET | `/deals/{id}` [新] | — | `DealDetailOut`（deal + `follow_ups[]` + `order_id/order_no` + `customer{id,name}`） | 404 |
| PUT | `/deals/{id}` [改] | 原入参；`stage` 只接受 `confirm/quote/negotiate` | `DealOut` | 404 / 409 `deal_frozen` / 400 `invalid_stage`（传 won/lost 时消息指向 `/win`、`/lose`） |
| POST | `/deals/{id}/win` [新] | `{}` | `{deal,order}` | 409 `deal_frozen`/`order_exists` / 400 `invalid_amount` |
| POST | `/deals/{id}/lose` [新] | `{lost_reason,lost_reason_other?}` | `DealOut` | 409 `deal_frozen` / 400 `invalid_enum` |

#### 订单（9）

| 方法 | 路径 | 入参 | 出参 | 主要错误 |
|---|---|---|---|---|
| GET | `/orders` [新] | `status?`,`customer_id?`,`page`,`size` | `{items:[OrderOut],total,page,size}` | 400 |
| GET | `/orders/{id}` [新] | — | `OrderDetailOut` | 404 |
| POST | `/orders` [新] | — | — | **405 `order_create_forbidden`**（N6 显式拒绝，比 404 好排查） |
| POST | `/orders/{id}/pay-deposit` [新] | multipart: `amount`, `note?`, `screenshots[]`(1–3) | `OrderDetailOut` | 409 `illegal_transition` / 400 |
| POST | `/orders/{id}/start-production` [新] | `{}` 或 `{note?}` | `OrderDetailOut` | 409 |
| POST | `/orders/{id}/pay-balance` [新] | multipart: `amount`, `note?`, `screenshots[]`(1–3) | `OrderDetailOut` | 409 / 400 |
| POST | `/orders/{id}/ready-to-ship` [新] | `{}` 或 `{note?}` | `OrderDetailOut` | 409 |
| POST | `/orders/{id}/ship` [新] | `{logistics_mode, carrier_id?, tracking_no, note?}` | `OrderDetailOut` | 409 / 400 `tracking_required`/`carrier_required` / 404 |
| POST | `/orders/{id}/complete` [新] | `{}` 或 `{note?}` | `OrderDetailOut` | 409 |

`OrderDetailOut`：

```json
{
  "order": {"id":1,"order_no":"SO-20261030-001","customer_id":3,"deal_id":2,
            "customer_name":"王先生","product_type":"天窗","model":"平移","spec":"1200*1400",
            "amount":12800.0,"deposit_paid":3800.0,"balance_paid":9000.0,"unpaid":0.0,
            "logistics_mode":"carrier","carrier_id":1,"carrier_name":"德邦物流",
            "tracking_no":"DP20261030001","shipped_at":"...","completed_at":"...",
            "status":"completed","status_label":"已完成",
            "next_status":null,"created_at":"...","updated_at":"..."},
  "status_log": [{"id":1,"from_status":null,"to_status":"pending_payment","to_status_label":"待支付",
                  "deposit_paid":null,"balance_paid":null,"tracking_no":null,
                  "screenshots":[],"note":"商机赢单生成订单","created_at":"..."}],
  "aftersales": [{"id":1,"no":"AS-20261030-001","type":"repair","status":"done"}]
}
```

> `order.next_status` 由后端按 `ORDER_FLOW` 算，前端**只认这个字段**渲染"下一步"按钮，杜绝前后端各写一份状态机。

#### 售后（6）

| 方法 | 路径 | 入参 | 出参 | 主要错误 |
|---|---|---|---|---|
| GET | `/aftersales` [新] | `status?`,`order_id?`,`customer_id?`,`sla_overdue?`,`page`,`size` | `{items:[AftersaleOut],total,page,size}` | 400 |
| POST | `/aftersales` [新] | `{order_id,type,type_other?,description}` | `AftersaleOut` | 404 / 400 |
| GET | `/aftersales/{id}` [新] | — | `AftersaleDetailOut`（含 `order` 摘要、`status_log[]`、`follow_ups[]`） | 404 |
| POST | `/aftersales/{id}/start` [新] | `{}` | `AftersaleOut` | 409 |
| POST | `/aftersales/{id}/finish` [新] | `{result}` | `AftersaleOut` | 409 / 400 `result_required` |
| POST | `/aftersales/{id}/reject` [新] | `{reject_reason}` | `AftersaleOut` | 409 / 400 `reject_reason_required` |

#### 物流（5）

| 方法 | 路径 | 入参 | 出参 | 主要错误 |
|---|---|---|---|---|
| GET | `/carriers` [新] | `active_only?` | `list[CarrierOut]` | — |
| POST | `/carriers` [新] | `{name,contact?,phone?,note?}` | `CarrierOut` | 409 `carrier_exists` / 400 |
| PUT | `/carriers/{id}` [新] | `{name?,contact?,phone?,note?,is_active?}` | `CarrierOut` | 404 / 409 `carrier_exists` |
| DELETE | `/carriers/{id}` [新] | — | `{ok}` | 404 / 409 `carrier_in_use` |
| GET | `/logistics/shipments` [新] | `status?`,`only_unfinished?` | `list[ShipmentOut]` | — |

#### 跟进（3，其中 2 个 V1 变更）

| 方法 | 路径 | 入参 | 出参 | 主要错误 |
|---|---|---|---|---|
| POST | `/follow-ups` [V1] | multipart：`object_type`,`object_id`,`method?`,`content`,`next_date?`,`intent_level?`,`photos[]`；**兼容** `customer_id`,`deal_id`,`stage` | `FollowUpItemOut`（V1 键 + `object_type/object_id/method/intent_level`） | 400 / 404 / 409 `deal_frozen`/`lead_closed` |
| GET | `/follow-ups` [V1] | 原 `customer_id/deal_id` + `object_type`,`object_id`,`limit?` | `list[FollowUpItemOut]` | 400 |
| DELETE | `/follow-ups/{id}` [V1] | — | `{ok,id}` | 404 |

#### 工作台（1，V1 键只增不改）

| 方法 | 路径 | 出参新增键 | 说明 |
|---|---|---|---|
| GET | `/dashboard` [V1] | `followups_today[五类]`、`orders{by_status,totals}`、`recent_orders[10]`、`aftersale_sla_alerts[]` | 原 `today_followups`（客户/商机两类）、`month_won`、`stats` **逐字保留**，V1 首页不改也能渲染 |

```json
{
  "today_followups": [ "…V1 原样…" ],
  "month_won": {"count": 1, "amount": 12800.0},
  "stats": { "…V1 原样…" },
  "followups_today": [
    {"object_type":"lead","object_id":1,"object_label":"王先生","title":"微信沟通，约周六量尺",
     "next_date":"2026-10-28","days_overdue":2,"overdue":true,"link":"#/leads/1"}
  ],
  "orders": {
    "by_status": {"pending_payment":{"count":0,"amount":0.0}, "…7 个态全给…":{}},
    "totals": {"count":2,"amount":17800.0,"paid":12800.0,"unpaid":5000.0}
  },
  "recent_orders": [{"id":1,"order_no":"SO-20261030-001","customer_name":"王先生",
                     "amount":12800.0,"status":"completed","status_label":"已完成","created_at":"…"}],
  "aftersale_sla_alerts": [{"id":2,"no":"AS-20261030-002","days_pending":4,
                            "order_no":"SO-20261030-001","customer_name":"王先生"}]
}
```

#### V1 完全保留、本次不动的端点（8）

`POST /login`、`POST /logout`、`GET /me`、`GET /tags`、`GET /attachments/{id}`、`POST /import/preview`、`POST /import/commit`、`GET /health`。

### 2.8 关键实现约定（写进 `app/services.py`，路由层只做取参与错误映射）

**发号（订单/售后）**

```python
def next_no(conn, table: str, column: str, prefix: str, day: str) -> str:
    """SO-20261030-001 / AS-20261030-001。单用户单 worker，事务内 MAX+1 足够；
    UNIQUE 约束是最后一道保险（并发撞号 → IntegrityError → 重试一次再报 409）。"""
    like = f"{prefix}{day}-%"
    row = conn.execute(
        f"SELECT COALESCE(MAX(CAST(substr({column}, -3) AS INTEGER)), 0) AS n "
        f"FROM {table} WHERE {column} LIKE ?", (like,)).fetchone()
    return f"{prefix}{day}-{int(row['n']) + 1:03d}"
```

- `day = datetime.now().strftime('%Y%m%d')`（本地时区，与"今天"口径一致）。
- 调用点必须已在 `BEGIN IMMEDIATE` 事务内（`db_conn()` 默认 `isolation_level` 即隐式事务；发号前先 `SELECT` 会拿共享锁，因此**先执行一次空写或直接 `BEGIN IMMEDIATE`**，避免并发下重号）。

**截图上传的两阶段落盘**（避免事务回滚留垃圾文件）

1. 校验并读入内存（≤3 张、≤20MB、仅图片）——复用 V1 `followups._read_photos` 的写法，抽到 `app/services.py: read_images(...)`。
2. 事务内先 `INSERT attachments` 拿 id，再写磁盘到 `uploads/YYYY/MM/DD/<uuid>.<ext>`；若磁盘写失败 → 抛错 → 事务回滚（DB 无残留），已写的文件由下一次清理任务兜底（V1 已有"物理文件留备份清理"的约定，不新增 GC）。

**金额**

- 入参 `Decimal` → `float(quantize(Decimal('0.01')))`；出参统一 `round(x, 2)`。
- 校验顺序：`amount > 0` → `amount <= 剩余可收` → 才落库。
- 汇总 SQL 一律 `ROUND(COALESCE(SUM(amount),0), 2)`。

**列表查询防 N+1**：沿用 V1 做法（`_tags_for`/`_photos_for` 一次批量查回）。V2 新增 `_contacts_for(customer_ids)`、`_screenshots_for(log_ids)` 两个批量 helper。

**查询口径统一放 `app/queries.py`**：客户生命周期、订单未收金额、SLA、工作台聚合，每个 SQL 只写一次，路由与测试都 import 它（避免 `/customers` 和 `/customers/{id}/360` 算出两种生命周期）。

---

## 3. 升级 / 迁移方案

### 3.1 策略与版本

| 项 | 定稿 |
|---|---|
| 迁移形态 | **代码内嵌迁移**：`app/migrations.py`（新增模块），`run_migrations()` 在 lifespan 里紧跟 `ensure_schema()` 执行 |
| 版本 | 单版本 `v2_001`（`schema_migrations.version`）+ `PRAGMA user_version = 2`（给运维一眼看版本） |
| 幂等 | 62 条语句逐条带状态 guard；重跑只走未完成的语句（实测重跑 22 条被跳过，数据不变） |
| 中断安全 | 每条语句自动提交，重跑从中间态收敛（实测 15 个切点全部收敛，见 §3.6） |
| 数据保护 | 迁移前 `sqlite3.backup()`；6 张业务表迁移前后行数比对；`DROP` 前比对 `COUNT(*)`；结束跑 `foreign_key_check` |
| `schema.py` | **不改一行**。V1 的 `ENSURE_SQL` 全是 `CREATE ... IF NOT EXISTS`，重放无副作用（实测 19 条） |
| 停机窗口 | 单用户系统，实测迁移 <1s，重启 <3s（§3.6） |
| 回滚成本 | **零 DDL 回滚**：全部增量 + 两表重建保留旧列名 → 回滚只需 `git revert` + `systemctl restart`，V1 代码在已迁移库上照常运行（实测 V1 19 条 DDL 重放 + V1 写法 INSERT 均可） |

### 3.2 启动时序（`app/main.py` 的唯一改动）

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema(settings.db_path)      # V1 建表（IF NOT EXISTS，不变）
    run_migrations(settings.db_path)     # V2 增量（幂等，v2_001）
    settings.uploads_path.mkdir(parents=True, exist_ok=True)
    seed_admin_if_needed()
    ...
```

**为什么是这个顺序**：全新库由 `ensure_schema` 建出 V1 九表（含 `follow_ups.customer_id NOT NULL` 与 `attachments.follow_up_id NOT NULL`），随后 `run_migrations` 用同一套 ALTER/重建把结构推到终态。这样**全新装库与存量升级走同一条代码路径**，结构收敛（实测两库 18 张表的列/索引/外键/触发器逐项一致，见 §3.6）。反过来（先迁移）在空库上会因为"表不存在"让 ALTER 全部跳过，终态缺列。

**失败即拒启**：`run_migrations` 任何断言失败都抛异常 → uvicorn 启动失败 → systemd `Restart=always` 会重试并在 5 分钟 10 次后放弃（`StartLimitBurst=10` 已配）。这是有意的：宁可服务起不来，也不能带着半迁移的库对外服务。

### 3.3 迁移脚本（`app/migrations.py`，已实测；全文另存 `/opt/data/crm/docs/planner-v2-migrations_v2.py`）

**语句分组（62 条，顺序即执行顺序）**

| 组 | 语句数 | 内容 | 幂等手段 |
|---|---|---|---|
| 0 | 1 | `schema_migrations` | `IF NOT EXISTS` |
| 1 | 7 | `leads` + `lead_tags` + 5 索引 | `IF NOT EXISTS` |
| 2 | 8 | `customers` 6 列 ALTER + `customer_contacts` + 索引 | `has_column` guard |
| 3 | 7 | `deals` 6 列 ALTER + 索引 | `has_column` guard |
| 4 | 2 | `carriers` + 索引 | `IF NOT EXISTS` |
| 5 | 6 | `orders` + `order_status_log` + 4 索引 | `IF NOT EXISTS` |
| 6 | 6 | `aftersales` + `aftersale_status_log` + 5 索引 | `IF NOT EXISTS` |
| 7 | 9 | `follow_ups` 重建（建表/复制/DROP/RENAME/清理） | 三态 guard：`final_ok` / 行数比对 |
| 8 | 6 | `attachments` 重建（建表/复制/DROP/RENAME/清理） | 同上 |
| 9 | 7 | 两表索引重建 + 2 个兼容触发器 | `IF NOT EXISTS` |
| 10 | 4 | 跟进 object 回填、`deals.stage` 映射、客户来源/类型回填 | `WHERE` 条件天然幂等 |
| 11 | 2 | 版本落账 + `user_version` | `INSERT OR IGNORE` |

**驱动骨架（完整实现见脚本文件，这里给出必须照抄的 5 个机关）**

```python
conn = sqlite3.connect(db_path, timeout=15, isolation_level=None)
conn.execute("PRAGMA foreign_keys=OFF")      # ① 必须在 BEGIN 之前：重建期关外键，
                                             #    否则 DROP 父表按 CASCADE 误删子表行
conn.execute("PRAGMA busy_timeout=10000")
before = {t: row_count(conn, t) for t in COUNT_STABLE_TABLES}   # ② 迁移前行数快照
conn.execute("BEGIN IMMEDIATE")              # ③ 一条事务包住全部 DDL/DML
for label, guard, sql in STATEMENTS:
    if guard is not None and guard(conn):     # ④ guard=True 表示"已完成，跳过"
        continue
    conn.execute(sql)                         #    失败即带 [label] 抛错，整笔回滚
conn.execute("COMMIT")
conn.execute("PRAGMA foreign_keys=ON")       # ⑤ 提交后开外键 + foreign_key_check
assert not conn.execute("PRAGMA foreign_key_check").fetchall()
assert before == {t: row_count(conn, t) for t in COUNT_STABLE_TABLES}   # 行数必须一致
```

**重建的三态 guard（`follow_ups` / `attachments` 共用同一工厂）**

| 语句 | 跳过条件（guard 返回 True） | 说明 |
|---|---|---|
| `CREATE TABLE xxx_new` | 终态已达成，或旧表不存在 | 全新库/已迁移库都跳过 |
| `INSERT ... SELECT ... FROM xxx` | 已复制过（`count(new) >= count(old)`） | 防重复插入 |
| `DROP TABLE xxx` | 终态已达成；**行数不相等则抛错** | 数据保护红线，不是跳过而是失败 |
| `ALTER TABLE xxx_new RENAME TO xxx` | 终态已达成，或 `_new` 不存在/旧表还在 | 收敛"已 DROP 未 RENAME"的中断态 |
| `DROP TABLE IF EXISTS xxx_new` | 残留表非空时不删 | 收敛"终态已成就但残留空表" |

> 实测覆盖了这 5 个 guard 的全部中断组合（§3.6 的 15 个切点），其中包括"已 DROP 旧表、还没 RENAME"这个最危险的中断点。

**CLI**

```bash
# 升级生产（自动备份到 /opt/data/crm/backups/crm-pre-v2-<时间戳>.db）
PYTHONPATH=/opt/data/crm /usr/bin/python3 -m app.migrations

# 在副本上演练（不备份、不碰生产）
cp /opt/data/crm/crm.db /tmp/crm-v2-mig.db
CRM_DB=/tmp/crm-v2-mig.db PYTHONPATH=/opt/data/crm /usr/bin/python3 -m app.migrations --no-backup
```

### 3.4 存量数据映射（数据量：2 客户 / 1 商机 / 2 跟进 / 1 标签 / 0 附件）

| 对象 | 迁移动作 | 断言（§5.5 会查） |
|---|---|---|
| `customers`（2 行） | `customer_type='personal'`、`source='stock'`；`intent_level/company_name/owner` 留 NULL | 2 行，类型全 personal，来源全 stock |
| `deals`（1 行，`stage='lead'`） | `stage='confirm'`（需求确认）；`title` 留 NULL（展示回退 `product_type + model`） | `stage='confirm'` |
| `follow_ups`（2 行） | 按 `deal_id` 派生：有 `deal_id` → `('deal', deal_id)`，否则 `('customer', customer_id)`；`method` 留 NULL | id=1 → `('customer',1)`；id=2 → `('deal',1)` |
| `tags`/`customer_tags`（1/1） | 不动 | 1/1 |
| `attachments`（0 行） | 走重建路径（0 行复制），`object_type/object_id` 列就位 | 0 行且列存在 |
| `sessions`（1 行） | 不动（升级后仍然有效，用户无感） | 1 行 |
| 存量商机**不补订单** | I6 已确认：保持"进行中"，可继续跟进；订单从 V2 首笔赢单起算 | `orders` 0 行 |

### 3.5 升级执行步骤（ops 照抄，含每步验证）

```bash
# ── 步骤 0：预检（不改任何东西）
cd /opt/data/crm
systemctl is-active crm-api.service                      # 期望 active
curl -s http://127.0.0.1:8010/health                     # 期望 {"status":"ok",...}
/usr/bin/python3 - <<'PY'
import sqlite3; c=sqlite3.connect('/opt/data/crm/crm.db')
for t in ('customers','deals','follow_ups','tags','customer_tags','attachments'):
    print(t, c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
print('user_version', c.execute('PRAGMA user_version').fetchone()[0])
PY
# 记下这 6 个数字：升级后必须完全一致（预期 2 / 1 / 2 / 1 / 1 / 0，user_version=0）

# ── 步骤 1：副本演练（副本库，绝不碰生产）
cp /opt/data/crm/crm.db /tmp/crm-v2-dryrun.db
CRM_DB=/tmp/crm-v2-dryrun.db PYTHONPATH=/opt/data/crm \
  /usr/bin/python3 -m app.migrations --no-backup
# 期望末行 OK v2_001 ...；再跑一次必须收敛（幂等）

# ── 步骤 2：备份（迁移脚本内部也会备份，这里再留一份"部署前镜像"）
mkdir -p /opt/data/crm/backups
cp /opt/data/crm/crm.db /opt/data/crm/backups/crm-pre-v2-manual-$(date +%Y%m%d-%H%M%S).db

# ── 步骤 3：停服 → 迁移 → 起服（窗口约 5s；必须先停，避免旧代码在迁移中途写库）
systemctl stop crm-api.service
PYTHONPATH=/opt/data/crm CRM_DB=/opt/data/crm/crm.db \
  /usr/bin/python3 -m app.migrations
systemctl start crm-api.service

# ── 步骤 4：验收（全绿才算完成，逐条对照 §5.5 断言表）
curl -s http://127.0.0.1:8010/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/api/crm/me           # 401 = 鉴权正常
curl -s -c /tmp/crm.jar -X POST http://127.0.0.1:8010/api/crm/login \
     -H 'Content-Type: application/json' -d '{"username":"chen","password":"<真实密码>"}' 
curl -s -b /tmp/crm.jar http://127.0.0.1:8010/api/crm/customers | head -c 300         # 2 个客户
curl -s -b /tmp/crm.jar http://127.0.0.1:8010/api/crm/deals                           # stage=confirm
curl -s -b /tmp/crm.jar http://127.0.0.1:8010/api/crm/dashboard | head -c 400
# 页面：浏览器打开 http://10.113.9.77:8000/crm/ ，登录后逐个点 §4.2 的 15 个路由
```

> **密码**：生产密码只在 `/opt/data/crm/.env` 的 `ADMIN_PASSWORD`（且 DB 里已是哈希，改 .env 不影响现有账号）。升级验收不要打印密码，用 `grep -c ADMIN_PASSWORD /opt/data/crm/.env` 确认存在即可，实际登录由用户手点。

### 3.6 回滚与灰度

| 场景 | 动作 | 是否丢数据 |
|---|---|---|
| 迁移失败（脚本抛错，事务未提交） | 服务本就停着；`git checkout` 回 V1 代码 → `systemctl start` | 不丢（事务已回滚） |
| 迁移成功但新代码有 bug | `git revert <v2 提交>` → `systemctl restart crm-api`，**不需要回滚 DB**（V1 代码在迁移后库上实测可跑：19 条 V1 DDL 重放 + V1 写法 INSERT 均通过） | 不丢；V2 新增表数据保留 |
| 极度异常需回到迁移前 | `systemctl stop` → `cp /opt/data/crm/backups/crm-pre-v2-manual-*.db /opt/data/crm/crm.db` → `systemctl start`（同时 revert 代码） | 丢失升级后产生的 V2 数据（正常） |
| 灰度 | 单用户系统，无灰度流量。用"副本演练 + 停机 5s 切换"替代灰度；建议在**无人在用的时段**（晚 22:00 后）执行 | — |

**兼容双向性证据（这是敢说"回滚零成本"的底气）**：迁移后库上跑 V1 的 `ENSURE_SQL` 19 条 → 全 `IF NOT EXISTS` 无副作用；V1 写法的 `INSERT INTO follow_ups (customer_id, deal_id, content, next_date, created_at)` 与 `INSERT INTO attachments (follow_up_id, storage_key, ...)` → 触发器自动补齐 `object_type/object_id`，不报错。

### 3.7 实测结果（本轮在 `crm.db` 副本上跑出来的真实输出）

```
# ① 存量库副本，首次迁移
M1 v2_001: 59 executed / 3 skipped
Rows unchanged: {'customers': 2, 'deals': 1, 'follow_ups': 2, 'tags': 1, 'customer_tags': 1, 'attachments': 0}
user_version=2

# ② 同库重跑（幂等）
M1 v2_001: 40 executed / 22 skipped
Rows unchanged: {...同上...}
（第二次"executed 40"全是 CREATE IF NOT EXISTS / 幂等 UPDATE，无 DROP、无 RENAME）

# ③ 结构收敛：全新空库(ensure_schema→migrations) vs 存量升级库
[fresh]    V1 ensure_schema: 19 条 DDL
[upgraded] V1 ensure_schema 重放: 19 条（必须无副作用）
✓ 结构完全一致（18 张表：列/索引/外键/触发器逐项相同）
✓ V1 路径 INSERT follow_ups 触发器补齐: [('customer', 1), ('deal', 1)]
✓ V1 路径 INSERT attachments 触发器补齐: [('follow_up', 1, 1)]
✓ 订单截图行可写（object_type=order_payment, follow_up_id=NULL）

# ④ 中断收敛：15 个切点（含"已 DROP 未 RENAME"最危险点）× 重跑
✓ 中断点扫描全部收敛：15 个切点 × 重跑 = 数据与结构一致
✓ attachments 4 行存量：重建后 0 丢失，object_type/object_id 自动补齐
✓ 有照片 + 中断在重建中途：重跑收敛，4 行照片不丢
✓ 连续重跑 3 次：幂等、无漂移

# ⑤ 业务流（副本 + 迁移后，全链路 SQL 级验证）
✓ 线索→客户/商机：意向顺延=high
✓ 赢单生成订单 SO-20261030-001，总额继承=12800.00
✓ 订单 7 态全流程：pending_payment→deposit_paid→producing→balance_paid→ready_to_ship→shipped→completed
✓ 越级/回退跃迁被状态机拒绝
✓ 自送场景运单号='无'
✓ DB 约束生效：商机↔订单 1:1 / 订单号唯一 / 外键不可悬挂
✓ 售后 3 态流：AS-...-001 done / AS-...-002 rejected
✓ SLA 查询命中超 3 天待处理单
✓ 删除保护生效：订单/商机/客户/物流公司均被 RESTRICT
```

**部署约束对齐（红线逐条核过）**

| 约束 | 本方案怎么满足 |
|---|---|
| `PYTHONPATH=/opt/data/crm` 钉死 | CLI 与 lifespan 都按该前缀调用；`app/migrations.py` 只 import 标准库，**不 import `app.*`**（避免 import 顺序/venv 污染） |
| systemd `Environment=CRM_DB/CRM_UPLOADS` | 迁移读 `$CRM_DB`，与 systemd 同一来源；手动执行显式传 `CRM_DB=` |
| 用 `/usr/bin/python3`（不用项目 venv） | 所有命令写死 `/usr/bin/python3`（3.10.12）；零新增依赖，不 import pydantic |
| 内存护栏 512M/1G | 迁移是**独立短进程**（峰值 <40MB，SQLite 页缓存默认 2MB），不占服务 cgroup 配额；服务侧新增代码零重依赖，RSS 增量预计 <30MB |
| 单 worker | 迁移与发号都假设单写入者；不引入后台线程/定时任务 |
| 不动 8010 / nginx | 端口、location 全不变；只加 router 与静态页 |

---

## 4. 前端页面清单（H5 / PWA）

### 4.1 改造原则

| 原则 | 做法 |
|---|---|
| **登录页复用 V1，不新增** | `static/index.html` 的 `#loginView`（含"禁止浏览器保存密码"的 `autocomplete="new-password"` 方案）与 `POST /api/crm/login` **一行不改**；V2 只在其后追加视图 |
| 单壳 + hash 路由 | 沿用 `index.html`（一个 `<main id="app">`）+ `app.js`（`#/xxx` 路由）结构；**不引入 React/Vue/构建链**（内存与部署约束） |
| 渐进扩展 | `app.js` 现 1246 行 → 预计 ~2600 行；按视图拆成 `static/views/*.js`（5 个文件）用 `<script>` 顺序引入，避免单文件失控（`index.html` 加 5 个 `<script>` 标签即可，仍无构建） |
| PWA 不变 | `manifest.json` / `sw.js` 的缓存清单加 5 个新 js 文件；其余不动 |
| 错误提示 | `api()` 的错误对象已有 `status`；再加 `code`（读 `data.code`），页面据 `code` 做差异化（如 `deal_frozen` → 显示冻结条） |

### 4.2 导航与路由表（15 个路由：8 新增 / 4 扩展 / 3 保留）

| 路由 | 视图 | 状态 | 说明 |
|---|---|---|---|
| `#/login` | 登录 | **保留** | V1 原样 |
| `#/dashboard` | 工作台 | **扩展**（V1 看板演进） | 今日待跟进 + 售后 SLA + 订单总览 + 最近订单 |
| `#/leads` | 线索列表 | **新增** | |
| `#/leads/{id}` | 线索详情 | **新增** | |
| `#/customers` | 客户列表 | **扩展** | 加类型/来源/生命周期筛选 |
| `#/customers/{id}` | 客户 360 | **扩展** | V1 客户详情升级为一页看全 |
| `#/deals` | 商机列表 | **扩展** | 阶段列 + 赢单/流失入口 |
| `#/deals/{id}` | 商机详情 | **新增** | |
| `#/orders` | 订单列表 | **新增** | |
| `#/orders/{id}` | 订单详情 | **新增** | 金额 + 截图上传 + 状态机 |
| `#/aftersales` | 售后列表 | **新增** | |
| `#/aftersales/{id}` | 售后详情 | **新增** | |
| `#/logistics` | 物流（公司主数据 + 运单查询） | **新增** | |
| `#/stats` | 统计 | **保留** | V1 原样（可加订单漏斗，不必须） |
| `#/import` | CSV 导入 | **保留** | V1 原样 |

**顶栏导航**（移动端横向滚动）：`工作台 · 线索 · 客户 · 商机 · 订单 · 售后 · 物流 · 统计 · 导入`，右侧保留 `#whoami` + 退出。

### 4.3 页面明细（核心交互 = reviewer 的验收清单）

#### ① 工作台 `#/dashboard`
- **顶部三块卡片**：今日待跟进 N 条 / 逾期 M 条（红字）/ 售后超时 K 条（红底）。
- **今日待跟进**：合并 5 类的 `followups_today`；每条显示 `对象类型徽章 + 对象名 + 内容摘要 + 下次跟进日`；`overdue=true` 整行左边 4px 红条 + 日期红字；点击按 `link` 跳对象详情（线索→`#/leads/{id}`，订单→`#/orders/{id}`…）。
- **售后 SLA 红条**（N8）：`aftersale_sla_alerts` 非空时置顶显示"⚠ 售后单 AS-xxx 已挂 N 天未处理"，点击进售后详情。
- **订单状态总览**：7 个态 7 个小卡（状态名 + 数量 + 金额小字），点击跳 `#/orders?status=xxx`。
- **最近订单**：最新 10 笔，行内显示 `订单号 / 客户 / 金额 / 状态徽章`，点击进详情。
- 空态：每块都有"暂无"文案，不显示空表格。

#### ② 线索列表 `#/leads`
- 顶部：状态 tab（全部 / 新线索 / 跟进中 / 已转化 / 已失效）+ 搜索框（姓名/手机/微信/地址，回车触发）。
- 列表行：`姓名（公司线索显示公司名+主联系人）· 手机/微信 · 来源徽章 · 意向徽章（高=绿/中=黄/低=灰/无意向=淡）· 下次跟进日（逾期红字）`。
- 右下角悬浮 `+ 新线索` → 抽屉表单（手机/微信二选一必填、类型切换时公司名显隐、来源下拉+其他文本框、意向、标签、备注）。
- 行点击进详情；已转化行显示"已转化 → 客户"链接（`converted_customer_id`）。

#### ③ 线索详情 `#/leads/{id}`
- 档案卡：联系方式可点（`tel:` / 复制微信号）、来源、地区、标签、备注、创建时间。
- 意向等级：4 个 pill，点一下即 `PUT /leads/{id}` 保存（N1 仅记录）。
- 跟进时间线：倒序，每条含方式图标/内容/照片缩略图/时间；底部"记跟进"按钮 → 抽屉（内容 + 方式 + 下次跟进日 + 意向等级 + ≤3 张照片）。
- 主操作（吸底）：`建商机并转化`（主按钮）/ `标记失效`（次按钮，弹必选原因）。
- **转化弹层**：字段 `商机名称* / 产品类型（天窗/天幕）/ 型号 / 规格 / 金额*`；点提交前先调 `GET /leads/convert-check`：
  - 无命中 → 直接 `POST convert {mode:"new"}`；
  - 命中 → 弹"客户 XXX 已存在"两选一：`关联到该客户`（`mode:"link"`）/ `仍要新建客户`（`mode:"new", force_new:true`）。
  - 成功 → toast + 跳 `#/customers/{customer_id}`（360 页能看到刚建的商机）。
  - `409 lead_closed` → 提示"该线索已转化/已失效"，刷新列表。

#### ④ 客户列表 `#/customers`（V1 升级）
- 原搜索 + 标签 chips 保留；新增筛选条：`类型（全部/个人/公司）· 来源 · 生命周期（潜在/商机中/已成交/复购）`。
- 列表行加：`生命周期徽章`、`公司名`、`联系人 N`、意向徽章。
- 保留 V1 的"新增客户"表单，加类型/公司名/来源/意向/标签字段；公司类型时展示"联系人"子表单（可加多条，第一条默认主联系人）。

#### ⑤ 客户 360 `#/customers/{id}`（核心页）
- 头部：`名称 / 类型 / 生命周期徽章 / 意向 / 来源 / 地区 / 电话（可点）/ 微信 / 标签`，右侧 `编辑`。
- 联系人区（公司客户）：列表 + `+ 添加联系人`，每行可编辑/删除/设为主联系人（`PUT /contacts/{id}`）。
- 统计条：`商机 N · 成交额 ¥X · 订单 N · 已完成额 ¥Y · 待处理售后 K`（来自 `/360.stats`）。
- 四个 Tab：
  - **商机**：卡片列表（名称/产品/金额/阶段徽章/冻结标记），`+ 新建商机`（D2，第 2 个及以后；`POST /deals`）。
  - **订单**：列表（订单号/金额/状态进度小条），点击进订单详情。
  - **售后**：列表（单号/类型/状态/挂起天数，>3 天红标）。
  - **时间线**：`/360.timeline` 合并渲染（跟进 / 订单跃迁 / 售后状态），倒序，可筛选类型。
- 底部固定"记跟进"（`object_type=customer`）。

#### ⑥ 商机列表 `#/deals`（V1 升级）
- 视图切换：`看板列`（5 列：需求确认/报价/成交洽谈/赢单/流失）与 `列表`。移动端默认列表 + 顶部阶段 chips。
- 卡片：商机名（空则 `产品+型号`）、客户名、金额、`产品型号规格`、最后跟进时间；赢单/流失卡片带锁图标。
- 卡片右侧快捷动作：进行中 → `赢单` / `流失`；已冻结 → 只有"查看"。

#### ⑦ 商机详情 `#/deals/{id}`（新增）
- 档案卡：商机名/客户/产品/规格/金额（**只读，R4 总额来源**）/阶段/创建时间。
- 阶段推进：3 个进行中阶段的 pill 直选（`PUT /deals/{id}`）；到终态只显示徽章。
- 跟进区：进行中可加（否则灰置 + 提示"已赢单/已流失，跟踪已移至订单"）；列表带照片。
- 主操作：`赢单并生成订单`（二次确认弹层："将生成订单，总额 ¥X 继承自商机，生成后商机冻结"）→ 成功跳订单详情；`设为流失`（必选原因下拉 + other 文本）。
- 冻结提示条：赢单显示"已生成订单 SO-xxx，跟踪请到订单"（可点跳转）；流失显示"流失原因：价格"；若 `source_lost_deal_id` 有值，显示"由流失商机 #旧id 重启"。

#### ⑧ 订单列表 `#/orders`
- 顶部 7 态 chips（带计数）+ 搜索（订单号/客户名）。
- 行：`订单号 · 客户 · 金额 · 状态进度条（7 段，当前段高亮）· 创建时间`；`待发货/已支付尾款` 等"待办态"加黄点提示。

#### ⑨ 订单详情 `#/orders/{id}`（金额 + 截图的核心页）
- 头部：大号金额 `¥12,800.00`、`已收 ¥12,800.00 / 未收 ¥0.00`、订单号、客户（可点进 360）、关联商机。
- **状态进度条**：7 段横向（移动端可横滑），当前态高亮，已过态打勾。
- **动作区（只显示当前态那一个表单，杜绝误操作）**：
  - `pending_payment`：金额输入（默认剩余应收）+ `选择截图`（多选，≤3，手机直接调相机）+ 备注 →「确认收到押金」。
  - `deposit_paid`：无输入 →「财务已确认，转入生产」。
  - `producing`：尾款金额（默认剩余）+ 截图 + 备注 →「确认收到尾款」。
  - `balance_paid`：无输入 →「备货完成，待发货」。
  - `ready_to_ship`：物流方式二选一（`物流公司` 下拉取 `/carriers?active_only=1` / `自送`）；物流公司模式显示运单号输入；自送模式运单号自动填 `无`（可改）→「确认发货」。
  - `shipped`：无输入 →「客户已确认收货」。
  - `completed`：显示完成时间 + 灰置提示"订单已完成；若有问题请开售后单"。
- **状态历史时间线**：每条显示 `状态变化 / 时间 / 金额 / 运单号 / 备注 / 截图缩略图（点击看大图，走 /attachments/{id}）`。
- 底部：`售后单` 区块（列表 + `+ 新建售后` → 类型/描述弹层）。

#### ⑩ 售后列表 `#/aftersales`
- tabs：全部/待处理/处理中/已完成/已拒绝；待处理超 3 天行首加红色 `⏰ N 天` 徽章。
- 行：`售后单号 · 订单号 · 类型徽章 · 状态徽章 · 客户 · 创建时间`。

#### ⑪ 售后详情 `#/aftersales/{id}`
- 订单摘要卡（订单号/金额/完成时间，可点进订单）。
- 问题描述 + 类型 + 时间线（`aftersale_status_log` + 跟进记录合并）。
- 动作区：`pending` → 「开始处理」/「拒绝」（填原因）；`processing` → 「完成」（填处理结果）/「拒绝」；终态 → 灰置。
- 记跟进（`object_type=aftersale`）。

#### ⑫ 物流 `#/logistics`
- Tab 1「物流公司」：表格（名称/联系人/电话/备注/状态），行内 `编辑 / 停用`；`+ 新增`；停用的不出现在建单下拉。删除按钮只在未被引用时可点（否则 toast `carrier_in_use` → 提示改用停用）。
- Tab 2「运单查询」：`GET /logistics/shipments`，列表 `订单号/客户/物流公司/运单号/发货日期/订单状态`，支持按状态过滤；运单号可复制。

### 4.4 共用交互规范（做错这几个细节会被打回）

| 项 | 规范 |
|---|---|
| 金额输入 | `<input type="number" inputmode="decimal" step="0.01" min="0">`；失焦格式化成两位小数；前端只做"非负/必填"校验，**上限校验以后端为准**（后端返回 `amount_exceeds_*` 时红字提示） |
| 截图上传 | `<input type="file" accept="image/*" capture="environment" multiple>`；选完立刻本地预览缩略图；>3 张或 >20MB 时前端拦截并 toast；微信内置浏览器沿用 V1 的"请用系统浏览器上传"提示 |
| 状态徽章 | 一套 `badge-<status>` CSS 类，7 态 + 5 阶段 + 4 售后态 + 4 意向；颜色固定：进行中=蓝、成功=绿、失败/流失=灰、超时=红、待处理=黄 |
| 冻结提示 | 商机 `won/lost` 时，详情页顶部固定一条浅灰提示条，底部动作按钮全部 `disabled` 并附原因文案（不许只灰掉不给理由） |
| 去重弹层 | 只在 `convert-check` 命中时出现；两个按钮文案固定："关联到该客户（推荐）"、"仍要新建客户"；后者需二次确认"会产生重复客户档案" |
| 错误码分支 | `deal_frozen` → 冻结条；`illegal_transition` → toast + 自动刷新详情（防并发/双开）；`duplicate_customer` → 去重弹层；其余 toast 后端 `detail` 原文 |
| 二次确认 | 删除客户/联系人/物流公司、赢单、流失、标记失效、完成售后，**必须**二次确认（V1 的"二次确认"约定延续） |
| 空态/加载态 | 每个列表：骨架屏（3 行）→ 空态文案 → 数据；提交中按钮 `disabled` + "处理中…"（防重复提交） |
| 移动优先 | 所有操作区在 375px 宽可用；表格类（物流）横向滚动；吸底主按钮避开 iOS 安全区（`padding-bottom: env(safe-area-inset-bottom)`） |

### 4.5 明确不做（防止 coder 自行加戏）

- 不做拖拽改阶段、不做多日日程、不做图表库（订单总览用数字卡，不引 Chart.js）、不做富文本、不做导出、不做消息推送/微信订阅、不做暗色主题、不做角色权限菜单、不做登录页改造、不做路由库（继续 hash）、不引任何 npm 构建链。

---

## 5. 回归与验证标准

### 5.1 环境前缀（所有命令都从这三行开始，缺一个就跑偏）

```bash
cd /opt/data/crm
export PYTHONPATH=/opt/data/crm
PY=/usr/bin/python3          # 3.10.12；不用项目 venv（8002 踩过的坑）
```

> **测试库隔离**：`tests/_bootstrap.py` 已硬编码红线——若 `CRM_DB` 指向 `/opt/data/crm/crm.db` 就**直接抛错**，默认落到 `/tmp/crm-t.db` + `/tmp/crm-t-up`。所以跑测试永远不会碰生产库，不需要额外保险。

### 5.2 V1 回归基线（当前实测：**87 条全绿**）

```bash
cd /opt/data/crm && export PYTHONPATH=/opt/data/crm
/usr/bin/python3 -m unittest discover -s tests -t . 2>&1 | tail -3
# 基线（升级前，本轮实测）：
#   Ran 87 tests in 10.288s
#   OK
```

**V2 必须同步更新的断言（仅阶段枚举字面量，共 3 个文件 / 8 处）**——这是唯一允许改的 V1 测试内容：

| 文件 | 行 | 改动 |
|---|---|---|
| `tests/test_deals.py` | 20-21 | `stage=="lead"` / `"线索"` → `"confirm"` / `"需求确认"` |
| `tests/test_deals.py` | 39-45 | `stage="quoted"` / `"已报价"` → `"quote"` / `"报价"` |
| `tests/test_deals.py` | 85-91 | `"shipped"` 不再是商机阶段 → 改断言 `400 invalid_stage`（发货只能在订单上做） |
| `tests/test_dashboard.py` | 109,135,145 | `stage="lead"/"quoted"` → `"confirm"/"quote"`，`deals_by_stage` 键改 `confirm/quote` |
| `tests/test_customers.py` | 117 | `deals[0]["stage"]=="lead"` → `"confirm"` |
| `tests/_util.py` | 54 | `insert_deal(stage: str = "lead")` → `"confirm"` |

验收：更新后 **87 条仍必须全绿**，且 `git diff tests/` 只出现上述字面量改动（reviewer 逐行核）。

### 5.3 新增测试文件与目标用例数

| 文件 | 目标条数 | 覆盖重点 |
|---|---|---|
| `tests/test_migrations.py` | 8 | 用**自建 fixture 库**（V1 结构 + 2 客户/1 lead 商机/2 跟进/1 标签）跑迁移：行数不变、stage 映射、跟进派生、两表重建、幂等重跑、中断重跑、`foreign_key_check`、全新库与升级库结构一致 |
| `tests/test_leads.py` | 14 | 建线索（手机/微信二选一、都空 400）、状态流转、失效原因必选、终态不可改（409）、搜索/筛选、分页 |
| `tests/test_lead_convert.py` | 12 | 无重复直接转化、去重命中 409 带 matches、link 分支、force_new 分支、link 到不匹配客户 400、意向顺延、created_at 继承、标签迁移、跟进迁移、商机字段必填、已转化线索 409、公司线索只带主联系人 |
| `tests/test_customers_v2.py` | 10 | 类型/来源/意向字段、公司多联系人 CRUD、主联系人唯一、生命周期四态、`/360` 结构与 stats、删客户有订单 409 |
| `tests/test_deals_v2.py` | 12 | 阶段 3 态推进、非法枚举 400、won/lost 必须走动作端点、冻结矩阵 6 条、赢单生成订单 + closed_at + order_id、重复赢单 409、金额 0 400、流失必选原因、来源流失商机关联校验 |
| `tests/test_orders.py` | 24 | 7 态 6 跃迁、每态非法输入（越级/回退/错态 409）、押金超总额 400、尾款超剩余 400、截图 1–3 张校验（0 张 400 / 4 张 400 / 非图片 400 / 超 20MB 400）、运单号必填、自送填"无"、carrier 停用不可选、`POST /orders` 405、状态日志 7 行且金额/截图齐全、`next_status` 正确、删除保护 409 |
| `tests/test_aftersales.py` | 10 | 建单（订单不存在 404）、3 态流、拒绝必填原因、完成必填结果、终态再操作 409、不回写订单状态（I2）、SLA 查询边界（3 天不提醒 / 4 天提醒） |
| `tests/test_carriers.py` | 8 | CRUD、重名 409、软停用后建单下拉不返回、被引用删除 409、`/logistics/shipments` 过滤 |
| `tests/test_followups_v2.py` | 10 | 5 类对象挂载、V1 参数兼容（customer_id/deal_id）、商机冻结 409、线索终态 409、意向顺带更新、≤3 张照片、`object_type` 非法 400 |
| `tests/test_workbench.py` | 8 | `followups_today` 五类合并 + 逾期标记、订单 7 态 keys 全给（缺补 0）、金额汇总、最近 10 单、SLA 告警、V1 键（today_followups/month_won/stats）逐字保留 |

**合计新增 116 条；加上 V1 的 87 条 = 203 条全绿** 是 T8 的放行线。

```bash
cd /opt/data/crm && export PYTHONPATH=/opt/data/crm
/usr/bin/python3 -m unittest discover -s tests -t . 2>&1 | tail -3     # 期望 Ran 203 tests ... OK
/usr/bin/python3 -m unittest tests.test_orders -v 2>&1 | tail -30      # 单卡自测
```

### 5.4 验收断言表（reviewer 按表打勾，一行一个断言）

> 记 `C`=客户 id、`D`=商机 id、`O`=订单 id、`A`=售后 id。所有请求带 `Cookie: crm_sid=<登录后>`。

| # | 端点 / 动作 | 输入要点 | 期望 |
|---|---|---|---|
| 1 | `GET /health` | 无鉴权 | 200，`status=ok` |
| 2 | `GET /customers` | 无 cookie | 401 |
| 3 | `GET /customers` | 登录 | 200，`total=2`，item 含 `customer_type/source/lifecycle` |
| 4 | `POST /leads` | 手机与微信都空 | 400 `missing_contact` |
| 5 | `POST /leads` | 手机 + 来源 wechat | 200，`status=new`，`intent_level` 原样 |
| 6 | `POST /leads` | `source="xxx"` | 400 `invalid_enum` |
| 7 | `POST /follow-ups` | `object_type=lead,object_id=L` + 照片 1 张 | 200；`leads.status` 变 `following`；`attachments.object_type=follow_up` |
| 8 | `GET /leads/convert-check` | 已存在客户的手机 | 200，`has_match=true`，`matches[0].customer_id` 命中 |
| 9 | `POST /leads/{L}/convert` | 命中重复 + `mode=new` 无 `force_new` | 409 `duplicate_customer`，body 含 `matches[]` |
| 10 | 同上 | `mode=new, force_new=true` | 200，`dedupe=forced`，新建客户 + 商机 |
| 11 | 同上 | `mode=link, link_customer_id=<命中>` | 200，`dedupe=linked`，客户数不变，商机挂老客户 |
| 12 | 转化副作用 | 转化后查 | `leads.status=converted`；`converted_customer_id/deal_id` 有值；客户 `intent_level` = 线索最后值；客户 `created_at` = 线索 `created_at`；线索标签进 `customer_tags`；线索跟进 `object_type` 变 `customer` |
| 13 | `POST /leads/{L}/convert` | 对已转化线索再转 | 409 `lead_closed` |
| 14 | `POST /leads/{L}/invalidate` | 不传原因 | 400 `invalid_enum` |
| 15 | `POST /deals` | `stage="won"` | 400 `invalid_stage`（赢单只能走动作端点） |
| 16 | `POST /deals/{D}/win` | 商机 amount=12800 | 200；`orders` 新增 1 行 `amount=12800`、`status=pending_payment`；`deals.stage=won`、`closed_at` 非空、`order_id=O` |
| 17 | `POST /deals/{D}/win` | 再次调用 | 409 `deal_frozen`（实现先校验 stage，故稳定命中 `deal_frozen`；`order_exists` 只在脏数据时出现） |
| 18 | `PUT /deals/{D}` | 赢单后改 amount | 409 `deal_frozen` |
| 19 | `POST /follow-ups` | `object_type=deal,object_id=<won D>` | 409 `deal_frozen` |
| 20 | `PUT /deals/{D2}` | `stage=lost` | 400 `invalid_stage`（指向 `/lose`） |
| 21 | `POST /deals/{D2}/lose` | `lost_reason=price` | 200；`stage=lost`、`closed_at` 为空、`lost_reason=price` |
| 22 | `POST /deals` | `source_lost_deal_id=<未流失商机>` | 409 `source_deal_not_lost` |
| 23 | `POST /orders` | — | 405 `order_create_forbidden` |
| 24 | `POST /orders/{O}/pay-deposit` | `amount=3800` + 1 张 jpg | 200；`status=deposit_paid`、`deposit_paid=3800`；`order_status_log` 多 1 行含 `screenshot_ids` |
| 25 | 同上 | 无截图 | 400 `screenshot_required`；`orders.status` 仍 `pending_payment`（事务回滚） |
| 26 | 同上 | `amount=999999` | 400 `amount_exceeds_total` |
| 27 | `POST /orders/{O}/pay-balance` | 当前态仍是 `pending_payment` | 409 `illegal_transition`，body 含 `current_status` |
| 28 | `POST /orders/{O}/start-production` | 当前态 `deposit_paid` | 200 → `producing` |
| 29 | `POST /orders/{O}/pay-balance` | `amount=9000` + 截图 | 200 → `balance_paid`，`balance_paid=9000` |
| 30 | 同上 | `amount=99999` | 400 `amount_exceeds_remaining` |
| 31 | `POST /orders/{O}/ready-to-ship` | 当前 `balance_paid` | 200 → `ready_to_ship` |
| 32 | `POST /orders/{O}/ship` | `logistics_mode=self` 且 `tracking_no=""` | 200 → `shipped`，库中 `tracking_no="无"` |
| 33 | `POST /orders/{O}/ship` | `logistics_mode=carrier` 无 `carrier_id` | 400 `carrier_required` |
| 34 | `POST /orders/{O}/complete` | 当前 `shipped` | 200 → `completed`，`completed_at` 非空 |
| 35 | `POST /orders/{O}/complete` | 再调一次 | 409 `illegal_transition` |
| 36 | `GET /orders/{O}` | — | 200；`status_log` 长度 7；`screenshot_ids` 解析出 2 张 url；`next_status=null` |
| 37 | `GET /orders?status=completed` | — | 200，`total` 含该单 |
| 38 | `POST /aftersales` | `order_id` 不存在 | 404 |
| 39 | `POST /aftersales` | 合法 | 200，`status=pending`，单号 `AS-YYYYMMDD-001` |
| 40 | `POST /aftersales/{A}/finish` | 当前 `pending`（未 start） | 409 `illegal_transition` |
| 41 | `POST /aftersales/{A}/start` → `/finish {result}` | — | 200 → `processing` → `done`，`closed_at` 非空 |
| 42 | `GET /orders/{O}` | 售后完成后 | `orders.status` 仍 `completed`（I2 不回写） |
| 43 | `POST /aftersales/{A2}/reject` | 不传 `reject_reason` | 400 `reject_reason_required` |
| 44 | `GET /customers/{C}/360` | — | 200；`deals/orders/aftersales/timeline/stats` 五键齐全；`lifecycle` 与已完成订单数一致（0→`dealing`、1→`won`、≥2→`repeat`；该用例造 2 单完成，期望 `repeat`） |
| 45 | `DELETE /customers/{C}` | 名下有订单 | 409 `customer_has_orders` |
| 46 | `POST /carriers` | 重名 | 409 `carrier_exists` |
| 47 | `DELETE /carriers/{id}` | 被订单引用 | 409 `carrier_in_use` |
| 48 | `GET /dashboard` | — | 200；`today_followups`/`month_won`/`stats` 三键存在（V1 兼容）；`orders.by_status` 含 7 个键；`recent_orders` ≤10；`aftersale_sla_alerts` 为数组 |
| 49 | `GET /dashboard` | 构造 4 天前 `pending` 售后 | `aftersale_sla_alerts[0].days_pending=4` |
| 50 | `GET /follow-ups?object_type=order&object_id=O` | — | 200，仅返回该单的跟进 |
| 51 | V1 页面 | 浏览器点 客户/商机/跟进/统计/导入 | 全部可打开、无 JS 报错、数据与升级前一致 |

### 5.5 迁移验收断言（升级后立刻执行，全绿才允许对外）

```bash
cd /opt/data/crm && export PYTHONPATH=/opt/data/crm
/usr/bin/python3 - <<'PY'
import sqlite3
c = sqlite3.connect('/opt/data/crm/crm.db'); q = lambda s: c.execute(s).fetchone()[0]
assert q("SELECT COUNT(*) FROM customers") == 2
assert q("SELECT COUNT(*) FROM deals") == 1
assert q("SELECT COUNT(*) FROM follow_ups") == 2
assert q("SELECT COUNT(*) FROM tags") == 1
assert q("SELECT COUNT(*) FROM customer_tags") == 1
assert q("SELECT COUNT(*) FROM attachments") == 0
assert q("SELECT stage FROM deals WHERE id=1") == 'confirm'
assert q("SELECT customer_type FROM customers WHERE id=1") == 'personal'
assert q("SELECT source FROM customers WHERE id=1") == 'stock'
assert q("SELECT object_type||':'||object_id FROM follow_ups WHERE id=1") == 'customer:1'
assert q("SELECT object_type||':'||object_id FROM follow_ups WHERE id=2") == 'deal:1'
assert q("SELECT version FROM schema_migrations") == 'v2_001'
assert q("PRAGMA user_version") == 2
assert c.execute("PRAGMA foreign_key_check").fetchall() == []
assert q("SELECT COUNT(*) FROM orders") == 0        # I6：存量商机不补订单
tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
for t in ('leads','lead_tags','customer_contacts','carriers','orders',
          'order_status_log','aftersales','aftersale_status_log','schema_migrations'):
    assert t in tables, t
assert 'follow_ups_new' not in tables and 'attachments_new' not in tables
print("✓ 迁移验收 20 条断言全部通过")
PY
```

**迁移专项脚本（本轮已跑通，reviewer 可复跑）**

```bash
cd /opt/data/crm/docs/planner-v2-checks
/usr/bin/python3 migrations_v2.py --db /tmp/chk.db --no-backup      # 需先 cp 一份 crm.db 到 /tmp/chk.db
/usr/bin/python3 verify_convergence.py        # 全新库 vs 升级库结构一致 + 触发器兼容
/usr/bin/python3 verify_interrupt.py          # 15 个中断切点 + 有照片重建 + 连跑 3 次
/usr/bin/python3 flow_sim.py                  # 业务全链路（线索→订单 7 态→售后 3 态→SLA）
/usr/bin/python3 check_doc_ddl.py             # 把本文档 §1 的 55 条 DDL 抽出来原样执行并与迁移脚本比对
```

### 5.6 手工冒烟（浏览器，10 分钟）

```bash
curl -s -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8010/health
curl -s -o /dev/null -w 'crm-page=%{http_code}\n' http://10.113.9.77:8000/crm/
```

1. 打开 `http://10.113.9.77:8000/crm/` → 登录页（**应为 V1 原样，未改版**）→ 登录。
2. 工作台：今日待跟进显示 2 条历史跟进；七态卡片齐全。
3. 客户：2 个存量客户可见，类型=个人、来源=存量、生命周期=潜在（无订单）。
4. 新建线索（手机 13900000001）→ 记跟进（带照片）→ 建商机转化 → 客户 360 看到商机。
5. 商机：推进到成交洽谈 → 赢单 → 自动跳订单详情，总额=商机金额。
6. 订单：押金（金额+截图）→ 下一步 → 尾款（截图）→ 下一步 → 发货（物流公司+运单号）→ 完成收货。
7. 售后：订单下新建售后（维修）→ 开始处理 → 完成（填结果）。
8. 物流：新增物流公司 → 下单时下拉能选到；停用后不再出现。
9. 手机（375px）：上述流程能走通，上传能调起相机，底部按钮不被安全区遮挡。
10. 退出登录 → 回登录页；再登录会话正常。

**注意**：步骤 4–7 会在**生产库**产生真实业务数据。要么在升级当晚用真实客户跑（用户接受），要么先跑一遍再删除——但订单/售后无删除接口（RESTRICT）。**建议**：把 §5.6 作为用户验收（UAT）由用户自己操作，`coder` 只在 `/tmp` 副本库上跑等价流程（`flow_sim.py` 已覆盖）。

---

## 6. 任务拆解（coder 任务卡）

> 通用纪律：每卡独立 `git commit`（`feat(Tn): ...`）；每卡自带测试并通过 `/usr/bin/python3 -m unittest`；不动机器上的 systemd/nginx；**任何卡都不许改 `/opt/data/crm/crm.db`**（只在副本上演练）。

### 6.1 依赖图

```
T1 基座/迁移 ──┬─▶ T2 线索+转化+统一跟进 ──▶ T3 客户扩展+360 ──▶ T4 商机V2(赢单/冻结) ──▶ T5 订单7态+物流 ──▶ T6 售后+工作台
               │                                                     │                          │                    │
               │                                                     └────────────┬─────────────┴────────────┬───────┘
               │                                                                  ▼                          ▼
               └────────────────────────────────────────────────▶ T7a 前端(线索/客户360/工作台)   T7b 前端(商机/订单/售后/物流)
                                                                                    └──────────┬───────────────┘
                                                                                               ▼
                                                                                        T8 回归/部署/回滚演练
```

### 6.2 任务卡

#### T1 基座：枚举 / 错误码 / 迁移 / 模型骨架（6h）
- **范围**：新增 `app/enums.py`（§1.1 全部枚举 + `ORDER_FLOW` + `AFTERSALE_SLA_DAYS` + `LEGACY_STAGE_MAP`）、`app/errors.py`（`ApiError` + handler）、`app/migrations.py`（§3.3，全文照抄 `docs/planner-v2-migrations_v2.py`）、`app/queries.py`（生命周期/SLA/未收金额 SQL）；改 `app/models.py`（扩展 Customer/Deal 出参、`DEFAULT_STAGE="confirm"`、`STAGE_LABELS` 换 V2）、`app/main.py`（lifespan 加 `run_migrations`、注册 errors handler）；改 §5.2 列的 6 处测试字面量；新增 `tests/test_migrations.py`。
- **不动**：`app/schema.py`（一行不改）。
- **AC**：① `unittest` 87 条（更新字面量后）全绿；② `/tmp` 副本上迁移首跑/重跑/中断重跑全通过；③ 全新空库起服务后 18 张表结构 == 升级库结构（跑 `verify_convergence.py`）；④ `GET /deals` 存量商机 `stage=confirm`。

#### T2 线索 + 转化 + 统一跟进（10h）
- **范围**：新增 `app/routers/leads.py`（7 端点）、`app/services.py: convert_lead()`（§2.3 八步，单事务）、`app/services.py: read_images()`；改造 `app/routers/followups.py`（多对象挂载 + V1 兼容 + 冻结校验 + 意向顺带更新）；`app/models.py` 加 Lead/Contact/FollowUpV2 模型；测试 `test_leads.py`、`test_lead_convert.py`、`test_followups_v2.py`。
- **AC**：§5.4 第 4–14、19、22、50 行断言全过；转化后客户/商机/标签/跟进/意向/created_at 六项迁移全部断言；V1 `/follow-ups` 旧参数调用仍 200。

#### T3 客户扩展 + 多联系人 + 360（8h）
- **范围**：改 `app/routers/customers.py`（新列读写、筛选、删除前置检查）、新增 `app/routers/contacts.py`（4 端点）、`GET /customers/{id}/360`（聚合 + `queries.py` 生命周期）、`GET /customers/list` 的 `lifecycle` 筛选；测试 `test_customers_v2.py`。
- **AC**：§5.4 第 3、44、45 行；V1 `test_customers.py` 12 条仍绿（仅 stage 字面量那 1 处改动）；360 出参五键齐全且 `stats` 数值与 SQL 直查一致。

#### T4 商机 V2：阶段 / 冻结 / 赢单 / 流失（8h）
- **范围**：改 `app/routers/deals.py`（阶段收敛、`PUT` 冻结、`/win` 7 步事务、`/lose`、`GET /deals/{id}`）；`services.py: next_no()`；`source_lost_deal_id` 校验；测试 `test_deals_v2.py`。
- **AC**：§5.4 第 15–22 行；冻结矩阵 6 条逐条断言；赢单后 `order_status_log` 首行 `to_status=pending_payment`；`closed_at` 驱动 `month_won` 统计不变（V1 dashboard 用例仍绿）。

#### T5 订单 7 态 + 截图 + 物流主数据（14h）
- **范围**：新增 `app/routers/orders.py`（8 端点，含 405 的 `POST /orders`）、`app/routers/carriers.py`（4 端点 + `/logistics/shipments`）、`services.py: transition()`（统一跃迁器：状态校验 + 字段校验 + 事务 + 日志）；测试 `test_orders.py`、`test_carriers.py`。
- **AC**：§5.4 第 23–37、46、47 行；6 次跃迁后 `status_log` 恰好 7 行且金额/截图/运单号逐行正确；所有失败路径均不产生半截数据（断言 `orders.status` 未变 + `order_status_log` 行数未变 + `attachments` 行数未变）。

#### T6 售后 + 工作台聚合（8h）
- **范围**：新增 `app/routers/aftersales.py`（6 端点）、改 `app/routers/dashboard.py`（追加 4 个新键，V1 三键逐字保留）；测试 `test_aftersales.py`、`test_workbench.py`。
- **AC**：§5.4 第 38–43、48、49 行；SLA 边界（3 天不算、4 天算）；`orders.by_status` 7 键齐全含 0 值。

#### T7a 前端：工作台 / 线索 / 客户 360（12h，依赖 T3）
- **范围**：`static/index.html` 加 5 个 `<script>`（不新增页面文件）；`static/app.js` 拆出 `static/views/leads.js`、`customers.js`、`dashboard.js`；`static/app.css` 加徽章/进度条/SLA 红条/抽屉/去重弹层样式；`sw.js` 缓存清单更新。
- **AC**：§4.3 ①②③④⑤ 五页交互逐条手点通过；375px 无横向溢出；登录页与 V1 像素级一致（不改）。

#### T7b 前端：商机 / 订单 / 售后 / 物流（14h，依赖 T6）
- **范围**：`static/views/deals.js`、`orders.js`、`aftersales.js`、`logistics.js` + 样式。
- **AC**：§4.3 ⑥⑦⑧⑨⑩⑪⑫ 七页；订单详情"动作区只显示当前态表单"、截图上传预览、状态进度条、历史含截图缩略图；物流公司停用后建单下拉不再出现。

#### T8 回归 / 部署 / 回滚演练（8h，依赖全部）
- **范围**：全量 `unittest`（203 条）；副本迁移演练 + 中断演练；执行 §3.5 步骤 0–4；备份校验（`backups/crm-pre-v2-*.db` 能打开且 6 表行数一致）；回滚演练（revert 代码 → 起服 → V1 页面可用 → 再切回）；更新 `docs/` 部署说明。
- **AC**：203 条全绿；§5.5 的 20 条迁移断言全过；§5.6 手工冒烟由用户完成并回复"可用"；回滚演练记录写入 commit message。

### 6.3 排期建议（1 人，顺序开发）

| 阶段 | 卡 | 累计 |
|---|---|---|
| D1 | T1 | 6h |
| D2–D3 | T2 | 16h |
| D3–D4 | T3 | 24h |
| D4–D5 | T4 | 32h |
| D5–D7 | T5 | 46h |
| D7–D8 | T6 | 54h |
| D8–D10 | T7a + T7b（可交替） | 80h |
| D10–D11 | T8 | 88h |

> 缓冲：+20%（枚举/交互细节返工）。**不建议压缩 T5**——7 态 + 截图 + 事务回滚是本次风险最高的一卡。

---

## 7. 待确认项（需用户拍板，不阻塞 T1–T6 开工）

| # | 问题 | 我的默认做法（未回复就按此实现） | 影响面 |
|---|---|---|---|
| **Q1** | 押金 + 尾款是否必须**等于**订单总额？业务文档只说"填金额"，没说等式 | 只校验 `押金 ≤ 总额`、`尾款 ≤ 总额 − 押金`，**不强制等式**（允许优惠/少收/多笔）；订单详情显示"未收 ¥X" | T5 校验、订单详情金额区 |
| **Q2** | 存量客户是否要补标签/意向？现只有 1 个标签、无意向 | 只补 `类型=个人`、`来源=存量`，意向留 NULL（显示"未标注"） | T1 迁移、客户列表展示 |
| **Q3** | 公司客户多联系人里，**主联系人是否必须且唯一**？ | 允许 0–N 个联系人；最多 1 个 `is_primary=1`（设新主联系人自动取消旧的）；不强制必须有 | T3 联系人校验 |
| **Q4** | 售后"已完成/已拒绝"是否允许**重开**？ | 终态不可逆（再操作 409）；如需重开，请回复"允许"，我改成加 `reopened` 端点 | T6 售后状态机 |
| **Q5** | 订单号/售后单号格式 `SO-20261030-001` / `AS-20261030-001` 是否接受？ | 按此实现（前缀 + 本地日期 + 3 位日流水） | T4/T5 发号 |
| **Q6** | 去重只在"线索转化"时查客户，**新建线索时**是否也要提示"已有同名/同号线索"？ | 新建线索**不查重**（业务 D4 只规定客户去重）；线索列表靠搜索 | T2 建线索 |
| **Q7** | 被订单引用的物流公司**只能停用不能删**，是否接受？ | 是（`RESTRICT` + 409 引导停用） | T5 物流 |
| **Q8** | 客户"备注"复用 V1 的 `house_note` 列（不新增 `note` 列），是否接受？ | 是（V1 该列本就是"户型/备注"，语义兼容；避免再加一列同名概念） | T1/T3 |

> 另：业务 §3.3 说"商机字段加产品（类型/型号/规格）"，V1 的 `deals` 已有 `product_type/model/spec` 三列 → 本方案**直接复用，不新增产品表**（产品规格字典已在业务 §6 登记为"本期不做"）。

---

## 8. 风险登记（已识别，均给了规避手段）

| # | 风险 | 概率 | 影响 | 规避 |
|---|---|---|---|---|
| R1 | 迁移中断留下半重建表（`follow_ups_new` 残留） | 中 | 数据不可读 | 三态 guard + 15 个切点实测收敛（§3.6 ④）；启动即跑迁移，失败拒启 |
| R2 | `DROP TABLE follow_ups` 误删照片行 | 低 | 数据丢失 | 重建期间 `PRAGMA foreign_keys=OFF`（在 BEGIN 之前）+ DROP 前行数比对 + 4 行照片实测不丢 |
| R3 | V1 前端因枚举改名显示空白 | 中 | 用户困惑 | 后端 `DealOut.stage_label` 兜底（未知值原样返回）；T4 同卡更新 `app.js` 阶段映射；V1 页面在 T7 一并替换 |
| R4 | 订单跃迁事务不严，出现"状态变了但日志没写" | 中 | 对账不可信 | 统一 `services.transition()`，单事务；测试断言失败路径下 `status`/`log`/`attachments` 三者都不变 |
| R5 | 内存超 512M 护栏被 OOM kill | 低 | 服务重启 | 零新依赖；不上 ORM/图表库；上传走流式/限 20MB；迁移在独立进程 |
| R6 | 截图文件与 DB 行不一致（DB 回滚但文件已落盘） | 低 | 磁盘垃圾 | 先写临时文件，事务提交后 rename；失败留 `.tmp`，沿用 V1"物理文件留备份清理"的约定，不加 GC |
| R7 | 单 worker 下并发双开导致重复赢单 | 低 | 两张订单 | `orders.deal_id UNIQUE` + 事务内 `SELECT ... WHERE deal_id=?` 前置检查 + 409 `order_exists` |
| R8 | 真实数据被测试污染 | 极低 | 灾难 | `_bootstrap.py` 硬红线（CRM_DB 指生产即抛错）+ 本轮所有验证只在副本上做 |

---

## 附录 A：本轮验证产物（可复跑）

| 文件 | 用途 | sha256 |
|---|---|---|
| `/opt/data/crm/docs/planner-v2-migrations_v2.py` | 迁移脚本全文（62 条语句，即 `app/migrations.py` 的内容） | `cc527f12…62f115` |
| `/opt/data/crm/docs/planner-v2-checks/verify_convergence.py` | 全新库 vs 升级库结构一致 + V1 路径兼容 | `6fa210cd…a019e4b` |
| `/opt/data/crm/docs/planner-v2-checks/verify_interrupt.py` | 15 个中断切点 + 有照片重建 + 连跑 3 次 | `bd76f375…f7907ce` |
| `/opt/data/crm/docs/planner-v2-checks/flow_sim.py` | 线索→转化→赢单→订单 7 态→售后 3 态→SLA→删除保护 | `c623be02…e41402c` |
| `/opt/data/crm/docs/planner-v2-checks/check_doc_ddl.py` | 抽取本文档 55 条 DDL 原样执行，并与迁移脚本结果比对 | `c3603ae2…8b4534` |

```bash
# 复跑（全部在副本上，不碰生产库）
cd /opt/data/crm/docs/planner-v2-checks
cp /opt/data/crm/crm.db /tmp/chk.db && /usr/bin/python3 migrations_v2.py --db /tmp/chk.db --no-backup
/usr/bin/python3 verify_convergence.py && /usr/bin/python3 verify_interrupt.py \
  && /usr/bin/python3 flow_sim.py && /usr/bin/python3 check_doc_ddl.py
```

**本轮结论**

- 表设计：18 张表、30 个索引（新增 20）、20 条外键规则、2 个兼容触发器，**在 `crm.db` 副本上 100% 可执行**；文档 §1 的 55 条 DDL 抽出来原样跑，建出的结构与迁移脚本逐项一致。
- 迁移：首跑 59 执行 / 3 跳过，重跑 40 / 22（全为幂等语句），15 个中断切点收敛，6 张业务表行数零变化。
- 业务流：订单 7 态、售后 3 态、SLA、删除保护、1:1 约束全部通过 SQL 级验证。

---

## 9. Q1–Q8 拍板决议（用户确认，2026-10-30，**替代 §7 的建议默认值**）

> 本节为权威决议。T1–T8 任务卡一律按本节执行；与 §7 冲突时以本节为准。

| # | 决议 | 对实施的影响 |
|---|---|---|
| Q1 | 押金+尾款**必须等于**订单总额（强制相等） | **T5**：pay-deposit 校验 0<押金≤总额；pay-balance 校验 尾款==总额−已收押金（精确相等，不接受缺口）；订单页"未收 ¥X"保留（付清为 0） |
| Q2 | 存量数据**清空**（保留 users 登录账号） | **T1**：迁移脚本末尾加一次性清空步骤（清 customers/deals/follow_ups/attachments/tags/customer_tags/import_log，保留 users，sessions 可清），schema_migrations 版本门控只跑一次；迁移前自动备份已有。§3.4 存量映射作废；T1 验收改为"升级后 6 业务表 0 行、users 完整"；"GET /deals 存量商机 stage=confirm"断言作废 |
| Q3 | 联系人 0–N，**不强制**主联系人 | **T3**：is_primary 可选（最多 1 个，设新主自动取消旧的）；创建不校验主联系人存在 |
| Q4 | 售后终态不可重开；新问题新建售后单；**一订单多售后单** | **T6**：aftersales.order_id **不加 UNIQUE**；不提供 reopen 端点；终态再操作 409 不变；订单详情返回售后单列表（复数） |
| Q5 | 单号格式照准 | **T4/T5**：`SO-YYYYMMDD-NNN` / `AS-YYYYMMDD-NNN` |
| Q6 | 新建线索查重：手机/微信命中已有线索或客户 → **提示**（不阻塞） | **T2**：leads POST 建前查 leads/customers 两表，命中在响应中带 `duplicate_hint`（类型/名称/id），仍返回成功；前端 T7a 弹提示 |
| Q7 | 被订单引用的物流公司**不能删除**（只能停用）；未引用可删 | **T5**：carriers DELETE：被 orders 引用 → 409 引导停用；未引用 → 允许删除 |
| Q8 | **删除 house_note**；客户备注用新 note 列 | **T1**：customers 表构造移除 house_note、新增 note（重建或 DROP COLUMN，按 SQLite 版本）；**T3**：清理 V1 代码全部 house_note 引用（routers/customers.py、CSV 导入字段映射、models、V1 前端客户表单/详情）；**"V1 零改动"承诺作废**（仅 house_note 相关点），§0.4 兼容承诺改为"除 house_note 改为 note 外零改动" |
- 已决：§7 的 8 条业务空白已由用户拍板，决议见 §9（2026-10-30）。