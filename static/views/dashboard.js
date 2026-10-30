/* 工作台页面逻辑 */
function viewDashboard(root) {
    return api('/dashboard').then(function (d) {
        var stats = d.stats || {};
        var monthWon = d.month_won || stats.month_won || { count: 0, amount: 0 };
        var todos = d.today_followups || [];

        var todoHtml = todos.length ? todos.map(function (item) {
            var stageTag = item.deal_stage_label
                ? '<span class=\"tag\">' + esc(item.deal_stage_label) + '</span>' : '';
            var link = '#/followups?customer=' + item.customer_id +
                (item.deal_id ? '&deal=' + item.deal_id : '');
            return '<div class=\"item\">' +
                '<div class=\"item-main\">' +
                '<div class=\"item-title\"><a href=\"#/customers/' + item.customer_id + '\">' +
                esc(item.customer_name) + '</a>' + overdueBadge(item.days_overdue) + stageTag + '</div>' +
                '<div class=\"item-sub\">' + esc(item.content) + '</div>' +
                '<div class=\"item-sub small\">约好 ' + esc(item.next_date) + '</div>' +
                '</div>' +
                '<div class=\"item-side\"><a class=\"btn btn-sm\" href=\"' + link + '\">记跟进</a></div>' +
                '</div>';
        }).join('') : '<p class=\"empty\">今天没有待跟进，清爽 👌</p>';

        // 售后 SLA 红条
        var slaAlertHtml = '';
        if (d.aftersale_sla_alerts && d.aftersale_sla_alerts.length > 0) {
            var alert = d.aftersale_sla_alerts[0];
            slaAlertHtml = '<div class=\"sla-alert\">' +
                '⚠ 售后单 ' + esc(alert.no) + ' 已挂 ' + esc(alert.days_pending) + ' 天未处理' +
                '<a href=\"#/aftersales/' + alert.id + '\" class=\"btn btn-sm\">查看详情</a>' +
                '</div>';
        }

        root.innerHTML =
            slaAlertHtml +
            '<div class=\"grid-kpi\">' +
            '<div class=\"kpi\"><div class=\"label\">本月成交</div><div class=\"value\">' + money(monthWon.amount) +
            '</div><div class=\"sub\">' + (monthWon.count || 0) + ' 单</div></div>' +
            '<div class=\"kpi\"><div class=\"label\">待跟进</div><div class=\"value\">' + todos.length +
            '</div><div class=\"sub\">含逾期</div></div>' +
            '<div class=\"kpi\"><div class=\"label\">客户总数</div><div class=\"value\">' + (stats.customers_total || 0) +
            '</div><div class=\"sub\">本月新增 ' + (stats.month_new_customers || 0) + '</div></div>' +
            '<div class=\"kpi\"><div class=\"label\">老客</div><div class=\"value\">' + (stats.repeat_customers || 0) +
            '</div><div class=\"sub\">名下 ≥2 个商机</div></div>' +
            '</div>' +
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>今日待跟进 <span class=\"badge warn\">' + todos.length + '</span></h2>' +
            '<a class=\"btn btn-sm\" href=\"#/followups\">全部跟进</a></div>' +
            todoHtml +
            '</div>' +
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>订单状态分布</h2><a class=\"btn btn-sm\" href=\"#/orders\">管理订单</a></div>' +
            barsHtml(d.orders.by_status) +
            '</div>' +
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>最近订单</h2><a class=\"btn btn-sm\" href=\"#/orders\">全部订单</a></div>' +
            (d.recent_orders && d.recent_orders.length ? d.recent_orders.map(function (order) {
                return '<div class=\"item\">' +
                    '<div class=\"item-main\">' +
                    '<div class=\"item-title\">' + esc(order.order_no) + '</div>' +
                    '<div class=\"item-sub\">' + esc(order.customer_name) + '</div>' +
                    '<div class=\"item-sub\">' + money(order.amount) + '</div>' +
                    '</div>' +
                    '<div class=\"item-side\"><span class=\"badge muted\">' + esc(order.status_label) + '</span></div>' +
                    '</div>';
            }).join('') : '<p class=\"empty\">暂无订单</p>') +
            '</div>';
    });
}