"""Static regression checks for the logistics/carriers list shell (Ticket #15)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CarriersListShellUiTest(unittest.TestCase):
    """Ticket #15：物流公司列表接入共享列表外壳（三态排序表头 + 页码按钮 + 每页条数），
    筛选（仅看启用 / 关键词）与分页排序全部交给服务端，状态写 `#/logistics` hash URL。"""

    def setUp(self):
        self.js = (ROOT / "static/views/logistics.js").read_text(encoding="utf-8")
        self.orders_js = (ROOT / "static/views/orders.js").read_text(encoding="utf-8")
        self.deals_js = (ROOT / "static/views/deals.js").read_text(encoding="utf-8")
        self.html = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")

    def test_sortable_columns_and_computed_columns_not(self):
        for key in ("'name'", "'address'"):
            with self.subTest(key=key):
                self.assertIn("sortKey: " + key, self.js)
        # 计算列 / 其他列不可排序：联系人、电话、被订单关联、操作列里没有 sortKey
        for title in ("'联系人'", "'电话'", "'被订单关联'", "'操作'"):
            with self.subTest(title=title):
                start = self.js.index("{ title: " + title)
                seg = self.js[start:self.js.index("},", start)]
                self.assertNotIn("sortKey", seg)

    def test_carrier_sort_keys_cover_whitelist(self):
        start = self.js.index("var CARRIER_SORT_KEYS")
        seg = self.js[start:self.js.index("];", start)]
        for key in ("name", "address"):
            with self.subTest(key=key):
                self.assertIn("'" + key + "'", seg)

    def test_list_state_kept_in_hash_url_with_filters(self):
        for marker in (
            "query.get('active')",
            "query.get('q')",
            "query.get('page')",
            "query.get('size')",
            "query.get('sort')",
            "query.get('order')",
            "history.replaceState",
            "p.set('active'",
            "p.set('q'",
            "p.set('page'",
            "p.set('size'",
            "p.set('sort'",
            "p.set('order'",
            "#/logistics?",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_sort_size_filter_change_resets_page_to_1(self):
        # 除翻页（patch.page）外，改条数/排序/任一筛选都回第 1 页
        self.assertIn("patch.page === undefined", self.js)
        self.assertIn("next.page = 1;", self.js)

    def test_uses_shell_pager_and_binding(self):
        self.assertIn("listPagerHtml(res)", self.js)
        self.assertIn("bindListShell($('#carrierShell', root)", self.js)
        self.assertIn("cycleSortOrder(order)", self.js)
        self.assertIn("dataTable([", self.js)
        # 旧的整表加载 + 本地过滤/排序必须移除
        self.assertNotIn("api('/carriers')", self.js)
        self.assertNotIn("list.sort(function (a, b)", self.js)
        self.assertNotIn("list.filter(function (c)", self.js)

    def test_api_call_sends_filters_and_page_size_sort_order(self):
        start = self.js.index("function loadCarriers")
        seg = self.js[start:]
        for marker in (
            "params.set('q'",
            "params.set('active'",
            "params.set('page'",
            "params.set('size'",
            "params.set('sort'",
            "params.set('order'",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, seg)

    def test_carrier_dropdowns_consumed_new_contract(self):
        # 订单编辑 / 发货弹层、商机出单弹层的物流公司下拉改为 {items,total,page,size} 契约
        self.assertEqual(self.orders_js.count("api('/carriers?size=500')"), 2)
        self.assertEqual(self.deals_js.count("api('/carriers?size=500')"), 1)
        for js in (self.orders_js, self.deals_js):
            with self.subTest(js=js):
                self.assertIn("res.items", js)
                self.assertNotIn("api('/carriers')", js)

    def test_cache_buster_bumped(self):
        self.assertIn("/crm/views/logistics.js?v=20261119carrier-list-shell1", self.html)
        self.assertNotIn("logistics.js?v=20261104lead1", self.html)

    def test_sortable_header_and_pager_styles(self):
        for selector in (
            "th.sortable",
            ".sort-arrow",
            ".list-pager",
            ".list-pager-pages",
            ".pager-page.active",
            ".list-pager-size",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.css)


if __name__ == "__main__":
    unittest.main()
