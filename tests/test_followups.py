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

    def test_non_image_and_html_allowed(self):
        """跟进附件支持文档/图纸/HTML；下载侧仍强制 attachment，避免 HTML 被执行"""
        c = self.create_customer(name="王强")
        ok = self.client.post(
            "/api/crm/follow-ups",
            data={"customer_id": str(c["id"]), "content": "报价单"},
            files=[
                ("files", ("quote.xlsx", b"PK\x03\x04demo", "application/vnd.ms-excel")),
                ("files", ("图纸.dwg", b"AC1032demo", "application/acad")),
                ("files", ("notes.html", b"<p>notes</p>", "text/html")),
            ],
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["photo_count"], 3)

        for item in ok.json()["photos"]:
            got = self.client.get(f"/api/crm/attachments/{item['id']}")
            self.assertEqual(got.status_code, 200)
            self.assertIn("attachment", got.headers.get("content-disposition", ""))

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
        self.assertEqual(deals["items"][0]["stage"], "won")
        self.assertTrue(deals["items"][0]["closed_at"], "进 won 必须置 closed_at（本月成交口径）")

        # 再记一条移出 won → closed_at 清空
        resp = self.post_follow_up(c["id"], deal_id=deal["id"], stage="lost")
        self.assertEqual(resp.status_code, 200, resp.text)
        deals = self.client.get(f"/api/crm/deals?customer_id={c['id']}").json()
        self.assertEqual(deals["items"][0]["stage"], "lost")
        self.assertIsNone(deals["items"][0]["closed_at"])

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

        all_items = self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}").json()["items"]
        self.assertEqual(len(all_items), 2)
        self.assertEqual(all_items[0]["id"], second["id"], "按时间倒序（新的在前）")
        by_id = {item["id"]: item for item in all_items}
        self.assertEqual(by_id[first["id"]]["photo_count"], 1)
        self.assertEqual(by_id[second["id"]]["photo_count"], 0)

        only_deal = self.client.get(f"/api/crm/follow-ups?deal_id={deal['id']}").json()["items"]
        self.assertEqual([item["id"] for item in only_deal], [second["id"]])

        self.assertEqual(
            self.client.get("/api/crm/follow-ups?customer_id=9999").json()["items"], []
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



class FollowUpListPaginationSortTest(ApiTestCase):
    """Ticket #16：GET /follow-ups 分页契约 + 排序白名单。

    与线索/客户/商机/订单同一套口径：{items,total,page,size}；size 白名单
    [10,20,50,100,500]；sort 白名单 customer/deal_stage/content/next_date/created_at；
    非法 page/size/sort/order 一律 400；默认 created_at DESC, id DESC；
    可空列（customer/deal_stage/next_date）升/降序都 NULL 沉底；显式排序稳定次键 id DESC。
    """

    # ---------- 小工具 ----------
    def post_fu(
        self,
        object_type: str,
        object_id: int,
        *,
        content: str = "跟进内容",
        next_date: str | None = None,
        deal_id: int | None = None,
    ) -> dict:
        data: dict[str, str] = {
            "object_type": object_type,
            "object_id": str(object_id),
            "content": content,
        }
        if next_date is not None:
            data["next_date"] = next_date
        if deal_id is not None:
            data["deal_id"] = str(deal_id)
        resp = self.client.post("/api/crm/follow-ups", data=data)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def create_lead(self, *, name: str = "线索甲", phone: str = "13800138000") -> dict:
        resp = self.client.post(
            "/api/crm/leads",
            json={"name": name, "phone": phone, "lead_type": "personal", "source": "wechat"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def ids(self, resp) -> list[int]:
        self.assertEqual(resp.status_code, 200, resp.text)
        return [item["id"] for item in resp.json()["items"]]

    # ---------- 契约 ----------
    def test_pagination_contract(self):
        """默认 page=1/size=20，返回 {items,total,page,size}；翻页切片正确。"""
        c = self.create_customer(name="张伟")
        for i in range(25):
            self.post_fu("customer", c["id"], content=f"第{i + 1}次跟进")

        resp = self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["size"], 20)
        self.assertEqual(data["total"], 25)
        self.assertEqual(len(data["items"]), 20)

        resp = self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}&page=2&size=10")
        data = resp.json()
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["size"], 10)
        self.assertEqual(data["total"], 25)
        self.assertEqual(len(data["items"]), 10)
        first_page = self.client.get(
            f"/api/crm/follow-ups?customer_id={c['id']}&page=1&size=10"
        ).json()["items"]
        self.assertNotEqual(
            [it["id"] for it in first_page], [it["id"] for it in data["items"]]
        )

        # 页码越过尾页：items 为空但 total 不变
        data = self.client.get(
            f"/api/crm/follow-ups?customer_id={c['id']}&page=9&size=10"
        ).json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 25)

    def test_page_size_sort_order_whitelists(self):
        """非法 page/size/sort/order 一律 400，错误码与 Ticket #9/#13 共享口径一致。"""
        cases = [
            ("/api/crm/follow-ups?page=0", "invalid_page"),
            ("/api/crm/follow-ups?page=-1", "invalid_page"),
            ("/api/crm/follow-ups?size=15", "invalid_page_size"),
            ("/api/crm/follow-ups?size=1000", "invalid_page_size"),
            ("/api/crm/follow-ups?sort=id", "invalid_sort"),
            ("/api/crm/follow-ups?sort=photo_count", "invalid_sort"),
            ("/api/crm/follow-ups?sort=content;DROP TABLE", "invalid_sort"),
            ("/api/crm/follow-ups?sort=content&order=up", "invalid_order"),
            ("/api/crm/follow-ups?sort=content&order=ASC", "invalid_order"),
        ]
        for url, code in cases:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 400, resp.text)
                self.assertEqual(resp.json()["code"], code)

    # ---------- 排序 ----------
    def test_default_order_created_at_desc_id_desc(self):
        """不传 sort：记录时间倒序 + id 倒序（新的在前）。"""
        c = self.create_customer(name="张伟")
        first = self.post_fu("customer", c["id"], content="第一次")
        second = self.post_fu("customer", c["id"], content="第二次")
        third = self.post_fu("customer", c["id"], content="第三次")

        got = self.ids(self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}"))
        self.assertEqual(got, [third["id"], second["id"], first["id"]])

    def test_sort_content_with_stable_tiebreak(self):
        """显式 sort=content：同值按稳定次键 id DESC。"""
        c = self.create_customer(name="张伟")
        a = self.post_fu("customer", c["id"], content="aaa")
        b = self.post_fu("customer", c["id"], content="bbb")
        d = self.post_fu("customer", c["id"], content="bbb")

        got = self.ids(
            self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}&sort=content&order=asc")
        )
        self.assertEqual(got, [a["id"], d["id"], b["id"]], "bbb 同值按 id DESC（后建的在前）")
        got = self.ids(
            self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}&sort=content&order=desc")
        )
        self.assertEqual(got, [d["id"], b["id"], a["id"]])

    def test_sort_created_at_explicit(self):
        """显式 sort=created_at 升序：最早的在前；降序与默认一致。

        created_at 精度到秒，连续两条可能同值；这里直接改库拉开时间差。
        """
        c = self.create_customer(name="张伟")
        first = self.post_fu("customer", c["id"], content="第一次")
        second = self.post_fu("customer", c["id"], content="第二次")
        with db_conn() as conn:
            conn.execute(
                "UPDATE follow_ups SET created_at = '2026-11-01T08:00:00Z' WHERE id = ?",
                (first["id"],),
            )
            conn.execute(
                "UPDATE follow_ups SET created_at = '2026-11-02T08:00:00Z' WHERE id = ?",
                (second["id"],),
            )

        got = self.ids(
            self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}&sort=created_at&order=asc")
        )
        self.assertEqual(got, [first["id"], second["id"]])
        got = self.ids(
            self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}&sort=created_at&order=desc")
        )
        self.assertEqual(got, [second["id"], first["id"]])

    def test_sort_customer_join_column_and_null_sink(self):
        """customer 走 JOIN 的 c.name；无线索客户（lead 跟进 customer_id 为空）升/降序都沉底。"""
        alpha = self.create_customer(name="Alpha 客户")
        beta = self.create_customer(name="Beta 客户")
        lead = self.create_lead(name="无线索客户", phone="13900139000")
        fa = self.post_fu("customer", alpha["id"], content="A 客户跟进")
        fb = self.post_fu("customer", beta["id"], content="B 客户跟进")
        fl = self.post_fu("lead", lead["id"], content="线索跟进（无客户）")
        self.assertIsNone(fl["customer_id"])

        for order, expect in (
            ("asc", [fa["id"], fb["id"], fl["id"]]),
            ("desc", [fb["id"], fa["id"], fl["id"]]),
        ):
            with self.subTest(order=order):
                got = self.ids(self.client.get(f"/api/crm/follow-ups?sort=customer&order={order}"))
                self.assertEqual(got, expect, "客户名为空的线索跟进必须沉底")

    def test_sort_deal_stage_join_column_and_null_sink(self):
        """deal_stage 走 JOIN 的 d.stage；未关联商机的跟进升/降序都沉底。"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"])
        with_deal = self.post_fu("customer", c["id"], content="带商机", deal_id=deal["id"])
        without_deal = self.post_fu("customer", c["id"], content="不带商机")
        self.assertEqual(with_deal["deal_stage"], deal["stage"])
        self.assertIsNone(without_deal["deal_stage"])

        for order in ("asc", "desc"):
            with self.subTest(order=order):
                got = self.ids(
                    self.client.get(f"/api/crm/follow-ups?sort=deal_stage&order={order}")
                )
                self.assertEqual(got[0], with_deal["id"])
                self.assertEqual(got[-1], without_deal["id"])

    def test_sort_next_date_null_sinks_both_directions(self):
        """next_date 可空：升序、降序都沉底（(expr IS NULL) ASC）。"""
        c = self.create_customer(name="张伟")
        with_date = self.post_fu("customer", c["id"], content="有下次", next_date="2026-12-01")
        without_date = self.post_fu("customer", c["id"], content="没下次")

        for order in ("asc", "desc"):
            with self.subTest(order=order):
                got = self.ids(
                    self.client.get(f"/api/crm/follow-ups?sort=next_date&order={order}")
                )
                self.assertEqual(got[0], with_date["id"])
                self.assertEqual(got[-1], without_date["id"])

    # ---------- 筛选 ----------
    def test_filters_combined_with_pagination(self):
        """customer_id/deal_id/object_type/object_id 过滤与分页共存；total 随过滤变化。"""
        c = self.create_customer(name="张伟")
        deal = self.create_deal(c["id"])
        lead = self.create_lead(name="李娜", phone="13900139000")
        for i in range(3):
            self.post_fu("customer", c["id"], content=f"客户跟进{i}")
        self.post_fu("customer", c["id"], content="挂商机的跟进", deal_id=deal["id"])
        self.post_fu("lead", lead["id"], content="线索跟进")

        data = self.client.get(
            f"/api/crm/follow-ups?customer_id={c['id']}&page=1&size=10"
        ).json()
        self.assertEqual(data["total"], 4)
        self.assertEqual(len(data["items"]), 4)

        data = self.client.get(f"/api/crm/follow-ups?deal_id={deal['id']}").json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["content"], "挂商机的跟进")

        data = self.client.get(
            f"/api/crm/follow-ups?object_type=lead&object_id={lead['id']}"
        ).json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["content"], "线索跟进")

    def test_include_system_still_server_side(self):
        """默认只回 kind='follow'；include_system=true 连系统履历一起分页返回。"""
        c = self.create_customer(name="张伟")
        self.create_deal(c["id"])  # 建商机会写 kind='create' 系统履历（customer_id 回填）
        self.post_fu("customer", c["id"], content="人工跟进")

        data = self.client.get(f"/api/crm/follow-ups?customer_id={c['id']}").json()
        self.assertTrue(data["items"])
        self.assertTrue(all(it["kind"] == "follow" for it in data["items"]))

        full = self.client.get(
            f"/api/crm/follow-ups?customer_id={c['id']}&include_system=true"
        ).json()
        self.assertGreaterEqual(full["total"], data["total"])
        self.assertTrue(any(it["kind"] != "follow" for it in full["items"]))


if __name__ == "__main__":
    unittest.main()
