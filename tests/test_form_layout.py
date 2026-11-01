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
                '<form id="invalidateForm" class="invalidate-form form-grid"',
            ],
            "deals.js": [
                '<form id="dealEditForm" class="form-grid"',
                '<form id="dealLoseForm" class="form-grid"',
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

    def test_customer_and_lead_share_deal_convert_modal(self):
        self.assertIn("openDealConvertModal(source, sourceType)", self.views["shared.js"])
        self.assertIn("openDealConvertModal(lead, 'lead')", self.views["leads.js"])
        self.assertIn("openDealConvertModal(customer, 'customer')", self.views["customers.js"])
        self.assertIn("openCustomerDealModal(c)", self.views["customers.js"])
        self.assertNotIn("/deals/new?customer=", self.views["customers.js"])

    def test_deal_convert_forms_only_require_a_note(self):
        shared = self.views["shared.js"]
        deals = self.views["deals.js"]

        self.assertIn("function dealConvertFormHtml(formId", shared)
        self.assertIn("function bindDealConvertForm(form, products, onSubmit)", shared)
        self.assertIn("dealConvertFormHtml('dealConvertForm'", shared)
        self.assertIn("dealConvertFormHtml('dealNewForm'", deals)
        self.assertIn("bindDealConvertForm(form, []", shared)
        self.assertIn("bindDealConvertForm(form, []", deals)

        form_builder = shared[
            shared.index("function dealConvertFormHtml"):
            shared.index("function bindDealConvertForm")
        ]
        self.assertNotIn("productPickerHtml(products", form_builder)
        self.assertNotIn('name="product_type"', form_builder)
        self.assertNotIn("modelComboHtml", form_builder)
        self.assertIn("商机备注", form_builder)
        self.assertIn('name="note"', form_builder)
        self.assertIn("产品与报价在商机内创建", form_builder)
        self.assertNotIn('name="amount"', form_builder)
        self.assertNotIn('name="drive_type"', form_builder)

    def test_product_picker_searches_catalog_fields_and_supports_keyboard(self):
        shared = self.views["shared.js"]
        picker = shared[
            shared.index("function productSearchText"):
            shared.index("function dealConvertSourceHtml")
        ]

        for field in (
            "product.code",
            "product.name",
            "product.category",
            "product.series",
            "product.structure",
            "product.opening_mode",
            "product.config_summary",
        ):
            self.assertIn(field, picker)
        for marker in (
            'role="combobox"',
            'role="listbox"',
            "ArrowDown",
            "ArrowUp",
            "aria-activedescendant",
        ):
            self.assertIn(marker, picker)

    def test_deal_convert_search_ui_has_desktop_and_mobile_styles(self):
        for selector in (
            ".modal-content.deal-convert-modal",
            ".modal-content.deal-edit-modal",
            ".deal-convert-source",
            ".deal-convert-section",
            ".deal-product-switch-note",
            ".product-picker",
            ".product-picker-list",
            ".product-picker-option",
            ".product-picker-card",
        ):
            self.assertIn(selector, self.css)
        self.assertIn("@media (max-width: 420px)", self.css)

    def test_existing_deal_can_replace_product_from_searchable_edit_form(self):
        deals = self.views["deals.js"]
        edit = deals[
            deals.index("function openDealEdit"):
            deals.index("function openDealLose")
        ]
        for marker in (
            "关联产品 <span class=\"deal-inline-badge\">可更换</span>",
            "产品可随沟通阶段调整",
            "productPickerHtml(products || [], deal.product_id",
            "syncProductFields(product)",
            "syncProductDriveField(product, driveSelect, driveHint)",
            "productPicker.getProduct().drive_type",
            "payload.product_id = productPicker.getValue()",
        ):
            self.assertIn(marker, edit)
        self.assertNotIn("productSelectHtml(", edit)

    def test_spec_labels_are_unified(self):
        self.assertIn("洞口尺寸", self.views["deals.js"])
        self.assertNotIn("尺寸（宽×高", self.views["deals.js"])
        for filename, source in self.views.items():
            self.assertNotIn("尺寸（宽×高 mm）", source, filename)

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

    def test_product_creation_uses_generated_code_and_order_form_import(self):
        products = self.views["products.js"]
        for marker in (
            "<label>产品编码",
            "（自动生成）",
            "编号由系统分配，无需手动填写",
            "从下单表生成",
            "openProductImport(",
            "api('/products/import-preview'",
            "api('/products/import-form'",
            "productImportPreviewHtml(result)",
            "该下单表已生成过产品",
            "查看已有产品",
            "submitBtn.disabled = busy || !preview;",
        ):
            self.assertIn(marker, products)
        for selector in (
            ".product-actions",
            ".product-import-modal",
            ".product-import-preview",
            ".product-import-title",
            ".product-import-warnings",
            ".product-import-actions",
        ):
            self.assertIn(selector, self.css)
        self.assertIn("position: sticky;", self.css)


if __name__ == "__main__":
    unittest.main()
