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
        body = resp.json()
        self.assertEqual(body["total"], 123)
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["size"], 20)
        products = body["items"]
        self.assertEqual(len(products), 20)
        self.assertEqual(products[0]["code"], "TS-001")
        self.assertTrue(all(p["form_available"] for p in products))
        self.assertTrue(all(p["form_file_name"].lower().endswith((".xlsx", ".xls")) for p in products))
        # 分类覆盖等全量断言取最大档位一次拉全（天窗类目超过一页，首页未必含全部类目）
        all_products = self.client.get("/api/crm/products", params={"size": 500}).json()["items"]
        self.assertEqual(len(all_products), 123)
        self.assertTrue(any(p["category"] == "天幕" for p in all_products))
        self.assertTrue(any(p["category"] == "开合屋面" for p in all_products))

        download = self.client.get(f"/api/crm/products/{products[0]['id']}/form-file")
        self.assertEqual(download.status_code, 200, download.text)
        self.assertTrue(download.content.startswith(b"PK\x03\x04"))

    def test_product_category_is_managed_by_data_dictionary(self):
        created = self.client.post(
            "/api/crm/dicts/product_type/items",
            json={"key": "测试新分类", "label": "测试新分类", "sort": 99},
        )
        self.assertEqual(created.status_code, 200, created.text)

        product = self.create_product(code="TS-DICT-001", category="测试新分类")
        self.assertEqual(product["category"], "测试新分类")

        product_types = self.client.get("/api/crm/dicts/product_type").json()["items"]
        used = next(item["used"] for item in product_types if item["key"] == "测试新分类")
        self.assertGreaterEqual(used, 1)

    def test_create_search_update_and_deactivate_product(self):
        product = self.create_product()
        self.assertRegex(product["code"], r"^TS-\d{3,}$")
        self.assertNotEqual(product["code"], "TS-TEST-001")
        self.assertEqual(product["config_summary"].count("电动纱窗"), 1)
        self.assertTrue(product["form_available"])

        hits = self.client.get("/api/crm/products", params={"q": "联排测试"}).json()["items"]
        self.assertEqual([p["id"] for p in hits], [product["id"]])

        resp = self.client.put(
            f"/api/crm/products/{product['id']}",
            json={"name": "55型2扇联排测试产品（新版）", "is_active": False},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["name"], "55型2扇联排测试产品（新版）")
        self.assertFalse(resp.json()["is_active"])

        active = self.client.get("/api/crm/products", params={"is_active": 1}).json()["items"]
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
        self.assertEqual(duplicate.json()["product_id"], product["id"])
        self.assertEqual(duplicate.json()["product_code"], product["code"])

    def test_existing_order_form_preview_links_to_existing_product(self):
        resp = self.client.post(
            "/api/crm/products/import-preview",
            files={
                "form_file": (
                    "TS-001.xlsx",
                    self.form_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        preview = resp.json()
        products = self.client.get("/api/crm/products", params={"size": 500}).json()["items"]
        existing = next(item for item in products if item["code"] == "TS-001")
        self.assertEqual(preview["duplicate_product_code"], "TS-001")
        self.assertEqual(preview["duplicate_product_id"], existing["id"])

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
            f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"}
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
            f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"}
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


# Product list server-side pagination / sorting / filtering (Ticket #14).
from tests._util import ApiTestCase


class TestProductListPagination(ApiTestCase):
    """Ticket #14：GET /products 改 {items,total,page,size}，筛选/排序/分页全部服务端。"""

    def get_items(self, **params) -> dict:
        resp = self.client.get("/api/crm/products", params=params)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_pagination_contract_and_size_whitelist(self):
        body = self.get_items()
        self.assertEqual(set(body), {"items", "total", "page", "size"})
        self.assertEqual(body["total"], 123)
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["size"], 20)
        self.assertEqual(len(body["items"]), 20)

        for size in (10, 20, 50, 100, 500):
            with self.subTest(size=size):
                page = self.get_items(size=size, page=1)
                self.assertEqual(page["size"], size)
                self.assertEqual(len(page["items"]), min(size, 123))
        page2 = self.get_items(size=10, page=2)
        self.assertEqual(page2["page"], 2)
        first_ids = {p["id"] for p in self.get_items(size=10, page=1)["items"]}
        self.assertFalse(first_ids & {p["id"] for p in page2["items"]}, "翻页不得重复")

    def test_invalid_page_size_sort_order_are_400(self):
        cases = [
            ({"page": 0}, "invalid_page"),
            ({"page": -3}, "invalid_page"),
            ({"size": 15}, "invalid_page_size"),
            ({"size": 5000}, "invalid_page_size"),
            ({"sort": "code"}, "invalid_sort"),
            ({"sort": "series"}, "invalid_sort"),
            ({"order": "up"}, "invalid_order"),
            ({"sort": "product", "order": ""}, "invalid_order"),
        ]
        for params, code in cases:
            with self.subTest(params=params):
                resp = self.client.get("/api/crm/products", params=params)
                self.assertEqual(resp.status_code, 400, resp.text)
                self.assertEqual(resp.json()["code"], code)

    def test_default_order_skylight_first_then_series_then_code(self):
        items = self.get_items(size=500)["items"]
        self.assertEqual(len(items), 123)
        # 天窗整体在最前，其后才是其他分类
        seen_other = False
        for product in items:
            if product["category"] == "天窗":
                self.assertFalse(seen_other, "天窗必须排在所有其他分类之前")
            else:
                seen_other = True
        self.assertTrue(seen_other, "种子数据应包含非天窗分类")
        # 每个分类内部：series 升序（SQLite 口径，NULL 在前），同 series 按 code 升序
        for category in {p["category"] for p in items}:
            with self.subTest(category=category):
                group = [p for p in items if p["category"] == category]
                keys = [(p["series"] or "", p["code"]) for p in group]
                self.assertEqual(keys, sorted(keys))

    def test_explicit_sort_whitelist_columns(self):
        asc = self.get_items(size=500, sort="product", order="asc")["items"]
        names = [p["name"] for p in asc]
        self.assertEqual(names, sorted(names))
        desc = self.get_items(size=500, sort="product", order="desc")["items"]
        self.assertEqual([p["name"] for p in desc], sorted(names, reverse=True))

        # drive_type 可空：升/降序都 NULL 沉底，非空部分有序
        for order in ("asc", "desc"):
            with self.subTest(order=order):
                rows = self.get_items(size=500, sort="drive_type", order=order)["items"]
                values = [p["drive_type"] for p in rows]
                seen_null = False
                non_null = []
                for value in values:
                    if value is None:
                        seen_null = True
                    else:
                        self.assertFalse(seen_null, "NULL 必须沉底")
                        non_null.append(value)
                self.assertEqual(non_null, sorted(non_null, reverse=(order == "desc")))
                self.assertGreater(sum(1 for v in values if v is None), 0, "种子数据含未指定驱动")

        # status（在售/停用）：停用(is_active=0)升序在最前；先造一个停用产品
        created = self.client.post(
            "/api/crm/products",
            data={"payload": json.dumps(
                {"name": "分页排序测试产品", "category": "天窗"},
                ensure_ascii=False,
            )},
            files={
                "form_file": (
                    "TS-TEST-001.xlsx",
                    TestProducts.form_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        product = created.json()
        self.client.put(
            f"/api/crm/products/{product['id']}", json={"is_active": False}
        )
        rows = self.get_items(size=500, sort="status", order="asc")["items"]
        flags = [p["is_active"] for p in rows]
        self.assertEqual(flags, sorted(flags))
        self.assertFalse(flags[0], "停用产品应排在最前")
        self.assertEqual(flags[0], False)
        # 同列稳定次键 id DESC：两个停用产品（若存在多个）按 id 倒序
        inactive = [p for p in rows if not p["is_active"]]
        self.assertEqual(
            [p["id"] for p in inactive],
            sorted((p["id"] for p in inactive), reverse=True),
        )

    def test_server_side_filters(self):
        skylight = self.get_items(size=500, category="天窗")
        self.assertTrue(all(p["category"] == "天窗" for p in skylight["items"]))
        self.assertEqual(skylight["total"], 113)
        self.assertLess(skylight["total"], 123)

        series_value = skylight["items"][0]["series"]
        series_hits = self.get_items(size=500, category="天窗", series=series_value)
        self.assertTrue(
            all(p["series"] == series_value for p in series_hits["items"])
        )
        self.assertLess(series_hits["total"], skylight["total"])

        electric = self.get_items(size=500, drive_type="electric")
        self.assertTrue(all(p["drive_type"] == "electric" for p in electric["items"]))
        self.assertGreater(electric["total"], 0)

        hits = self.get_items(q="TS-0")
        self.assertGreater(hits["total"], 0)
        for product in hits["items"]:
            blob = " ".join(
                str(product.get(k) or "")
                for k in ("code", "name", "series", "structure")
            )
            self.assertIn("TS-0", blob)

        # 无匹配：total 为 0，items 为空数组
        empty = self.get_items(q="绝对不存在的编号xyz")
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["items"], [])

    def test_filter_and_pagination_combine(self):
        base = self.get_items(q="TS-0", size=500)
        page1 = self.get_items(q="TS-0", size=10, page=1)
        page2 = self.get_items(q="TS-0", size=10, page=2)
        self.assertEqual(page1["total"], base["total"])
        self.assertEqual(page2["total"], base["total"])
        self.assertEqual(len(page1["items"]), 10)
        combined = page1["items"] + page2["items"]
        self.assertEqual(
            [p["id"] for p in combined],
            [p["id"] for p in base["items"][:20]],
            "筛选后的分页切片必须与全量筛选结果一致",
        )
        # 筛选 + 显式排序同样服务端生效
        sorted_hits = self.get_items(q="TS-0", size=500, sort="product", order="asc")
        names = [p["name"] for p in sorted_hits["items"]]
        self.assertEqual(names, sorted(names))
        self.assertEqual(sorted_hits["total"], base["total"])
