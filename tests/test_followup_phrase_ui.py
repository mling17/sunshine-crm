"""跟进常用短语交互与分对象接入的静态回归。"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FollowupPhraseUiTest(unittest.TestCase):
    def setUp(self):
        self.shared = (ROOT / "static/views/shared.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")
        self.index = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.sw = (ROOT / "static/sw.js").read_text(encoding="utf-8")

    def test_modal_shows_phrase_panel_before_content(self):
        modal = self.shared[
            self.shared.index("function openFollowModal"):
            self.shared.index("function renderEntityFollowPage")
        ]
        self.assertIn("followPhrasePanelHtml(opts.objectType)", modal)
        self.assertLess(
            modal.index("followPhrasePanelHtml(opts.objectType)"),
            modal.index("<label>跟进内容 *</label>"),
        )
        self.assertIn("bindFollowPhrasePanel(", modal)
        self.assertIn("opts.objectType", modal)

    def test_phrase_panel_loads_inserts_adds_and_deletes(self):
        phrases = self.shared[
            self.shared.index("function followPhrasePanelHtml"):
            self.shared.index("function openFollowModal")
        ]
        for marker in (
            "/follow-up-phrases?object_type=",
            "method: 'POST'",
            "method: 'DELETE'",
            "textarea.setSelectionRange(caret, caret)",
            "data-phrase-delete",
            "window.confirm",
            "aria-expanded",
            "短语加载失败",
        ):
            self.assertIn(marker, phrases)

    def test_all_five_business_pages_supply_their_phrase_set(self):
        expected = {
            "leads.js": "objectType: 'lead'",
            "customers.js": "objectType: 'customer'",
            "deals.js": "objectType: 'deal'",
            "orders.js": "objectType: 'order'",
            "aftersales.js": "objectType: 'aftersale'",
        }
        for filename, marker in expected.items():
            source = (ROOT / "static" / "views" / filename).read_text(encoding="utf-8")
            self.assertIn(marker, source, f"{filename} 未接入自己的短语集")

    def test_phrase_chips_wrap_instead_of_clipping_long_text(self):
        panel = self.css[
            self.css.index("/* ================= 跟进常用短语"):
        ]
        self.assertIn(".follow-phrase-chips", panel)
        self.assertIn("flex-wrap: wrap", panel)
        self.assertIn("overflow-wrap: anywhere", panel)
        self.assertIn("grid-column: 1 / -1", panel)

    def test_asset_versions_are_bumped_for_phrase_panel(self):
        self.assertIn("/crm/views/shared.js?v=20261103a1", self.index)
        self.assertIn("/crm/app.css?v=20261103a1", self.index)
        self.assertIn("const CACHE = 'crm-shell-v59';", self.sw)


if __name__ == "__main__":
    unittest.main()
