/* ============================================================================
 * 工作台（Demo 版）
 * 规格依据：/opt/data/crm/docs/PAGES-V2.md §1（D1–D5 已定稿）
 *   A 数字卡 5 个（含 D2 新增「本月新增客户」）
 *   B 今日待跟进（核心区，D1：跟进优先）→ 弹窗内「记一条」，不跳页
 *   C 订单待办（按状态分组计数）
 *   D 最近动态 10 条（金额走 👁 遮罩，D4）
 *   E 空态引导
 * ==========================================================================*/
function viewDashboard(root) {
  return api('/dashboard').then(function (d) {
    var stats = d.stats || {};
    var todos = d.today_followups || [];
    var inProgress = stats.in_progress_deals || { count: 0, amount: 0 };
    var monthWon = d.month_won || { count: 0, amount: 0 };
    var ordersByStatus = stats.orders_by_status || {};

    /* ---------- 售后 SLA 红条 ---------- */
    var slaHtml = '';
    var alerts = stats.aftersale_sla_alerts || [];
    if (alerts.length) {
      var a0 = alerts[0];
      slaHtml = '<div class="sla-alert">⚠ 售后单 ' + esc(a0.no) + ' 已挂 ' + esc(a0.days_pending) +
        ' 天未处理（SLA 3 天）<a href="#/aftersales/' + a0.id + '" class="btn btn-sm">去处理</a></div>';
    }

    /* ---------- A. 数字卡 ---------- */
    var overdueCount = todos.filter(function (t) { return t.days_overdue > 0; }).length;
    var kpi = '' +
      '<div class="grid-kpi">' +
        '<a class="kpi kpi-link" href="#/followups">' +
          '<div class="label">今日待跟进</div><div class="value">' + todos.length + '</div>' +
          '<div class="sub">按最近一次跟进算</div></a>' +
        '<a class="kpi kpi-link' + (overdueCount ? ' kpi-danger' : '') + '" href="#/followups">' +
          '<div class="label">逾期未跟进</div><div class="value">' + overdueCount + '</div>' +
          '<div class="sub">' + (overdueCount ? '已超约定日期' : '没有逾期') + '</div></a>' +
        '<a class="kpi kpi-link" href="#/deals">' +
          '<div class="label">进行中商机</div><div class="value">' + inProgress.count + '</div>' +
          '<div class="sub">' + money(inProgress.amount) + '</div></a>' +
        '<a class="kpi kpi-link" href="#/deals?stage=won">' +
          '<div class="label">本月成交</div><div class="value">' + money(monthWon.amount) + '</div>' +
          '<div class="sub">' + (monthWon.count || 0) + ' 单</div></a>' +
        '<a class="kpi kpi-link" href="#/customers">' +
          '<div class="label">本月新增客户</div><div class="value">' + (stats.month_new_customers || 0) + '</div>' +
          '<div class="sub">客户总数 ' + (stats.customers_total || 0) + '</div></a>' +
      '</div>';

    /* ---------- B. 今日待跟进（核心区） ---------- */
    var todoHtml;
    if (todos.length) {
      todoHtml = todos.map(function (t) {
        var intent = INTENT_LABELS[t.intent_level] || '';
        var intentCls = t.intent_level === 'high' ? 'badge danger' : (t.intent_level === 'medium' ? 'badge warn' : 'badge muted');
        var stage = t.deal_stage_label ? '<span class="tag">' + esc(t.deal_stage_label) + '</span>' : '';
        return '<div class="item todo-row' + (t.days_overdue > 0 ? ' todo-overdue' : '') + '">' +
          '<div class="item-main">' +
            '<div class="item-title">' +
              '<a href="#/customers/' + t.customer_id + '">' + esc(t.customer_name) + '</a>' +
              (intent ? '<span class="' + intentCls + '">' + intent + '</span>' : '') + stage +
            '</div>' +
            '<div class="item-sub">' + esc(t.content) + '</div>' +
            '<div class="item-sub small">' +
              '上次跟进 ' + fmtDateTime(t.last_follow_at).slice(0, 10) +
              ' · 约好 ' + esc(t.next_date) +
              (t.days_overdue > 0
                ? ' <span class="badge danger">逾期 ' + t.days_overdue + ' 天</span>'
                : ' <span class="badge warn">今天</span>') +
            '</div>' +
          '</div>' +
          '<div class="item-side">' +
            '<button type="button" class="btn btn-sm btn-primary" data-log-fu="' + t.customer_id + '">记一条</button>' +
          '</div>' +
        '</div>';
      }).join('');
    } else {
      todoHtml = '<p class="empty">今天没有待跟进，清爽 👌</p>';
    }

    /* ---------- C. 订单待办 ---------- */
    var orderChips = ORDER_STATUS.map(function (p) {
      var c = (ordersByStatus[p[0]] || {}).count || 0;
      if (!c) { return ''; }
      return '<a class="chip-due" href="#/orders?status=' + p[0] + '">' +
        '<span class="chip-due-num">' + c + '</span>' +
        '<span class="chip-due-label">' + p[1] + '</span></a>';
    }).join('');
    if (!orderChips) { orderChips = '<p class="empty">暂无待办订单</p>'; }

    /* ---------- D. 最近动态 ---------- */
    var acts = stats.recent_activities || [];
    var actHtml = acts.length ? acts.map(function (a) {
      var icon = a.type === 'followup' ? '💬' : '📦';
      var amt = (a.type === 'order' && a.amount) ? ' · ' + money(a.amount) : '';
      return '<div class="act-row">' +
        '<span class="act-time">' + fmtDateTime(a.at).slice(5) + '</span>' +
        '<span class="act-icon">' + icon + '</span>' +
        '<span class="act-text">' + esc(a.text) + amt + '</span>' +
        '</div>';
    }).join('') : '<p class="empty">还没有动态</p>';

    /* ---------- E. 空态 ---------- */
    var emptyGuide = '';
    if (!stats.customers_total) {
      emptyGuide = '<div class="card"><div class="card-head"><h2>开始使用</h2></div>' +
        '<p class="small muted">还没有数据，按这个顺序三步就能跑起来：</p>' +
        '<div class="row-3">' +
          '<a class="btn btn-primary" href="#/customers">① 录第一个客户</a>' +
          '<a class="btn" href="#/deals">② 建第一个商机</a>' +
          '<a class="btn" href="#/followups">③ 记第一条跟进</a>' +
        '</div></div>';
    }

    root.innerHTML =
      slaHtml + kpi + emptyGuide +
      '<div class="card">' +
        '<div class="card-head"><h2>今日待跟进 <span class="badge warn">' + todos.length + '</span></h2>' +
          '<a class="btn btn-sm" href="#/followups">全部跟进</a></div>' +
        todoHtml +
      '</div>' +
      '<div class="card">' +
        '<div class="card-head"><h2>订单待办</h2><a class="btn btn-sm" href="#/orders">管理订单</a></div>' +
        '<div class="grid-kpi">' + orderChips + '</div>' +
      '</div>' +
      '<div class="card">' +
        '<div class="card-head"><h2>最近动态</h2>' +
          '<span class="small muted">金额点右上 👁 查看</span></div>' +
        actHtml +
      '</div>';

    /* ---------- 「记一条」弹窗（不跳页） ---------- */
    $$('button[data-log-fu]', root).forEach(function (btn) {
      btn.addEventListener('click', function () {
        var cid = Number(btn.getAttribute('data-log-fu'));
        openFollowupModal(cid);
      });
    });
  });
}

