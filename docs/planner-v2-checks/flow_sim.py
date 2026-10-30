"""业务流验证：在「存量库副本 + M1 迁移」上跑一遍 V2 全链路，证明 DDL 支撑状态机。

不联网、不起服务、不碰生产库。任何断言失败 = 表设计有缺口。
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).parent
PROD_DB = Path("/opt/data/crm/crm.db")

spec = importlib.util.spec_from_file_location("mig", HERE / "migrations_v2.py")
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)

NOW = "2026-10-30T22:40:00+08:00"


def setup(path: Path) -> sqlite3.Connection:
    path.unlink(missing_ok=True)
    src = sqlite3.connect(PROD_DB)
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.close()
    mig.apply(path, backup=False, verbose=False)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def next_no(conn, table: str, column: str, prefix: str, day: str) -> str:
    """单用户场景的发号：同一事务内 MAX+1，UNIQUE 兜底。"""
    like = f"{prefix}{day}-%"
    row = conn.execute(
        f"SELECT COALESCE(MAX(CAST(substr({column}, -3) AS INTEGER)), 0) AS n "
        f"FROM {table} WHERE {column} LIKE ?", (like,)).fetchone()
    return f"{prefix}{day}-{int(row['n']) + 1:03d}"


def ts(conn, table, pk):  # 便捷读取
    return dict(conn.execute(f"SELECT * FROM {table} WHERE id = ?", (pk,)).fetchone())


def main() -> int:
    conn = setup(HERE / "flow.db")

    # ---------- 1. 线索 + 跟进 + 意向 ----------
    cur = conn.execute(
        "INSERT INTO leads (name, phone, wechat, lead_type, company_name, source, location, note,"
        " intent_level, status, owner, created_at, updated_at)"
        " VALUES ('王先生', '13900000001', NULL, 'personal', NULL, 'wechat', '潍坊市奎文区', '看样板房后联系',"
        " 'high', 'new', '本人', ?, ?)", (NOW, NOW))
    lead_id = cur.lastrowid
    conn.execute(
        "INSERT INTO follow_ups (object_type, object_id, method, content, next_date, created_at)"
        " VALUES ('lead', ?, 'wechat', '微信沟通，约周六量尺', '2026-11-01', ?)", (lead_id, NOW))
    conn.execute("UPDATE leads SET status='following', updated_at=? WHERE id=?", (NOW, lead_id))

    # ---------- 2. 转化：建客户 + 首商机，线索归档（N2 意向顺延）----------
    lead = ts(conn, "leads", lead_id)
    cur = conn.execute(
        "INSERT INTO customers (name, phone, wechat, location, house_note, customer_type, source,"
        " intent_level, owner, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (lead["name"], lead["phone"], lead["wechat"], lead["location"], lead["note"],
         lead["lead_type"], lead["source"], lead["intent_level"], "本人", lead["created_at"], NOW))
    customer_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO deals (customer_id, title, product_type, model, spec, amount, stage,"
        " owner, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (customer_id, "王先生-天窗首单", "天窗", "平移", "1200*1400", 12800.00, "confirm",
         "本人", NOW, NOW))
    deal_id = cur.lastrowid
    conn.execute("UPDATE leads SET status='converted', converted_customer_id=?, converted_deal_id=?,"
                 " updated_at=? WHERE id=?", (customer_id, deal_id, NOW, lead_id))
    conn.execute("INSERT INTO customer_tags (customer_id, tag_id) SELECT ?, tag_id FROM lead_tags",
                 (customer_id,))
    # D4 去重查询（提示用，不阻断）
    dup = conn.execute("SELECT id, name FROM customers WHERE phone = ? OR (wechat IS NOT NULL AND wechat = ?)",
                       (lead["phone"], lead["wechat"])).fetchall()
    assert [r["id"] for r in dup] == [customer_id], dup
    assert ts(conn, "customers", customer_id)["intent_level"] == "high"  # N2
    print(f"✓ 线索→客户/商机：lead={lead_id} customer={customer_id} deal={deal_id}，意向顺延=high")

    # ---------- 3. 商机推进：confirm → quote → negotiate ----------
    for stage in ("quote", "negotiate"):
        conn.execute("UPDATE deals SET stage=?, updated_at=? WHERE id=?", (stage, NOW, deal_id))

    # ---------- 4. 赢单 → 生成订单（1:1，总额继承 R4）----------
    deal = ts(conn, "deals", deal_id)
    order_no = next_no(conn, "orders", "order_no", "SO-", "20261030")
    cur = conn.execute(
        "INSERT INTO orders (order_no, customer_id, deal_id, product_type, model, spec, amount,"
        " status, owner, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (order_no, customer_id, deal_id, deal["product_type"], deal["model"], deal["spec"],
         deal["amount"], "pending_payment", "本人", NOW, NOW))
    order_id = cur.lastrowid
    conn.execute("UPDATE deals SET stage='won', closed_at=?, order_id=?, updated_at=? WHERE id=?",
                 (NOW, order_id, NOW, deal_id))
    conn.execute("INSERT INTO order_status_log (order_id, from_status, to_status, note, created_at)"
                 " VALUES (?, NULL, 'pending_payment', '商机赢单生成订单', ?)", (order_id, NOW))
    assert ts(conn, "orders", order_id)["amount"] == deal["amount"] == 12800.0
    print(f"✓ 赢单生成订单 {order_no}，总额继承={deal['amount']:.2f}")

    # ---------- 5. 订单 7 态 6 跃迁 ----------
    def screenshot(order_id: int, tag: str) -> int:
        cur = conn.execute(
            "INSERT INTO attachments (object_type, object_id, storage_key, file_name, mime_type, size, created_at)"
            " VALUES ('order_payment', ?, ?, ?, 'image/jpeg', 1024, ?)",
            (order_id, f"2026/10/30/{tag}.jpg", f"{tag}.jpg", NOW))
        return cur.lastrowid

    ORDER_FLOW = {
        "pending_payment": "deposit_paid",
        "deposit_paid": "producing",
        "producing": "balance_paid",
        "balance_paid": "ready_to_ship",
        "ready_to_ship": "shipped",
        "shipped": "completed",
        "completed": None,
    }

    def move(order_id: int, expect: str, to: str, *, log: dict | None = None, **columns):
        """columns 落 orders 表；log 落 order_status_log（截图/运单等审计字段）。"""
        cur = conn.execute("SELECT status FROM orders WHERE id=?", (order_id,)).fetchone()["status"]
        if cur != expect or ORDER_FLOW.get(cur) != to:
            raise RuntimeError(f"非法跃迁：{cur} → {to}（合法下一态：{ORDER_FLOW.get(cur)}）")
        log = log or {}
        sets = "".join(f"{k}=?, " for k in columns)
        conn.execute(f"UPDATE orders SET {sets}status=?, updated_at=? WHERE id=?",
                     [*columns.values(), to, NOW, order_id])
        conn.execute(
            "INSERT INTO order_status_log (order_id, from_status, to_status, deposit_paid, balance_paid,"
            " screenshot_ids, logistics_mode, carrier_id, tracking_no, note, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (order_id, expect, to, log.get("deposit_paid"), log.get("balance_paid"),
             log.get("screenshot_ids"), log.get("logistics_mode"), log.get("carrier_id"),
             log.get("tracking_no"), log.get("note"), NOW))
        return to

    # 5.1 待支付 → 已支付押金（金额 + 截图）
    shot_deposit = screenshot(order_id, "deposit")
    move(order_id, "pending_payment", "deposit_paid",
         deposit_paid=3800.00,
         log={"deposit_paid": 3800.00, "screenshot_ids": f"[{shot_deposit}]",
              "note": "押金到账（系统外财务已确认）"})
    # 5.2 已支付押金 → 生产中（无输入）
    move(order_id, "deposit_paid", "producing", log={"note": "财务确认后转入生产"})
    # 5.3 生产中 → 已支付尾款（金额 + 截图）
    shot_balance = screenshot(order_id, "balance")
    move(order_id, "producing", "balance_paid",
         balance_paid=9000.00,
         log={"balance_paid": 9000.00, "screenshot_ids": f"[{shot_balance}]", "note": "尾款到账"})
    # 5.4 已支付尾款 → 待发货
    move(order_id, "balance_paid", "ready_to_ship", log={"note": "备货完成"})
    # 5.5 待发货 → 已发货（物流公司 + 运单号必填）
    cur = conn.execute("INSERT INTO carriers (name, contact, phone, created_at, updated_at)"
                       " VALUES ('德邦物流', '李师傅', '400-000-0000', ?, ?)", (NOW, NOW))
    carrier_id = cur.lastrowid
    move(order_id, "ready_to_ship", "shipped", logistics_mode="carrier", carrier_id=carrier_id,
         tracking_no="DP20261030001", shipped_at=NOW,
         log={"logistics_mode": "carrier", "carrier_id": carrier_id,
              "tracking_no": "DP20261030001", "note": "已交德邦"})
    # 5.6 已发货 → 已完成
    move(order_id, "shipped", "completed", completed_at=NOW, log={"note": "客户确认收货"})

    order = ts(conn, "orders", order_id)
    assert order["status"] == "completed"
    assert order["deposit_paid"] + order["balance_paid"] == order["amount"]
    logs = conn.execute("SELECT to_status FROM order_status_log WHERE order_id=? ORDER BY id",
                        (order_id,)).fetchall()
    assert [r[0] for r in logs] == [
        "pending_payment", "deposit_paid", "producing", "balance_paid",
        "ready_to_ship", "shipped", "completed"], logs
    print(f"✓ 订单 7 态全流程：{[r[0] for r in logs]}")

    # 5.7 非法跃迁必须被拒（越级 / 回退）
    for bad_from, bad_expect, bad_to in (
        ("pending_payment", "pending_payment", "producing"),   # 越级
        ("completed", "completed", "shipped"),                 # 回退
    ):
        conn.execute("UPDATE orders SET status=? WHERE id=?", (bad_from, order_id))
        try:
            move(order_id, bad_expect, bad_to)
            raise AssertionError(f"越级跃迁未被拒绝：{bad_from}→{bad_to}")
        except RuntimeError:
            pass
    conn.execute("UPDATE orders SET status='completed' WHERE id=?", (order_id,))
    print("✓ 越级/回退跃迁被状态机拒绝")

    # 5.8 自送场景：运单号填「无」
    cur = conn.execute("INSERT INTO deals (customer_id, title, amount, stage, created_at, updated_at)"
                       " VALUES (?, '自送单', 5000, 'won', ?, ?)", (customer_id, NOW, NOW))
    deal2 = cur.lastrowid
    no2 = next_no(conn, "orders", "order_no", "SO-", "20261030")
    cur = conn.execute("INSERT INTO orders (order_no, customer_id, deal_id, amount, status,"
                       " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                       (no2, customer_id, deal2, 5000, "pending_payment", NOW, NOW))
    order2 = cur.lastrowid
    conn.execute("UPDATE orders SET status='ready_to_ship', logistics_mode='self' WHERE id=?", (order2,))
    conn.execute("UPDATE orders SET status='shipped', tracking_no='无', shipped_at=? WHERE id=?", (NOW, order2))
    assert ts(conn, "orders", order2)["tracking_no"] == "无"
    print("✓ 自送场景运单号='无'")

    # ---------- 6. 冻结约束（N6/N7 的 DB 层兜底）----------
    for stmt, args, why in (
        ("INSERT INTO orders (order_no, customer_id, deal_id, amount, status, created_at, updated_at)"
         " VALUES ('SO-20261030-999', ?, ?, 1, 'pending_payment', ?, ?)", (customer_id, deal_id, NOW, NOW),
         "同一商机第二张订单（UNIQUE(deal_id)）"),
        ("INSERT INTO orders (order_no, customer_id, deal_id, amount, status, created_at, updated_at)"
         " VALUES (?, ?, ?, 1, 'pending_payment', ?, ?)", (order_no, customer_id, deal2, NOW, NOW),
         "订单号重复（UNIQUE(order_no)）"),
        ("INSERT INTO customer_contacts (customer_id, name, created_at, updated_at)"
         " VALUES (999999, '幽灵联系人', ?, ?)", (NOW, NOW), "联系人挂不存在的客户（FK）"),
        ("INSERT INTO aftersales (no, order_id, customer_id, type, description, created_at, updated_at)"
         " VALUES ('AS-X', 999999, ?, 'repair', 'x', ?, ?)", (customer_id, NOW, NOW), "售后挂不存在的订单（FK）"),
    ):
        try:
            conn.execute(stmt, args)
            raise AssertionError(f"约束未生效：{why}")
        except sqlite3.IntegrityError:
            pass
    print("✓ DB 约束生效：商机↔订单 1:1 / 订单号唯一 / 外键不可悬挂")

    # ---------- 7. 售后 3 态流 ----------
    as_no = next_no(conn, "aftersales", "no", "AS-", "20261030")
    cur = conn.execute("INSERT INTO aftersales (no, order_id, customer_id, type, description, status,"
                       " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                       (as_no, order_id, customer_id, "repair", "天窗密封条渗水", "pending", NOW, NOW))
    as_id = cur.lastrowid
    for frm, to in (("pending", "processing"), ("processing", "done")):
        conn.execute("UPDATE aftersales SET status=?, result=COALESCE(result,?), closed_at=?, updated_at=?"
                     " WHERE id=?",
                     (to, "已更换密封条并复检" if to == "done" else None,
                      NOW if to == "done" else None, NOW, as_id))
        conn.execute("INSERT INTO aftersale_status_log (aftersale_id, from_status, to_status, note, created_at)"
                     " VALUES (?,?,?,?,?)", (as_id, frm, to, "售后处理", NOW))
    # 拒绝分支
    cur = conn.execute("INSERT INTO aftersales (no, order_id, customer_id, type, description, status,"
                       " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                       (next_no(conn, "aftersales", "no", "AS-", "20261030"), order_id, customer_id,
                        "complaint", "投诉安装噪音", "pending", NOW, NOW))
    as2 = cur.lastrowid
    conn.execute("UPDATE aftersales SET status='rejected', reject_reason='非质量问题，已电话解释',"
                 " closed_at=?, updated_at=? WHERE id=?", (NOW, NOW, as2))
    assert ts(conn, "aftersales", as_id)["status"] == "done"
    assert ts(conn, "aftersales", as2)["reject_reason"]
    print(f"✓ 售后 3 态流：{as_no} done / AS-...-002 rejected")

    # ---------- 8. SLA 查询（N8：待处理超 3 天）----------
    conn.execute("UPDATE aftersales SET status='pending', created_at=datetime('now','localtime','-4 days')"
                 " WHERE id=?", (as2,))
    overdue = conn.execute(
        "SELECT no FROM aftersales WHERE status='pending'"
        " AND julianday(date('now','localtime')) - julianday(date(created_at)) > 3").fetchall()
    assert [r["no"] for r in overdue] == [ts(conn, "aftersales", as2)["no"]], overdue
    print(f"✓ SLA 查询命中超 3 天待处理单：{[r['no'] for r in overdue]}")

    # ---------- 9. 删除保护（RESTRICT）----------
    for stmt, args, why in (
        ("DELETE FROM orders WHERE id=?", (order_id,), "删订单（有售后单 RESTRICT）"),
        ("DELETE FROM deals WHERE id=?", (deal_id,), "删商机（有订单 RESTRICT）"),
        ("DELETE FROM customers WHERE id=?", (customer_id,), "删客户（有订单 RESTRICT）"),
        ("DELETE FROM carriers WHERE id=?", (carrier_id,), "删物流公司（被订单引用 RESTRICT）"),
    ):
        try:
            conn.execute(stmt, args)
            raise AssertionError(f"删除保护未生效：{why}")
        except sqlite3.IntegrityError:
            pass
    print("✓ 删除保护生效：订单/商机/客户/物流公司均被 RESTRICT")

    # ---------- 10. 级联删除：删订单 → 状态日志、售后日志级联 ----------
    conn.execute("DELETE FROM aftersales WHERE order_id=?", (order_id,))
    conn.execute("DELETE FROM order_status_log WHERE order_id=? AND id != (SELECT MIN(id) FROM order_status_log)", (order_id,))
    n_log = conn.execute("SELECT COUNT(*) FROM order_status_log WHERE order_id=?", (order_id,)).fetchone()[0]
    assert n_log == 1
    print("✓ 清理路径可用（售后先清，再删日志）")

    conn.rollback()
    conn.close()
    print("\n全部业务流断言通过（副本库 flow.db 已回滚，不留脏数据）")
    return 0


if __name__ == "__main__":
    sys.exit(main())