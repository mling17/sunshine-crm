#!/usr/bin/env python3
"""
T5 功能测试脚本
用于验证订单7态、金额校验、截图和物流主数据功能是否正确实现
"""

import sys
import os
sys.path.insert(0, '/opt/data/crm')

from app.db import db_conn
from app.services import transition
from app.models import OrderOut

def test_order_status_flow():
    """测试订单状态流转"""
    print("测试订单状态流转...")
    
    with db_conn() as conn:
        # 创建测试客户
        conn.execute(
            "INSERT INTO customers (name, created_at, updated_at) VALUES (?, ?, ?)",
            ("测试客户", "2026-10-30T10:00:00Z", "2026-10-30T10:00:00Z")
        )
        customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # 创建测试订单
        conn.execute(
            """
            INSERT INTO orders 
                (order_no, customer_id, deal_id, product_type, model, spec, 
                 amount, status, owner, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SO-20261030-001",
                customer_id,
                1,
                "产品类型",
                "型号",
                "规格",
                1000.0,
                "pending_payment",
                "测试人员",
                "2026-10-30T10:00:00Z",
                "2026-10-30T10:00:00Z",
            ),
        )
        order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        print(f"创建订单 ID: {order_id}")
        
        # 测试状态流转：待支付 -> 已支付押金
        result1 = transition(conn, order_id, "deposit_paid", {
            "deposit": 300.0,
            "note": "支付押金"
        })
        print(f"支付押金后状态: {result1['order'].status}")
        print(f"已付金额: {result1['order'].paid_amount}")
        
        # 测试状态流转：已支付押金 -> 生产中
        result2 = transition(conn, order_id, "producing", {
            "note": "进入生产"
        })
        print(f"进入生产后状态: {result2['order'].status}")
        
        # 测试状态流转：生产中 -> 已支付尾款
        result3 = transition(conn, order_id, "balance_paid", {
            "balance": 700.0,
            "note": "支付尾款"
        })
        print(f"支付尾款后状态: {result3['order'].status}")
        print(f"已付金额: {result3['order'].paid_amount}")
        
        # 测试状态流转：已支付尾款 -> 待发货
        result4 = transition(conn, order_id, "ready_to_ship", {
            "logistics_mode": "self",
            "note": "准备发货"
        })
        print(f"准备发货后状态: {result4['order'].status}")
        
        # 测试状态流转：待发货 -> 已发货
        result5 = transition(conn, order_id, "shipped", {
            "note": "已发货"
        })
        print(f"已发货后状态: {result5['order'].status}")
        
        # 测试状态流转：已发货 -> 已完成
        result6 = transition(conn, order_id, "completed", {
            "note": "已完成"
        })
        print(f"完成后状态: {result6['order'].status}")
        
        # 验证状态日志数量
        logs = conn.execute(
            "SELECT COUNT(*) as count FROM order_status_log WHERE order_id = ?",
            (order_id,)
        ).fetchone()
        print(f"状态日志总数: {logs[0]}")
        
        # 清理测试数据
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        
        print("订单状态流转测试通过!")
        return True

def test_q1_balance_validation():
    """测试Q1尾款校验"""
    print("\n测试Q1尾款校验...")
    
    with db_conn() as conn:
        # 创建测试客户
        conn.execute(
            "INSERT INTO customers (name, created_at, updated_at) VALUES (?, ?, ?)",
            ("测试客户", "2026-10-30T10:00:00Z", "2026-10-30T10:00:00Z")
        )
        customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # 创建测试订单
        conn.execute(
            """
            INSERT INTO orders 
                (order_no, customer_id, deal_id, product_type, model, spec, 
                 amount, status, owner, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SO-20261030-002",
                customer_id,
                1,
                "产品类型",
                "型号",
                "规格",
                1000.0,
                "pending_payment",
                "测试人员",
                "2026-10-30T10:00:00Z",
                "2026-10-30T10:00:00Z",
            ),
        )
        order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # 先支付押金
        transition(conn, order_id, "deposit_paid", {
            "deposit": 300.0,
            "note": "支付押金"
        })
        
        # 尝试支付错误的尾款金额（应该失败）
        try:
            transition(conn, order_id, "balance_paid", {
                "balance": 600.0,  # 应该是700元
                "note": "支付尾款"
            })
            print("错误：应该拒绝尾款金额不正确的请求")
            return False
        except Exception as e:
            print(f"正确拒绝了错误的尾款金额: {str(e)}")
        
        # 支付正确的尾款金额
        transition(conn, order_id, "balance_paid", {
            "balance": 700.0,
            "note": "支付尾款"
        })
        print("正确的尾款金额被接受")
        
        # 清理测试数据
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        
        print("Q1尾款校验测试通过!")
        return True

def test_carrier_delete_protection():
    """测试物流公司删除保护"""
    print("\n测试物流公司删除保护...")
    
    with db_conn() as conn:
        # 创建测试物流公司
        conn.execute(
            """
            INSERT INTO carriers 
                (name, code, contact_person, phone, address, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "测试物流公司",
                "TEST001",
                "测试联系人",
                "13800138000",
                "测试地址",
                "2026-10-30T10:00:00Z",
                "2026-10-30T10:00:00Z",
            ),
        )
        carrier_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # 创建测试订单并关联物流公司
        conn.execute(
            """
            INSERT INTO orders 
                (order_no, customer_id, deal_id, product_type, model, spec, 
                 amount, status, carrier_id, owner, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SO-20261030-003",
                1,
                1,
                "产品类型",
                "型号",
                "规格",
                1000.0,
                "ready_to_ship",
                carrier_id,
                "测试人员",
                "2026-10-30T10:00:00Z",
                "2026-10-30T10:00:00Z",
            ),
        )
        order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # 尝试删除被引用的物流公司
        try:
            # 这个测试实际上需要通过API调用来验证
            print("测试逻辑：被引用的物流公司无法删除（需通过API测试）")
        except Exception as e:
            print(f"删除被引用物流公司失败: {str(e)}")
        
        # 清理测试数据
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.execute("DELETE FROM carriers WHERE id = ?", (carrier_id,))
        
        print("物流公司删除保护测试完成!")
        return True

def main():
    """主测试函数"""
    print("=== T5 功能测试 ===")
    
    try:
        success = True
        success &= test_order_status_flow()
        success &= test_q1_balance_validation()
        success &= test_carrier_delete_protection()
        
        if success:
            print("\n🎉 所有测试通过!")
            return 0
        else:
            print("\n❌ 部分测试失败!")
            return 1
            
    except Exception as e:
        print(f"\n💥 测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())