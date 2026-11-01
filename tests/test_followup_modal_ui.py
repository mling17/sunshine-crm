"""Regression checks for the compact shared follow-up modal."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FollowupModalUiTest(unittest.TestCase):
    def setUp(self):
        self.shared = (ROOT / "static" / "views" / "shared.js").read_text(
            encoding="utf-8"
        )
        self.modal = self.shared[
            self.shared.index("function openFollowModal"):
            self.shared.index("function renderEntityFollowPage")
        ]

    def test_checkbox_precedes_the_next_followup_label(self):
        self.assertIn('class="label-with-switch label-with-checkbox"', self.modal)
        self.assertIn(
            '<span class="switch"><input type="checkbox" id="fuNextOn" checked>',
            self.modal,
        )
        self.assertIn("<span>下次跟进时间</span>", self.modal)
        self.assertLess(
            self.modal.index("id=\"fuNextOn\""),
            self.modal.index("下次跟进时间"),
        )

    def test_standalone_need_label_is_removed(self):
        self.assertNotIn("<span>需要</span>", self.modal)
        self.assertIn("nextDate.disabled = !nextOn.checked", self.modal)

    def test_quote_field_precedes_next_followup_time(self):
        extra_html = self.modal.index("(opts.extraHtml || '')")
        next_followup = self.modal.index("下次跟进时间")
        self.assertLess(self.modal.index('name="method"'), extra_html)
        self.assertLess(extra_html, next_followup)
        self.assertIn('class="field followup-schedule-field"', self.modal)


if __name__ == "__main__":
    unittest.main()
