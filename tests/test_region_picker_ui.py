"""Regression checks for searchable region fields and select option hygiene."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class RegionPickerUiTest(unittest.TestCase):
    def setUp(self):
        self.shared = (STATIC / "views/shared.js").read_text(encoding="utf-8")
        self.regions = (STATIC / "views/regions.js").read_text(encoding="utf-8")
        self.leads = (STATIC / "views/leads.js").read_text(encoding="utf-8")
        self.customers = (STATIC / "views/customers.js").read_text(encoding="utf-8")
        self.app = (STATIC / "app.js").read_text(encoding="utf-8")
        self.index = (STATIC / "index.html").read_text(encoding="utf-8")
        self.css = (STATIC / "app.css").read_text(encoding="utf-8")

    def test_region_field_uses_shared_searchable_combobox(self):
        for source in (self.leads, self.customers):
            self.assertIn("regionComboHtml(", source)
            self.assertIn("bindRegionCombo(", source)
            self.assertNotRegex(
                source,
                r'<input name=\\?"location\\?" type=\\?"text\\?"',
            )

        self.assertIn("function searchableSelectHtml", self.shared)
        self.assertIn("function bindSearchableSelect", self.shared)
        for marker in (
            'role="combobox"',
            'role="listbox"',
            "ArrowDown",
            "ArrowUp",
            "aria-activedescendant",
            "aria-selected",
        ):
            self.assertIn(marker, self.shared)

    def test_region_options_cover_provinces_and_cities(self):
        for marker in (
            "'北京市'",
            "'河北省'",
            "'山东省'",
            "'青岛市'",
            "'广东省'",
            "'新疆维吾尔自治区'",
            "'香港特别行政区'",
            "当前已保存地区",
        ):
            self.assertIn(marker, self.regions)
        self.assertIn("item.provinceOnly || item.legacy", self.regions)
        self.assertIn("/crm/views/regions.js", self.index)

    def test_customer_edit_has_no_source_supplement_field(self):
        form = self.customers[
            self.customers.index("function customerFormHtml"):
            self.customers.index("function readCustomerForm")
        ]
        self.assertNotIn("来源补充", form)
        self.assertNotIn('name="source_other"', form)

    def test_dictionary_dropdowns_never_render_blank_options(self):
        self.assertIn("String(it.label", self.app)
        self.assertIn(".trim() !== ''", self.app)
        self.assertIn("if (emptyLabel)", self.app)
        self.assertNotRegex(self.leads, r"dictOptions\([^\n]*,\s*''\)")
        self.assertNotRegex(self.customers, r"dictOptions\([^\n]*,\s*''\)")

        empty_options = []
        for path in STATIC.rglob("*.js"):
            source = path.read_text(encoding="utf-8")
            for match in re.finditer(r"<option\b[^>]*>\s*</option>", source):
                empty_options.append(f"{path.relative_to(ROOT)}:{match.start()}")
        self.assertEqual(empty_options, [], "下拉框不能渲染空白选项")

    def test_region_picker_styles_are_present(self):
        for selector in (
            ".combo-control",
            ".combo-toggle",
            ".searchable-select .combo-item",
            ".searchable-select .combo-group",
        ):
            self.assertIn(selector, self.css)


if __name__ == "__main__":
    unittest.main()
