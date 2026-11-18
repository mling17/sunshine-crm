"""Static regression checks for the leads list and form layout."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LeadsUiStructureTest(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / "static/views/leads.js").read_text(encoding="utf-8")
        self.shared = (ROOT / "static/views/shared.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")
        self.polish_css = (ROOT / "static/ui-polish.css").read_text(encoding="utf-8")

    def test_list_keeps_separate_tag_and_intent_columns(self):
        self.assertIn("{ title: '类型'", self.js)
        self.assertIn("{ title: '标签'", self.js)
        self.assertIn("{ title: '意向'", self.js)

    def test_list_tags_are_read_only_and_width_bounded(self):
        start = self.js.index("{ title: '标签'")
        end = self.js.index("{ title: '意向'", start)
        cell = self.js[start:end]
        self.assertIn("leadTagSummaryHtml(l.tags)", cell)
        self.assertNotIn("data-op=\"tags\"", cell)
        self.assertNotIn("lead-tag-add", cell)
        self.assertIn("Math.min(list.length, 3)", self.js)
        self.assertIn("lead-tag-more", self.js)

    def test_contact_phone_is_in_first_column_and_table_has_no_horizontal_scroll(self):
        self.assertIn("{ title: '联系人 / 联系方式'", self.js)
        self.assertNotIn("{ title: '联系方式'", self.js)
        self.assertIn('class="lead-phone-text"', self.js)
        self.assertNotIn('href="tel:', self.js)
        self.assertIn("'lead-table', 'lead-table-wrap'", self.js)
        self.assertIn(".table-wrap.lead-table-wrap", self.polish_css)
        lead_table = self.polish_css[
            self.polish_css.index("table.data-table.lead-table {"):
            self.polish_css.index("table.data-table.lead-table td {")
        ]
        self.assertIn("width: 100%", lead_table)
        self.assertIn("min-width: 0", lead_table)
        self.assertIn("overflow-x: hidden", self.polish_css)

    def test_detail_tags_open_bulk_editor_and_save_once(self):
        for marker in (
            "data-lead-tag-manage",
            "function openLeadTagEditor",
            "data-lead-tag-suggest",
            "data-lead-tag-toggle",
            "自定义新标签",
            "data-lead-tag-save",
            "data-lead-tag-cancel",
            "选择或取消多个标签后",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)
        editor = self.js[
            self.js.index("function openLeadTagEditor"):
            self.js.index("function invalidReasonLabel")
        ]
        self.assertEqual(
            editor.count("api('/leads/' + lead.id + '/tags'"),
            2,
            "编辑器只应 GET 当前标签，并在保存时 PUT 一次",
        )
        self.assertIn("method: 'PUT'", editor)
        self.assertIn("body: { tags: selected.map", editor)
        toggle = editor[
            editor.index("function toggleTag"):
            editor.index("function addPendingTag")
        ]
        self.assertNotIn("api(", toggle, "点选标签只改待选状态，不能立即提交")

    def test_quick_tag_panel_has_responsive_accessibility_styles(self):
        for selector in (
            ".lead-tag-summary",
            ".lead-tag-chip-pair",
            ".lead-tag-more",
            ".lead-tag-detail-add",
            ".lead-tag-quick-layer",
            ".lead-tag-quick-card",
            ".lead-tag-suggestion",
            ".lead-tag-quick-chip",
            ".lead-tag-quick-feedback",
            ".lead-tag-quick-actions",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.css)
        self.assertIn("@media (max-width: 767px)", self.css)
        self.assertIn("aria-modal=\"true\"", self.js)
        self.assertIn("aria-live=\"polite\"", self.js)
        self.assertIn("prefers-reduced-motion: reduce", self.css)

    def test_lead_type_uses_dictionary_label(self):
        self.assertIn(
            "dictLabel('customer_type', l.lead_type, l.lead_type || '—')",
            self.js,
        )

    def test_list_truncates_long_values_and_uses_compact_status_badges(self):
        for marker in (
            'class="lead-name-cell"',
            'class="lead-cell-ellipsis"',
            "leadStatusBadge(l.status, true)",
            "'lead-table'",
            "new: ['ok', '新线索', '新']",
            "following: ['warn', '跟进中', '跟']",
            "invalid: ['danger', '无效', '无']",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)
        self.assertIn("tableClass", self.shared)
        self.assertIn("table.data-table.lead-table", self.polish_css)
        self.assertIn("table-layout: fixed", self.polish_css)
        self.assertIn(".lead-status-badge", self.polish_css)

    def test_detail_heading_groups_tags_and_right_aligned_badges(self):
        for marker in ("titleHtml:", "lead-detail-title-line", "detail-title-tags"):
            self.assertIn(marker, self.js)
        for marker in ("entity-title-main", "entity-title-badges"):
            self.assertIn(marker, self.shared)
        self.assertNotIn("['标签', (l.tags || [])", self.js)

    def test_lead_form_uses_compact_two_column_rows(self):
        start = self.js.index("function leadFormHtml")
        end = self.js.index("function parseLeadTags")
        form = self.js[start:end]
        self.assertGreaterEqual(form.count('<div class=\\"row-2\\">'), 4)
        self.assertIn("regionComboHtml(l.location)", form)

    def test_new_lead_form_defaults_and_required_fields(self):
        start = self.js.index("function leadFormHtml")
        end = self.js.index("function parseLeadTags")
        form = self.js[start:end]
        self.assertIn('class=\\"lead-form form-grid\\" autocomplete=\\"off\\" novalidate', form)
        self.assertIn('id=\\"leadFormError\\"', form)
        self.assertIn("<label>电话 *</label>", form)
        self.assertIn("required", form)
        self.assertIn("dictOptions('customer_source', l.source || 'other')", form)
        self.assertIn("dictOptions('intent_level', l.intent_level || 'low')", form)
        self.assertNotIn("dictOptions(" + "'customer_source', l.source || 'other', '')", form)

    def test_lead_submit_shows_visible_validation_and_api_errors(self):
        start = self.js.index("function openLeadFormModal")
        end = self.js.index("function refreshAfterLeadChange")
        handler = self.js[start:end]
        self.assertIn("showLeadFormError('名称不能为空'", handler)
        self.assertIn("showLeadFormError('电话不能为空'", handler)
        self.assertIn("showLeadFormError(err.message", handler)
        self.assertIn("toast(text, true)", handler)

    def test_detail_layout_styles_exist(self):
        for selector in (
            ".entity-title-main",
            ".entity-title-badges",
            ".lead-detail-title-line",
            ".detail-title-tags",
            ".lead-form .row-2",
        ):
            self.assertIn(selector, self.css)




class LeadsListShellUiTest(unittest.TestCase):
    """Ticket #9：共享列表外壳（三态排序表头 + 页码按钮 + 每页条数）在线索页落地。"""

    def setUp(self):
        self.js = (ROOT / "static/views/leads.js").read_text(encoding="utf-8")
        self.shared = (ROOT / "static/views/shared.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")

    def test_shared_shell_exports(self):
        for marker in (
            "function listPagerHtml",
            "function bindListShell",
            "function cycleSortOrder",
            "var LIST_PAGE_SIZES = [10, 20, 50, 100, 500]",
            "data-sort=\"",
            "data-size-select",
            "aria-sort",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.shared)

    def test_three_state_sort_cycle_asc_desc_default(self):
        self.assertIn("currentOrder === 'asc') { return 'desc';", self.shared)
        self.assertIn("currentOrder === 'desc') { return '';", self.shared)

    def test_data_table_renders_sortable_headers_only_with_sortkey(self):
        start = self.shared.index("function dataTable")
        head = self.shared[start:self.shared.index("var body", start)]
        for marker in ("c.sortKey", "sortState", "aria-sort", "data-order"):
            self.assertIn(marker, head)
        self.assertIn("esc(c.title)", head, "非排序列仍走普通表头")

    def test_leads_six_columns_sortable_and_tags_wechat_ops_not(self):
        for key in ("'type'", "'source'", "'location'", "'intent'", "'last_follow'", "'created_at'"):
            with self.subTest(key=key):
                self.assertIn("sortKey: " + key, self.js)
        for col in ("{ title: '标签'", "{ title: '微信号'", "{ title: '操作'"):
            with self.subTest(col=col):
                start = self.js.index(col)
                seg = self.js[start:self.js.index("},", start)]
                self.assertNotIn("sortKey", seg)

    def test_list_state_kept_in_hash_url(self):
        for marker in (
            "query.get('page')",
            "query.get('size')",
            "query.get('sort')",
            "query.get('order')",
            "history.replaceState",
            "p.set('sort'",
            "p.set('order'",
            "#/leads?",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_sort_or_size_change_resets_page_to_1(self):
        self.assertIn("patch.size !== undefined || patch.sort !== undefined", self.js)
        self.assertIn("next.page = 1;", self.js)

    def test_leads_uses_shell_pager_and_binding(self):
        self.assertIn("listPagerHtml(res)", self.js)
        self.assertIn("bindListShell($('#leadShell', root)", self.js)
        self.assertNotIn("pagerHtml(res)", self.js)
        self.assertNotIn("pagerEl.onclick", self.js)

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