/* 弹窗内记一条跟进：演示版直接插进内存数据，会话内可见 */
function openFollowupModal(customerId) {
  var cust = (window.DEMO.customers || []).filter(function (c) { return c.id === customerId; })[0] || { name: '客户' };

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content">' +
      '<div class="modal-header"><h3>给 ' + esc(cust.name) + ' 记一条跟进</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="quickFuForm">' +
        '<div class="field"><label>跟进内容 *</label>' +
          '<textarea name="content" maxlength="2000" rows="4" required ' +
            'placeholder="聊了什么、客户什么态度、下一步做什么"></textarea></div>' +
        '<div class="row-2">' +
          '<div class="field"><label>下次跟进日期</label>' +
            '<input type="date" name="next_date" value="' + dayAfter(3) + '"></div>' +
          '<div class="field"><label>跟进方式</label>' +
            '<select name="method"><option value="phone">电话</option><option value="wechat" selected>微信</option>' +
            '<option value="visit">到面/上门</option><option value="online">线上</option></select></div>' +
        '</div>' +
        '<div class="form-actions">' +
          '<button type="button" class="btn modal-close-2">取消</button>' +
          '<button type="submit" class="btn btn-primary">保存跟进</button>' +
        '</div>' +
      '</form>' +
    '</div>';
  document.body.appendChild(modal);

  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  $('.modal-close', modal).addEventListener('click', close);
  $('.modal-close-2', modal).addEventListener('click', close);

  $('#quickFuForm', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var content = String($('[name="content"]', modal).value || '').trim();
    if (!content) { toast('跟进内容不能为空', true); return; }
    var nextDate = $('[name="next_date"]', modal).value || null;
    var method = $('[name="method"]', modal).value;

    /* 演示：写进内存，会话内立刻能看到效果 */
    window.DEMO.followups.push({
      id: Date.now(),
      object_type: 'customer',
      object_id: customerId,
      customer_id: customerId,
      deal_id: null,
      method: method,
      content: content,
      next_date: nextDate,
      created_at: new Date().toISOString().slice(0, 19)
    });

    close();
    toast('已记录跟进（演示：仅本次会话有效）');
    render();
  });
}

function dayAfter(n) {
  var d = new Date();
  d.setDate(d.getDate() + n);
  return d.getFullYear() + '-' + ((d.getMonth() + 1) < 10 ? '0' : '') + (d.getMonth() + 1) +
    '-' + (d.getDate() < 10 ? '0' : '') + d.getDate();
}