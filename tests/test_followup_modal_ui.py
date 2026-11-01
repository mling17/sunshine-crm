"""Regression checks for the polished shared follow-up modal."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FollowupModalUiTest(unittest.TestCase):
    def setUp(self):
        self.shared = (ROOT / "static" / "views" / "shared.js").read_text(
            encoding="utf-8"
        )
        self.css = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
        self.modal = self.shared[
            self.shared.index("function openFollowModal"):
            self.shared.index("function renderEntityFollowPage")
        ]

    def test_followup_modal_has_clear_visual_hierarchy(self):
        for marker in (
            'class="modal-content followup-modal"',
            'class="followup-modal-heading"',
            'class="followup-label-line"',
            'class="row-2 followup-options"',
            'class="field followup-option-card"',
            'class="field followup-option-card followup-schedule"',
            'class="followup-date-control"',
            'class="form-actions followup-actions"',
        ):
            self.assertIn(marker, self.modal)

    def test_next_followup_toggle_is_accessible_and_synchronizes_state(self):
        for marker in (
            'class="next-followup-toggle"',
            "aria-label=\"安排下次跟进\"",
            "nextDate.disabled = !nextOn.checked",
            "schedule.classList.toggle('is-off', !nextOn.checked)",
            "本次不再安排跟进提醒",
        ):
            self.assertIn(marker, self.modal)
        self.assertNotIn("nextDate.style.opacity", self.modal)

    def test_followup_modal_styles_are_responsive(self):
        for selector in (
            ".modal-content.followup-modal",
            ".followup-modal-heading",
            ".followup-option-card",
            ".next-followup-toggle input:checked + .next-followup-track",
            ".followup-schedule.is-off",
            ".followup-date-control",
            ".followup-actions",
            "@media (max-width: 560px)",
        ):
            self.assertIn(selector, self.css)


if __name__ == "__main__":
    unittest.main()
