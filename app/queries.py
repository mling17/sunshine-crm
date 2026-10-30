"""
CRM V2 SQL 查询语句（Planner §2.8）。

所有查询只写一次，供路由层和测试共同 import。
"""

# ---------------- 客户生命周期 ----------------
CUSTOMER_LIFECYCLE_SQL = """
    CASE
        WHEN NOT EXISTS (SELECT 1 FROM deals d WHERE d.customer_id = customers.id)
            THEN 'potential'
        WHEN EXISTS (SELECT 1 FROM deals d WHERE d.customer_id = customers.id AND d.stage IN ('confirm','quote','negotiate'))
            THEN 'dealing'
        WHEN EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = customers.id AND o.status = 'completed')
            THEN 'won'
        WHEN (
            SELECT COUNT(*) FROM orders o
            WHERE o.customer_id = customers.id AND o.status = 'completed'
        ) >= 2
            THEN 'repeat'
        ELSE 'potential'
    END
"""


# ---------------- 订单未收金额 ----------------
ORDER_UNPAID_SQL = """
    ROUND(COALESCE(
        (SELECT amount FROM orders WHERE id = orders.id) -
        (SELECT COALESCE(SUM(deposit_paid), 0) FROM orders WHERE id = orders.id) -
        (SELECT COALESCE(SUM(balance_paid), 0) FROM orders WHERE id = orders.id),
    0), 2)
"""


# ---------------- 售后 SLA 查询 ----------------
AFTERSALE_SLA_SQL = """
    SELECT a.id, a.no, a.type, a.created_at,
           CAST(julianday(date('now','localtime')) - julianday(date(a.created_at)) AS INTEGER) AS days_pending,
           o.order_no, c.name AS customer_name
      FROM aftersales a
      JOIN orders o    ON o.id = a.order_id
      JOIN customers c ON c.id = a.customer_id
     WHERE a.status = 'pending'
       AND julianday(date('now','localtime')) - julianday(date(a.created_at)) > ?
     ORDER BY a.created_at ASC;
"""