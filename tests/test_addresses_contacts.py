"""客户地址簿 + 物流多联系人（PLANNER-V3 §5.4 / §5.8）。"""
from __future__ import annotations

import unittest

from tests._util import ApiTestCase


class AddressTest(ApiTestCase):
    def test_address_crud_and_single_default(self):
        c = self.create_customer(name="李地址")
        first = self.client.post(
            f"/api/crm/customers/{c['id']}/addresses",
            json={"label": "家", "receiver_name": "李地址", "phone": "13900000000",
                  "address": "济南市历下区万科城", "is_default": True},
        )
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(
            f"/api/crm/customers/{c['id']}/addresses",
            json={"label": "工地", "receiver_name": "李地址", "phone": "13900000000",
                  "address": "青岛市崂山区", "is_default": True},
        )
        self.assertEqual(second.status_code, 200, second.text)

        rows = self.client.get(f"/api/crm/customers/{c['id']}/addresses").json()
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(1 for r in rows if r["is_default"]), 1, "默认地址只能有一条")
        self.assertEqual(rows[0]["label"], "工地", "默认地址排最前")

    def test_address_requires_complete_info(self):
        c = self.create_customer(name="李地址")
        bad = self.client.post(
            f"/api/crm/customers/{c['id']}/addresses",
            json={"receiver_name": "李地址"},
        )
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertEqual(bad.json()["code"], "address_incomplete")

    def test_order_snapshot_survives_address_edit_and_delete(self):
        c = self.create_customer(name="李地址")
        addr = self.client.post(
            f"/api/crm/customers/{c['id']}/addresses",
            json={"label": "家", "receiver_name": "李地址", "phone": "13900000000",
                  "address": "济南市历下区万科城"},
        ).json()

        deal = self.create_deal(c["id"], amount=8000.0, drive_type="manual")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        order = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={"deposit": 2000, "logistics_mode": "self", "address_id": addr["id"]},
        ).json()["order"]
        self.assertEqual(order["receiver_address"], "济南市历下区万科城")
        self.assertEqual(order["address_id"], addr["id"])

        # 改地址簿 + 删地址簿，历史订单快照不受影响
        self.client.put(
            f"/api/crm/customers/{c['id']}/addresses/{addr['id']}",
            json={"address": "搬家后的新地址"},
        )
        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["receiver_address"], "济南市历下区万科城")

        self.client.delete(f"/api/crm/customers/{c['id']}/addresses/{addr['id']}")
        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["receiver_address"], "济南市历下区万科城", "快照不能没")
        self.assertIsNone(detail["address_id"], "地址被删后关联置空")

    def test_order_saves_new_address_to_book(self):
        c = self.create_customer(name="李地址")
        deal = self.create_deal(c["id"], amount=5000.0, drive_type="manual")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        resp = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={"deposit": 1000, "logistics_mode": "self",
                  "receiver_name": "李地址", "receiver_phone": "13900000000",
                  "receiver_address": "潍坊市奎文区建材市场 3 号库"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        rows = self.client.get(f"/api/crm/customers/{c['id']}/addresses").json()
        self.assertEqual(len(rows), 1, "手填地址要回存地址簿，方便复购")


class CarrierContactTest(ApiTestCase):
    def test_multiple_contacts_with_tags(self):
        resp = self.client.post(
            "/api/crm/carriers",
            json={"name": "德邦物流", "contacts": [
                {"name": "李经理", "phone": "13800001111", "tags": ["大件业务", "报价"]},
                {"name": "王调度", "phone": "13800002222", "tags": ["派车"]},
            ]},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(len(data["contacts"]), 2)
        self.assertEqual(data["contacts"][0]["tags"], ["大件业务", "报价"])

    def test_contacts_can_be_replaced(self):
        created = self.client.post(
            "/api/crm/carriers",
            json={"name": "顺丰快运", "contacts": [{"name": "老张", "phone": "13900000001", "tags": []}]},
        ).json()
        updated = self.client.put(
            f"/api/crm/carriers/{created['id']}",
            json={"contacts": [{"name": "新张", "phone": "13900000002", "tags": ["派车"]}]},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        contacts = updated.json()["contacts"]
        self.assertEqual([c["name"] for c in contacts], ["新张"])

    def test_duplicate_name_409(self):
        self.client.post("/api/crm/carriers", json={"name": "安能物流"})
        again = self.client.post("/api/crm/carriers", json={"name": "安能物流"})
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json()["code"], "carrier_exists")

    def test_order_count_and_delete_protection(self):
        carrier = self.client.post(
            "/api/crm/carriers",
            json={
                "name": "济南专线",
                "contacts": [{"name": "赵经理", "phone": "13700000001", "tags": []}],
            },
        ).json()
        self.assertEqual(carrier["order_count"], 0)

        c = self.create_customer(name="赵物流")
        deal = self.create_deal(c["id"], amount=6000.0, drive_type="manual")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        resp = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={"deposit": 1000, "logistics_mode": "agent", "carrier_id": carrier["id"],
                  "carrier_contact_id": carrier["contacts"][0]["id"],
                  "logistics_fee": 300, "receiver_name": "赵物流", "receiver_phone": "13700000000",
                  "receiver_address": "济南市市中区"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        rows = self.client.get("/api/crm/carriers").json()
        self.assertEqual([r["order_count"] for r in rows if r["id"] == carrier["id"]][0], 1)

        blocked = self.client.delete(f"/api/crm/carriers/{carrier['id']}")
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["code"], "carrier_in_use")


if __name__ == "__main__":
    unittest.main()
