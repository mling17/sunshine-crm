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


def reset_data() -> None:
    """清空业务数据；``DELETE FROM customers`` 会按外键级联清掉 deals/follow_ups/customer_tags。

    前提：表已建好（TestClient 已进入 lifespan，见 ``ApiTestCase.setUp``）。
    """
    with db_conn() as conn:
        conn.execute("DELETE FROM customers")
        conn.execute("DELETE FROM tags")
        conn.execute("DELETE FROM sessions")


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


def insert_deal(
    customer_id: int,
    *,
    stage: str = "lead",
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
        return int(cur.lastrowid or 0)


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
        return int(cur.lastrowid or 0)


class ApiTestCase(unittest.TestCase):
    """每个用例：进 lifespan 建表 → 清数据 → 登录。

    顺序不能反：``reset_data`` 依赖已建好的表，所以 TestClient 必须先 ``__enter__``。
    """

    def setUp(self) -> None:
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
