"""Product master API and deal/order snapshot contract."""

from __future__ import annotations

import json
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

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

    @classmethod
    def unique_form_bytes(cls, title: str) -> bytes:
        workbook = load_workbook(BytesIO(cls.form_bytes()), data_only=False)
        workbook.worksheets[0]["A1"] = title
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

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
        self.assertRegex(product["code"], r"^TS-\d{3,}$")
        self.assertNotEqual(product["code"], "TS-TEST-001")
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

    def test_payload_code_is_ignored_and_invalid_dimensions_are_rejected(self):
        product = self.create_product()
        second = self.create_product(
            code=product["code"],
            name="仍然自动编号的产品",
        )
        self.assertNotEqual(second["code"], product["code"])
        self.assertRegex(second["code"], r"^TS-\d{3,}$")

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

    def test_import_preview_infers_product_fields_from_order_form(self):
        form = self.unique_form_bytes(
            "95型平起电动3扇联排天窗下单表-带电动纱窗、金刚网"
        )
        resp = self.client.post(
            "/api/crm/products/import-preview",
            files={
                "form_file": (
                    "95型平起电动3扇联排下单表.xlsx",
                    form,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        preview = resp.json()
        self.assertRegex(preview["code"], r"^TS-124$")
        self.assertIsNone(preview["duplicate_product_code"])
        self.assertEqual(preview["name"], "95型平起电动3扇联排天窗下单表-带电动纱窗、金刚网")
        self.assertEqual(preview["series"], "95型")
        self.assertEqual(preview["structure"], "平起")
        self.assertEqual(preview["opening_mode"], "联排")
        self.assertEqual(preview["drive_type"], "electric")
        self.assertEqual(preview["leaf_count"], 3)
        self.assertEqual(preview["attributes"]["screen"], "电动纱窗")
        self.assertEqual(preview["attributes"]["mesh"], "金刚网")
        self.assertIn("95型", preview["config_summary"])

    def test_import_form_creates_product_with_generated_code_and_archive(self):
        form = self.unique_form_bytes(
            "140型嵌入电动4扇联排天窗下单表-带电动纱窗"
        )
        resp = self.client.post(
            "/api/crm/products/import-form",
            files={
                "form_file": (
                    "新品140型嵌入4扇.xlsx",
                    form,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        product = resp.json()
        self.assertRegex(product["code"], r"^TS-124$")
        self.assertEqual(product["series"], "140型")
        self.assertEqual(product["structure"], "嵌入")
        self.assertEqual(product["leaf_count"], 4)
        self.assertEqual(product["attributes"]["screen"], "电动纱窗")
        self.assertTrue(product["form_available"])

        duplicate = self.client.post(
            "/api/crm/products/import-form",
            files={
                "form_file": (
                    "新品140型嵌入4扇.xlsx",
                    form,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["code"], "product_form_exists")
        self.assertEqual(duplicate.json()["product_code"], product["code"])

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
        self.assertEqual(deal["product_code_snapshot"], product["code"])
        self.assertEqual(deal["product_name_snapshot"], "55型2扇联排测试产品")
        self.assertIn("电动纱窗", deal["product_config_snapshot"])

        resp = self.client.put(
            f"/api/crm/products/{product['id']}",
            json={"code": "TS-TEST-NEW", "name": "改名后的产品"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        fresh_deal = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        self.assertEqual(fresh_deal["product_code_snapshot"], product["code"])
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
        self.assertEqual(order["product_code_snapshot"], product["code"])
        self.assertEqual(order["product_name_snapshot"], "55型2扇联排测试产品")
        self.assertIn("电动纱窗", order["product_config_snapshot"])

    def test_deal_product_can_be_replaced_before_order(self):
        product_a = self.create_product()
        product_b = self.create_product(
            code="TS-TEST-002",
            name="沟通后更适合的天幕产品",
            category="天幕",
            drive_type="manual",
            config_summary="天幕 / 沟通后选定",
        )
        customer = self.create_customer(name="换产品客户", phone="13900003333")
        deal = self.create_deal(
            customer["id"],
            product_id=product_a["id"],
            spec="1480*2350",
            amount=8800.0,
        )
        self.assertEqual(deal["product_id"], product_a["id"])

        changed = self.client.put(
            f"/api/crm/deals/{deal['id']}",
            json={
                "product_id": product_b["id"],
                "drive_type": "manual",
                "spec": "1600*2600",
                "amount": 9600.0,
                "note": "几轮沟通后改为 B 产品",
            },
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        changed_deal = changed.json()
        self.assertEqual(changed_deal["product_id"], product_b["id"])
        self.assertEqual(changed_deal["product_code_snapshot"], product_b["code"])
        self.assertEqual(changed_deal["product_name_snapshot"], "沟通后更适合的天幕产品")
        self.assertEqual(changed_deal["product_type"], "天幕")
        self.assertEqual(changed_deal["model"], product_b["code"])
        self.assertEqual(changed_deal["drive_type"], "manual")
        self.assertEqual(changed_deal["spec"], "1600*2600")

        timeline = self.client.get(f"/api/crm/deals/{deal['id']}").json()["timeline"]
        self.assertTrue(any(item["type"] == "change" for item in timeline))

        won = self.client.put(
            f"/api/crm/deals/{deal['id']}", json={"stage": "won"}
        )
        self.assertEqual(won.status_code, 200, won.text)
        ordered = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={"amount": 9600.0, "deposit": 2000.0, "logistics_mode": "self"},
        )
        self.assertEqual(ordered.status_code, 200, ordered.text)
        order = ordered.json()["order"]
        self.assertEqual(order["product_id"], product_b["id"])
        self.assertEqual(order["product_code_snapshot"], product_b["code"])
        self.assertEqual(order["product_name_snapshot"], "沟通后更适合的天幕产品")

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
