/* 工作台（2026-10-31 对齐 demo 定稿 PAGES-V2 §1 D1–D5）
 *   A 数字卡 5 个（今日待跟进 / 逾期未跟进 / 进行中商机 / 本月成交 / 本月新增客户）
 *   B 今日待跟进（核心区，行内「记一条」直接开弹窗，不跳页）
 *   C 订单待办（按状态分组的计数 chip，点进订单列表）
 *   D 最近动态 10 条（跟进 + 订单事件混排）
 *   E 空态引导（一个客户都没有时给三步上手）
 * 依赖后端 GET /dashboard：today_followups / month_won / stats.{in_progress_deals, recent_activities, orders_by_status, ...}
 */
function viewDashboard(root) {
    return api('/dashboard').then(function (d) {
        var stats = d.stats || {};
        var monthWon = d.month_won || stats.month_won || { count: 0, amount: 0 };
        var todos = d.today_followups || [];
        var inProgress = stats.in_progress_deals || { count: 0, amount: 0 };
        var ordersByStatus = stats.orders_by_status || {};
        var acts = stats.recent_activities || [];

        /* ---------- 售后 SLA 红条 ---------- */
        var slaAlerts = stats.aftersale_sla_alerts || [];
        var slaAlertHtml = '';
        if (slaAlerts.length) {
            var a0 = slaAlerts[0];
            slaAlertHtml = '<div class="sla-alert">' +
                '⚠ 售后单 ' + esc(a0.no) + ' 已挂 ' + esc(a0.days_pending) + ' 天未处理（SLA 3 天）' +
                '<a class="btn btn-sm" href="#/aftersales/' + a0.id + '">去处理</a>' +
                '</div>';
        }

        /* ---------- A. 数字卡（5 个，可点） ---------- */
        var overdueCount = todos.filter(function (t) { return Number(t.days_overdue) > 0; }).length;
        var kpiHtml =
            '<div class="grid-kpi">' +
            '<a class="kpi kpi-link" href="#/followups">' +
            '<div class="label">今日待跟进</div><div class="value">' + todos.length + '</div>' +
            '<div class="sub">按最近一次跟进算</div></a>' +
            '<a class="kpi kpi-link' + (overdueCount ? ' kpi-danger' : '') + '" href="#/followups">' +
            '<div class="label">逾期未跟进</div><div class="value">' + overdueCount + '</div>' +
            '<div class="sub">' + (overdueCount ? '已超约定日期' : '没有逾期') + '</div></a>' +
            '<a class="kpi kpi-link" href="#/deals">' +
            '<div class="label">进行中商机</div><div class="value">' + (inProgress.count || 0) + '</div>' +
            '<div class="sub">报价 ' + money(inProgress.amount) + '</div></a>' +
            '<a class="kpi kpi-link" href="#/deals?stage=won">' +
            '<div class="label">本月成交</div><div class="value">' + money(monthWon.amount) + '</div>' +
            '<div class="sub">' + (monthWon.count || 0) + ' 单</div></a>' +
            '<a class="kpi kpi-link" href="#/customers">' +
            '<div class="label">本月新增客户</div><div class="value">' + (stats.month_new_customers || 0) + '</div>' +
            '<div class="sub">客户总数 ' + (stats.customers_total || 0) + '</div></a>' +
            '</div>';

        /* ---------- B. 今日待跟进 ---------- */
        var todoHtml = todos.length ? todos.map(function (t) {
            var intent = t.intent_level ? (INTENT_LABELS[t.intent_level] || '') : '';
            var intentCls = t.intent_level === 'high' ? 'badge danger'
                : (t.intent_level === 'medium' ? 'badge warn' : 'badge muted');
            var stage = t.deal_stage_label ? '<span class="tag">' + esc(t.deal_stage_label) + '</span>' : '';
            var overdue = Number(t.days_overdue);
            return '<div class="item todo-row' + (overdue > 0 ? ' todo-overdue' : '') + '">' +
                '<div class="item-main">' +
                '<div class="item-title"><a href="#/customers/' + t.customer_id + '">' +
                esc(t.customer_name) + '</a>' +
                (intent ? '<span class="' + intentCls + '">' + esc(intent) + '</span>' : '') + stage + '</div>' +
                '<div class="item-sub">' + esc(t.content) + '</div>' +
                '<div class="item-sub small">' +
                (t.last_follow_at ? '上次跟进 ' + fmtDateTime(t.last_follow_at).slice(0, 10) + ' · ' : '') +
                '约好 ' + esc(t.next_date) +
                (overdue > 0
                    ? ' <span class="badge danger">逾期 ' + overdue + ' 天</span>'
                    : ' <span class="badge warn">今天</span>') +
                '</div>' +
                '</div>' +
                '<div class="item-side">' +
                '<button type="button" class="btn btn-sm btn-primary" data-log-fu="' + t.customer_id + '"' +
                (t.deal_id ? ' data-log-deal="' + t.deal_id + '"' : '') + '>记一条</button>' +
                '</div>' +
                '</div>';
        }).join('') : '<p class="empty">今天没有待跟进，清爽 👌</p>';

        /* ---------- C. 订单待办（按状态分组） ---------- */
        var orderChips = ORDER_STATUS.map(function (p) {
            var c = (ordersByStatus[p[0]] || {}).count || 0;
            if (!c) { return ''; }
            return '<a class="chip-due" href="#/orders?status=' + p[0] + '">' +
                '<span class="chip-due-num">' + c + '</span>' +
                '<span class="chip-due-label">' + esc(p[1]) + '</span></a>';
        }).join('');
        if (!orderChips) { orderChips = '<p class="empty">暂无待办订单</p>'; }

        /* ---------- D. 最近动态 ---------- */
        var actHtml = acts.length ? acts.map(function (a) {
            var icon = a.type === 'followup' ? '💬' : (a.type === 'order' ? '📦' : '•');
            var amt = (a.type === 'order' && a.amount) ? ' · ' + money(a.amount) : '';
            return '<div class="act-row">' +
                '<span class="act-time">' + fmtDateTime(a.at).slice(5) + '</span>' +
                '<span class="act-icon">' + icon + '</span>' +
                '<span class="act-text">' + esc(a.text) + esc(amt) + '</span>' +
                '</div>';
        }).join('') : '<p class="empty">还没有动态</p>';

        /* ---------- E. 空态引导 ---------- */
        var emptyGuide = '';
        if (!stats.customers_total) {
            emptyGuide = '<div class="card"><div class="card-head"><h2>开始使用</h2></div>' +
                '<p class="small muted">还没有数据，按这个顺序三步就能跑起来：</p>' +
                '<div class="row-3">' +
                '<a class="btn btn-primary" href="#/leads">① 录第一条线索</a>' +
                '<a class="btn" href="#/followups">② 记一条跟进</a>' +
                '<a class="btn" href="#/deals">③ 线索转商机</a>' +
                '</div></div>';
        }

        root.innerHTML =
            slaAlertHtml + kpiHtml + emptyGuide +
            '<div class="card">' +
            '<div class="card-head"><h2>今日待跟进 <span class="badge warn">' + todos.length + '</span></h2>' +
            '<a class="btn btn-sm" href="#/followups">全部跟进</a></div>' +
            todoHtml +
            '</div>' +
            '<div class="card">' +
            '<div class="card-head"><h2>订单待办</h2><a class="btn btn-sm" href="#/orders">管理订单</a></div>' +
            '<div class="chip-grid">' + orderChips + '</div>' +
            '</div>' +
            '<div class="card">' +
            '<div class="card-head"><h2>最近动态</h2><span class="small muted">跟进与订单事件混排</span></div>' +
            actHtml +
            '</div>';

        /* ---------- 「记一条」弹窗 ---------- */
        $$('button[data-log-fu]', root).forEach(function (btn) {
            btn.addEventListener('click', function () {
                openQuickFollowup(
                    Number(btn.getAttribute('data-log-fu')),
                    Number(btn.getAttribute('data-log-deal')) || 0
                );
            });
        });
    });
}

