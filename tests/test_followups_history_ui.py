"""跟进历史页（Ticket #16）静态结构校验：去掉表单、接入共享列表外壳、状态写 hash URL。"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FollowupsHistoryUiTest(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / "static/views/followups.js").read_text(encoding="utf-8")
        self.shared = (ROOT / "static/views/shared.js").read_text(encoding="utf-8")
        self.index = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")

    def test_history_page_has_no_inline_follow_form(self):
        """历史页不再内联「记一条跟进」表单；跟进弹层（详情页用）保持不动。"""
        self.assertNotIn("followupFormHtml", self.js)
        self.assertNotIn("followupItemHtml", self.js)
        self.assertNotIn('id="fuForm"', self.js)
        self.assertNotIn("<form", self.js)
        self.assertNotIn("保存跟进", self.js)
        self.assertNotIn("navigate('#/followups')", self.js)
        # 详情页共用的跟进弹层不受影响
        self.assertIn("openFollowModal", self.shared)

    def test_uses_shared_list_shell(self):
        for marker in (
            "bindListShell($('#fuShell', root)",
            "listPagerHtml(res)",
            "cycleSortOrder(order)",
            "dataTable(columns, items",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_five_sortable_columns_and_others_not(self):
        for key in ("'customer'", "'deal_stage'", "'content'", "'next_date'", "'created_at'"):
            with self.subTest(key=key):
                self.assertIn("sortKey: " + key, self.js)
        for col in ("{ title: '附件'", "{ title: '操作'"):
            with self.subTest(col=col):
                start = self.js.index(col)
                end = self.js.find("{ title:", start + len(col))
                seg = self.js[start:] if end < 0 else self.js[start:end]
                self.assertNotIn("sortKey", seg)

    def test_list_state_kept_in_hash_url(self):
        for marker in (
            "query.get('customer')",
            "query.get('deal')",
            "query.get('page')",
            "query.get('size')",
            "query.get('sort')",
            "query.get('order')",
            "history.replaceState",
            "p.set('page'",
            "p.set('size'",
            "p.set('sort'",
            "p.set('order'",
            "#/followups?",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_sort_size_filter_change_resets_page_to_1(self):
        self.assertIn("if (patch.page === undefined) { next.page = 1; }", self.js)

    def test_api_params_match_backend_contract(self):
        for marker in (
            "params.set('customer_id'",
            "params.set('deal_id'",
            "params.set('page'",
            "params.set('size'",
            "params.set('sort'",
            "params.set('order'",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_detail_page_consumers_use_items_contract(self):
        """详情页履历调用适配 {items,total,page,size}：size=500 取全量并读 items。"""
        for name in ("aftersales.js", "customers.js", "deals.js", "leads.js"):
            src = (ROOT / "static/views" / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertIn("include_system=true&size=500", src)
        self.assertIn("(all[1] && all[1].items) || []",
                      (ROOT / "static/views/aftersales.js").read_text(encoding="utf-8"))
        self.assertIn("(all[1] && all[1].items) || []",
                      (ROOT / "static/views/customers.js").read_text(encoding="utf-8"))
        self.assertIn("(all[4] && all[4].items) || []",
                      (ROOT / "static/views/deals.js").read_text(encoding="utf-8"))
        self.assertIn("(all[1] && all[1].items) || []",
                      (ROOT / "static/views/leads.js").read_text(encoding="utf-8"))

    def test_cache_buster_bumped(self):
        self.assertIn("/crm/views/followups.js?v=20261119followup-list-shell1", self.index)
        self.assertNotIn("followups.js?v=20261118deal-list1", self.index)
        # 适配新契约的详情页脚本一并刷新
        for name in ("aftersales", "customers", "deals", "leads"):
            with self.subTest(file=name):
                self.assertIn(f"/crm/views/{name}.js?v=20261119followup-items1", self.index)

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
