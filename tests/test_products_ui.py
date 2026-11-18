"""Static regression checks for the products list shell (Ticket #14)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductsListShellUiTest(unittest.TestCase):
    """Ticket #14：产品列表接入共享列表外壳（三态排序表头 + 页码按钮 + 每页条数），
    筛选与分页排序全部交给服务端，状态（含筛选）写 `#/products` hash URL。"""

    def setUp(self):
        self.js = (ROOT / "static/views/products.js").read_text(encoding="utf-8")
        self.html = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")

    def test_sortable_columns_and_computed_columns_not(self):
        for key in ("'product'", "'drive_type'", "'status'"):
            with self.subTest(key=key):
                self.assertIn("sortKey: " + key, self.js)
        # 计算列 / 其他列不可排序：操作列里没有 sortKey（其 render 内含对象字面量，取到表尾）
        start = self.js.index("{ title: '操作'")
        seg = self.js[start:self.js.index("], (res && res.items)", start)]
        self.assertNotIn("sortKey", seg)
        for title in ("'配置'", "'规格范围'", "'引用'"):
            with self.subTest(title=title):
                start = self.js.index("{ title: " + title)
                seg = self.js[start:self.js.index("},", start)]
                self.assertNotIn("sortKey", seg)

    def test_product_sort_keys_cover_whitelist(self):
        start = self.js.index("var PRODUCT_SORT_KEYS")
        seg = self.js[start:self.js.index("];", start)]
        for key in ("product", "drive_type", "status"):
            with self.subTest(key=key):
                self.assertIn("'" + key + "'", seg)

    def test_list_state_kept_in_hash_url_with_filters(self):
        for marker in (
            "query.get('q')",
            "query.get('category')",
            "query.get('series')",
            "query.get('drive')",
            "query.get('active')",
            "query.get('page')",
            "query.get('size')",
            "query.get('sort')",
            "query.get('order')",
            "history.replaceState",
            "p.set('q'",
            "p.set('category'",
            "p.set('series'",
            "p.set('drive'",
            "p.set('active'",
            "p.set('page'",
            "p.set('size'",
            "p.set('sort'",
            "p.set('order'",
            "#/products?",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_sort_size_filter_change_resets_page_to_1(self):
        # 除翻页（patch.page）外，改条数/排序/任一筛选都回第 1 页
        self.assertIn("patch.page === undefined", self.js)
        self.assertIn("next.page = 1;", self.js)

    def test_uses_shell_pager_and_binding(self):
        self.assertIn("listPagerHtml(res)", self.js)
        self.assertIn("bindListShell($('#productShell', root)", self.js)
        self.assertIn("cycleSortOrder(order)", self.js)
        self.assertIn("dataTable([", self.js)
        # 旧的整表加载 + 本地过滤/排序必须移除
        self.assertNotIn("function filterProducts", self.js)
        self.assertNotIn("function bindProductFilters", self.js)
        self.assertNotIn("function productRowsHtml", self.js)
        self.assertNotIn("api('/products')", self.js)

    def test_api_call_sends_filters_and_page_size_sort_order(self):
        start = self.js.index("function loadProducts")
        seg = self.js[start:]
        for marker in (
            "params.set('q'",
            "params.set('category'",
            "params.set('series'",
            "params.set('drive_type'",
            "params.set('is_active'",
            "params.set('page'",
            "params.set('size'",
            "params.set('sort'",
            "params.set('order'",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, seg)

    def test_cache_buster_bumped(self):
        self.assertIn("/crm/views/products.js?v=20261118product-list-shell1", self.html)
        self.assertNotIn("products.js?v=20261104lead1", self.html)

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
