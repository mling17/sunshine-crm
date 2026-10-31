"""T7：CSV 导入 —— preview（表头 + 前 N 行 + 建议映射）+ commit（手动映射写 customers + import_log）。

零依赖：只用 stdlib ``csv``。.xlsx 不解析（V1.5 才上 openpyxl），收到就给友好提示、不报错。
"""

from __future__ import annotations

import json
import unittest

from tests import _bootstrap  # noqa: F401  —— 必须在 app.* 之前 import

from app.db import db_conn
from tests._util import ApiTestCase, open_client

CSV_UTF8 = (
    "姓名,电话,楼盘\n"
    "张伟,13800138000,阳光花园\n"
    "李娜,13900139000,翡翠湾\n"
    "王强,13700137000,金地中心\n"
).encode("utf-8")

CSV_GBK = (
    "姓名,电话,楼盘\n"
    "张伟,13800138000,阳光花园\n"
).encode("gbk")

MAPPING = {"姓名": "name", "电话": "phone", "楼盘": "location"}


class CsvImportTest(ApiTestCase):
    # ---------- 小工具 ----------
    def preview(self, data: bytes = CSV_UTF8, filename: str = "customers.csv"):
        return self.client.post(
            "/api/crm/import/preview",
            files={"file": (filename, data, "text/csv")},
        )

    def commit_json(self, **payload):
        return self.client.post("/api/crm/import/commit", json=payload)

    def commit_multipart(self, data: bytes = CSV_UTF8, filename: str = "customers.csv", mapping=None):
        return self.client.post(
            "/api/crm/import/commit",
            files={"file": (filename, data, "text/csv")},
            data={"column_mapping": json.dumps(mapping or MAPPING)},
        )

    def customer_total(self) -> int:
        return self.client.get("/api/crm/customers").json()["total"]

    def import_logs(self) -> list[dict]:
        with db_conn() as conn:
            rows = conn.execute("SELECT * FROM import_log ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    # ---------- preview ----------
    def test_preview_reads_headers_rows_and_suggested_mapping(self):
        resp = self.preview()
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()

        self.assertTrue(body["ok"])
        self.assertEqual(body["kind"], "csv")
        self.assertEqual(body["file_name"], "customers.csv")
        self.assertEqual(body["headers"], ["姓名", "电话", "楼盘"])
        self.assertEqual(len(body["headers"]), 3)
        self.assertEqual(body["total_rows"], 3)
        self.assertEqual(len(body["preview"]), 3)
        self.assertEqual(body["preview"][0]["姓名"], "张伟")
        self.assertEqual(body["preview"][0]["楼盘"], "阳光花园")
        self.assertEqual(
            body["suggested_mapping"], {"姓名": "name", "电话": "phone", "楼盘": "location"}
        )
        self.assertTrue(body["file_ref"], "commit 要靠 file_ref 取回刚上传的文件")
        self.assertRegex(body["file_ref"], r"^[0-9a-f]{32}$")
        self.assertIsNone(body["last_mapping"])

    def test_preview_decodes_gbk(self):
        resp = self.preview(CSV_GBK)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["headers"], ["姓名", "电话", "楼盘"])
        self.assertEqual(body["preview"][0]["姓名"], "张伟")
        self.assertIn("gb", body["encoding"].lower())

    def test_preview_xlsx_extension_gets_friendly_message(self):
        resp = self.preview(b"not really xlsx", filename="客户表.xlsx")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["kind"], "xlsx_unsupported")
        self.assertEqual(body["headers"], [])
        self.assertIn("CSV", body["message"])
        self.assertIn("另存为", body["message"])

    def test_preview_xlsx_magic_bytes_even_if_named_csv(self):
        resp = self.preview(b"PK\x03\x04" + b"\x00" * 32, filename="fake.csv")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["kind"], "xlsx_unsupported")

    def test_preview_empty_file_400(self):
        resp = self.preview(b"", filename="empty.csv")
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_preview_duplicate_headers_400(self):
        resp = self.preview("姓名,姓名,电话\nA,B,1\n".encode("utf-8"))
        self.assertEqual(resp.status_code, 400, resp.text)

    # ---------- commit ----------
    def test_commit_with_file_ref_imports_customers_and_audits(self):
        preview = self.preview().json()
        resp = self.commit_json(
            file_ref=preview["file_ref"],
            column_mapping=MAPPING,
            source_name="customers.csv",
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["imported"], 3)
        self.assertEqual(body["skipped"], 0)
        self.assertEqual(body["total_rows"], 3)
        self.assertFalse(body["mapping_reused"])
        self.assertEqual(body["mapping_used"], MAPPING)

        self.assertEqual(self.customer_total(), 3)
        customers = self.client.get("/api/crm/customers?size=100").json()["items"]
        by_name = {c["name"]: c for c in customers}
        self.assertEqual(by_name["张伟"]["phone"], "13800138000")
        self.assertEqual(by_name["张伟"]["location"], "阳光花园")

        logs = self.import_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["source_name"], "customers.csv")
        self.assertEqual(logs[0]["row_count"], 3)
        self.assertEqual(json.loads(logs[0]["column_mapping"]), MAPPING)

    def test_commit_multipart_with_file(self):
        resp = self.commit_multipart()
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["imported"], 3)
        self.assertEqual(self.customer_total(), 3)
        self.assertEqual(self.import_logs()[0]["source_name"], "customers.csv")

    def test_commit_without_mapping_and_no_history_400(self):
        preview = self.preview().json()
        resp = self.commit_json(file_ref=preview["file_ref"])
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("映射", resp.json()["detail"])
        self.assertEqual(self.customer_total(), 0)

    def test_commit_reuses_last_mapping(self):
        first = self.commit_multipart().json()
        self.assertFalse(first["mapping_reused"])

        preview = self.preview().json()
        self.assertEqual(preview["last_mapping"], MAPPING, "preview 要把上次映射带回来给前端预填")

        second = self.commit_json(file_ref=preview["file_ref"])
        self.assertEqual(second.status_code, 200, second.text)
        body = second.json()
        self.assertTrue(body["mapping_reused"])
        self.assertEqual(body["mapping_used"], MAPPING)
        self.assertEqual(body["imported"], 3)
        self.assertEqual(self.customer_total(), 6)
        self.assertEqual([log["row_count"] for log in self.import_logs()], [3, 3])

    def test_commit_explicit_mapping_overrides_last(self):
        self.commit_multipart()
        preview = self.preview().json()
        resp = self.commit_json(
            file_ref=preview["file_ref"],
            column_mapping={"姓名": "name", "电话": "wechat", "楼盘": "note"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertFalse(resp.json()["mapping_reused"])
        items = self.client.get("/api/crm/customers?size=100").json()["items"]
        target = [c for c in items if c["name"] == "张伟"]
        self.assertTrue(any(c["wechat"] == "13800138000" for c in target))

    def test_commit_skips_rows_without_name(self):
        csv_bytes = "姓名,电话\n张伟,13800138000\n ,13900139000\n李娜,\n".encode("utf-8")
        preview = self.preview(csv_bytes).json()
        body = self.commit_json(
            file_ref=preview["file_ref"], column_mapping={"姓名": "name", "电话": "phone"}
        ).json()
        self.assertEqual(body["imported"], 2)
        self.assertEqual(body["skipped"], 1)
        self.assertEqual(body["total_rows"], 3)
        self.assertEqual(self.import_logs()[0]["row_count"], 2)

    def test_commit_rejects_mapping_without_name(self):
        preview = self.preview().json()
        resp = self.commit_json(
            file_ref=preview["file_ref"], column_mapping={"电话": "phone"}
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("姓名", resp.json()["detail"])

    def test_commit_rejects_unknown_target_field(self):
        preview = self.preview().json()
        resp = self.commit_json(
            file_ref=preview["file_ref"],
            column_mapping={"姓名": "name", "电话": "not_a_field"},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_commit_rejects_mapping_for_missing_column(self):
        preview = self.preview().json()
        resp = self.commit_json(
            file_ref=preview["file_ref"],
            column_mapping={"不存在的列": "name"},
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("不存在的列", resp.json()["detail"])

    def test_commit_expired_file_ref_400(self):
        resp = self.commit_json(
            file_ref="0" * 32, column_mapping=MAPPING
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("重新上传", resp.json()["detail"])

    def test_commit_rejects_bad_file_ref_format(self):
        resp = self.commit_json(
            file_ref="../../etc/passwd", column_mapping=MAPPING
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    # ---------- 鉴权 ----------
    def test_import_requires_auth(self):
        anon = open_client(login_first=False)
        self.addCleanup(anon.__exit__, None, None, None)
        self.assertEqual(
            anon.post(
                "/api/crm/import/preview",
                files={"file": ("a.csv", CSV_UTF8, "text/csv")},
            ).status_code,
            401,
        )
        self.assertEqual(
            anon.post("/api/crm/import/commit", json={"column_mapping": MAPPING}).status_code,
            401,
        )


class LeadCsvImportTest(ApiTestCase):
    LEAD_MAPPING = {
        "姓名": "name",
        "电话": "phone",
        "微信": "wechat",
        "地区": "location",
        "来源": "source",
    }
    CSV = (
        "姓名,电话,微信,地区,来源\n"
        "青岛装饰,13800138000,qdzs,青岛市北区,转介绍\n"
        "济南门窗,13900139000,jnmc,济南高新区,微信\n"
    ).encode("utf-8")

    def commit_leads(self, data: bytes, mapping=None):
        preview = self.client.post(
            "/api/crm/import/preview",
            files={"file": ("leads.csv", data, "text/csv")},
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        return self.client.post(
            "/api/crm/import/commit",
            json={
                "file_ref": preview.json()["file_ref"],
                "column_mapping": mapping or self.LEAD_MAPPING,
                "target": "leads",
            },
        )

    def test_import_leads_defaults_to_medium_and_writes_create_history(self):
        resp = self.commit_leads(self.CSV)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["imported"], 2)

        leads = self.client.get("/api/crm/leads?size=100").json()["items"]
        self.assertEqual(len(leads), 2)
        self.assertTrue(all(item["intent_level"] == "medium" for item in leads))
        self.assertEqual({item["source"] for item in leads}, {"referral", "wechat"})

        for lead in leads:
            history = self.client.get(
                f"/api/crm/follow-ups?object_type=lead&object_id={lead['id']}&include_system=true"
            ).json()
            self.assertTrue(any(row["kind"] == "create" for row in history))

    def test_import_rejects_source_outside_dictionary_without_partial_write(self):
        data = (
            "姓名,电话,微信,地区,来源\n"
            "合法线索,13800138000,okwx,济南,微信\n"
            "非法来源,13900139000,badwx,青岛,自己编的来源\n"
        ).encode("utf-8")
        resp = self.commit_leads(data)
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("来源", resp.json()["detail"])
        self.assertIn("微信", resp.json()["detail"])
        self.assertEqual(self.client.get("/api/crm/leads").json()["total"], 0)

    def test_import_requires_contact_info(self):
        data = "姓名,电话,微信,地区,来源\n无联系方式,,,济南,微信\n".encode("utf-8")
        resp = self.commit_leads(data)
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("电话和微信至少填写一个", resp.json()["detail"])
        self.assertEqual(self.client.get("/api/crm/leads").json()["total"], 0)

    def test_import_requires_source_column_mapping(self):
        resp = self.commit_leads(
            self.CSV,
            {"姓名": "name", "电话": "phone", "微信": "wechat"},
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("来源", resp.json()["detail"])

    def test_import_deduplicates_normalized_phone_and_wechat(self):
        existing = self.client.post("/api/crm/leads", json={
            "name": "已有线索",
            "phone": "138-0013-8000",
            "wechat": "QdZS",
            "source": "wechat",
        })
        self.assertEqual(existing.status_code, 200, existing.text)

        data = (
            "姓名,电话,微信,地区,来源\n"
            "重复电话,138 0013 8000,newwx,济南,微信\n"
            "重复微信,13700137000,qdzs,青岛,转介绍\n"
            "有效新线索一,13600136000,unique,烟台,电话\n"
            "文件内重复电话,136-0013-6000,samefile,潍坊,电话\n"
            "有效新线索二,13500135000,newunique,临沂,微信\n"
        ).encode("utf-8")
        resp = self.commit_leads(data)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["imported"], 2)
        self.assertEqual(body["duplicate_count"], 3)
        self.assertEqual(self.client.get("/api/crm/leads").json()["total"], 3)


if __name__ == "__main__":
    unittest.main()
