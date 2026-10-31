/* ============================================================================
 * 统计（Demo 版，覆盖正式版 views/stats.js）
 * 2026-10-31 定稿：多一些图表，更直观
 *   · 4 个 KPI
 *   · 月度成交趋势（近 6 个月柱状）
 *   · 线索→商机→订单 转化漏斗
 *   · 商机阶段分布（横向条）
 *   · 订单状态分布（横向条）
 *   · 客户来源分布（环形）
 *   · 售后类型分布（横向条）
 * ==========================================================================*/

/* 纵向柱状图 */
function vBarChart(items, opts) {
  opts = opts || {};
  var max = Math.max.apply(null, items.map(function (i) { return i.value; }).concat([1]));
  return '<div class="vbar-chart">' + items.map(function (it) {
    var h = max ? Math.round((it.value / max) * 100) : 0;
    return '<div class="vbar-col">' +
      '<div class="vbar-val">' + (opts.money ? money(it.value) : it.value) + '</div>' +
      '<div class="vbar-track"><div class="vbar-fill' + (it.highlight ? ' hot' : '') +
        '" style="height:' + Math.max(h, 2) + '%"></div></div>' +
      '<div class="vbar-label">' + esc(it.label) + '</div>' +
    '</div>';
  }).join('') + '</div>';
}

/* 横向条形图 */
function hBarChart(items) {
  var max = Math.max.apply(null, items.map(function (i) { return i.value; }).concat([1]));
  return '<div class="hbar-chart">' + items.map(function (it) {
    var w = Math.round((it.value / max) * 100);
    return '<div class="hbar-row">' +
      '<div class="hbar-label">' + esc(it.label) + '</div>' +
      '<div class="hbar-track"><div class="hbar-fill' + (it.cls ? ' ' + it.cls : '') +
        '" style="width:' + (it.value ? Math.max(w, 3) : 0) + '%"></div></div>' +
      '<div class="hbar-val">' + it.value + (it.unit || '') + '</div>' +
    '</div>';
  }).join('') + '</div>';
}

/* 环形图（conic-gradient） */
function donutChart(items) {
  var total = items.reduce(function (s, i) { return s + i.value; }, 0) || 1;
  var palette = ['#1f6feb', '#22a06b', '#f59e0b', '#8b5cf6', '#ef4444', '#0ea5e9', '#64748b'];
  var acc = 0;
  var segs = items.map(function (it, i) {
    var from = (acc / total) * 360;
    acc += it.value;
    var to = (acc / total) * 360;
    return palette[i % palette.length] + ' ' + from.toFixed(1) + 'deg ' + to.toFixed(1) + 'deg';
  }).join(', ');
  return '<div class="donut-wrap">' +
    '<div class="donut" style="background: conic-gradient(' + segs + ')">' +
      '<div class="donut-hole"><b>' + total + '</b><span>合计</span></div>' +
    '</div>' +
    '<div class="donut-legend">' + items.map(function (it, i) {
      return '<div class="donut-item"><i style="background:' + palette[i % palette.length] + '"></i>' +
        esc(it.label) + '<b>' + it.value + '</b></div>';
    }).join('') + '</div>' +
  '</div>';
}

/* 漏斗 */
function funnelChart(stages) {
  var top = stages.length ? stages[0].value || 1 : 1;
  return '<div class="funnel">' + stages.map(function (s, i) {
    var pct = Math.round(((s.value || 0) / top) * 100);
    var rate = i === 0 ? '' : ('转化 ' + Math.round(((s.value || 0) / (stages[i - 1].value || 1)) * 100) + '%');
    return '<div class="funnel-row">' +
      '<div class="funnel-name">' + esc(s.label) + '</div>' +
      '<div class="funnel-track"><div class="funnel-fill" style="width:' + Math.max(pct, 6) + '%">' +
        '<span>' + (s.value || 0) + (s.unit || '') + '</span></div></div>' +
      '<div class="funnel-rate small muted">' + esc(rate) + '</div>' +
    '</div>';
  }).join('') + '</div>';
}

