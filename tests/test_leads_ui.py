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

    def test_list_keeps_separate_tag_and_intent_columns(self):
        self.assertIn("{ title: '标签'", self.js)
        self.assertIn("{ title: '意向'", self.js)

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
        self.assertIn("省份.城市", form)

    def test_detail_layout_styles_exist(self):
        for selector in (
            ".entity-title-main",
            ".entity-title-badges",
            ".lead-detail-title-line",
            ".detail-title-tags",
            ".lead-form .row-2",
        ):
            self.assertIn(selector, self.css)


if __name__ == "__main__":
    unittest.main()
