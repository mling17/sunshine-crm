"""附件能力（PLANNER-V3 §6.5）+ 资料汇总卡（§5.7）。"""
from __future__ import annotations

import unittest

from tests._util import ApiTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class FileUploadTest(ApiTestCase):
    def _post_files(self, customer_id: int, files, content: str = "带附件"):
        return self.client.post(
            "/api/crm/follow-ups",
            data={"customer_id": str(customer_id), "content": content},
            files=files,
        )

    def test_image_and_doc_mixed_upload(self):
        c = self.create_customer(name="张附件")
        resp = self._post_files(
            c["id"],
            [
                ("files", ("现场.png", PNG, "image/png")),
                ("files", ("报价.xlsx", b"PK\x03\x04data", "application/vnd.ms-excel")),
                ("files", ("图纸.dwg", b"AC1032demo", "application/acad")),
            ],
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["photo_count"], 3)
        kinds = [p["mime_type"] for p in resp.json()["photos"]]
        self.assertTrue(any(k.startswith("image/") for k in kinds))
        self.assertTrue(any("spreadsheet" in k or "excel" in k for k in kinds))

    def test_over_20mb_rejected(self):
        c = self.create_customer(name="张附件")
        big = b"0" * (20 * 1024 * 1024 + 1)
        resp = self._post_files(c["id"], [("files", ("big.pdf", big, "application/pdf"))])
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("20MB", resp.json()["detail"])

    def test_dangerous_type_rejected(self):
        c = self.create_customer(name="张附件")
        for name, payload in (
            ("x.html", b"<script>alert(1)</script>"),
            ("x.svg", b"<svg onload=alert(1)></svg>"),
            ("x.js", b"alert(1)"),
        ):
            resp = self._post_files(c["id"], [("files", (name, payload, "text/plain"))])
            self.assertEqual(resp.status_code, 400, f"{name} 不该被接受")

    def test_download_headers_force_attachment(self):
        c = self.create_customer(name="张附件")
        resp = self._post_files(
            c["id"],
            [
                ("files", ("现场.png", PNG, "image/png")),
                ("files", ("报价.xlsx", b"PK\x03\x04data", "application/vnd.ms-excel")),
            ],
        )
        attachments = resp.json()["photos"]
        for item in attachments:
            got = self.client.get(f"/api/crm/attachments/{item['id']}")
            self.assertEqual(got.status_code, 200)
            self.assertEqual(got.headers.get("x-content-type-options"), "nosniff")
            disposition = got.headers.get("content-disposition", "")
            self.assertIn("attachment", disposition, "默认一律下载，图片要预览得显式 ?inline=1")

    def test_image_inline_and_attachment_toggle(self):
        c = self.create_customer(name="张附件")
        resp = self._post_files(c["id"], [("files", ("现场.png", PNG, "image/png"))])
        att_id = resp.json()["photos"][0]["id"]
        inline = self.client.get(f"/api/crm/attachments/{att_id}", params={"inline": 1})
        self.assertIn("inline", inline.headers.get("content-disposition", ""))
        forced = self.client.get(f"/api/crm/attachments/{att_id}")
        self.assertIn("attachment", forced.headers.get("content-disposition", ""))

    def test_materials_aggregates_files(self):
        c = self.create_customer(name="张附件")
        self._post_files(c["id"], [("files", ("a.png", PNG, "image/png"))], content="第一条")
        self._post_files(c["id"], [("files", ("b.pdf", b"%PDF-1.4 demo", "application/pdf"))], content="第二条")

        items = self.client.get(
            "/api/crm/follow-ups/materials", params={"object_type": "customer", "object_id": c["id"]}
        ).json()
        self.assertEqual(len(items), 2)
        self.assertEqual({i["name"] for i in items}, {"a.png", "b.pdf"})
        self.assertEqual(items[0]["at"] >= items[1]["at"], True, "按时间倒序")

    def test_materials_deep_includes_deal_and_aftersale(self):
        c = self.create_customer(name="张附件")
        self._post_files(c["id"], [("files", ("客户.png", PNG, "image/png"))])

        deal = self.create_deal(c["id"], amount=9000.0, drive_type="manual")
        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "deal", "object_id": str(deal["id"]), "content": "图纸"},
            files=[("files", ("商机.dwg", b"AC1032demo", "application/acad"))],
        )

        shallow = self.client.get(
            "/api/crm/follow-ups/materials", params={"object_type": "customer", "object_id": c["id"]}
        ).json()
        deep = self.client.get(
            "/api/crm/follow-ups/materials",
            params={"object_type": "customer", "object_id": c["id"], "deep": True},
        ).json()
        self.assertEqual(len(shallow), 1, "浅层只算客户自己的跟进")
        self.assertEqual(len(deep), 2, "deep 要把商机的附件并进来")


