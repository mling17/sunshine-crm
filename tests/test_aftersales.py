"""
售后单功能测试
"""
import unittest
from unittest.mock import patch, MagicMock

# 注意：tests._util 必须先于 app.* import（_bootstrap 设置临时库环境变量）。
from tests._util import ApiTestCase, insert_customer, insert_order
from app.db import db_conn
from app.security import now_iso


class TestAftersales(ApiTestCase):
    def setUp(self):
        super().setUp()
        # 初始化一些测试数据
        self.customer = insert_customer(name="测试客户")
        self.order = insert_order(
            customer_id=self.customer["id"],
            amount=1000.0,
            status="completed"
        )

    def _create_aftersale(self) -> int:
        resp = self.client.post(
            "/api/crm/aftersales",
            json={"order_id": self.order["id"], "type": "repair",
                  "description": "产品有质量问题"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["id"]

    def test_create_aftersale(self):
        """测试创建售后单"""
        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["type"], "repair")
        self.assertIn("AS-", data["no"])

    def test_create_aftersale_can_link_previous_aftersale_from_same_order(self):
        first_id = self._create_aftersale()
        self.client.post(
            "/api/crm/follow-ups",
            data={
                "object_type": "aftersale",
                "object_id": str(first_id),
                "content": "首次售后处理完成",
            },
        )
        finished = self.client.post(
            f"/api/crm/aftersales/{first_id}/finish",
            json={"result": "首次问题已解决"},
        )
        self.assertEqual(finished.status_code, 200, finished.text)
        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "同一问题再次出现",
                "related_aftersale_id": first_id,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        created = resp.json()
        self.assertEqual(created["related_aftersale_id"], first_id)
        self.assertTrue(created["related_aftersale_no"].startswith("AS-"))
        self.assertEqual(created["related_aftersale_status"], "done")

        detail = self.client.get(f"/api/crm/aftersales/{created['id']}").json()
        self.assertEqual(detail["related_aftersale_id"], first_id)
        listed = self.client.get(
            "/api/crm/aftersales", params={"order_id": self.order["id"]}
        ).json()["items"]
        linked = next(item for item in listed if item["id"] == created["id"])
        self.assertEqual(linked["related_aftersale_no"], created["related_aftersale_no"])

    def test_related_aftersale_must_belong_to_the_same_order(self):
        first_id = self._create_aftersale()
        self.client.post(
            "/api/crm/follow-ups",
            data={
                "object_type": "aftersale",
                "object_id": str(first_id),
                "content": "处理历史售后",
            },
        )
        self.client.post(
            f"/api/crm/aftersales/{first_id}/finish",
            json={"result": "已完成"},
        )
        other_customer = insert_customer(name="另一个客户", phone="13800000088")
        other_order = insert_order(customer_id=other_customer["id"], amount=800.0)

        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": other_order["id"],
                "type": "repair",
                "description": "跨订单关联",
                "related_aftersale_id": first_id,
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "related_aftersale_order_mismatch")

    def test_related_aftersale_must_be_completed(self):
        first_id = self._create_aftersale()
        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "重复问题",
                "related_aftersale_id": first_id,
            },
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["code"], "related_aftersale_not_completed")

    def test_create_aftersale_not_found_order(self):
        """测试创建售后单时订单不存在"""
        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": 99999,
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(resp.status_code, 404)

    def test_get_aftersale_detail(self):
        """测试获取售后单详情"""
        # 先创建一个售后单
        aftersale_resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(aftersale_resp.status_code, 200)
        aftersale_data = aftersale_resp.json()
        aftersale_id = aftersale_data["id"]

        # 获取详情
        resp = self.client.get(f"/api/crm/aftersales/{aftersale_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], aftersale_id)
        self.assertEqual(data["type"], "repair")

    def test_start_aftersale_deprecated(self):
        """定稿：不再有「开始处理」，接口返回 410（记跟进自动进入处理中）"""
        aftersale_id = self._create_aftersale()
        resp = self.client.post(f"/api/crm/aftersales/{aftersale_id}/start")
        self.assertEqual(resp.status_code, 410, resp.text)
        self.assertEqual(resp.json()["code"], "deprecated")

    def test_follow_up_moves_aftersale_to_processing(self):
        """记一条跟进 → 待处理自动变处理中（定稿 v2.4 #9）"""
        aftersale_id = self._create_aftersale()
        fu = self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id),
                  "content": "已上门检查，等配件"},
        )
        self.assertEqual(fu.status_code, 200, fu.text)
        detail = self.client.get(f"/api/crm/aftersales/{aftersale_id}").json()
        self.assertEqual(detail["status"], "processing")
        types = [t["type"] for t in detail.get("timeline", [])]
        self.assertIn("follow", types)
        self.assertIn("create", types)
        self.assertIn("stage", types)

    def test_finish_aftersale(self):
        """先记跟进（自动处理中）→ 标记完成 → 写 result/closed_at + 履历"""
        aftersale_id = self._create_aftersale()
        pending_finish = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish", json={"result": "已修复"}
        )
        self.assertEqual(pending_finish.status_code, 409, "待处理不能直接完成")
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id),
                  "content": "已上门更换电机"},
        )
        done = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish", json={"result": "已修复"}
        )
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json()["status"], "done")
        self.assertTrue(done.json()["closed_at"])

        locked = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish", json={"result": "再次修改"}
        )
        self.assertEqual(locked.status_code, 409, locked.text)
        detail = self.client.get(f"/api/crm/aftersales/{aftersale_id}").json()
        self.assertEqual(detail["result"], "已修复")

    def test_finish_aftersale_missing_result(self):
        """测试完成售后单缺少处理结果"""
        # 先创建并开始处理售后单
        aftersale_resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(aftersale_resp.status_code, 200)
        aftersale_data = aftersale_resp.json()
        aftersale_id = aftersale_data["id"]

        # 定稿：记一条跟进 → 自动进入处理中
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id), "content": "开始处理"},
        )
        
        # 完成处理但没有结果
        resp = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish",
            json={"result": ""}
        )
        self.assertEqual(resp.status_code, 400)

    def test_reject_aftersale_deprecated(self):
        """定稿：售后不再支持拒绝，接口 410"""
        aftersale_id = self._create_aftersale()
        resp = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/reject", json={"reject_reason": "不属于售后范围"}
        )
        self.assertEqual(resp.status_code, 410, resp.text)

    def test_reject_without_reason_also_deprecated(self):
        aftersale_id = self._create_aftersale()
        resp = self.client.post(f"/api/crm/aftersales/{aftersale_id}/reject", json={})
        self.assertEqual(resp.status_code, 410, resp.text)

    def test_list_aftersales(self):
        """测试获取售后单列表"""
        # 创建几个售后单
        self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "return",
                "description": "想要退货"
            }
        )

        # 获取列表
        resp = self.client.get("/api/crm/aftersales")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["items"]), 2)

    def test_list_aftersales_filter_by_status(self):
        """测试按状态筛选售后单列表"""
        # 创建一个售后单
        aftersale_resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(aftersale_resp.status_code, 200)
        aftersale_data = aftersale_resp.json()
        aftersale_id = aftersale_data["id"]

        # 定稿：记一条跟进 → 自动进入处理中
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id), "content": "开始处理"},
        )
        
        # 获取待处理的售后单
        resp = self.client.get("/api/crm/aftersales?status=pending")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 应该没有待处理的单
        self.assertEqual(data["total"], 0)

        # 获取处理中的售后单
        resp = self.client.get("/api/crm/aftersales?status=processing")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 应该有一个处理中的单
        self.assertEqual(data["total"], 1)

    def test_aftersale_closed_after_done(self):
        """完成后再记跟进 → 409 aftersale_closed（定稿 v2.6 #3）"""
        aftersale_id = self._create_aftersale()
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id), "content": "处理中"},
        )
        self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish", json={"result": "已修复"}
        )
        resp = self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id), "content": "再来一条"},
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["code"], "aftersale_closed")

    def test_aftersale_sla_boundary(self):
        """测试售后单SLA边界条件"""
        # 创建售后单
        resp = self.client.post(
            "/api/crm/aftersales",
            json={
                "order_id": self.order["id"],
                "type": "repair",
                "description": "产品有质量问题"
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        aftersale_id = data["id"]
        
        # 检查售后单是否在待处理状态
        resp = self.client.get(f"/api/crm/aftersales/{aftersale_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "pending")


if __name__ == "__main__":
    unittest.main()


class TestAftersalesListSort(ApiTestCase):
    """Ticket #11：售后列表 size 白名单 + sort/order 服务端排序。"""

    def setUp(self):
        super().setUp()
        self.customer_a = insert_customer(name="张售后客户", phone="13800139001")
        self.customer_b = insert_customer(name="李售后客户", phone="13800139002")
        self.order_a = insert_order(
            customer_id=self.customer_a, order_no="SO-SORT-001", amount=100.0
        )
        self.order_b = insert_order(
            customer_id=self.customer_b, order_no="SO-SORT-002", amount=200.0
        )

    def _create(self, order_id, *, type="repair", description="问题描述"):
        resp = self.client.post(
            "/api/crm/aftersales",
            json={"order_id": order_id, "type": type, "description": description},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    @staticmethod
    def _rebuild_aftersales(nullable_description: bool) -> None:
        """测试内重建 aftersales 表（仅放宽/收紧 description 的 NOT NULL，列序不变）。"""
        description_ddl = "TEXT" if nullable_description else "TEXT NOT NULL"
        with db_conn() as conn:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute(
                f"""
                CREATE TABLE aftersales_shell (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  no TEXT NOT NULL UNIQUE,
                  order_id INTEGER NOT NULL,
                  customer_id INTEGER NOT NULL,
                  type TEXT NOT NULL,
                  type_other TEXT,
                  description {description_ddl},
                  status TEXT NOT NULL DEFAULT 'pending',
                  result TEXT,
                  reject_reason TEXT,
                  closed_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  create_time TEXT NOT NULL DEFAULT '',
                  update_time TEXT NOT NULL DEFAULT '',
                  is_delete INTEGER NOT NULL DEFAULT 0,
                  related_aftersale_id INTEGER
                )
                """
            )
            conn.execute("INSERT INTO aftersales_shell SELECT * FROM aftersales")
            conn.execute("DROP TABLE aftersales")
            conn.execute("ALTER TABLE aftersales_shell RENAME TO aftersales")
            conn.execute("PRAGMA foreign_keys=ON")

    def test_default_order_created_at_desc_id_desc(self):
        """默认口径：created_at DESC，同时间戳时稳定次键 id DESC（最新建的在前）。"""
        ids = [self._create(self.order_a, description=f"问题{i}")["id"] for i in range(3)]
        with db_conn() as conn:
            for aid in ids:
                conn.execute(
                    "UPDATE aftersales SET created_at = '2026-11-18T00:00:00' WHERE id = ?",
                    (aid,),
                )
        resp = self.client.get("/api/crm/aftersales?size=500")
        self.assertEqual(resp.status_code, 200, resp.text)
        ordered_ids = [item["id"] for item in resp.json()["items"]]
        self.assertEqual(ordered_ids, [ids[2], ids[1], ids[0]])

    def test_explicit_sort_stable_id_desc_tiebreak(self):
        """显式排序也必须带稳定次键：同 created_at 按 id DESC。"""
        ids = [self._create(self.order_a, description=f"问题{i}")["id"] for i in range(3)]
        with db_conn() as conn:
            for aid in ids:
                conn.execute(
                    "UPDATE aftersales SET created_at = '2026-11-18T00:00:00' WHERE id = ?",
                    (aid,),
                )
        resp = self.client.get("/api/crm/aftersales?sort=created_at&order=asc&size=500")
        self.assertEqual(resp.status_code, 200, resp.text)
        ordered_ids = [item["id"] for item in resp.json()["items"]]
        self.assertEqual(ordered_ids, [ids[2], ids[1], ids[0]])

    def test_size_whitelist(self):
        self._create(self.order_a)
        for bad in (0, 1, 15, 200, 501, -10):
            resp = self.client.get(f"/api/crm/aftersales?size={bad}")
            self.assertEqual(resp.status_code, 400, f"size={bad}")
            self.assertEqual(resp.json()["code"], "invalid_page_size", f"size={bad}")
        resp = self.client.get("/api/crm/aftersales")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["size"], 20)  # 默认 20
        for ok in (10, 20, 50, 100, 500):
            resp = self.client.get(f"/api/crm/aftersales?size={ok}")
            self.assertEqual(resp.status_code, 200, f"size={ok}")

    def test_page_must_be_positive(self):
        self._create(self.order_a)
        for bad in (0, -1):
            resp = self.client.get(f"/api/crm/aftersales?page={bad}")
            self.assertEqual(resp.status_code, 400, f"page={bad}")
            self.assertEqual(resp.json()["code"], "invalid_page", f"page={bad}")

    def test_pagination_window(self):
        for i in range(25):
            self._create(self.order_a, description=f"批量问题{i}")
        resp = self.client.get("/api/crm/aftersales?size=10&page=2")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["total"], 25)
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["size"], 10)
        self.assertEqual(len(data["items"]), 10)

    def test_invalid_sort_or_order_400(self):
        self._create(self.order_a)
        for url in (
            "/api/crm/aftersales?sort=description",
            "/api/crm/aftersales?sort=no;DROP TABLE aftersales",
            "/api/crm/aftersales?sort=created_at&order=up",
            "/api/crm/aftersales?sort=customer&order=1 desc",
        ):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 400, resp.text)

    def test_sort_by_join_columns_customer_and_order(self):
        self._create(self.order_a, description="A客户问题")
        self._create(self.order_b, description="B客户问题")
        # 客户名（JOIN customers）：SQLite BINARY 字节序 张(0x5F20) < 李(0x674E)
        resp = self.client.get("/api/crm/aftersales?sort=customer&order=asc&size=500")
        names = [item["customer_name"] for item in resp.json()["items"]]
        self.assertEqual(names, ["张售后客户", "李售后客户"])
        resp = self.client.get("/api/crm/aftersales?sort=customer&order=desc&size=500")
        names = [item["customer_name"] for item in resp.json()["items"]]
        self.assertEqual(names, ["李售后客户", "张售后客户"])
        # 关联订单号（JOIN orders）
        resp = self.client.get("/api/crm/aftersales?sort=order&order=asc&size=500")
        order_nos = [item["order_no"] for item in resp.json()["items"]]
        self.assertEqual(order_nos, ["SO-SORT-001", "SO-SORT-002"])
        resp = self.client.get("/api/crm/aftersales?sort=order&order=desc&size=500")
        order_nos = [item["order_no"] for item in resp.json()["items"]]
        self.assertEqual(order_nos, ["SO-SORT-002", "SO-SORT-001"])

    def test_sort_by_aftersale_no_and_type(self):
        self._create(self.order_a, type="return", description="退货")
        self._create(self.order_a, type="repair", description="维修")
        resp = self.client.get("/api/crm/aftersales?sort=type&order=asc&size=500")
        types = [item["type"] for item in resp.json()["items"]]
        self.assertEqual(types, ["repair", "return"])
        resp = self.client.get("/api/crm/aftersales?sort=aftersale_no&order=asc&size=500")
        nos = [item["no"] for item in resp.json()["items"]]
        self.assertEqual(nos, sorted(nos))

    def test_sort_problem_nulls_last_both_directions(self):
        """可空排序列（problem → description）升/降序都 NULL 沉底。

        新建口径 description 必填，这里临时重建表放宽 NOT NULL 来构造 NULL 数据，
        用例结束（含失败）都会恢复严格口径。
        """
        self._rebuild_aftersales(nullable_description=True)

        def _restore_strict_schema():
            with db_conn() as conn:
                conn.execute("DELETE FROM aftersales WHERE description IS NULL")
            self._rebuild_aftersales(False)

        self.addCleanup(_restore_strict_schema)
        self._create(self.order_a, description="Alpha 问题")
        self._create(self.order_b, description="Zulu 问题")
        now = now_iso()
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO aftersales (no, order_id, customer_id, type, description,"
                " status, created_at, updated_at)"
                " VALUES ('AS-NULL-1', ?, ?, 'repair', NULL, 'pending', ?, ?)",
                (int(self.order_a), int(self.customer_a), now, now),
            )
        resp = self.client.get("/api/crm/aftersales?sort=problem&order=asc&size=500")
        descriptions = [item["description"] for item in resp.json()["items"]]
        self.assertEqual(descriptions[:2], ["Alpha 问题", "Zulu 问题"])
        self.assertIsNone(descriptions[-1])
        resp = self.client.get("/api/crm/aftersales?sort=problem&order=desc&size=500")
        descriptions = [item["description"] for item in resp.json()["items"]]
        self.assertEqual(descriptions[:2], ["Zulu 问题", "Alpha 问题"])
        self.assertIsNone(descriptions[-1])

    def test_filters_keep_working_with_sort(self):
        first = self._create(self.order_a, description="第一个")
        second = self._create(self.order_b, description="第二个")
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(second["id"]),
                  "content": "开始处理"},
        )
        # 状态筛选 + 排序
        resp = self.client.get(
            "/api/crm/aftersales?status=processing&sort=created_at&order=desc"
        )
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], second["id"])
        resp = self.client.get("/api/crm/aftersales?status=pending")
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], first["id"])
        # 客户筛选 + 排序
        resp = self.client.get(
            f"/api/crm/aftersales?customer_id={int(self.customer_a)}&sort=created_at&order=asc"
        )
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], first["id"])
        # 订单筛选
        resp = self.client.get(f"/api/crm/aftersales?order_id={int(self.order_b)}")
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], second["id"])
