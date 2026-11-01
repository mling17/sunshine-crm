"""
CRM V2 字典功能测试。
"""
import os
import tempfile
import unittest

from tests._util import ApiTestCase

from app.dicts import (
    DICT_REGISTRY,
    DICT_SEEDS,
    items,
    label_map,
    level,
    validate,
    used_count,
)


class TestDicts(unittest.TestCase):
    """字典功能测试"""
    
    def setUp(self):
        """测试前准备"""
        # 设置测试数据库路径
        self.test_db = tempfile.mktemp(suffix='.db')
        os.environ['CRM_DB'] = self.test_db
        
    def tearDown(self):
        """测试后清理"""
        # 清理测试数据库
        if os.path.exists(self.test_db):
            os.unlink(self.test_db)
    
    def test_dict_registry_complete(self):
        """测试字典注册表完整性"""
        # 检查所有12个字典都存在
        self.assertEqual(len(DICT_REGISTRY), 12)
        
        # 检查关键字典
        expected_keys = {
            "product_model", "customer_source", "intent_level", "product_type",
            "lost_reason", "aftersale_type", "follow_method", "deal_stage",
            "order_status", "aftersale_status", "customer_type", "follow_object"
        }
        self.assertEqual(set(DICT_REGISTRY.keys()), expected_keys)
        
        # 检查各字典级别
        self.assertEqual(DICT_REGISTRY["deal_stage"]["level"], "B")
        self.assertEqual(DICT_REGISTRY["product_model"]["level"], "A")
        self.assertEqual(DICT_REGISTRY["follow_object"]["level"], "D")
        self.assertEqual(DICT_REGISTRY["product_type"]["name"], "产品分类")
        self.assertIn("products.category", DICT_REGISTRY["product_type"]["table"])
    
    def test_dict_seeds_complete(self):
        """测试字典种子数据完整性"""
        # 检查种子数据完整性
        self.assertIn("product_model", DICT_SEEDS)
        self.assertIn("customer_source", DICT_SEEDS)
        self.assertIn("intent_level", DICT_SEEDS)
        self.assertIn("product_type", DICT_SEEDS)
        self.assertIn("lost_reason", DICT_SEEDS)
        self.assertIn("aftersale_type", DICT_SEEDS)
        self.assertIn("follow_method", DICT_SEEDS)
        self.assertIn("deal_stage", DICT_SEEDS)
        self.assertIn("order_status", DICT_SEEDS)
        self.assertIn("aftersale_status", DICT_SEEDS)
        self.assertIn("customer_type", DICT_SEEDS)
        self.assertIn("follow_object", DICT_SEEDS)
        customer_types = {item["key"]: item["label"] for item in DICT_SEEDS["customer_type"]}
        self.assertEqual(customer_types.get("other"), "其他")
        
        # 检查产品型号种子数据
        product_models = DICT_SEEDS["product_model"]
        self.assertGreater(len(product_models), 20)
        xw60 = [m for m in product_models if m["key"] == "XW-60"]
        self.assertEqual(len(xw60), 1, "产品型号 XW-60 必须存在且唯一")
        self.assertEqual(xw60[0]["label"], "XW-60 天窗 600×1200")
        self.assertEqual(xw60[0]["meta"]["size"], "600×1200", "型号必须带出尺寸")

        product_types = {item["key"] for item in DICT_SEEDS["product_type"]}
        self.assertTrue(
            {"天窗", "天幕", "开合屋面", "纱窗", "遮阳", "配件"}.issubset(product_types),
            "产品主档实际使用的分类都必须进入数据字典",
        )

        sources = {item["key"]: item["label"] for item in DICT_SEEDS["customer_source"]}
        self.assertEqual(sources["video_account"], "视频号")
        self.assertEqual(sources["xianyu"], "咸鱼")
        
    def test_items_function(self):
        """测试 items 函数"""
        # 测试降级到种子数据
        result = items("deal_stage")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 4)
        
        # 检查返回格式
        item = result[0]
        self.assertIn("key", item)
        self.assertIn("label", item)
        self.assertIn("sort", item)
        self.assertIn("enabled", item)
        self.assertIn("used", item)
        
    def test_label_map_function(self):
        """测试 label_map 函数"""
        # 测试降级到种子数据
        result = label_map("deal_stage")
        self.assertIsInstance(result, dict)
        self.assertIn("quote", result)
        self.assertEqual(result["quote"], "报价")
        
    def test_validate_function(self):
        """测试 validate 函数"""
        # 测试存在的项
        self.assertTrue(validate("deal_stage", "quote"))
        self.assertTrue(validate("deal_stage", "won"))
        
        # 测试不存在的项
        self.assertFalse(validate("deal_stage", "nonexistent"))
        
        # 测试不存在的字典
        self.assertFalse(validate("nonexistent_dict", "test"))
    
    def test_used_count_function(self):
        """used_count 必须实时统计业务表引用数（不是种子里的假数字）"""
        self.assertEqual(used_count("deal_stage", "lost"), 0, "没人用的阶段应为 0")
        self.assertIsInstance(used_count("deal_stage", "quote"), int)
        
    def test_level_function(self):
        """测试 level 函数"""
        self.assertEqual(level("deal_stage"), "B")
        self.assertEqual(level("product_model"), "A")
        self.assertEqual(level("follow_object"), "D")
        self.assertEqual(level("nonexistent"), "D")
    
    def test_product_model_search(self):
        """测试产品型号搜索功能"""
        # 从种子数据中获取产品型号
        product_models = items("product_model")
        self.assertGreater(len(product_models), 20)
        
        # 测试搜索功能
        filtered_models = [m for m in product_models if "XW" in m["label"]]
        self.assertGreater(len(filtered_models), 0)
        
        # 检查元数据
        first_model = product_models[0]
        self.assertIn("meta", first_model)
        self.assertIn("product", first_model["meta"])
        self.assertIn("size", first_model["meta"])
        self.assertIn("drive", first_model["meta"])


