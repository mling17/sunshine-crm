"""订单详情页布局与信息层级静态校验。"""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OrderDetailUiTest(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "static/views/orders.js").read_text(encoding="utf-8")
        self.deals = (ROOT / "static/views/deals.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/order-detail.css").read_text(encoding="utf-8")
        self.index = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.sw = (ROOT / "static/sw.js").read_text(encoding="utf-8")

    def test_order_overview_uses_wireframe_information_order(self):
        detail = self.source[
            self.source.index("function renderOrderDetail"):
            self.source.index("/* ---------------- 修改订单")
        ]
        for marker in (
            'class="card order-command-card"',
            "订单金额",
            "售后数量",
            "物流方式",
            "order-tags-row",
            "商机状态",
            "关联商机",
            "报价单",
            "关联产品",
            "发货日期",
            "运单号",
        ):
            self.assertIn(marker, detail)
        self.assertIn("afterSaleCount", detail)
        self.assertLess(detail.index("订单金额"), detail.index("物流方式"))
        self.assertLess(detail.index("物流方式"), detail.index("商机状态"))
        self.assertEqual(
            detail.count('<div class="order-metric">') +
            detail.count('<div class="order-metric '),
            5,
        )
        self.assertEqual(detail.count('class="order-context"'), 5)
        self.assertEqual(detail.count('class="order-logistics-fact"'), 5)
        self.assertNotIn("order-tags-label", detail)
        self.assertNotIn(">标签<", detail)
        self.assertNotIn('<span class="badge ok">客户已确认</span>', detail)
        self.assertLess(
            detail.index('class="order-command-no"'),
            detail.index('class="order-tags-row"'),
        )
        self.assertIn("flex: 0 1 auto;", self.css)

    def test_after_sale_metric_and_section_are_conditional(self):
        detail = self.source[
            self.source.index("function renderOrderDetail"):
            self.source.index("/* ---------------- 修改订单")
        ]
        self.assertIn("var afterSaleCount = aftersales.length;", detail)
        self.assertIn("(afterSaleCount", detail)
        self.assertIn("var aftersalesHtml = afterSaleCount ?", detail)
        self.assertNotIn("暂无售后单", detail)
        self.assertLess(
            detail.index('id="orderPrimaryActions"'),
            detail.index("var actionHost"),
        )

    def test_completed_order_uses_aftersale_followup_and_locked_tags(self):
        detail = self.source[
            self.source.index("function renderOrderDetail"):
            self.source.index("/* ---------------- 修改订单")
        ]
        self.assertIn("order.status === 'completed'", detail)
        self.assertIn("后续跟进请创建售后单", detail)
        self.assertIn(
            "orderTagsHtml(deal, order.status === 'completed')",
            detail,
        )
        self.assertNotIn(
            'disabled title="订单完成后才能申请售后">添加售后',
            detail,
        )
        self.assertEqual(
            detail.count("order.status !== 'completed'"),
            2,
            "完成订单不再显示跟进、修改订单按钮",
        )
        self.assertLess(
            detail.index("售后数量 ' + afterSaleCount"),
            detail.index("orderTagsHtml(deal, order.status === 'completed')"),
            "售后数量必须排在订单标签前",
        )

        tags = self.source[
            self.source.index("function orderTagsHtml"):
            self.source.index("function orderFollowModal")
        ]
        self.assertIn("tag.deletable && !locked", tags)
        self.assertIn("(!locked", tags)

    def test_add_aftersale_modal_can_link_same_order_history(self):
        modal = self.source[
            self.source.index("function openAftersaleModal"):
            self.source.index("/* ---------------- 通用状态推进")
        ]
        self.assertIn("openAftersaleModal(order, aftersales)", self.source)
        self.assertIn("关联历史售后（可选）", modal)
        self.assertIn('name="related_aftersale_id"', modal)
        self.assertIn("related_aftersale_id: relatedId", modal)
        self.assertIn("a.status === 'done'", modal)
        self.assertIn("只能关联当前订单下已完成的历史售后单", modal)

    def test_logistics_handles_carrier_and_self_pickup(self):
        detail = self.source[
            self.source.index("function renderOrderDetail"):
            self.source.index("/* ---------------- 修改订单")
        ]
        self.assertIn("var isSelfPickup = order.logistics_mode === 'self';", detail)
        self.assertIn("客户自提", detail)
        self.assertIn("order.carrier_contact_name", detail)
        self.assertIn("order.carrier_contact_phone", detail)
        self.assertIn("record.type === 'ship'", detail)

    def test_order_history_reuses_unified_timeline_and_allows_follow_up(self):
        detail = self.source[
            self.source.index("function renderOrderDetail"):
            self.source.index("/* ---------------- 修改订单")
        ]
        self.assertIn("var timelineRecords = orderTimelineRecords(order);", detail)
        self.assertIn("<h2>跟进履历", detail)
        self.assertIn("timelineHtml(timelineRecords)", detail)
        self.assertIn("function orderTimelineContent", self.source)
        self.assertIn("ORDER_CHANGE_LABELS", self.source)
        self.assertNotIn("<h2>状态历史", detail)
        self.assertIn("btnOrderFollow", detail)
        self.assertIn("openFollowModal", self.source)
        self.assertIn("fd.append('object_type', 'order');", self.source)
        self.assertIn("api('/follow-ups'", self.source)

    def test_quote_amount_logistics_aftersales_history_and_files_order(self):
        detail = self.source[
            self.source.index("function renderOrderDetail"):
            self.source.index("/* ---------------- 修改订单")
        ]
        sections = (
            "<h2>报价单明细",
            "<h2>订单金额及收付款",
            "<h2>物流信息",
            "<h2>跟进履历",
            "filesCardHtml(files",
        )
        positions = [detail.index(marker) for marker in sections]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(detail.index("aftersalesHtml"), detail.index("historyHtml"))
        self.assertLess(detail.index("historyHtml"), detail.index("documentsHtml"))

    def test_order_detail_styles_and_cache_versions_are_wired(self):
        for marker in (
            ".order-command-card {",
            ".order-metrics {",
            ".order-context-grid {",
            ".order-logistics-strip {",
            ".order-payment-grid {",
            "@media (max-width: 640px)",
        ):
            self.assertIn(marker, self.css)
        self.assertIn('/crm/order-detail.css?v=20261103a3', self.index)
        self.assertIn("'/crm/order-detail.css'", self.sw)
        self.assertIn("const CACHE = 'crm-shell-v63';", self.sw)
        self.assertGreaterEqual(self.css.count("grid-template-columns: repeat(5,"), 3)

    def test_pending_customer_confirmation_is_not_a_frontend_state(self):
        self.assertIn("return item[0] !== 'pending_confirmation';", self.source)
        self.assertIn("return status === 'pending_confirmation' ? 'pending_payment' : status;", self.source)
        self.assertNotIn("showCustomerConfirmModal", self.source)
        self.assertNotIn("记录客户确认", self.source)
        self.assertNotIn('class="order-confirmation-note"', self.source)
        self.assertNotIn(".order-confirmation-note", self.css)

    def test_confirmed_quote_has_no_void_action(self):
        quote_cards = self.deals[
            self.deals.index("function quoteCardsHtml"):
            self.deals.index("function dealTagsHtml")
        ]
        self.assertIn(
            "(quote.status === 'draft' || quote.status === 'pending')",
            quote_cards,
        )
        self.assertNotIn("quote.status !== 'void'", quote_cards)


if __name__ == "__main__":
    unittest.main()
