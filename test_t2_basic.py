#!/usr/bin/env python3
"""
简单的集成测试脚本，用于验证 T2 功能是否基本正常运行
"""
import sys
import os
import tempfile
import shutil

# 设置环境变量
sys.path.insert(0, '/opt/data/crm')

def test_basic_imports():
    """测试基本导入是否正常"""
    try:
        from app.routers import leads
        from app.routers import followups
        from app.models import LeadIn, LeadOut, LeadConvertIn, LeadConvertOut
        from app.services import convert_lead
        print("✓ 基本导入正常")
        return True
    except Exception as e:
        print(f"✗ 基本导入失败: {e}")
        return False

def test_models():
    """测试模型定义"""
    try:
        from app.models import LeadIn, LeadOut, LeadConvertIn, LeadConvertOut, DuplicateHint
        print("✓ 模型定义正常")
        return True
    except Exception as e:
        print(f"✗ 模型定义失败: {e}")
        return False

def test_routes_exist():
    """测试路由是否定义"""
    try:
        from app.routers.leads import router as leads_router
        from app.routers.followups import router as followups_router
        print("✓ 路由定义正常")
        return True
    except Exception as e:
        print(f"✗ 路由定义失败: {e}")
        return False

def test_services_exist():
    """测试服务函数是否定义"""
    try:
        from app.services import convert_lead, read_images
        print("✓ 服务函数定义正常")
        return True
    except Exception as e:
        print(f"✗ 服务函数定义失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=== CRM V2 T2 功能基础测试 ===")
    
    tests = [
        test_basic_imports,
        test_models,
        test_routes_exist,
        test_services_exist,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n=== 测试结果: {passed}/{total} 通过 ===")
    
    if passed == total:
        print("🎉 所有基础测试通过！")
        return 0
    else:
        print("❌ 部分测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())