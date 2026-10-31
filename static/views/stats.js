/* 统计页面（V1 视图迁移到 V2 拆分结构）
 * barsHtml 已移到 views/shared.js（工作台也要用） */

function viewStats(root) {
  return api('/dashboard').then(function (d) {
    var stats = d.stats || {};
    var monthWon = d.month_won || stats.month_won || { count: 0, amount: 0 };
    var byStage = stats.deals_by_stage || {};
    var stageTotal = Object.keys(byStage).reduce(function (sum, key) { return sum + Number(byStage[key] || 0); }, 0);

    root.innerHTML =
      '<div class="grid-kpi">' +
        '<div class="kpi"><div class="label">客户总数</div><div class="value">' + (stats.customers_total || 0) + '</div></div>' +
        '<div class="kpi"><div class="label">本月新客</div><div class="value">' + (stats.month_new_customers || 0) + '</div></div>' +
        '<div class="kpi"><div class="label">本月成交</div><div class="value">' + money(monthWon.amount) +
          '</div><div class="sub">' + (monthWon.count || 0) + ' 单</div></div>' +
        '<div class="kpi"><div class="label">老客</div><div class="value">' + (stats.repeat_customers || 0) +
          '</div><div class="sub">名下 ≥2 个商机</div></div>' +
      '</div>' +
      '<div class="card">' +
        '<div class="card-head"><h2>商机阶段分布</h2><span class="small muted">共 ' + stageTotal + ' 个商机</span></div>' +
        barsHtml(byStage) +
      '</div>' +
      '<div class="card">' +
        '<div class="card-head"><h2>口径说明</h2></div>' +
        '<ul class="small muted" style="margin:0;padding-left:18px">' +
          '<li><b>本月成交</b>：阶段为「已成交」且成交时间在本月的商机，金额按商机报价合计。</li>' +
          '<li><b>老客</b>：名下商机累计 ≥2 个的客户数（不论是否成交），客户列表里的「老客」标记同口径。</li>' +
          '<li><b>今日待跟进</b>：下次跟进日期 ≤ 今天、且关联商机未成交/未流失；逾期天数按自然日算。</li>' +
          '<li><b>本月新客</b>：建档时间在本月的客户数（按服务器本地时区）。</li>' +
        '</ul>' +
      '</div>';
  });
}

/* ================= CSV 导入 ================= */