/* 工作台行内「记一条」：POST /follow-ups（方式取字典 follow_method） */
function openQuickFollowup(customerId, dealId) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content">' +
        '<div class="modal-header"><h3>记一条跟进</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<form id="quickFuForm" autocomplete="off">' +
        '<div class="field"><label>跟进内容 *</label>' +
        '<textarea name="content" rows="4" maxlength="2000" required ' +
        'placeholder="聊了什么、客户什么态度、下一步做什么"></textarea></div>' +
        '<div class="row-2">' +
        '<div class="field"><label>下次跟进日期</label>' +
        '<input type="date" name="next_date" value="' + quickDayAfter(3) + '"></div>' +
        '<div class="field"><label>跟进方式</label>' +
        '<select name="method">' + dictOptions('follow_method', 'wechat') + '</select></div>' +
        '</div>' +
        '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">保存跟进</button>' +
        '</div>' +
        '</form>' +
        '</div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);

    var form = modal.querySelector('form');
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var content = String(form.querySelector('[name="content"]').value || '').trim();
        if (!content) { toast('跟进内容不能为空', true); return; }
        var fd = new FormData();
        fd.append('customer_id', String(customerId));
        fd.append('content', content);
        fd.append('method', form.querySelector('[name="method"]').value || 'wechat');
        var nextDate = form.querySelector('[name="next_date"]').value;
        if (nextDate) { fd.append('next_date', nextDate); }
        if (dealId) { fd.append('deal_id', String(dealId)); }
        btn.disabled = true;
        api('/follow-ups', { method: 'POST', body: fd }).then(function () {
            toast('已记录跟进');
            close();
            return render();
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}

function quickDayAfter(n) {
    var dt = new Date();
    dt.setDate(dt.getDate() + n);
    return dt.getFullYear() + '-' + ((dt.getMonth() + 1) < 10 ? '0' : '') + (dt.getMonth() + 1) +
        '-' + (dt.getDate() < 10 ? '0' : '') + dt.getDate();
}
