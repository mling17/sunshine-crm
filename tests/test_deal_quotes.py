"""商机报价单、下单表展示、客户确认与报价转订单回归测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests._util import ApiTestCase


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FORM = ROOT / "app/data/product_forms/TS-001.xlsx"


class DealQuoteTest(ApiTestCase):
    def _deal(self) -> tuple[dict, dict]:
        customer = self.create_customer(name="报价单客户", phone="13912345678")
        resp = self.client.post(
            "/api/crm/deals",
            json={"customer_id": customer["id"], "note": "客户想先比较两套方案"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        deal = resp.json()
        self.assertEqual(deal["amount"], 0.0)
        self.assertIsNone(deal["product_id"])
        return customer, deal

    def _quote_with_item(self) -> tuple[dict, dict, dict]:
        customer, deal = self._deal()
        product = self.client.get("/api/crm/products").json()[0]
        created_quote = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes",
            json={"title": "客厅天窗方案", "note": "客户先看这一版"},
        )
        self.assertEqual(created_quote.status_code, 200, created_quote.text)
        quote = created_quote.json()
        self.assertEqual(quote["status"], "draft")
        self.assertEqual(quote["items"], [])

        form_bytes = SAMPLE_FORM.read_bytes()
        item = self.client.post(
            f"/api/crm/quotes/{quote['id']}/items",
            data={
                "product_id": str(product["id"]),
                "quantity": "2",
                "unit_price": "5800",
                "spec": "1200x2400",
                "production_spec": "框 1180*2380；扇 1160*2360",
                "note": "客户确认现场洞口",
            },
            files={
                "form_file": (
                    "客厅天窗下单表.xlsx",
                    form_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(item.status_code, 200, item.text)
        quote = item.json()
        self.assertEqual(quote["amount"], 11600.0)
        self.assertEqual(len(quote["items"]), 1)
        line = quote["items"][0]
        self.assertEqual(line["spec"], "1200*2400")
        self.assertTrue(line["form_available"])
        self.assertGreater(len(line["form_content"]["sheets"]), 0)
        self.assertTrue(line["form_url"])
        self.assertTrue(line["template_url"])
        return customer, deal, quote

    def test_deal_is_created_with_only_note(self):
        customer, deal = self._deal()
        detail = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        self.assertEqual(detail["note"], "客户想先比较两套方案")
        self.assertEqual(detail["items"], [])
        quotes = self.client.get(f"/api/crm/deals/{deal['id']}/quotes").json()
        self.assertEqual(quotes, [])

    def test_quote_item_uploads_and_returns_excel_content(self):
        _, deal, quote = self._quote_with_item()
        listed = self.client.get(f"/api/crm/deals/{deal['id']}/quotes").json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["quote_no"], quote["quote_no"])
        self.assertIn("客厅天窗方案", listed[0]["title"])
        line = listed[0]["items"][0]
        first_sheet = line["form_content"]["sheets"][0]
        self.assertIn("name", first_sheet)
        self.assertIn("rows", first_sheet)

        form_download = self.client.get(line["form_url"])
        self.assertEqual(form_download.status_code, 200)
        self.assertIn("spreadsheetml", form_download.headers["content-type"])
        template_download = self.client.get(line["template_url"])
        self.assertEqual(template_download.status_code, 200)

        timeline = self.client.get(f"/api/crm/deals/{deal['id']}").json()["timeline"]
        self.assertTrue(any(item["type"] == "quote" for item in timeline))
        self.assertTrue(any("上传下单表" in item["content"] for item in timeline))

    def test_follow_up_can_link_to_quote(self):
        _, deal, quote = self._quote_with_item()
        follow = self.client.post(
            "/api/crm/follow-ups",
            data={
                "object_type": "deal",
                "object_id": str(deal["id"]),
                "quote_id": str(quote["id"]),
                "content": "已把客厅天窗方案发给客户",
                "method": "wechat",
            },
        )
        self.assertEqual(follow.status_code, 200, follow.text)
        self.assertEqual(follow.json()["quote_id"], quote["id"])
        self.assertEqual(follow.json()["quote_no"], quote["quote_no"])

    def test_only_confirmed_quote_can_generate_order(self):
        _, deal, quote = self._quote_with_item()
        blocked = self.client.post(
            f"/api/crm/quotes/{quote['id']}/orders",
            json={"deposit": 2000, "logistics_mode": "self"},
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["code"], "quote_not_confirmed")

        confirmed = self.client.post(
            f"/api/crm/quotes/{quote['id']}/confirm",
            data={"note": "客户已微信确认报价单"},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["status"], "confirmed")
        deal_after = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        self.assertEqual(deal_after["stage"], "won")
        self.assertEqual(deal_after["amount"], 11600.0)

        second_quote = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes",
            json={"title": "不应允许的第二个确认报价单"},
        )
        self.assertEqual(second_quote.status_code, 409, second_quote.text)
        self.assertEqual(second_quote.json()["code"], "quote_already_confirmed")

        ordered = self.client.post(
            f"/api/crm/quotes/{quote['id']}/orders",
            json={
                "discount_amount": 600,
                "discount_reason": "整单优惠",
                "deposit": 3000,
                "logistics_mode": "self",
            },
        )
        self.assertEqual(ordered.status_code, 200, ordered.text)
        data = ordered.json()
        self.assertEqual(data["order"]["quote_id"], quote["id"])
        self.assertEqual(data["order"]["status"], "pending_payment")
        self.assertEqual(data["order"]["product_total"], 11600.0)
        self.assertEqual(data["order"]["amount"], 11000.0)
        self.assertEqual(data["order"]["balance_amount"], 8000.0)

        detail = self.client.get(f"/api/crm/orders/{data['order']['id']}").json()
        self.assertEqual(detail["quote"]["quote_no"], quote["quote_no"])
        self.assertEqual(len(detail["items"]), 1)
        self.assertIsNotNone(detail["customer_confirmed_at"])
        self.assertTrue(detail["product_name_snapshot"])
        self.assertEqual(detail["items"][0]["production_spec"], "框 1180*2380；扇 1160*2360")

    def test_quote_requires_xlsx_form(self):
        _, deal = self._deal()
        quote = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes", json={"title": "测试"}
        ).json()
        product = self.client.get("/api/crm/products").json()[0]
        resp = self.client.post(
            f"/api/crm/quotes/{quote['id']}/items",
            data={"product_id": str(product["id"]), "quantity": "1", "unit_price": "100"},
            files={"form_file": ("bad.xls", b"not-excel", "application/vnd.ms-excel")},
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "quote_form_xlsx_required")


if __name__ == "__main__":
    unittest.main()
