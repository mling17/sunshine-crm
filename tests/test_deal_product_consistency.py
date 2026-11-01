"""Deal parameters must follow the linked product catalog."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests._util import ApiTestCase


ROOT = Path(__file__).resolve().parents[1]


class DealProductParameterUiTest(unittest.TestCase):
    def test_quote_form_uploads_product_spreadsheet(self):
        shared = (ROOT / "static/views/shared.js").read_text(encoding="utf-8")
        deals = (ROOT / "static/views/deals.js").read_text(encoding="utf-8")
        css = (ROOT / "static/app.css").read_text(encoding="utf-8")

        for marker in ("function productPickerHtml", "function bindProductPicker"):
            self.assertIn(marker, shared)
        for marker in (
            "function openQuoteItemModal",
            "productPickerHtml(products || []",
            "选择产品后上传对应的 Excel 下单表",
            'name="form_file"',
            "quotes/form-preview",
            "A1 校验通过",
            "recognized_total",
        ):
            self.assertIn(marker, deals)
        quote_form = deals[
            deals.index("function openQuoteItemModal"):
            deals.index("function openQuoteConfirmModal")
        ]
        self.assertNotIn('name="quantity"', quote_form)
        self.assertNotIn('name="unit_price"', quote_form)
        self.assertNotIn('name="spec"', quote_form)
        self.assertIn(".product-picker", css)

    def test_empty_product_state_is_distinct_and_focuses_search(self):
        shared = (ROOT / "static/views/shared.js").read_text(encoding="utf-8")
        css = (ROOT / "static/app.css").read_text(encoding="utf-8")

        for marker in (
            "data-picker-open-search",
            "尚未关联产品",
            "请在上方搜索框输入产品编码、名称或配置",
            "ev.target.closest('[data-picker-open-search]')",
            "input.focus()",
        ):
            self.assertIn(marker, shared)
        for selector in (
            ".product-picker-empty-mark",
            ".product-picker-placeholder-action",
        ):
            self.assertIn(selector, css)


class DealProductParameterApiTest(ApiTestCase):
    @staticmethod
    def product_form() -> bytes:
        return (ROOT / "app/data/product_forms/TS-001.xlsx").read_bytes()

    def create_product(self, name: str, *, drive_type: str) -> dict:
        payload = {
            "code": "TS-CONSISTENCY",
            "name": name,
            "category": "天窗",
            "series": "140型",
            "structure": "嵌入",
            "opening_mode": "联排",
            "drive_type": drive_type,
        }
        response = self.client.post(
            "/api/crm/products",
            data={"payload": json.dumps(payload, ensure_ascii=False)},
            files={
                "form_file": (
                    "product-consistency.xlsx",
                    self.product_form(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_create_update_and_replace_keep_product_drive_type(self):
        product_a = self.create_product("电动测试产品", drive_type="electric")
        product_b = self.create_product("手动测试产品", drive_type="manual")
        customer = self.create_customer(name="参数一致客户", phone="13900004444")

        created = self.client.post(
            "/api/crm/deals",
            json={
                "customer_id": customer["id"],
                "product_id": product_a["id"],
                "drive_type": "manual",
                "spec": "1480*2350",
                "amount": 8800,
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        deal = created.json()
        self.assertEqual(deal["drive_type"], "electric")
        self.assertEqual(deal["product_type"], product_a["category"])
        self.assertEqual(deal["model"], product_a["code"])

        same_product = self.client.put(
            f"/api/crm/deals/{deal['id']}",
            json={"drive_type": "manual"},
        )
        self.assertEqual(same_product.status_code, 200, same_product.text)
        self.assertEqual(same_product.json()["drive_type"], "electric")

        replaced = self.client.put(
            f"/api/crm/deals/{deal['id']}",
            json={
                "product_id": product_b["id"],
                "drive_type": "electric",
            },
        )
        self.assertEqual(replaced.status_code, 200, replaced.text)
        replaced_deal = replaced.json()
        self.assertEqual(replaced_deal["product_id"], product_b["id"])
        self.assertEqual(replaced_deal["drive_type"], "manual")
        self.assertEqual(replaced_deal["product_type"], product_b["category"])
        self.assertEqual(replaced_deal["model"], product_b["code"])


if __name__ == "__main__":
    unittest.main()
