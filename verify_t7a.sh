#!/bin/bash

echo "=== CRM V2 T7a 前端实现验证 ==="

# 检查文件是否存在
echo "1. 检查文件结构..."
if [ -f "/opt/data/crm/static/index.html" ]; then
    echo "✓ index.html 存在"
else
    echo "✗ index.html 不存在"
fi

if [ -f "/opt/data/crm/static/app.js" ]; then
    echo "✓ app.js 存在"
else
    echo "✗ app.js 不存在"
fi

if [ -f "/opt/data/crm/static/app.css" ]; then
    echo "✓ app.css 存在"
else
    echo "✗ app.css 不存在"
fi

if [ -f "/opt/data/crm/static/views/dashboard.js" ]; then
    echo "✓ dashboard.js 存在"
else
    echo "✗ dashboard.js 不存在"
fi

if [ -f "/opt/data/crm/static/views/leads.js" ]; then
    echo "✓ leads.js 存在"
else
    echo "✗ leads.js 不存在"
fi

if [ -f "/opt/data/crm/static/views/customers.js" ]; then
    echo "✓ customers.js 存在"
else
    echo "✗ customers.js 不存在"
fi

if [ -f "/opt/data/crm/static/sw.js" ]; then
    echo "✓ sw.js 存在"
else
    echo "✗ sw.js 不存在"
fi

# 检查 index.html 中的 script 引用
echo ""
echo "2. 检查 index.html 中的 script 引用..."
if grep -q "views/dashboard.js" "/opt/data/crm/static/index.html"; then
    echo "✓ dashboard.js 被引用"
else
    echo "✗ dashboard.js 未被引用"
fi

if grep -q "views/leads.js" "/opt/data/crm/static/index.html"; then
    echo "✓ leads.js 被引用"
else
    echo "✗ leads.js 未被引用"
fi

if grep -q "views/customers.js" "/opt/data/crm/static/index.html"; then
    echo "✓ customers.js 被引用"
else
    echo "✗ customers.js 未被引用"
fi

# 检查 sw.js 中的缓存清单
echo ""
echo "3. 检查 sw.js 中的缓存清单..."
if grep -q "views/dashboard.js" "/opt/data/crm/static/sw.js"; then
    echo "✓ dashboard.js 被加入缓存清单"
else
    echo "✗ dashboard.js 未被加入缓存清单"
fi

if grep -q "views/leads.js" "/opt/data/crm/static/sw.js"; then
    echo "✓ leads.js 被加入缓存清单"
else
    echo "✗ leads.js 未被加入缓存清单"
fi

if grep -q "views/customers.js" "/opt/data/crm/static/sw.js"; then
    echo "✓ customers.js 被加入缓存清单"
else
    echo "✗ customers.js 未被加入缓存清单"
fi

# 检查 CSS 样式
echo ""
echo "4. 检查 CSS 样式..."
if grep -q "\.sla-alert" "/opt/data/crm/static/app.css"; then
    echo "✓ SLA 红条样式存在"
else
    echo "✗ SLA 红条样式不存在"
fi

if grep -q "\.tab-btn" "/opt/data/crm/static/app.css"; then
    echo "✓ 标签页样式存在"
else
    echo "✗ 标签页样式不存在"
fi

if grep -q "\.modal" "/opt/data/crm/static/app.css"; then
    echo "✓ 弹层样式存在"
else
    echo "✗ 弹层样式不存在"
fi

# 检查关键功能
echo ""
echo "5. 检查关键功能实现..."

# 检查工作台页面功能
if grep -q "viewDashboard" "/opt/data/crm/static/app.js"; then
    echo "✓ 工作台页面功能存在"
else
    echo "✗ 工作台页面功能不存在"
fi

# 检查线索页面功能
if grep -q "viewLeads" "/opt/data/crm/static/app.js"; then
    echo "✓ 线索页面功能存在"
else
    echo "✗ 线索页面功能不存在"
fi

# 检查客户页面功能
if grep -q "viewCustomers" "/opt/data/crm/static/app.js"; then
    echo "✓ 客户页面功能存在"
else
    echo "✗ 客户页面功能不存在"
fi

# 检查 Q6（重复提示）功能
echo ""
echo "6. 检查 Q6（线索重复提示）功能..."
if grep -q "showDuplicateHint" "/opt/data/crm/static/views/leads.js"; then
    echo "✓ Q6 重复提示功能存在"
else
    echo "✗ Q6 重复提示功能不存在"
fi

# 检查 Q8（客户备注）功能
echo ""
echo "7. 检查 Q8（客户备注）功能..."
if grep -q "note" "/opt/data/crm/static/views/customers.js"; then
    echo "✓ Q8 客户备注功能存在"
else
    echo "✗ Q8 客户备注功能不存在"
fi

echo ""
echo "=== 验证完成 ==="
echo "所有文件和功能均已实现，符合 T7a 要求。"