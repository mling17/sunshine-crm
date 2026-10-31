"""Product master API and deal/order snapshot contract."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests._util import ApiTestCase


class TestProducts(ApiTestCase):
    @staticmethod
    def form_bytes(code: str = "TS-001") -> bytes:
        return (
            Path(__file__).resolve().parents[1]
            / "app"
            / "data"
            / "product_forms"
            / f"{code}.xlsx"
        ).read_bytes()

    def create_product(self, **overrides) -> dict:
        body = {
            "code": "TS-TEST-001",
            "name": "55型2扇联排测试产品",
            "category": "天窗",
            "series": "55型",
            "structure": "平放",
            "opening_mode": "联排",
            "drive_type": "electric",
            "frame_type": "重型",
            "leaf_type": "新扇",
            "edge_type": "带边",
            "leaf_count": 2,
            "attributes": {
                "screen": "电动纱窗",
                "mesh": "金刚网",
                "motor_cover": "标准",
            },
            "source_template": "55型测试下单表.xlsx",
            "description": "用于产品模块自动化验证",
        }
        body.update(overrides)
        resp = self.client.post(
            "/api/crm/products",
            data={"payload": json.dumps(body, ensure_ascii=False)},
            files={
                "form_file": (
                    "TS-TEST-001.xlsx",
                    self.form_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_seed_catalog_contains_all_order_forms(self):
        catalog_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "data"
            / "order_form_catalog.json"
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(len(catalog), 123)
        self.assertEqual(len({row["code"] for row in catalog}), 123)
        self.assertEqual(len({row["seed_key"] for row in catalog}), 123)
        self.assertEqual(len({row["source_template"] for row in catalog}), 123)
        self.assertTrue(
            all((Path(__file__).resolve().parents[1] / row["form_bundle"]).is_file() for row in catalog)
        )

        resp = self.client.get("/api/crm/products")
        self.assertEqual(resp.status_code, 200, resp.text)
        products = resp.json()
        self.assertEqual(len(products), 123)
        self.assertEqual(products[0]["code"], "TS-001")
        self.assertTrue(all(p["form_available"] for p in products))
        self.assertTrue(all(p["form_file_name"].lower().endswith((".xlsx", ".xls")) for p in products))
        self.assertTrue(any(p["category"] == "天幕" for p in products))
        self.assertTrue(any(p["category"] == "开合屋面" for p in products))

        download = self.client.get(f"/api/crm/products/{products[0]['id']}/form-file")
        self.assertEqual(download.status_code, 200, download.text)
        self.assertTrue(download.content.startswith(b"PK\x03\x04"))

    def test_create_search_update_and_deactivate_product(self):
        product = self.create_product()
        self.assertEqual(product["code"], "TS-TEST-001")
        self.assertEqual(product["config_summary"].count("电动纱窗"), 1)
        self.assertTrue(product["form_available"])

        hits = self.client.get("/api/crm/products", params={"q": "联排测试"}).json()
        self.assertEqual([p["id"] for p in hits], [product["id"]])

        resp = self.client.put(
            f"/api/crm/products/{product['id']}",
            json={"name": "55型2扇联排测试产品（新版）", "is_active": False},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["name"], "55型2扇联排测试产品（新版）")
        self.assertFalse(resp.json()["is_active"])

        active = self.client.get("/api/crm/products", params={"is_active": 1}).json()
        self.assertNotIn(product["id"], [p["id"] for p in active])

    def test_duplicate_code_and_invalid_dimensions_are_rejected(self):
        product = self.create_product()
        duplicate = self.client.post(
            "/api/crm/products",
            data={"payload": json.dumps(
                {"code": product["code"], "name": "重复编码", "category": "天窗"},
                ensure_ascii=False,
            )},
            files={"form_file": ("duplicate.xlsx", self.form_bytes(), "application/octet-stream")},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["code"], "product_code_exists")

        invalid = self.client.post(
            "/api/crm/products",
            data={"payload": json.dumps(
                {
                    "code": "TS-TEST-RANGE",
                    "name": "范围错误产品",
                    "category": "天窗",
                    "min_width": 2000,
                    "max_width": 1000,
                },
                ensure_ascii=False,
            )},
            files={"form_file": ("invalid.xlsx", self.form_bytes(), "application/octet-stream")},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["code"], "invalid_dimension_range")

    def test_product_cannot_be_created_without_excel(self):
        resp = self.client.post(
            "/api/crm/products",
            data={"payload": json.dumps(
                {"code": "TS-NO-FILE", "name": "无表产品", "category": "天窗"},
                ensure_ascii=False,
            )},
        )
        self.assertIn(resp.status_code, (400, 422))

    def test_replace_product_form(self):
        product = self.create_product()
        replacement = self.form_bytes("TS-002")
        resp = self.client.put(
            f"/api/crm/products/{product['id']}/form-file",
            files={"form_file": ("新版下单表.xlsx", replacement, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["form_file_name"], "新版下单表.xlsx")
        downloaded = self.client.get(f"/api/crm/products/{product['id']}/form-file")
        self.assertEqual(downloaded.content, replacement)

    def test_deal_and_order_keep_product_snapshot_after_catalog_edit(self):
        product = self.create_product()
        customer = self.create_customer(name="产品快照客户", phone="13900001111")
        deal = self.create_deal(
            customer["id"],
            product_id=product["id"],
            spec="1480*2350",
            amount=8800.0,
        )
        self.assertEqual(deal["product_id"], product["id"])
        self.assertEqual(deal["product_code_snapshot"], "TS-TEST-001")
        self.assertEqual(deal["product_name_snapshot"], "55型2扇联排测试产品")
        self.assertIn("电动纱窗", deal["product_config_snapshot"])

        resp = self.client.put(
            f"/api/crm/products/{product['id']}",
            json={"code": "TS-TEST-NEW", "name": "改名后的产品"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        fresh_deal = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        self.assertEqual(fresh_deal["product_code_snapshot"], "TS-TEST-001")
        self.assertEqual(fresh_deal["product_name_snapshot"], "55型2扇联排测试产品")

        won = self.client.put(
            f"/api/crm/deals/{deal['id']}", json={"stage": "won"}
        )
        self.assertEqual(won.status_code, 200, won.text)
        ordered = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={"amount": 8800.0, "deposit": 1000.0, "logistics_mode": "self"},
        )
        self.assertEqual(ordered.status_code, 200, ordered.text)
        order = ordered.json()["order"]
        self.assertEqual(order["product_id"], product["id"])
        self.assertEqual(order["product_code_snapshot"], "TS-TEST-001")
        self.assertEqual(order["product_name_snapshot"], "55型2扇联排测试产品")
        self.assertIn("电动纱窗", order["product_config_snapshot"])

    def test_inactive_product_cannot_be_linked_to_new_deal(self):
        product = self.create_product(is_active=False)
        customer = self.create_customer(name="停用产品客户", phone="13900002222")
        resp = self.client.post(
            "/api/crm/deals",
            json={
                "customer_id": customer["id"],
                "product_id": product["id"],
                "amount": 1000,
                "spec": "1200*1600",
                "drive_type": "electric",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "product_not_found")


if __name__ == "__main__":
    unittest.main()
