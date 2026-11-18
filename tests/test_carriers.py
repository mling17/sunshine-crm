"""物流公司模块测试"""
import unittest
from tests import _bootstrap  # noqa: F401  —— 必须在 app.* 之前 import，设定临时 DB/上传目录
from tests._util import ApiTestCase, db_conn


class CarriersTest(ApiTestCase):
    def test_create_carrier(self):
        """测试创建物流公司"""
        response = self.client.post("/api/crm/carriers", json={
            "name": "顺丰快递",
            "code": "SF",
            "contact_person": "张三",
            "phone": "13800138000",
            "address": "北京市朝阳区"
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "顺丰快递")
        self.assertEqual(data["code"], "SF")
        
        # 清理测试数据
        carrier_id = data["id"]
        self.client.delete(f"/api/crm/carriers/{carrier_id}")

    def test_list_carriers(self):
        """测试获取物流公司列表（Ticket #15 起为 {items,total,page,size} 分页契约）"""
        response = self.client.get("/api/crm/carriers")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, dict)
        for key in ("items", "total", "page", "size"):
            self.assertIn(key, data)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["size"], 20)
        self.assertEqual(data["total"], len(data["items"]))

    def test_get_carrier(self):
        """测试获取物流公司详情"""
        # 先创建一个物流公司
        response = self.client.post("/api/crm/carriers", json={
            "name": "圆通快递",
            "code": "YT",
            "contact_person": "李四",
            "phone": "13900139000",
            "address": "上海市浦东新区"
        })
        self.assertEqual(response.status_code, 200)
        carrier_data = response.json()
        carrier_id = carrier_data["id"]
        
        # 获取详情
        response = self.client.get(f"/api/crm/carriers/{carrier_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "圆通快递")
        self.assertEqual(data["code"], "YT")
        
        # 清理测试数据
        self.client.delete(f"/api/crm/carriers/{carrier_id}")

    def test_update_carrier(self):
        """测试更新物流公司"""
        # 先创建一个物流公司
        response = self.client.post("/api/crm/carriers", json={
            "name": "中通快递",
            "code": "ZT",
            "contact_person": "王五",
            "phone": "13700137000",
            "address": "广州市天河区"
        })
        self.assertEqual(response.status_code, 200)
        carrier_data = response.json()
        carrier_id = carrier_data["id"]
        
        # 更新信息
        response = self.client.put(f"/api/crm/carriers/{carrier_id}", json={
            "name": "中通快递(更新)",
            "code": "ZT2",
            "contact_person": "赵六",
            "phone": "13600136000",
            "address": "深圳市南山区"
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "中通快递(更新)")
        self.assertEqual(data["code"], "ZT2")
        
        # 清理测试数据
        self.client.delete(f"/api/crm/carriers/{carrier_id}")

    def test_carrier_delete_referenced(self):
        """测试删除被引用的物流公司应该返回 409"""
        # 创建一个物流公司
        carrier_response = self.client.post("/api/crm/carriers", json={
            "name": "测试物流",
            "code": "TEST001"
        })
        self.assertEqual(carrier_response.status_code, 200)
        carrier_data = carrier_response.json()
        carrier_id = carrier_data["id"]
        
        # 创建一个订单并关联该物流公司
        with db_conn() as conn:
            # 先插入一个测试客户
            conn.execute(
                "INSERT INTO customers (name, created_at, updated_at) VALUES (?, ?, ?)",
                ("测试客户", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
            )
            customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 订单必须挂在真实商机上（1:1 + 外键）
            conn.execute(
                "INSERT INTO deals (customer_id, amount, stage, created_at, updated_at)"
                " VALUES (?, ?, 'won', ?, ?)",
                (customer_id, 1000.0, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
            )
            deal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 插入一个测试订单
            conn.execute(
                """
                INSERT INTO orders (order_no, customer_id, deal_id, amount, status, 
                                  carrier_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("SO-20260101-001", customer_id, deal_id, 1000.0, "pending_payment", 
                 carrier_id, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
            )
        
        # 尝试删除被引用的物流公司，应该返回 409
        response = self.client.delete(f"/api/crm/carriers/{carrier_id}")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "carrier_in_use")  # 计划 §2.6 错误码
        
        # 清理测试数据
        with db_conn() as conn:
            # 删除订单
            conn.execute("DELETE FROM orders WHERE carrier_id = ?", (carrier_id,))
            # 删除物流公司
            conn.execute("DELETE FROM carriers WHERE id = ?", (carrier_id,))

    def test_carrier_delete_not_referenced(self):
        """测试删除未被引用的物流公司应该成功"""
        # 创建一个物流公司
        carrier_response = self.client.post("/api/crm/carriers", json={
            "name": "测试物流2",
            "code": "TEST002"
        })
        self.assertEqual(carrier_response.status_code, 200)
        carrier_data = carrier_response.json()
        carrier_id = carrier_data["id"]
        
        # 删除未被引用的物流公司，应该返回 200
        response = self.client.delete(f"/api/crm/carriers/{carrier_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "删除成功")




class CarriersListPaginationTest(ApiTestCase):
    """Ticket #15：物流公司列表服务端分页 / 排序 / 筛选。"""

    def _make_carrier(self, name, **payload):
        body = {"name": name}
        body.update(payload)
        resp = self.client.post("/api/crm/carriers", json=body)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def _link_orders(self, carrier_id, count):
        """直接落库给物流公司挂 count 张订单（订单必须挂在真实客户+商机上）。"""
        now = "2026-01-01T00:00:00Z"
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO customers (name, created_at, updated_at) VALUES (?, ?, ?)",
                (f"物流客户{carrier_id}", now, now),
            )
            customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for i in range(count):
                conn.execute(
                    "INSERT INTO deals (customer_id, amount, stage, created_at, updated_at)"
                    " VALUES (?, ?, 'won', ?, ?)",
                    (customer_id, 1000.0, now, now),
                )
                deal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    "INSERT INTO orders (order_no, customer_id, deal_id, amount, status,"
                    " carrier_id, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, 'pending_payment', ?, ?, ?)",
                    (f"SO-{carrier_id}-{i}", customer_id, deal_id, 1000.0, carrier_id, now, now),
                )

    def test_pagination_contract(self):
        """默认 page=1/size=20，返回 {items,total,page,size}；翻页切片正确。"""
        for i in range(25):
            self._make_carrier(f"分页公司{i:02d}")
        resp = self.client.get("/api/crm/carriers")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["size"], 20)
        self.assertEqual(data["total"], 25)
        self.assertEqual(len(data["items"]), 20)

        resp = self.client.get("/api/crm/carriers?page=2&size=10")
        data = resp.json()
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["size"], 10)
        self.assertEqual(data["total"], 25)
        self.assertEqual(len(data["items"]), 10)
        first_page = self.client.get("/api/crm/carriers?page=1&size=10").json()["items"]
        self.assertNotEqual(
            [c["id"] for c in first_page], [c["id"] for c in data["items"]],
        )

    def test_page_size_sort_order_whitelists(self):
        """非法 page/size/sort/order 一律 400，错误码与 Ticket #9/#13 共享口径一致。"""
        cases = [
            ("/api/crm/carriers?page=0", "invalid_page"),
            ("/api/crm/carriers?page=-1", "invalid_page"),
            ("/api/crm/carriers?size=15", "invalid_page_size"),
            ("/api/crm/carriers?size=1000", "invalid_page_size"),
            ("/api/crm/carriers?sort=order_count", "invalid_sort"),
            ("/api/crm/carriers?sort=id", "invalid_sort"),
            ("/api/crm/carriers?sort=name;DROP TABLE", "invalid_sort"),
            ("/api/crm/carriers?sort=name&order=up", "invalid_order"),
            ("/api/crm/carriers?sort=name&order=ASC", "invalid_order"),
        ]
        for url, code in cases:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 400, resp.text)
                self.assertEqual(resp.json()["code"], code)

    def test_default_order_is_order_reference_count_desc(self):
        """issue #8：默认被订单关联次数倒序，次数相同按 id DESC（稳定次键）。"""
        a = self._make_carrier("零次A")
        b = self._make_carrier("两次B")
        c = self._make_carrier("一次C")
        d = self._make_carrier("零次D")
        e = self._make_carrier("零次E")
        self._link_orders(b["id"], 2)
        self._link_orders(c["id"], 1)

        resp = self.client.get("/api/crm/carriers?size=500")
        items = resp.json()["items"]
        got = [(it["id"], it["order_count"]) for it in items]
        self.assertEqual(
            got,
            [(b["id"], 2), (c["id"], 1), (e["id"], 0), (d["id"], 0), (a["id"], 0)],
        )
        # order_count 是计算列：可以出现在返回里，但不可作为 sort 白名单 key
        resp = self.client.get("/api/crm/carriers?sort=order_count")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_sort")

    def test_sort_by_name_and_address(self):
        """显式排序：name 升/降序；address 升序；同值命中稳定次键 id DESC。

        name 有 UNIQUE 约束（含已删除行），同名行造不出来；
        同值次键用 address 相同的两个公司验证。
        """
        a = self._make_carrier("阿尔法物流", address="杭州市西湖区")
        b = self._make_carrier("贝塔物流", address="北京市朝阳区")
        c = self._make_carrier("咖马物流", address="成都市武侯区")
        d = self._make_carrier("德尔塔物流", address="同地址园区")
        e = self._make_carrier("艾普西龙物流", address="同地址园区")

        items = self.client.get(
            "/api/crm/carriers?sort=name&order=asc&size=500"
        ).json()["items"]
        self.assertEqual([it["id"] for it in items], [c["id"], d["id"], e["id"], b["id"], a["id"]])  # SQLite 按码位排序
        items = self.client.get(
            "/api/crm/carriers?sort=name&order=desc&size=500"
        ).json()["items"]
        self.assertEqual([it["id"] for it in items], [a["id"], b["id"], e["id"], d["id"], c["id"]])

        items = self.client.get(
            "/api/crm/carriers?sort=address&order=asc&size=500"
        ).json()["items"]
        # 北京(5317) < 同地址(540C) < 成都(6210) < 杭州(676D)，SQLite 按码位排序；
        # 「同地址园区」d/e 同值，稳定次键 id DESC → e 先于 d
        self.assertEqual(
            [it["id"] for it in items],
            [b["id"], e["id"], d["id"], c["id"], a["id"]],
        )
    def test_nullable_address_sinks_both_directions(self):
        """地址可空：升序、降序都沉底（(expr IS NULL) ASC）。"""
        with_addr = self._make_carrier("有地址", address="上海市浦东新区")
        no_addr = self._make_carrier("无地址")

        for order in ("asc", "desc"):
            with self.subTest(order=order):
                items = self.client.get(
                    f"/api/crm/carriers?sort=address&order={order}&size=500"
                ).json()["items"]
                self.assertEqual(items[-1]["id"], no_addr["id"])
                self.assertEqual(items[0]["id"], with_addr["id"])

    def test_keyword_filter_matches_name_address_and_contacts(self):
        """关键词匹配公司名 / 地址 / 多联系人姓名电话（原前端本地过滤同口径）。"""
        by_name = self._make_carrier("杭州快运专线")
        by_address = self._make_carrier("城西物流", address="杭州市余杭区")
        by_contact = self._make_carrier("联运公司", contacts=[
            {"name": "王调度", "phone": "13800000001", "tags": []},
        ])
        other = self._make_carrier("北方货运")

        resp = self.client.get("/api/crm/carriers?q=" + "杭州")
        ids = [it["id"] for it in resp.json()["items"]]
        self.assertIn(by_name["id"], ids)
        self.assertIn(by_address["id"], ids)
        self.assertNotIn(by_contact["id"], ids)
        self.assertNotIn(other["id"], ids)

        resp = self.client.get("/api/crm/carriers?q=王调度")
        ids = [it["id"] for it in resp.json()["items"]]
        self.assertEqual(ids, [by_contact["id"]])

        # LIKE 通配符按字面量处理，不当模式匹配
        resp = self.client.get("/api/crm/carriers?q=100%")
        self.assertEqual(resp.json()["total"], 0)

    def test_active_filter(self):
        """仅看启用（active=1）/ 仅看停用（active=0）服务端过滤。"""
        active_carrier = self._make_carrier("启用中的")
        stopped = self._make_carrier("已停用的")
        resp = self.client.put(f"/api/crm/carriers/{stopped['id']}", json={"is_active": False})
        self.assertEqual(resp.status_code, 200, resp.text)

        items = self.client.get("/api/crm/carriers?active=1&size=500").json()["items"]
        self.assertEqual([it["id"] for it in items], [active_carrier["id"]])
        items = self.client.get("/api/crm/carriers?active=0&size=500").json()["items"]
        self.assertEqual([it["id"] for it in items], [stopped["id"]])
        total = self.client.get("/api/crm/carriers?size=500").json()["total"]
        self.assertEqual(total, 2)

    def test_filter_and_pagination_combined(self):
        """筛选 + 分页组合：total 按筛选后计，翻页切片在筛选结果内。"""
        for i in range(15):
            self._make_carrier(f"专线{i:02d}", address="金华市义乌区")
        self._make_carrier("无关公司", address="沈阳市和平区")

        data = self.client.get(
            "/api/crm/carriers?q=金华&size=10&page=1"
        ).json()
        self.assertEqual(data["total"], 15)
        self.assertEqual(len(data["items"]), 10)
        data = self.client.get(
            "/api/crm/carriers?q=金华&size=10&page=2"
        ).json()
        self.assertEqual(data["total"], 15)
        self.assertEqual(len(data["items"]), 5)
        page1 = self.client.get("/api/crm/carriers?q=金华&size=10&page=1").json()["items"]
        self.assertFalse(
            {c["id"] for c in page1} & {c["id"] for c in data["items"]},
        )
        # 筛选 + 显式排序同样组合生效
        data = self.client.get(
            "/api/crm/carriers?q=专线&sort=name&order=asc&size=500"
        ).json()
        names = [it["name"] for it in data["items"]]
        self.assertEqual(names, sorted(names))

if __name__ == "__main__":
    unittest.main()
