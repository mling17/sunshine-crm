"""商机报价单、下单表展示、客户确认与报价转订单回归测试。"""

from __future__ import annotations

import io
import json
import unittest
import zipfile
from pathlib import Path
from urllib.parse import unquote

from openpyxl import load_workbook

from tests._util import ApiTestCase

from app.db import db_conn


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FORM = ROOT / "app/data/product_forms/TS-003.xlsx"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _form_with_updated_visible_text() -> bytes:
    source = SAMPLE_FORM.read_bytes()
    workbook = load_workbook(io.BytesIO(source), read_only=True, data_only=True)
    target = workbook.worksheets[0]["A2"].value
    workbook.close()
    old = str(target).encode("utf-8")
    new = (str(target) + "（更新）").encode("utf-8")

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as source_zip:
        with zipfile.ZipFile(output, "w") as target_zip:
            for info in source_zip.infolist():
                content = source_zip.read(info.filename)
                if info.filename == "xl/sharedStrings.xml":
                    content = content.replace(old, new, 1)
                target_zip.writestr(info, content)
    return output.getvalue()


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
        product = next(
            p for p in self.client.get("/api/crm/products").json()
            if p["code"] == "TS-003"
        )
        created_quote = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes",
            json={"title": "客厅天窗方案", "note": "客户先看这一版"},
        )
        self.assertEqual(created_quote.status_code, 200, created_quote.text)
        quote = created_quote.json()
        self.assertEqual(quote["status"], "draft")
        self.assertEqual(quote["items"], [])

        form_bytes = SAMPLE_FORM.read_bytes()
        preview = self.client.post(
            "/api/crm/quotes/form-preview",
            data={"product_id": str(product["id"])},
            files={
                "form_file": (
                    "客厅天窗下单表.xlsx",
                    form_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        preview_data = preview.json()
        self.assertTrue(preview_data["a1_value"])
        self.assertEqual(preview_data["recognized_total"], 20.0)
        self.assertTrue(preview_data["image_url"])
        self.assertNotIn("amount_cell", preview_data)
        self.assertEqual(preview_data["sheet_content"]["name"], "Sheet1")

        item = self.client.post(
            f"/api/crm/quotes/{quote['id']}/items",
            data={
                "product_id": str(product["id"]),
                "preview_token": preview_data["preview_token"],
                "amount": "25.50",
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
        self.assertEqual(quote["amount"], 25.5)
        self.assertEqual(len(quote["items"]), 1)
        line = quote["items"][0]
        self.assertEqual(line["recognized_total"], 20.0)
        self.assertEqual(line["amount"], 25.5)
        self.assertTrue(line["form_available"])
        self.assertTrue(line["form_preview_url"])
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
        image_download = self.client.get(line["form_preview_url"])
        self.assertEqual(image_download.status_code, 200)
        self.assertEqual(image_download.headers["content-type"], "image/png")
        self.assertEqual(len(line["form_content"]["sheets"]), 1)
        self.assertEqual(line["form_content"]["sheets"][0]["name"], "Sheet1")

        timeline = self.client.get(f"/api/crm/deals/{deal['id']}").json()["timeline"]
        self.assertTrue(any(item["type"] == "quote" for item in timeline))
        upload_event = next(item for item in timeline if "上传下单表" in item["content"])
        self.assertEqual(upload_event["detail"]["event"], "item_created")
        upload_item = upload_event["detail"]["items"][0]
        self.assertEqual(upload_item["sheet_name"], "Sheet1")
        self.assertGreater(upload_item["row_count"], 0)
        self.assertTrue(upload_item["form_preview_url"])
        self.assertTrue(upload_item["form_url"])

        follow_records = self.client.get(
            "/api/crm/follow-ups",
            params={"object_type": "deal", "object_id": deal["id"], "include_system": True},
        ).json()
        follow_upload = next(item for item in follow_records if "上传下单表" in item["content"])
        self.assertEqual(follow_upload["detail"]["event"], "item_created")

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

        sent = self.client.post(f"/api/crm/quotes/{quote['id']}/send")
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(sent.json()["status"], "pending")
        self.assertEqual(
            self.client.get(f"/api/crm/deals/{deal['id']}").json()["stage"],
            "confirm",
        )

        confirmed = self.client.post(
            f"/api/crm/quotes/{quote['id']}/confirm",
            data={"note": "客户已微信确认报价单"},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["status"], "confirmed")
        deal_after = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        self.assertEqual(deal_after["stage"], "won")
        self.assertEqual(deal_after["amount"], 25.5)

        second_quote = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes",
            json={"title": "不应允许的第二个确认报价单"},
        )
        self.assertEqual(second_quote.status_code, 409, second_quote.text)
        self.assertEqual(second_quote.json()["code"], "quote_already_confirmed")

        ordered = self.client.post(
            f"/api/crm/quotes/{quote['id']}/orders",
            json={
                "discount_amount": 2,
                "discount_reason": "整单优惠",
                "deposit": 5,
                "logistics_mode": "self",
            },
        )
        self.assertEqual(ordered.status_code, 200, ordered.text)
        data = ordered.json()
        self.assertEqual(data["order"]["quote_id"], quote["id"])
        self.assertEqual(data["order"]["status"], "pending_payment")
        self.assertEqual(data["order"]["product_total"], 25.5)
        self.assertEqual(data["order"]["amount"], 23.5)
        self.assertEqual(data["order"]["balance_amount"], 18.5)

        detail = self.client.get(f"/api/crm/orders/{data['order']['id']}").json()
        self.assertEqual(detail["quote"]["quote_no"], quote["quote_no"])
        self.assertEqual(len(detail["items"]), 1)
        self.assertIsNotNone(detail["customer_confirmed_at"])
        self.assertTrue(detail["product_name_snapshot"])

        quotes_after_order = self.client.get(
            f"/api/crm/deals/{deal['id']}/quotes"
        ).json()
        source_after_order = next(
            item for item in quotes_after_order if item["id"] == quote["id"]
        )
        self.assertEqual(source_after_order["status"], "confirmed")
        self.assertEqual(source_after_order["order_id"], data["order"]["id"])

    def test_order_name_inherits_quote_title_and_can_be_edited(self):
        _, _, quote = self._quote_with_item()
        self.client.post(f"/api/crm/quotes/{quote['id']}/send")
        self.client.post(f"/api/crm/quotes/{quote['id']}/confirm")

        ordered = self.client.post(
            f"/api/crm/quotes/{quote['id']}/orders",
            json={"deposit": 5, "logistics_mode": "self"},
        )
        self.assertEqual(ordered.status_code, 200, ordered.text)
        order = ordered.json()["order"]
        self.assertEqual(order["order_name"], quote["title"])

        renamed = self.client.put(
            f"/api/crm/orders/{order['id']}",
            json={"order_name": "客厅天窗最终订单"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["order_name"], "客厅天窗最终订单")

        immutable = self.client.put(
            f"/api/crm/orders/{order['id']}",
            json={"order_no": "SO-CHANGED"},
        )
        self.assertEqual(immutable.status_code, 400, immutable.text)
        self.assertEqual(immutable.json()["code"], "validation_failed")
        detail = self.client.get(f"/api/crm/orders/{order['id']}").json()
        self.assertEqual(detail["order_no"], order["order_no"])

    def test_quote_confirmation_with_screenshot_returns_file_url(self):
        _, _, quote = self._quote_with_item()
        sent = self.client.post(f"/api/crm/quotes/{quote['id']}/send")
        self.assertEqual(sent.status_code, 200, sent.text)

        confirmed = self.client.post(
            f"/api/crm/quotes/{quote['id']}/confirm",
            data={"note": "客户通过微信确认"},
            files={"screenshots": ("微信确认.png", PNG, "image/png")},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        files = confirmed.json()["confirmation_files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["file_name"], "微信确认.png")
        self.assertEqual(
            files[0]["url"],
            f"/api/crm/attachments/{files[0]['id']}",
        )
        downloaded = self.client.get(files[0]["url"])
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, PNG)

    def test_pending_quote_can_return_to_draft_for_requote(self):
        _, deal, quote = self._quote_with_item()
        self.assertEqual(
            self.client.post(f"/api/crm/quotes/{quote['id']}/requote").json()["status"],
            "draft",
            "报价状态重复提交应保持幂等",
        )

        sent = self.client.post(f"/api/crm/quotes/{quote['id']}/send")
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(sent.json()["status"], "pending")

        requoted = self.client.post(f"/api/crm/quotes/{quote['id']}/requote")
        self.assertEqual(requoted.status_code, 200, requoted.text)
        requoted_quote = requoted.json()
        self.assertEqual(requoted_quote["status"], "draft")
        self.assertEqual(requoted_quote["status_label"], "报价")
        self.assertEqual(
            self.client.get(f"/api/crm/deals/{deal['id']}").json()["stage"],
            "quote",
        )

        item_id = requoted_quote["items"][0]["id"]
        changed = self.client.put(
            f"/api/crm/quotes/items/{item_id}",
            data={"amount": "30.00", "note": "客户要求重新核算"},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["amount"], 30.0)

        timeline = self.client.get(f"/api/crm/deals/{deal['id']}").json()["timeline"]
        self.assertTrue(any("退回重新报价" in entry["content"] for entry in timeline))

        resent = self.client.post(f"/api/crm/quotes/{quote['id']}/send")
        self.assertEqual(resent.status_code, 200, resent.text)
        confirmed = self.client.post(f"/api/crm/quotes/{quote['id']}/confirm")
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        blocked = self.client.post(f"/api/crm/quotes/{quote['id']}/requote")
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["code"], "quote_requote_not_allowed")

    def test_send_quote_creates_auto_tags_and_requote_removes_them(self):
        _, deal, quote = self._quote_with_item()
        manual = self.client.post(
            f"/api/crm/deals/{deal['id']}/tags",
            json={"name": "重点跟进"},
        )
        self.assertEqual(manual.status_code, 200, manual.text)

        sent = self.client.post(f"/api/crm/quotes/{quote['id']}/send")
        self.assertEqual(sent.status_code, 200, sent.text)
        detail = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        tags = {tag["name"]: tag for tag in detail["tags"]}
        self.assertIn("待确认", tags)
        self.assertIn("金额 ¥25.50", tags)
        self.assertEqual(tags["待确认"]["source"], "auto")
        self.assertFalse(tags["待确认"]["deletable"])
        self.assertTrue(tags["重点跟进"]["deletable"])

        send_event = next(
            item for item in detail["timeline"]
            if item["content"] == f"报价单 {quote['quote_no']} 已发客户确认"
        )
        self.assertEqual(send_event["detail"]["event"], "sent")
        self.assertEqual(send_event["detail"]["quote"]["status"], "pending")
        self.assertTrue(send_event["detail"]["items"][0]["form_preview_url"])

        locked = self.client.delete(
            f"/api/crm/deals/{deal['id']}/tags/{tags['待确认']['id']}"
        )
        self.assertEqual(locked.status_code, 409, locked.text)
        self.assertEqual(locked.json()["code"], "deal_tag_auto_locked")

        removed = self.client.delete(
            f"/api/crm/deals/{deal['id']}/tags/{tags['重点跟进']['id']}"
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertNotIn("重点跟进", {tag["name"] for tag in removed.json()})

        requoted = self.client.post(f"/api/crm/quotes/{quote['id']}/requote")
        self.assertEqual(requoted.status_code, 200, requoted.text)
        after_requote = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        auto_names = {
            tag["name"] for tag in after_requote["tags"] if tag["source"] == "auto"
        }
        self.assertEqual(auto_names, set())

    def test_quote_requires_xlsx_form(self):
        _, deal = self._deal()
        quote = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes", json={"title": "测试"}
        ).json()
        product = self.client.get("/api/crm/products").json()[0]
        resp = self.client.post(
            f"/api/crm/quotes/{quote['id']}/items",
            data={"product_id": str(product["id"]), "preview_token": "0" * 64},
            files={"form_file": ("bad.xls", b"not-excel", "application/vnd.ms-excel")},
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "quote_form_xlsx_required")

    def test_preview_rejects_other_products_form_by_a1(self):
        _, deal = self._deal()
        quote = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes", json={"title": "校验测试"}
        ).json()
        product = next(
            p for p in self.client.get("/api/crm/products").json()
            if p["code"] == "TS-004"
        )
        resp = self.client.post(
            "/api/crm/quotes/form-preview",
            data={"product_id": str(product["id"])},
            files={
                "form_file": (
                    "错误产品.xlsx",
                    SAMPLE_FORM.read_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["code"], "quote_form_product_mismatch")

    def test_recognized_price_can_be_adjusted_without_reuploading(self):
        _, _, quote = self._quote_with_item()
        item_id = quote["items"][0]["id"]
        changed = self.client.put(
            f"/api/crm/quotes/items/{item_id}",
            data={"amount": "88.88", "note": "最终让利价"},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        changed_quote = changed.json()
        self.assertEqual(changed_quote["amount"], 88.88)
        self.assertEqual(changed_quote["items"][0]["amount"], 88.88)
        self.assertEqual(changed_quote["items"][0]["recognized_total"], 20.0)
        self.assertTrue(changed_quote["items"][0]["form_preview_url"])

    def test_replaced_form_preview_uses_new_versioned_url(self):
        _, _, quote = self._quote_with_item()
        item = quote["items"][0]
        old_preview_url = item["form_preview_url"]
        old_preview = self.client.get(old_preview_url)
        self.assertEqual(old_preview.status_code, 200, old_preview.text)

        form_bytes = _form_with_updated_visible_text()

        preview = self.client.post(
            "/api/crm/quotes/form-preview",
            data={"product_id": str(item["product_id"])},
            files={
                "form_file": (
                    "更新后的下单表.xlsx",
                    form_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        preview_data = preview.json()

        changed = self.client.put(
            f"/api/crm/quotes/items/{item['id']}",
            data={
                "product_id": str(item["product_id"]),
                "preview_token": preview_data["preview_token"],
                "amount": "26.00",
            },
            files={
                "form_file": (
                    "更新后的下单表.xlsx",
                    form_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        changed_item = changed.json()["items"][0]
        self.assertEqual(changed_item["amount"], 26.0)
        self.assertNotEqual(changed_item["form_preview_url"], old_preview_url)
        self.assertIn(
            "/api/crm/quotes/form-previews/" + preview_data["preview_token"],
            changed_item["form_preview_url"],
        )

        new_preview = self.client.get(changed_item["form_preview_url"])
        self.assertEqual(new_preview.status_code, 200, new_preview.text)
        self.assertNotEqual(new_preview.content, old_preview.content)
        self.assertIn(
            f"/api/crm/quotes/form-previews/{preview_data['preview_token']}",
            changed_item["form_preview_url"],
        )

    def test_history_download_keeps_exact_uploaded_version(self):
        _, deal, quote = self._quote_with_item()
        item = quote["items"][0]
        original_bytes = SAMPLE_FORM.read_bytes()

        # 模拟修复前写入的旧履历地址：只有报价明细 ID，没有上传版本。
        with db_conn() as conn:
            event = conn.execute(
                "SELECT id, detail FROM follow_ups"
                " WHERE deal_id = ? AND kind = 'quote'"
                " AND content LIKE '%添加产品%'"
                " ORDER BY id LIMIT 1",
                (deal["id"],),
            ).fetchone()
            self.assertIsNotNone(event)
            detail = json.loads(event["detail"])
            detail["items"][0]["form_url"] = (
                f"/api/crm/quotes/items/{item['id']}/form"
            )
            conn.execute(
                "UPDATE follow_ups SET detail = ? WHERE id = ?",
                (json.dumps(detail, ensure_ascii=False), event["id"]),
            )

        updated_bytes = _form_with_updated_visible_text()
        preview = self.client.post(
            "/api/crm/quotes/form-preview",
            data={"product_id": str(item["product_id"])},
            files={
                "form_file": (
                    "更新后的下单表.xlsx",
                    updated_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        changed = self.client.put(
            f"/api/crm/quotes/items/{item['id']}",
            data={
                "product_id": str(item["product_id"]),
                "preview_token": preview.json()["preview_token"],
                "amount": "26.00",
            },
            files={
                "form_file": (
                    "更新后的下单表.xlsx",
                    updated_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(changed.status_code, 200, changed.text)

        timeline = self.client.get(f"/api/crm/deals/{deal['id']}").json()["timeline"]
        old_event = next(entry for entry in timeline if "添加产品" in entry["content"])
        new_event = next(entry for entry in timeline if entry["detail"].get("event") == "item_updated")
        old_item = old_event["detail"]["items"][0]
        new_item = new_event["detail"]["items"][0]

        self.assertIn("/api/crm/quotes/form-versions/", old_item["form_url"])
        self.assertIn("/api/crm/quotes/form-versions/", new_item["form_url"])
        old_download = self.client.get(old_item["form_url"])
        new_download = self.client.get(new_item["form_url"])
        self.assertEqual(old_download.status_code, 200, old_download.text)
        self.assertEqual(new_download.status_code, 200, new_download.text)
        self.assertEqual(old_download.content, original_bytes)
        self.assertEqual(new_download.content, updated_bytes)
        self.assertIn(
            "客厅天窗下单表.xlsx",
            unquote(old_download.headers["content-disposition"]),
        )
        self.assertIn(
            "更新后的下单表.xlsx",
            unquote(new_download.headers["content-disposition"]),
        )

    def test_quote_priority_void_and_delete_refresh_deal_status(self):
        _, deal, quote = self._quote_with_item()
        second = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes",
            json={"title": "备选报价单"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        second = second.json()
        self.assertEqual(
            self.client.get(f"/api/crm/deals/{deal['id']}").json()["stage"],
            "quote",
        )

        sent = self.client.post(f"/api/crm/quotes/{quote['id']}/send")
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(
            self.client.get(f"/api/crm/deals/{deal['id']}").json()["stage"],
            "confirm",
        )

        confirmed = self.client.post(f"/api/crm/quotes/{quote['id']}/confirm")
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(
            self.client.get(f"/api/crm/deals/{deal['id']}").json()["stage"],
            "won",
        )

        voided = self.client.post(f"/api/crm/quotes/{second['id']}/void")
        self.assertEqual(voided.status_code, 200, voided.text)
        self.assertEqual(voided.json()["status"], "void")
        self.assertEqual(
            self.client.get(f"/api/crm/deals/{deal['id']}").json()["stage"],
            "won",
        )

        voided_confirmed = self.client.post(f"/api/crm/quotes/{quote['id']}/void")
        self.assertEqual(voided_confirmed.status_code, 409, voided_confirmed.text)
        self.assertEqual(voided_confirmed.json()["code"], "quote_void_locked")
        self.assertEqual(
            self.client.get(f"/api/crm/deals/{deal['id']}").json()["stage"],
            "won",
        )

        removed = self.client.delete(f"/api/crm/quotes/{second['id']}")
        self.assertEqual(removed.status_code, 200, removed.text)
        removed_confirmed = self.client.delete(f"/api/crm/quotes/{quote['id']}")
        self.assertEqual(removed_confirmed.status_code, 409, removed_confirmed.text)
        self.assertEqual(removed_confirmed.json()["code"], "quote_delete_locked")
        deal_after = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        self.assertEqual(deal_after["stage"], "won")
        self.assertEqual(deal_after["amount"], 25.5)

    def test_pending_and_confirmed_quotes_cannot_be_deleted(self):
        _, deal, quote = self._quote_with_item()

        sent = self.client.post(f"/api/crm/quotes/{quote['id']}/send")
        self.assertEqual(sent.status_code, 200, sent.text)
        pending_delete = self.client.delete(f"/api/crm/quotes/{quote['id']}")
        self.assertEqual(pending_delete.status_code, 409, pending_delete.text)
        self.assertEqual(pending_delete.json()["code"], "quote_delete_locked")

        confirmed = self.client.post(f"/api/crm/quotes/{quote['id']}/confirm")
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        confirmed_delete = self.client.delete(f"/api/crm/quotes/{quote['id']}")
        self.assertEqual(confirmed_delete.status_code, 409, confirmed_delete.text)
        self.assertEqual(confirmed_delete.json()["code"], "quote_delete_locked")

    def test_generating_order_voids_only_unconfirmed_quotes(self):
        _, deal, quote = self._quote_with_item()
        alternative = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes",
            json={"title": "未采用的备选方案"},
        )
        self.assertEqual(alternative.status_code, 200, alternative.text)
        alternative = alternative.json()

        self.client.post(f"/api/crm/quotes/{quote['id']}/send")
        confirmed = self.client.post(f"/api/crm/quotes/{quote['id']}/confirm")
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        ordered = self.client.post(
            f"/api/crm/quotes/{quote['id']}/orders",
            json={"deposit": 5, "logistics_mode": "self"},
        )
        self.assertEqual(ordered.status_code, 200, ordered.text)
        order = ordered.json()["order"]

        quotes = self.client.get(f"/api/crm/deals/{deal['id']}/quotes").json()
        self.assertTrue(quotes)
        source = next(item for item in quotes if item["id"] == quote["id"])
        alternative = next(item for item in quotes if item["id"] == alternative["id"])
        self.assertEqual(source["status"], "confirmed")
        self.assertEqual(alternative["status"], "void")
        self.assertEqual(source["order_id"], order["id"])
        self.assertIsNone(alternative["order_id"])

        timeline = self.client.get(f"/api/crm/deals/{deal['id']}").json()["timeline"]
        auto_void = next(
            item for item in timeline
            if item.get("detail", {}).get("event") == "auto_void_for_order"
        )
        self.assertEqual(
            {item["status_after"] for item in auto_void["detail"]["quotes"]},
            {"void"},
        )
        self.assertNotIn(quote["quote_no"], auto_void["content"])
        self.assertIn(alternative["quote_no"], auto_void["content"])

    def test_quote_name_is_required(self):
        _, deal = self._deal()
        response = self.client.post(
            f"/api/crm/deals/{deal['id']}/quotes", json={"title": "  "}
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["code"], "quote_title_required")


if __name__ == "__main__":
    unittest.main()
