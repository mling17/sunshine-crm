"""Regression checks for compact create/edit form layouts."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FormLayoutStructureTest(unittest.TestCase):
    def setUp(self):
        static = ROOT / "static"
        self.css = (static / "app.css").read_text(encoding="utf-8")
        self.index = (static / "index.html").read_text(encoding="utf-8")
        self.views = {
            path.name: path.read_text(encoding="utf-8").replace('\\"', '"')
            for path in (static / "views").glob("*.js")
        }

    def test_all_create_and_edit_forms_use_compact_grid(self):
        expected = {
            "customers.js": '<form class="customer-form form-grid"',
            "leads.js": [
                '<form class="lead-form form-grid"',
                '<form id="leadDealForm" class="form-grid"',
                '<form id="invalidateForm" class="invalidate-form form-grid"',
            ],
            "deals.js": [
                '<form id="dealEditForm" class="form-grid"',
                '<form id="dealLoseForm" class="form-grid"',
                '<form id="dealNewForm" class="form-grid"',
                '<form id="dealOrderForm" class="form-grid"',
            ],
            "orders.js": [
                '<form id="asNewForm" class="form-modal form-grid"',
                '<form id="shipForm" class="form-modal form-grid"',
                '<form id="depositForm" class="form-modal form-grid"',
                '<form id="balanceForm" class="form-modal form-grid"',
            ],
            "logistics.js": '<form id="carrierFormEl" class="form-grid"',
            "followups.js": '<form id="fuForm" class="form-grid"',
            "shared.js": [
                '<form id="newDealForm" class="form-grid"',
                '<form id="fuModalForm" class="form-grid"',
            ],
            "dashboard.js": '<form id="quickFuForm" class="form-grid"',
            "aftersales.js": [
                '<form id="asFollowForm" class="card form-grid"',
                '<form id="asFinishForm" class="form-grid"',
            ],
        }

        for filename, markers in expected.items():
            markers = [markers] if isinstance(markers, str) else markers
            with self.subTest(filename=filename):
                for marker in markers:
                    self.assertIn(marker, self.views[filename])

        self.assertIn('<form id="profileForm" class="modal-body form-grid"', self.index)
        self.assertIn('<form id="passwordForm" class="modal-body form-grid"', self.index)

    def test_long_fields_span_both_columns(self):
        for selector in (
            '.form-grid > .field.field-wide',
            '.form-grid > .field:has(> textarea)',
            '.form-grid > .field:has(> input[type="file"])',
            '.form-grid > .field:has(#contactRows)',
        ):
            self.assertIn(selector, self.css)

    def test_short_fields_stay_compact_on_mobile(self):
        mobile = self.css.split("@media (max-width: 640px)", 2)[-1]
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", mobile)


if __name__ == "__main__":
    unittest.main()
