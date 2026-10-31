/* 统计页面（2026-10-31 对齐 demo 定稿：8 块）
 *
 * 数据源换成后端 GET /stats（一次算好 7 组数据 + KPI），
 * 前端只负责画：KPI 行 / 月度成交趋势 / 销售漏斗 / 线索转化 / 三个阶段+来源分布 / 口径说明。
 * demo 里同样是这 8 块，差别只是 demo 用假数据。
 */

/* /stats 的数组 → barsHtml 需要的 { 计数对象, [[key,label]] } */
function statsCounts(list) {
  var counts = {};
  (list || []).forEach(function (it) { counts[it.key] = it.value; });
  return counts;
}

function statsPairs(list, fallback) {
  var pairs = (list || []).map(function (it) { return [it.key, it.label]; });
  return pairs.length ? pairs : (fallback || []);
}

function statsCard(title, sub, barsHtmlStr) {
  return '<div class="card">' +
    '<div class="card-head"><h2>' + esc(title) + '</h2>' +
    (sub ? '<span class="small muted">' + esc(sub) + '</span>' : '') + '</div>' +
    barsHtmlStr +
    '</div>';
}

function viewStats(root) {
  return api('/stats?months=6').then(function (d) {
    var kpis = (d && d.kpis) || {};
    var months = (d && d.months) || [];
    var funnel = (d && d.funnel) || [];
    var lc = (d && d.lead_conversion) || {};
    var stageList = (d && d.deals_by_stage) || [];
    var orderList = (d && d.orders_by_status) || [];
    var sourceList = (d && d.customer_sources) || [];
    var asList = (d && d.aftersale_types) || [];
    var monthWon = kpis.month_won || { count: 0, amount: 0 };

    var stageTotal = stageList.reduce(function (s, it) { return s + Number(it.value || 0); }, 0);
    var trendTotal = months.reduce(function (s, it) { return s + Number(it.value || 0); }, 0);

    root.innerHTML =
      '<div class="grid-kpi">' +
        '<div class="kpi"><div class="label">客户总数</div><div class="value">' + (kpis.customers_total || 0) + '</div></div>' +
        '<div class="kpi"><div class="label">本月新客</div><div class="value">' + (kpis.month_new_customers || 0) + '</div></div>' +
        '<div class="kpi"><div class="label">本月成交</div><div class="value">' + money(monthWon.amount) +
          '</div><div class="sub">' + (monthWon.count || 0) + ' 单</div></div>' +
        '<div class="kpi"><div class="label">在谈商机</div><div class="value">' + (kpis.active_deals || 0) +
          '</div><div class="sub">报价 ' + money(kpis.active_deal_amount) + '</div></div>' +
        '<div class="kpi"><div class="label">老客户</div><div class="value">' + (kpis.repeat_customers || 0) +
          '</div><div class="sub">名下 ≥2 个商机</div></div>' +
        '<div class="kpi"><div class="label">待处理售后</div><div class="value">' + (kpis.pending_aftersales || 0) + '</div></div>' +
      '</div>' +

      statsCard('月度成交趋势', '近 6 个月成交金额，合计 ' + money(trendTotal),
        barsHtml(statsCounts(months), statsPairs(months))) +

      statsCard('商机销售漏斗', '累计到达（成交也算经过报价/待确认）',
        barsHtml(statsCounts(funnel), statsPairs(funnel))) +

      '<div class="card">' +
        '<div class="card-head"><h2>线索转化</h2>' +
        '<span class="small muted">转化率 ' + (lc.rate || 0) + '%</span></div>' +
        '<div class="grid-kpi">' +
          '<div class="kpi"><div class="label">线索总数</div><div class="value">' + (lc.total || 0) + '</div></div>' +
          '<div class="kpi"><div class="label">跟进中 / 新</div><div class="value">' + (lc.following || 0) + '</div></div>' +
          '<div class="kpi"><div class="label">已转化</div><div class="value">' + (lc.converted || 0) + '</div></div>' +
          '<div class="kpi"><div class="label">已失效</div><div class="value">' + (lc.invalid || 0) + '</div></div>' +
        '</div>' +
      '</div>' +

      statsCard('商机阶段分布', '共 ' + stageTotal + ' 个商机',
        barsHtml(statsCounts(stageList), statsPairs(stageList))) +

      statsCard('订单状态分布', '', barsHtml(statsCounts(orderList), statsPairs(orderList))) +

      statsCard('客户来源分布', '', barsHtml(statsCounts(sourceList), statsPairs(sourceList))) +

      statsCard('售后类型分布', '', barsHtml(statsCounts(asList), statsPairs(asList))) +

      '<div class="card">' +
        '<div class="card-head"><h2>口径说明</h2></div>' +
        '<ul class="small muted" style="margin:0;padding-left:18px">' +
          '<li><b>本月成交</b>：阶段为「成交」且成交时间在本月的商机，金额按商机报价合计。</li>' +
          '<li><b>在谈商机</b>：阶段仍是报价 / 待客户确认的商机数，金额为这些商机的报价合计。</li>' +
          '<li><b>老客户</b>：名下商机累计 ≥2 个的客户数（不论是否成交）。</li>' +
          '<li><b>线索转化率</b>：已转化线索 ÷ 线索总数（含新 / 跟进中 / 已转化 / 已失效）。</li>' +
          '<li><b>漏斗</b>：累计到达口径 —— 处于「成交」的商机同时计入报价、待确认两档。</li>' +
        '</ul>' +
      '</div>';
  });
}
