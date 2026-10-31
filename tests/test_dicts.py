"""
CRM V2 字典功能测试。
"""
import os
import tempfile
import unittest

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
        
        # 检查产品型号种子数据
        product_models = DICT_SEEDS["product_model"]
        self.assertGreater(len(product_models), 20)
        xw60 = [m for m in product_models if m["key"] == "XW-60"]
        self.assertEqual(len(xw60), 1, "产品型号 XW-60 必须存在且唯一")
        self.assertEqual(xw60[0]["label"], "XW-60 天窗 600×1200")
        self.assertEqual(xw60[0]["meta"]["size"], "600×1200", "型号必须带出尺寸")
        
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


if __name__ == '__main__':
    unittest.main()