/* 商机阶段累计口径：到达过第 n 阶段（含之后各阶段）的数量 */
function dealReached(n) {
  var order = ['confirm', 'quote', 'negotiate', 'won'];
  return (window.DEMO.deals || []).filter(function (d) {
    return order.indexOf(d.stage) >= n;
  }).length;
}

function viewStats(root) {
  var D = window.DEMO;
  var today = todayISO();
  var monthKey = today.slice(0, 7);
  var won = D.deals.filter(function (d) { return d.stage === 'won'; });
  var monthWon = won.filter(function (d) { return d.closed_at && d.closed_at.slice(0, 7) === monthKey; });
  var monthNewCust = D.customers.filter(function (c) { return String(c.created_at).slice(0, 7) === monthKey; }).length;
  var repeat = D.customers.filter(function (c) {
    return D.deals.filter(function (d) { return d.customer_id === c.id; }).length >= 2;
  }).length;

  /* 近 6 个月成交趋势 */
  var months = [];
  for (var i = 5; i >= 0; i--) {
    var dt = new Date();
    dt.setMonth(dt.getMonth() - i);
    var key = dt.getFullYear() + '-' + ('0' + (dt.getMonth() + 1)).slice(-2);
    var amt = won.filter(function (d) { return d.closed_at && d.closed_at.slice(0, 7) === key; })
      .reduce(function (s, d) { return s + Number(d.amount || 0); }, 0);
    months.push({ label: (dt.getMonth() + 1) + '月', value: amt, highlight: key === monthKey });
  }

  var dealsByStage = STAGES.map(function (p) {
    return {
      label: p[1],
      value: D.deals.filter(function (d) { return d.stage === p[0]; }).length,
      cls: p[0] === 'won' ? 'ok' : p[0] === 'lost' ? 'danger' : ''
    };
  });

  var ordersByStatus = ORDER_STATUS.map(function (p) {
    return { label: p[1], value: D.orders.filter(function (o) { return o.status === p[0]; }).length };
  });

  var sourceCount = {};
  D.customers.forEach(function (c) {
    var k = c.source === 'other' && c.source_other ? c.source_other : (SOURCE_LABELS[c.source] || '其他');
    sourceCount[k] = (sourceCount[k] || 0) + 1;
  });
  var sources = Object.keys(sourceCount).map(function (k) { return { label: k, value: sourceCount[k] }; })
    .sort(function (a, b) { return b.value - a.value; });

  var asCount = {};
  D.aftersales.forEach(function (a) {
    var k = AFTERSALE_TYPE_LABEL[a.type] || a.type;
    asCount[k] = (asCount[k] || 0) + 1;
  });
  var asTypes = Object.keys(asCount).map(function (k) { return { label: k, value: asCount[k] }; });

  var convertedLeads = D.leads.filter(function (l) { return l.status === 'converted'; }).length;

  root.innerHTML =
    '<div class="card" style="padding:10px 16px"><span class="small muted">金额默认遮罩，点右上角 👁 显示</span></div>' +
    '<div class="grid-kpi">' +
      '<div class="kpi"><div class="label">客户总数</div><div class="value">' + D.customers.length + '</div>' +
        '<div class="sub">本月新增 ' + monthNewCust + '</div></div>' +
      '<div class="kpi"><div class="label">本月成交</div><div class="value">' + money(monthWon.reduce(function (s, d) { return s + Number(d.amount || 0); }, 0)) + '</div>' +
        '<div class="sub">' + monthWon.length + ' 单</div></div>' +
      '<div class="kpi"><div class="label">进行中商机</div><div class="value">' +
        D.deals.filter(function (d) { return d.stage !== 'won' && d.stage !== 'lost'; }).length + '</div>' +
        '<div class="sub">老客 ' + repeat + ' 位</div></div>' +
      '<div class="kpi"><div class="label">待处理售后</div><div class="value">' +
        D.aftersales.filter(function (a) { return a.status === 'pending'; }).length + '</div>' +
        '<div class="sub">累计 ' + D.aftersales.length + ' 单</div></div>' +
    '</div>' +

    '<div class="card">' +
      '<div class="card-head"><h2>月度成交趋势</h2><span class="small muted">近 6 个月，按成交金额</span></div>' +
      vBarChart(months, { money: true }) +
    '</div>' +

    '<div class="chart-2col">' +
      '<div class="card">' +
        '<div class="card-head"><h2>商机销售漏斗</h2><span class="small muted">累计到达该阶段的数量</span></div>' +
        funnelChart([
          { label: '需求确认', value: dealReached(0), unit: ' 个' },
          { label: '报价', value: dealReached(1), unit: ' 个' },
          { label: '成交洽谈', value: dealReached(2), unit: ' 个' },
          { label: '赢单', value: dealReached(3), unit: ' 个' }
        ]) +
      '</div>' +
      '<div class="card">' +
        '<div class="card-head"><h2>线索转化</h2><span class="small muted">线索池 → 客户</span></div>' +
        (D.leads.length
          ? hBarChart([
              { label: '线索总数', value: D.leads.length, unit: ' 条' },
              { label: '跟进中', value: D.leads.filter(function (l) { return l.status === 'following' || l.status === 'new'; }).length, unit: ' 条' },
              { label: '已转化', value: convertedLeads, unit: ' 条', cls: 'ok' },
              { label: '已失效', value: D.leads.filter(function (l) { return l.status === 'invalid'; }).length, unit: ' 条', cls: 'danger' }
            ]) + '<p class="small muted">转化率 <b>' + Math.round(convertedLeads / D.leads.length * 100) + '%</b>（已转化 / 线索总数）</p>'
          : '<p class="empty">暂无线索</p>') +
      '</div>' +
    '</div>' +

    '<div class="chart-2col">' +
      '<div class="card">' +
        '<div class="card-head"><h2>商机阶段分布</h2><span class="small muted">共 ' + D.deals.length + ' 个</span></div>' +
        hBarChart(dealsByStage) +
      '</div>' +
      '<div class="card">' +
        '<div class="card-head"><h2>订单状态分布</h2><span class="small muted">共 ' + D.orders.length + ' 单</span></div>' +
        hBarChart(ordersByStatus) +
      '</div>' +
    '</div>' +

    '<div class="chart-2col">' +
      '<div class="card">' +
        '<div class="card-head"><h2>客户来源</h2><span class="small muted">按来源人数</span></div>' +
        donutChart(sources) +
      '</div>' +
      '<div class="card">' +
        '<div class="card-head"><h2>售后类型</h2><span class="small muted">共 ' + D.aftersales.length + ' 单</span></div>' +
        (asTypes.length ? hBarChart(asTypes) : '<p class="empty">暂无售后</p>') +
      '</div>' +
    '</div>' +

    '<div class="card">' +
      '<div class="card-head"><h2>口径说明</h2></div>' +
      '<ul class="small muted" style="margin:0;padding-left:18px;line-height:1.9">' +
        '<li><b>本月成交</b>：阶段为「赢单」、且成交时间在本月的商机，按报价合计。</li>' +
        '<li><b>月度趋势</b>：同样口径，往前推 6 个自然月（本月高亮）。</li>' +
        '<li><b>转化漏斗</b>：线索数 → 已转化线索 → 商机数 → 赢单数 → 订单数，百分比是相对上一层。</li>' +
        '<li><b>商机销售漏斗</b>：按「累计到达」算——商机现在处于报价，说明它经过了需求确认，所以越往下越少；流失单不计入。</li>' +
        '<li><b>线索转化</b>：只统计线索池（存量客户导入的不算），所以转化率不会超过 100%。</li>' +
        '<li><b>老客</b>：名下商机 ≥2 个的客户数。</li>' +
      '</ul>' +
    '</div>';
}