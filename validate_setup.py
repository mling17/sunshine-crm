#!/usr/bin/env python3
"""
验证 CRM V2 基础设置是否正确完成
"""
import os
import sys
import sqlite3
from pathlib import Path

# 添加项目路径
sys.path.insert(0, '/opt/data/crm')

def validate_files_created():
    """验证所需文件是否已创建"""
    required_files = [
        'app/enums.py',
        'app/errors.py', 
        'app/migrations.py',
        'app/queries.py',
        'tests/test_migrations.py'
    ]
    
    print("验证文件创建...")
    all_good = True
    for file_path in required_files:
        full_path = Path(file_path)
        if full_path.exists():
            print(f"✓ {file_path}")
        else:
            print(f"✗ {file_path}")
            all_good = False
    
    return all_good

def validate_models_updated():
    """验证 models.py 是否已更新"""
    print("\n验证 models.py 更新...")
    
    try:
        from app.models import STAGE_LABELS, STAGES, DEFAULT_STAGE
        print(f"✓ STAGE_LABELS: {len(STAGE_LABELS)} items")
        print(f"✓ STAGES: {len(STAGES)} items")
        print(f"✓ DEFAULT_STAGE: {DEFAULT_STAGE}")
        
        # 检查新阶段是否正确
        expected_stages = ['confirm', 'quote', 'negotiate', 'won', 'lost']
        if all(stage in STAGES for stage in expected_stages):
            print("✓ 阶段枚举正确")
        else:
            print("✗ 阶段枚举不正确")
            return False
            
        if DEFAULT_STAGE == "confirm":
            print("✓ 默认阶段正确")
        else:
            print("✗ 默认阶段不正确")
            return False
            
        return True
    except Exception as e:
        print(f"✗ 模型验证失败: {e}")
        return False

def validate_main_updated():
    """验证 main.py 是否已更新"""
    print("\n验证 main.py 更新...")
    
    try:
        with open('/opt/data/crm/app/main.py', 'r') as f:
            content = f.read()
            
        if 'run_migrations' in content and 'install_error_handler' in content:
            print("✓ 已添加迁移和错误处理")
            return True
        else:
            print("✗ 未找到迁移或错误处理相关代码")
            return False
    except Exception as e:
        print(f"✗ main.py 验证失败: {e}")
        return False

def validate_migrations_functionality():
    """验证迁移功能基本可用"""
    print("\n验证迁移功能...")
    
    try:
        from app.migrations import MIGRATION_VERSION, SCHEMA_USER_VERSION
        print(f"✓ 迁移版本: {MIGRATION_VERSION}")
        print(f"✓ 用户版本: {SCHEMA_USER_VERSION}")
        return True
    except Exception as e:
        print(f"✗ 迁移功能验证失败: {e}")
        return False

def main():
    print("CRM V2 基础设置验证")
    print("=" * 50)
    
    checks = [
        validate_files_created,
        validate_models_updated,
        validate_main_updated,
        validate_migrations_functionality
    ]
    
    all_passed = True
    for check in checks:
        if not check():
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ 所有验证通过！基础设置已正确完成。")
        return 0
    else:
        print("✗ 部分验证失败，请检查错误信息。")
        return 1

if __name__ == "__main__":
    sys.exit(main())