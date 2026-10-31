"""Static regression checks for the leads list and form layout."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LeadsUiStructureTest(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / "static/views/leads.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")

    def test_name_cell_groups_tags_status_and_intent(self):
        for marker in (
            "function leadNameCell",
            'class="lead-name-row"',
            'class="lead-name-main"',
            'class="lead-name-tags"',
            'class="lead-name-meta"',
        ):
            self.assertIn(marker, self.js)
        # 标签、意向不再作为独立表格列，避免与姓名行重复展示。
        self.assertNotIn("{ title: '标签'", self.js)
        self.assertNotIn("{ title: '意向'", self.js)

    def test_lead_form_uses_compact_two_column_rows(self):
        start = self.js.index("function leadFormHtml")
        end = self.js.index("function parseLeadTags")
        form = self.js[start:end]
        self.assertGreaterEqual(form.count('<div class=\\"row-2\\">'), 4)
        self.assertIn("省份.城市", form)

    def test_lead_name_layout_styles_exist(self):
        for selector in (
            ".lead-name-row",
            ".lead-name-tags",
            ".lead-name-meta",
            ".lead-form .row-2",
        ):
            self.assertIn(selector, self.css)


if __name__ == "__main__":
    unittest.main()
