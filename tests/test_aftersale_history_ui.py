"""售后历史关联、跟进记录与完成锁定页面的静态校验。"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AftersaleHistoryUiTest(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "static/views/aftersales.js").read_text(encoding="utf-8")
        self.index = (ROOT / "static/index.html").read_text(encoding="utf-8")

    def test_aftersale_detail_shows_follow_history_and_relation(self):
        detail = self.source[
            self.source.index("function viewAftersaleDetail"):
            self.source.index("function openAftersaleFinish")
        ]
        self.assertIn("object_type=aftersale", detail)
        self.assertIn("关联历史售后", detail)
        self.assertIn("related_aftersale_no", detail)
        self.assertIn("renderEntityFollowPage(root", detail)
        self.assertIn("openFollowModal", (ROOT / "static/views/shared.js").read_text(encoding="utf-8"))
        self.assertIn("include_system=true", detail)

    def test_status_tabs_match_three_state_flow(self):
        self.assertIn("['pending', '待处理']", self.source)
        self.assertIn("['processing', '处理中']", self.source)
        self.assertIn("['done', '已完成']", self.source)
        self.assertNotIn("['rejected', '已拒绝']", self.source)

    def test_processing_can_finish_and_done_is_read_only(self):
        detail = self.source[
            self.source.index("function viewAftersaleDetail"):
            self.source.index("function openAftersaleFinish")
        ]
        self.assertIn("id=\"asFinish\"", detail)
        self.assertIn("已完成：售后单已锁定，只能查看", detail)
        self.assertNotIn("id=\"asFollowForm\"", detail)
        self.assertIn("canFollow: !finished", detail)

    def test_script_cache_version_bumped(self):
        self.assertIn("/crm/views/orders.js?v=20261109order-name1", self.index)
        self.assertIn("/crm/views/aftersales.js?v=20261104lead1", self.index)


if __name__ == "__main__":
    unittest.main()
