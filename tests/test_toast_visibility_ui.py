"""Regression checks that toast messages are visibly rendered."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ToastVisibilityUiTest(unittest.TestCase):
    def test_toast_sets_the_class_that_makes_it_visible(self):
        app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "app.css").read_text(encoding="utf-8")

        self.assertIn(
            "el.className = 'toast show' + (isError ? ' error' : '');",
            app,
        )
        self.assertIn(".toast.show {", css)
        self.assertIn("opacity: 1;", css)


if __name__ == "__main__":
    unittest.main()
