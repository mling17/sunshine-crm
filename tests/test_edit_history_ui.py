"""Static checks that edit history is visible on customer follow-up pages."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EditHistoryUiTest(unittest.TestCase):
    def test_customer_detail_loads_and_renders_shared_followup_history(self):
        view = (ROOT / "static/views/customers.js").read_text(encoding="utf-8")
        shared = (ROOT / "static/views/shared.js").read_text(encoding="utf-8")

        self.assertIn("include_system=true", view)
        self.assertIn("followupRecordsFromApi(", view)
        self.assertIn("renderEntityFollowPage(root", view)
        self.assertIn("change: { label: '编辑'", shared)


if __name__ == "__main__":
    unittest.main()
