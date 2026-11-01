"""Regression checks for quote-only deal amounts and shared entity follow-up pages."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DealQuoteAndFollowupUiTest(unittest.TestCase):
    def setUp(self):
        views = ROOT / "static" / "views"
        self.shared = (views / "shared.js").read_text(encoding="utf-8")
        self.leads = (views / "leads.js").read_text(encoding="utf-8")
        self.customers = (views / "customers.js").read_text(encoding="utf-8")
        self.deals = (views / "deals.js").read_text(encoding="utf-8")
        self.orders = (views / "orders.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static" / "app.css").read_text(encoding="utf-8")

    def test_leads_customers_and_deals_share_followup_timeline_adapter(self):
        self.assertIn("function followupRecordsFromApi(records)", self.shared)
        for source in (self.leads, self.customers, self.deals):
            self.assertIn("followupRecordsFromApi(", source)

    def test_customer_and_deal_details_use_shared_followup_page(self):
        customer_detail = self.customers[
            self.customers.index("function viewCustomerDetail"):
        ]
        deal_detail = self.deals[
            self.deals.index("function viewDealDetail"):
            self.deals.index("function openDealEdit")
        ]
        for source in (customer_detail, deal_detail):
            self.assertIn("renderEntityFollowPage(root", source)
            self.assertIn("fd.append('object_type'", source)
            self.assertIn("fd.append('method'", source)
            self.assertIn("fd.append('next_date'", source)
            self.assertIn("fd.append('files'", source)

    def test_deal_edit_only_contains_quote_amount(self):
        edit = self.deals[
            self.deals.index("function openDealEdit"):
            self.deals.index("function openDealLose")
        ]
        self.assertIn("<label>报价金额 *</label>", edit)
        self.assertNotIn('name="deposit"', edit)
        self.assertNotIn('name="balance"', edit)
        self.assertNotIn("deposit: numOrNull", edit)
        self.assertNotIn("balance: numOrNull", edit)

    def test_order_modal_separates_product_discount_and_freight(self):
        order_modal = self.deals[
            self.deals.index("function openDealOrderModal"):
        ]
        self.assertIn("<label>产品合计</label>", order_modal)
        self.assertIn("<label>整单优惠</label>", order_modal)
        self.assertIn("<label>优惠后产品应收</label>", order_modal)
        self.assertIn("<label>运费（我方收取）</label>", order_modal)
        self.assertIn("<label>订单应收</label>", order_modal)
        self.assertIn("<label>定金（第一笔）*</label>", order_modal)
        self.assertIn("优惠只减产品合计，运费单独计入订单应收", order_modal)
        self.assertIn("Math.round(receivable * 100) / 100", order_modal)
        self.assertNotIn("amount: amount,", order_modal)

    def test_order_modal_uses_confirmed_quote_thumbnails(self):
        order_modal = self.deals[
            self.deals.index("function openDealOrderModal"):
        ]
        self.assertIn('class="order-quote-gallery"', order_modal)
        self.assertIn('class="order-quote-preview"', order_modal)
        self.assertIn("item.form_preview_url", order_modal)
        self.assertIn('data-img="', order_modal)
        self.assertIn("点击查看报价单大图", order_modal)
        self.assertIn("报价单缩略图暂不可用", order_modal)
        self.assertNotIn("<h3>产品明细</h3>", order_modal)

    def test_order_modal_uses_grouped_responsive_form_layout(self):
        order_modal = self.deals[
            self.deals.index("function openDealOrderModal"):
        ]
        for marker in (
            '<form id="dealOrderForm" class="order-form"',
            '<section class="order-quote-summary">',
            '<section class="order-form-section">',
            '<h4>金额与定金</h4>',
            '<h4>物流与收货</h4>',
            '<h4>订单备注</h4>',
            'class="order-money-grid"',
            'class="order-payment-grid"',
            'class="order-shipping-grid"',
            'class="order-address-grid"',
            'class="form-actions order-form-actions"',
        ):
            self.assertIn(marker, order_modal)
        for marker in (
            ".deal-order-modal .order-money-grid {",
            ".deal-order-modal .order-payment-grid,",
            ".deal-order-modal .order-shipping-grid,",
            ".deal-order-modal .order-address-grid {",
            ".deal-order-modal .order-form-actions {",
            "@media (max-width: 720px)",
            "@media (max-width: 640px)",
        ):
            self.assertIn(marker, self.css)

    def test_order_money_inputs_do_not_step_with_mouse(self):
        order_modal = self.deals[
            self.deals.index("function openDealOrderModal"):
        ]
        self.assertGreaterEqual(
            order_modal.count('class="order-money-input is-editable"'),
            3,
            "优惠、运费和定金都应是价格输入框",
        )
        self.assertIn("input.addEventListener('wheel'", order_modal)
        self.assertIn("ev.preventDefault()", order_modal)
        self.assertIn("input.blur()", order_modal)
        self.assertIn("ev.key === 'ArrowUp' || ev.key === 'ArrowDown'", order_modal)
        self.assertIn(".order-money-input::-webkit-inner-spin-button", self.css)
        self.assertIn("appearance: textfield", self.css)

    def test_deal_list_and_customer_deal_cards_do_not_prefill_deposit(self):
        deal_items = self.shared[
            self.shared.index("function dealItemHtml"):
            self.shared.index("function aftersaleTypeLabel")
        ]
        self.assertIn("报价金额", self.deals)
        self.assertNotIn("deal.deposit", deal_items)
        self.assertNotIn("deal.balance", deal_items)

    def test_deal_items_and_customer_confirmation_are_wired(self):
        self.assertIn("function openDealItemModal", self.deals)
        self.assertIn("function dealItemsCardHtml", self.deals)
        self.assertIn("/items", self.deals)
        self.assertIn("showCustomerConfirmModal", self.orders)
        self.assertIn("/confirm", self.orders)
        self.assertIn("客户通过微信查看下单表", self.orders)

    def test_quotation_upload_preview_and_followup_link_are_wired(self):
        for marker in (
            "function quoteCardsHtml",
            "function quoteFormPreviewHtml",
            "function openQuoteItemModal",
            "function openQuoteConfirmModal",
            'name="form_file"',
            "quotes/form-preview",
            "recognized_total",
            "quoteFormPreview",
            "<label>报价金额 *</label>",
            "quote-form-thumbnail",
            "data-quote-confirm",
            "data-quote-send",
            "data-quote-requote",
            "data-quote-void",
            "data-quote-delete",
            "data-quote-order",
            "quote-card",
            "deal-quote-list",
            "deal-quote-empty",
            "/quotes/items/",
        ):
            self.assertIn(marker, self.deals)
        self.assertIn("opts.followExtraHtml", self.shared)
        self.assertIn("重新报价", self.deals)
        self.assertIn("/requote", self.deals)
        self.assertIn("timelineQuoteDetailHtml", self.shared)
        self.assertIn("下单表内容缩略图", self.shared)
        self.assertIn("data-deal-tag-add", self.deals)
        self.assertIn("data-deal-tag-remove", self.deals)
        self.assertNotIn("下载产品模板", self.deals)
        self.assertIn("payload.quote_id", self.shared)
        self.assertIn('name="quote_id"', self.deals)
        quote_cards = self.deals[
            self.deals.index("function quoteCardsHtml"):
            self.deals.index("function dealTagsHtml")
        ]
        self.assertLess(
            quote_cards.index('data-quote-delete="'),
            quote_cards.index("</summary>"),
            "删除按钮应位于报价单卡片标题层级，而不是卡片明细操作区",
        )
        self.assertIn('class="deal-quote-card-delete"', quote_cards)
        self.assertIn('aria-label="删除报价单 ', quote_cards)
        self.assertIn('<span aria-hidden="true">×</span>', quote_cards)
        self.assertIn(
            "quote.status === 'draft' || quote.status === 'void'",
            quote_cards,
        )
        delete_binding = self.deals[
            self.deals.index("$$('[data-quote-delete]'"):
            self.deals.index("$$('[data-quote-order]'")
        ]
        self.assertIn("ev.stopPropagation()", delete_binding)
        quote_form = self.deals[
            self.deals.index("function openQuoteItemModal"):
            self.deals.index("function openQuoteConfirmModal")
        ]
        self.assertNotIn("识别依据", quote_form)

    def test_deal_page_uses_quote_cards_and_priority_actions(self):
        detail = self.deals[
            self.deals.index("function viewDealDetail"):
            self.deals.index("function openDealEdit")
        ]
        self.assertNotIn("infoHtml: infoGrid([", detail)
        self.assertIn("hideEntityCard: true", detail)
        self.assertIn("beforeTimelineHtml: dealOverviewHtml", detail)
        self.assertIn("报价单名称 *", self.deals)

    def test_deal_layout_matches_quote_wireframe(self):
        overview = self.deals[
            self.deals.index("function dealOverviewHtml"):
            self.deals.index("function bindQuoteActions")
        ]
        self.assertIn('class="deal-overview-head"', overview)
        self.assertIn('class="deal-overview-name"', overview)
        self.assertIn('class="deal-overview-status"', overview)
        self.assertIn("dealTagsHtml(deal, quotes)", overview)
        self.assertNotIn("(noteText ?", overview)
        self.assertIn('class="deal-overview-actions"', overview)
        self.assertIn("＋ 添加报价单", overview)
        self.assertIn(">生成订单</button>", overview)
        self.assertIn(">标记流失</button>", overview)
        self.assertIn("dealTagsHtml(deal, quotes)", overview)
        self.assertIn("addQuoteAction +", overview)
        self.assertIn("orderAction + loseAction", overview)
        self.assertNotIn("编辑备注", overview)
        self.assertNotIn("deal-overview-note", overview)

        for marker in (
            ".deal-overview {",
            ".deal-tags {",
            ".deal-tag-auto {",
            ".deal-tag-manual {",
            ".deal-tag-add {",
            ".deal-quote-list {",
            "display: flex;",
            ".deal-quote-empty {",
            ".deal-overview-actions {",
            ".deal-quote-card-delete {",
            "opacity: 0;",
            "pointer-events: none;",
            ".deal-quote-card:hover .deal-quote-card-delete,",
            ".deal-quote-card:focus-within .deal-quote-card-delete {",
            "@media (hover: none) {",
        ):
            self.assertIn(marker, self.css)
        self.assertIn("线索将移出线索池", self.shared)
        self.assertIn("确定创建商机", self.shared)

    def test_add_quote_is_disabled_when_a_quote_is_pending_or_confirmed(self):
        overview = self.deals[
            self.deals.index("function dealOverviewHtml"):
            self.deals.index("function bindQuoteActions")
        ]
        self.assertIn(
            "quote.status === 'pending' || quote.status === 'confirmed'",
            overview,
        )
        self.assertIn(
            "deal.stage !== 'lost' && !hasPendingOrConfirmedQuote",
            overview,
        )
        self.assertIn(
            'title="已有待客户确认或客户已确认的报价单，或商机已关闭"',
            overview,
        )

    def test_quote_action_colors_are_not_overridden_by_neutral_buttons(self):
        neutral = (
            ".btn:not(.btn-primary):not(.btn-danger):not(.btn-success)"
            ":not(.btn-warning):not(.btn-outline-danger)"
        )
        for marker in (
            ".btn-success {",
            ".btn-warning {",
            ".btn-outline-danger {",
            neutral,
        ):
            self.assertIn(marker, self.css)


if __name__ == "__main__":
    unittest.main()