class AftersaleFollowFlowTest(ApiTestCase):
    def test_aftersale_lifecycle_with_timeline(self):
        c = self.create_customer(name="售后客户")
        deal = self.create_deal(c["id"], amount=9000.0, drive_type="manual")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        order = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={"deposit": 9000, "logistics_mode": "self"},
        ).json()["order"]
        self.client.post(
            f"/api/crm/orders/{order['id']}/confirm",
            data={"note": "售后流程测试客户已确认"},
        )
        # 走完 6 态；确认发货即完成
        self.client.post(f"/api/crm/orders/{order['id']}/pay-deposit", data={"amount": "9000"})
        for target in ("producing",):
            self.client.post(f"/api/crm/orders/{order['id']}/transition", json={"to_status": target})
        self.client.post(f"/api/crm/orders/{order['id']}/pay-balance", data={"amount": "0"})
        self.client.post(f"/api/crm/orders/{order['id']}/transition",
                         json={"to_status": "ready_to_ship", "logistics_mode": "self"})
        done = self.client.post(f"/api/crm/orders/{order['id']}/transition", json={"to_status": "completed"})
        self.assertEqual(done.status_code, 200, done.text)

        created = self.client.post(
            "/api/crm/aftersales",
            json={"order_id": order["id"], "type": "repair", "description": "推拉门关不严"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        aftersale_id = created.json()["id"]

        before = self.client.get(f"/api/crm/aftersales/{aftersale_id}").json()
        self.assertEqual(before["status"], "pending")

        self.client.post(
            "/api/crm/follow-ups",
            data={"object_type": "aftersale", "object_id": str(aftersale_id),
                  "content": "已上门调整轨道", "method": "phone"},
        )
        after = self.client.get(f"/api/crm/aftersales/{aftersale_id}").json()
        self.assertEqual(after["status"], "processing", "记跟进自动处理中")
        self.assertIn("follow", [t["type"] for t in after["timeline"]])

        finished = self.client.post(
            f"/api/crm/aftersales/{aftersale_id}/finish", json={"result": "已调整好"}
        )
        self.assertEqual(finished.status_code, 200, finished.text)
        final = self.client.get(f"/api/crm/aftersales/{aftersale_id}").json()
        self.assertEqual(final["status"], "done")
        self.assertIn("stage", [t["type"] for t in final["timeline"]], "完成也要留履历")

    def test_aftersale_requires_completed_order(self):
        c = self.create_customer(name="售后客户")
        deal = self.create_deal(c["id"], amount=1000.0, drive_type="manual")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        order = self.client.post(
            f"/api/crm/deals/{deal['id']}/orders",
            json={"deposit": 1000, "logistics_mode": "self"},
        ).json()["order"]
        resp = self.client.post(
            "/api/crm/aftersales",
            json={"order_id": order["id"], "type": "repair", "description": "还没完工就报修"},
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["code"], "order_not_completed")


if __name__ == "__main__":
    unittest.main()
