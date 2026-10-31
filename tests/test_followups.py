"""T5：跟进记录 + 照片上传（本地目录，≤3 张）+ 附件流（登录 + 防路径穿越）。

覆盖验收点：
- 带 1 张图建跟进成功，``GET /api/crm/attachments/{id}`` 能取回字节（非空、image/*）；
- 一次传 4 张 → 400（应用层上限，且不落任何文件/行）；
- 带 ``stage`` + ``deal_id`` 时顺手改商机阶段（won 置 closed_at、移出 won 清空）；
- 列表按 customer_id/deal_id 过滤并带照片数；删除跟进级联删 attachments 行；
- 未登录 401；storage_key 路径穿越/绝对路径一律 404。
"""

from __future__ import annotations

import unittest

from tests import _bootstrap  # noqa: F401  —— 必须在 app.* 之前 import，设定临时 DB/上传目录

from app.config.settings import settings
from app.db import db_conn
from tests._util import ApiTestCase, open_client

#: 最小 PNG 头 + 一点载荷（够验“字节原样取回”，不需要真解码）
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 8


class FollowUpsTest(ApiTestCase):
    # ---------- 小工具 ----------
    def post_follow_up(
        self,
        customer_id: int,
        *,
        content: str = "电话沟通，客户要 3 天内报价",
        deal_id: int | None = None,
        next_date: str | None = None,
        stage: str | None = None,
        photo_count: int = 0,
        filename: str = "site.png",
        mime: str = "image/png",
        payload: bytes = PNG_BYTES,
        object_type: str = "customer",
        object_id: int | None = None,
    ):
        data: dict[str, str] = {
            "object_type": object_type,
            "object_id": str(object_id or customer_id),
            "content": content
        }
        if deal_id is not None:
            data["deal_id"] = str(deal_id)
        if next_date is not None:
            data["next_date"] = next_date
        if stage is not None:
            data["stage"] = stage

        files = [
            ("photos", (f"{i}_{filename}", payload, mime)) for i in range(photo_count)
        ]
        return self.client.post(
            "/api/crm/follow-ups", data=data, files=files or None
        )

    def attachments(self, follow_up_id: int) -> list[dict]:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM attachments"
                " WHERE follow_up_id = ? AND is_delete = 0 ORDER BY id",
                (follow_up_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_follow_ups(self) -> int:
        with db_conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM follow_ups WHERE is_delete = 0"
            ).fetchone()["n"]

    # ---------- 新建 + 照片 ----------
    def test_create_with_one_photo_and_fetch_bytes(self):
        c = self.create_customer(name="张伟", phone="13800138000")

        resp = self.post_follow_up(c["id"], photo_count=1)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()

        self.assertEqual(body["customer_id"], c["id"])
        self.assertIsNone(body["deal_id"])
        self.assertEqual(body["photo_count"], 1)
        self.assertEqual(len(body["photos"]), 1)
        self.assertEqual(body["customer_name"], "张伟")

        att_id = body["photos"][0]["id"]
        self.assertEqual(body["photos"][0]["url"], f"/api/crm/attachments/{att_id}")
        self.assertEqual(body["photos"][0]["size"], len(PNG_BYTES))

        # 落盘：storage_key 是相对上传根的路径，文件真实存在且分日期目录
        rows = self.attachments(body["id"])
        self.assertEqual(len(rows), 1)
        key = rows[0]["storage_key"]
        self.assertFalse(key.startswith("/"), "storage_key 必须是相对路径")
        self.assertFalse(key.startswith("uploads/"), "storage_key 相对上传根，不应带 uploads/ 前缀")
        stored = (settings.uploads_path / key).resolve()
        self.assertTrue(stored.is_file(), f"文件未落盘：{stored}")
        self.assertEqual(stored.read_bytes(), PNG_BYTES)
        self.assertRegex(key, r"^\d{4}/\d{2}/\d{2}/[0-9a-f]{32}\.png$")

        # 取回字节：非空、image/*、内容一致
        got = self.client.get(f"/api/crm/attachments/{att_id}")
        self.assertEqual(got.status_code, 200, got.text)
        self.assertTrue(got.content)
        self.assertEqual(got.content, PNG_BYTES)
        self.assertTrue(
            got.headers["content-type"].startswith("image/"),
            got.headers.get("content-type"),
        )

    def test_ten_files_allowed_eleven_rejected(self):
        """定稿 v2.6：一条跟进最多 10 个附件（原来是 3 张照片）"""
        c = self.create_customer(name="李娜")
        ten = [("photos", (f"{i}_site.png", b"\x89PNG" + b"0" * 10, "image/png")) for i in range(10)]
        ok = self.client.post(
            "/api/crm/follow-ups",
            data={"customer_id": str(c["id"]), "content": "十张图"},
            files=ten,
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["photo_count"], 10)

        eleven = [("photos", (f"{i}_x.png", b"\x89PNG" + b"0" * 10, "image/png")) for i in range(11)]
        bad = self.client.post(
            "/api/crm/follow-ups",
            data={"customer_id": str(c["id"]), "content": "十一个"},
            files=eleven,
        )
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertIn("10", bad.json()["detail"])

    def test_non_image_allowed_and_html_rejected(self):
        """定稿 v2.4：附件任意类型（PDF/Excel/图纸…）；.html/.svg 这类可执行内容仍然拒"""
        c = self.create_customer(name="王强")
        ok = self.client.post(
            "/api/crm/follow-ups",
            data={"customer_id": str(c["id"]), "content": "报价单"},
            files=[("files", ("quote.xlsx", b"PK\x03\x04demo", "application/vnd.ms-excel"))],
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["photo_count"], 1)

        bad = self.client.post(
            "/api/crm/follow-ups",
            data={"customer_id": str(c["id"]), "content": "网页"},
            files=[("files", ("x.html", b"<script>alert(1)</script>", "text/html"))],
        )
        self.assertEqual(bad.status_code, 400, bad.text)

    def test_three_photos_allowed(self):
        c = self.create_customer(name="赵敏")
        resp = self.post_follow_up(c["id"], photo_count=3)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["photo_count"], 3)
        keys = {row["storage_key"] for row in self.attachments(body["id"])}
        self.assertEqual(len(keys), 3, "每张照片一个独立 uuid 文件")

    # ---------- 校验 ----------
    def test_unknown_customer_404(self):
        resp = self.post_follow_up(9999)
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_blank_content_rejected(self):
        c = self.create_customer(name="张伟")
        resp = self.post_follow_up(c["id"], content="   ")
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_deal_of_other_customer_rejected(self):
        a = self.create_customer(name="A")
        b = self.create_customer(name="B")
        deal = self.create_deal(a["id"])
        resp = self.post_follow_up(b["id"], deal_id=deal["id"])
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_unknown_deal_404(self):
        c = self.create_customer(name="张伟")
        resp = self.post_follow_up(c["id"], deal_id=9999)
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_invalid_next_date_400(self):
        c = self.create_customer(name="张伟")
        resp = self.post_follow_up(c["id"], next_date="2026/11/01")
        self.assertEqual(resp.status_code, 400, resp.text)

    # ---------- 顺手改阶段 ----------
    def test_stage_with_deal_updates_deal(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"], amount=12000.0)

        resp = self.post_follow_up(c["id"], deal_id=deal["id"], stage="won")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["deal_stage"], "won")

        deals = self.client.get(f"/api/crm/deals?customer_id={c['id']}").json()
        self.assertEqual(deals[0]["stage"], "won")
        self.assertTrue(deals[0]["closed_at"], "进 won 必须置 closed_at（本月成交口径）")

        # 再记一条移出 won → closed_at 清空
        resp = self.post_follow_up(c["id"], deal_id=deal["id"], stage="lost")
        self.assertEqual(resp.status_code, 200, resp.text)
        deals = self.client.get(f"/api/crm/deals?customer_id={c['id']}").json()
        self.assertEqual(deals[0]["stage"], "lost")
        self.assertIsNone(deals[0]["closed_at"])

    def test_stage_validated_even_without_deal(self):
        c = self.create_customer(name="张伟")
        resp = self.post_follow_up(c["id"], stage="not-a-stage")
        self.assertEqual(resp.status_code, 400, resp.text)

    # ---------- 列表 ----------
    def test_list_filters_and_photo_count(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"])
        first = self.post_follow_up(c["id"], content="第一次", photo_count=1).json()
        second = self.post_follow_up(
            c["id"], content="第二次", deal_id=deal["id"], next_date="2026-11-05"
        ).json()

        all_items = self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}").json()
        self.assertEqual(len(all_items), 2)
        self.assertEqual(all_items[0]["id"], second["id"], "按时间倒序（新的在前）")
        by_id = {item["id"]: item for item in all_items}
        self.assertEqual(by_id[first["id"]]["photo_count"], 1)
        self.assertEqual(by_id[second["id"]]["photo_count"], 0)

        only_deal = self.client.get(f"/api/crm/follow-ups?deal_id={deal['id']}").json()
        self.assertEqual([item["id"] for item in only_deal], [second["id"]])

        self.assertEqual(
            self.client.get("/api/crm/follow-ups?customer_id=9999").json(), []
        )

    def test_follow_up_attached_to_deleted_deal_is_gone(self):
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"])
        self.post_follow_up(c["id"], deal_id=deal["id"], photo_count=1)

        with db_conn() as conn:
            conn.execute("DELETE FROM deals WHERE id = ?", (deal["id"],))
        # DB 外键级联：deal 删了，挂它的跟进和照片行都没了
        self.assertEqual(self.count_follow_ups(), 0)
        with db_conn() as conn:
            n = conn.execute("SELECT COUNT(*) AS n FROM attachments").fetchone()["n"]
        self.assertEqual(n, 0)

    # ---------- 删除 ----------
    def test_delete_follow_up_cascades_attachments_rows(self):
        c = self.create_customer(name="张伟")
        body = self.post_follow_up(c["id"], photo_count=2).json()
        self.assertEqual(len(self.attachments(body["id"])), 2)

        resp = self.client.delete(f"/api/crm/follow-ups/{body['id']}")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json(), {"ok": True, "id": body["id"]})
        self.assertEqual(self.count_follow_ups(), 0)
        self.assertEqual(self.attachments(body["id"]), [])
        with db_conn() as conn:
            follow_deleted = conn.execute(
                "SELECT is_delete FROM follow_ups WHERE id = ?", (body["id"],)
            ).fetchone()[0]
            attachment_flags = [
                row[0] for row in conn.execute(
                    "SELECT is_delete FROM attachments WHERE follow_up_id = ?",
                    (body["id"],),
                ).fetchall()
            ]
        self.assertEqual(follow_deleted, 1)
        self.assertTrue(attachment_flags and all(flag == 1 for flag in attachment_flags))
        self.assertEqual(
            self.client.delete(f"/api/crm/follow-ups/{body['id']}").status_code, 404
        )

    # ---------- 附件安全 ----------
    def test_attachment_path_traversal_blocked(self):
        c = self.create_customer(name="张伟")
        body = self.post_follow_up(c["id"]).json()

        for evil_key in ("../../../../etc/passwd", "/etc/passwd", "2026/../../etc/hosts"):
            with self.subTest(key=evil_key), db_conn() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO attachments (follow_up_id, storage_key, file_name, mime_type, size, created_at)
                    VALUES (?, ?, 'x.png', 'image/png', 0, '2026-10-29T00:00:00')
                    """,
                    (body["id"], evil_key),
                )
                att_id = int(cur.lastrowid or 0)
            resp = self.client.get(f"/api/crm/attachments/{att_id}")
            self.assertEqual(resp.status_code, 404, f"{evil_key} 不应能读到文件")
            with db_conn() as conn:
                conn.execute("DELETE FROM attachments WHERE id = ?", (att_id,))

    def test_attachment_missing_file_404(self):
        c = self.create_customer(name="张伟")
        body = self.post_follow_up(c["id"]).json()
        with db_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO attachments (follow_up_id, storage_key, file_name, mime_type, size, created_at)
                VALUES (?, '2020/01/01/deadbeef.png', 'x.png', 'image/png', 0, '2026-10-29T00:00:00')
                """,
                (body["id"],),
            )
            att_id = int(cur.lastrowid or 0)
        self.assertEqual(self.client.get(f"/api/crm/attachments/{att_id}").status_code, 404)

    def test_attachment_and_followups_require_auth(self):
        c = self.create_customer(name="张伟")
        body = self.post_follow_up(c["id"], photo_count=1).json()
        att_id = body["photos"][0]["id"]

        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        self.assertEqual(anon.get(f"/api/crm/follow-ups?customer_id={c['id']}").status_code, 401)
        self.assertEqual(anon.get(f"/api/crm/attachments/{att_id}").status_code, 401)
        self.assertEqual(
            anon.post(
                "/api/crm/follow-ups",
                data={"object_type": "customer", "object_id": str(c["id"]), "content": "x"},
            ).status_code,
            401,
        )
        self.assertEqual(anon.delete(f"/api/crm/follow-ups/{body['id']}").status_code, 401)


if __name__ == "__main__":
    unittest.main()