class DictHttpTest(ApiTestCase):
    """字典的 HTTP 行为（R1 断言表 A17–A20 的可执行版本）。"""

    def test_new_default_sources_are_usable(self):
        sources = ["video_account", "xianyu"]
        for index, source in enumerate(sources):
            cust = self.client.post(
                "/api/crm/customers",
                json={"name": f"新来源客户{index}", "source": source},
            )
            self.assertEqual(cust.status_code, 200, cust.text)
            self.assertEqual(cust.json()["source"], source)

    def test_add_source_immediately_usable(self):
        created = self.client.post(
            "/api/crm/dicts/customer_source/items",
            json={"key": "douyin", "label": "抖音", "sort": 7},
        )
        self.assertEqual(created.status_code, 200, created.text)
        items = self.client.get("/api/crm/dicts/customer_source").json()["items"]
        self.assertIn("douyin", [i["key"] for i in items])
        # 新建客户可以直接用这个来源（字典校验放行）
        cust = self.client.post("/api/crm/customers", json={"name": "抖音客户", "source": "douyin"})
        self.assertEqual(cust.status_code, 200, cust.text)

    def test_rename_propagates_to_output_labels(self):
        """A18 后半：改字典显示名，出参 *_label 必须跟着变（R1 M1）"""
        c = self.create_customer(name="改名客户")
        deal = self.create_deal(c["id"], amount=500.0, drive_type="manual")
        self.client.put(f"/api/crm/deals/{deal['id']}", json={"stage": "confirm"})
        self.assertEqual(
            self.client.get(f"/api/crm/deals/{deal['id']}").json()["stage_label"], "待客户确认"
        )

        renamed = self.client.put(
            "/api/crm/dicts/deal_stage/items/confirm", json={"label": "等待客户拍板"}
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)

        detail = self.client.get(f"/api/crm/deals/{deal['id']}").json()
        self.assertEqual(detail["stage_label"], "等待客户拍板", "字典改名必须作用到出参")
        rows = self.client.get("/api/crm/deals").json()
        self.assertEqual([r["stage_label"] for r in rows if r["id"] == deal["id"]], ["等待客户拍板"])

    def test_status_and_type_labels_follow_dict(self):
        created = self.client.post(
            "/api/crm/dicts/aftersale_type/items", json={"key": "install", "label": "安装返工", "sort": 9}
        )
        self.assertEqual(created.status_code, 200, created.text)
        items = self.client.get("/api/crm/dicts/aftersale_type").json()["items"]
        self.assertIn("install", [i["key"] for i in items])

    def test_delete_referenced_item_conflict(self):
        self.client.post(
            "/api/crm/dicts/customer_source/items", json={"key": "douyin2", "label": "抖音", "sort": 8}
        )
        for i in range(3):
            self.client.post(
                "/api/crm/customers", json={"name": f"抖音客户{i}", "source": "douyin2"}
            )
        resp = self.client.delete("/api/crm/dicts/customer_source/items/douyin2")
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["code"], "dict_item_in_use")
        self.assertIn("3", resp.json()["detail"], "提示里要带被引用条数")

    def test_level_field_permissions(self):
        """R1 M2：C 只能改名；B 只能改名+排序；越权 403"""
        c_type = self.client.put("/api/crm/dicts/customer_type/items/personal", json={"sort": 9})
        self.assertEqual(c_type.status_code, 403, c_type.text)
        self.assertEqual(c_type.json()["code"], "dict_field_forbidden")

        c_disable = self.client.put("/api/crm/dicts/customer_type/items/personal", json={"enabled": False})
        self.assertEqual(c_disable.status_code, 403, c_disable.text)

        b_disable = self.client.put("/api/crm/dicts/order_status/items/pending_payment", json={"enabled": False})
        self.assertEqual(b_disable.status_code, 403, b_disable.text)

        # 允许的：C 改名、B 改名/排序
        self.assertEqual(
            self.client.put("/api/crm/dicts/customer_type/items/personal", json={"label": "个人客户"}).status_code,
            200,
        )
        self.assertEqual(
            self.client.put("/api/crm/dicts/order_status/items/pending_payment", json={"label": "待收款", "sort": 5}).status_code,
            200,
        )

    def test_b_class_cannot_add_or_delete(self):
        add = self.client.post("/api/crm/dicts/order_status/items", json={"key": "x", "label": "X"})
        self.assertEqual(add.status_code, 403, add.text)
        rm = self.client.delete("/api/crm/dicts/order_status/items/completed")
        self.assertEqual(rm.status_code, 403, rm.text)

    def test_key_immutable_and_invalid(self):
        rename = self.client.put(
            "/api/crm/dicts/customer_source/items/wechat", json={"key": "wx"}
        )
        self.assertEqual(rename.status_code, 400, rename.text)
        bad_key = self.client.post(
            "/api/crm/dicts/customer_source/items", json={"key": "a b/c", "label": "坏 key"}
        )
        self.assertEqual(bad_key.status_code, 400, bad_key.text)

    def test_reorder_items_updates_whole_enabled_list(self):
        before = self.client.get("/api/crm/dicts/customer_source").json()["items"]
        before_keys = [item["key"] for item in before]
        reversed_keys = list(reversed(before_keys))

        try:
            resp = self.client.put(
                "/api/crm/dicts/customer_source/items/order",
                json={"keys": reversed_keys},
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            items = resp.json()["items"]
            self.assertEqual([item["key"] for item in items], reversed_keys)
            self.assertEqual([item["sort"] for item in items], list(range(1, len(items) + 1)))

            duplicate = self.client.put(
                "/api/crm/dicts/customer_source/items/order",
                json={"keys": [reversed_keys[0], reversed_keys[0]]},
            )
            self.assertEqual(duplicate.status_code, 400, duplicate.text)
            self.assertEqual(duplicate.json()["code"], "dict_order_duplicate")

            incomplete = self.client.put(
                "/api/crm/dicts/customer_source/items/order",
                json={"keys": reversed_keys[:-1]},
            )
            self.assertEqual(incomplete.status_code, 400, incomplete.text)
            self.assertEqual(incomplete.json()["code"], "dict_order_incomplete")
        finally:
            self.client.put(
                "/api/crm/dicts/customer_source/items/order",
                json={"keys": before_keys},
            )

    def test_reorder_rejects_level_c_dictionary(self):
        keys = [item["key"] for item in self.client.get("/api/crm/dicts/customer_type").json()["items"]]
        resp = self.client.put(
            "/api/crm/dicts/customer_type/items/order",
            json={"keys": list(reversed(keys))},
        )
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(resp.json()["code"], "dict_level_forbidden")


if __name__ == '__main__':
    unittest.main()
