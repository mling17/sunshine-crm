"""测试公共工具：数据重置、已登录 TestClient、直接造数据的小助手。

只给测试用，不参与生产路径。所有操作都指向 ``tests/_bootstrap.py`` 设定的临时库。
"""

from __future__ import annotations

import unittest

from tests import _bootstrap  # noqa: F401  —— 必须最先 import，设置临时 DB 环境变量

from fastapi.testclient import TestClient

from app.db import db_conn
from app.main import app
from app.security import now_iso

ADMIN = {"username": "chen", "password": "test123"}


class IdRow(int):
    """既当 int（老用例）、又能下标取字段（新用例）的返回值。"""

    def __new__(cls, value: int, **data):
        obj = super().__new__(cls, int(value))
        obj._data = data
        return obj

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)


def reset_data() -> None:
    """清空业务数据；``DELETE FROM customers`` 会按外键级联清掉 deals/follow_ups/customer_tags。

    前提：表已建好（TestClient 已进入 lifespan，见 ``ApiTestCase.setUp``）。
    """
    with db_conn() as conn:
        # 子表先删，避免 orders/aftersales 的 RESTRICT 外键挡住 customers 删除
        for table in (
            "aftersale_status_log", "aftersales", "order_status_log", "orders",
            "attachments", "follow_ups", "deals", "customer_tags",
            "lead_tags", "leads", "customers", "tags", "sessions", "import_log",
        ):
            conn.execute(f"DELETE FROM {table}")


def login(client: TestClient, password: str = ADMIN["password"]) -> TestClient:
    resp = client.post(
        "/api/crm/login", json={"username": ADMIN["username"], "password": password}
    )
    if resp.status_code != 200:
        raise AssertionError(f"测试登录失败：{resp.status_code} {resp.text}")
    return client


def open_client(login_first: bool = True) -> TestClient:
    """进入 lifespan（建表 + 种子用户）的 TestClient；默认顺手登录。"""
    client = TestClient(app)
    client.__enter__()
    if login_first:
        login(client)
    return client


def insert_customer(
    *,
    name: str = "测试客户",
    phone: str = "13900000000",
    wechat: str | None = None,
    customer_type: str = "personal",
    source: str = "wechat",
    intent_level: str | None = None,
    company_name: str | None = None,
) -> int:
    """直接落一条 customer"""
    now = now_iso()
    with db_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO customers (name, phone, wechat, customer_type, source, intent_level, company_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, phone, wechat, customer_type, source, intent_level, company_name, now, now),
        )
        cid = int(cur.lastrowid or 0)
        return IdRow(cid, id=cid, name=name, phone=phone, wechat=wechat,
                     customer_type=customer_type, source=source, intent_level=intent_level)


def insert_order(
    customer_id: int,
    deal_id: int | None = None,
    *,
    order_no: str | None = None,
    product_type: str = "天窗",
    model: str = "平移",
    spec: str = "1200*1400",
    amount: float = 12800.0,
    status: str = "completed",
) -> int:
    """直接落一条 order"""
    now = now_iso()
    with db_conn() as conn:
        if order_no is None:
            _n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] + 1
            order_no = f"SO-20261030-{_n:03d}"
        if deal_id is None:
            cur = conn.execute(
                "INSERT INTO deals (customer_id, product_type, amount, stage, closed_at, created_at, updated_at)"
                " VALUES (?, ?, ?, 'won', ?, ?, ?)",
                (customer_id, product_type, amount, now, now, now),
            )
            deal_id = int(cur.lastrowid or 0)
        cur = conn.execute(
            """
            INSERT INTO orders (order_no, customer_id, deal_id, product_type, model, spec, amount, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (order_no, customer_id, deal_id, product_type, model, spec, amount, status, now, now),
        )
        oid = int(cur.lastrowid or 0)
        return IdRow(oid, id=oid, customer_id=customer_id, deal_id=deal_id,
                     order_no=order_no, amount=amount, status=status)


def insert_deal(
    customer_id: int,
    *,
    stage: str = "confirm",  # 修改默认值为 confirm
    amount: float = 1000.0,
    product_type: str = "天窗",
    closed_at: str | None = None,
) -> int:
    """直接落一条 deal（T3 阶段 deals 路由还没实现，级联删除要用真数据验）。"""
    now = now_iso()
    with db_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO deals (customer_id, product_type, amount, stage, closed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (customer_id, product_type, amount, stage, closed_at, now, now),
        )
        did = int(cur.lastrowid or 0)
        return IdRow(did, id=did, customer_id=customer_id, stage=stage, amount=amount)


def insert_follow_up(
    customer_id: int,
    *,
    content: str,
    deal_id: int | None = None,
    next_date: str | None = None,
) -> int:
    with db_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO follow_ups (customer_id, deal_id, content, next_date, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (customer_id, deal_id, content, next_date, now_iso()),
        )
        fid = int(cur.lastrowid or 0)
        return IdRow(fid, id=fid, customer_id=customer_id, deal_id=deal_id, content=content)


class ApiTestCase(unittest.TestCase):
    """每个用例：进 lifespan 建表 → 清数据 → 登录。

    顺序不能反：``reset_data`` 依赖已建好的表，所以 TestClient 必须先 ``__enter__``。
    """

    def setUp(self) -> None:
        from app.db import db_conn as _db_conn
        self.db_conn = _db_conn
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        reset_data()
        login(self.client)

    # ---- 常用动作 ----

    def create_customer(self, **payload) -> dict:
        resp = self.client.post("/api/crm/customers", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def create_deal(self, customer_id: int, **payload) -> dict:
        body = {"customer_id": customer_id, "amount": 1000.0}
        body.update(payload)
        resp = self.client.post("/api/crm/deals", json=body)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()
