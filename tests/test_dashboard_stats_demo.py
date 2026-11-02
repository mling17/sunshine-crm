"""工作台 / 统计交互 Demo 的静态完整性检查。"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "static" / "demo" / "dashboard-stats-preview"


class DashboardStatsDemoTest(unittest.TestCase):
    def test_demo_files_exist(self):
        self.assertTrue((DEMO / "index.html").is_file())
        self.assertTrue((DEMO / "styles.css").is_file())
        self.assertTrue((DEMO / "app.js").is_file())

    def test_demo_contains_both_pages_and_required_interactions(self):
        html = (DEMO / "index.html").read_text(encoding="utf-8")
        script = (DEMO / "app.js").read_text(encoding="utf-8")
        styles = (DEMO / "styles.css").read_text(encoding="utf-8")

        self.assertIn('data-page="dashboard"', html)
        self.assertIn('data-page="stats"', html)
        self.assertIn('id="moneyToggle"', html)

        for range_key in ("month", '"3m"', '"6m"', "year"):
            self.assertIn(range_key, script)
        self.assertIn('"7d"', script)
        self.assertIn("openFollowupModal", script)
        self.assertIn("renderSources", script)
        self.assertIn("renderFunnel", script)
        self.assertIn("renderTrendCombo", script)
        self.assertIn("renderDonut", script)
        self.assertIn("renderStageSteps", script)
        self.assertIn("renderOrderPipeline", script)
        self.assertIn("renderAftersales", script)
        self.assertIn("昨日新增与跟进", script)
        self.assertIn("yesterdayActivity", script)
        self.assertIn("newCount", script)
        self.assertIn("yesterday-card", styles)
        self.assertIn(".yesterday-grid", styles)

        self.assertNotIn("snapshot-row", script)
        self.assertNotIn("snapshotItem", script)
        self.assertNotIn("本月快照", script)
        self.assertNotIn("snapshot-row", styles)

        self.assertIn("@media (max-width: 760px)", styles)
        self.assertIn("prefers-reduced-motion", styles)


class ProductionDashboardStatsTest(unittest.TestCase):
    def test_production_views_and_scoped_styles_are_wired(self):
        dashboard = (ROOT / "static" / "views" / "dashboard.js").read_text(encoding="utf-8")
        stats = (ROOT / "static" / "views" / "stats.js").read_text(encoding="utf-8")
        styles = (ROOT / "static" / "dashboard-stats.css").read_text(encoding="utf-8")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("昨日新增与跟进", dashboard)
        self.assertIn("recent_aftersales", dashboard)
        self.assertIn("ds-work-grid", dashboard)
        self.assertIn("data-stat-range", stats)
        self.assertIn('"7d", "近7天"', stats)
        self.assertIn("/stats?range=", stats)
        self.assertIn("dashboard-stats.css", html)
        self.assertIn(".ds-page", styles)
        self.assertIn("@media (max-width: 760px)", styles)
        self.assertIn("prefers-reduced-motion", styles)


if __name__ == "__main__":
    unittest.main()
