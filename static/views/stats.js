/* 统计：按工作台/统计 demo 的 8 块分析结构实现。
 * 后端 GET /stats?range=... 返回同一形状，前端只负责可视化与区间切换。 */

var statsCurrentRange = window.__crmStatsRange || "6m";
var statsCurrentData = null;

function statsIcon(name) {
  var icons = {
    lead: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"></circle><path d="M5 20c.8-4 3.1-6 7-6s6.2 2 7 6"></path><path d="M18 4v4M16 6h4"></path></svg>',
    wand: '<svg viewBox="0 0 24 24"><path d="m4 20 12-12M14 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2ZM19 13l.7 1.3L21 15l-1.3.7L19 17l-.7-1.3L17 15l1.3-.7L19 13Z"></path></svg>',
    chart: '<svg viewBox="0 0 24 24"><path d="M5 20V10m7 10V4m7 16v-7M3 20h18"></path></svg>',
    won: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="m8 12 2.5 2.5L16 9"></path></svg>',
    service: '<svg viewBox="0 0 24 24"><path d="M4 13a8 8 0 0 1 16 0"></path><path d="M4 13v5h3v-5H4Zm13 0h3v5h-3v-5Z"></path><path d="M10 21h4"></path></svg>',
    eye: '<svg viewBox="0 0 24 24"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.6"></circle></svg>',
    eyeOff: '<svg viewBox="0 0 24 24"><path d="m4 4 16 16M10.6 6.1A9 9 0 0 1 12 6c6 0 9.5 6 9.5 6a15 15 0 0 1-2.2 2.8M6.2 7.8A17 17 0 0 0 2.5 12s3.5 6 9.5 6a9 9 0 0 0 3.6-.7"></path></svg>'
  };
  return icons[name] || "";
}

function statsMoneyVisible() {
  return window.__crmMoneyVisible === true;
}

function statsMoney(value, compact) {
  var number = Number(value || 0);
  if (!statsMoneyVisible()) { return compact ? "¥••" : "¥••••"; }
  if (compact && Math.abs(number) >= 10000) {
    return "¥" + (number / 10000).toFixed(number % 10000 === 0 ? 0 : 1) + "万";
  }
  return money(number);
}

function statsRangeTabs(active) {
  var ranges = [
    ["7d", "近7天"],
    ["month", "本月"],
    ["3m", "近3月"],
    ["6m", "近6月"],
    ["year", "今年"]
  ];
  return '<div class="ds-segmented" role="group" aria-label="统计区间">' +
    ranges.map(function (pair) {
      return '<button type="button" class="' + (active === pair[0] ? "is-active" : "") +
        '" data-stat-range="' + pair[0] + '">' + pair[1] + "</button>";
    }).join("") + "</div>";
}

function statsKpi(options) {
  return '<div class="ds-kpi ' + esc(options.tone) + '">' +
    '<div class="ds-kpi-head"><span>' + esc(options.label) + '</span><span class="ds-kpi-icon">' +
      statsIcon(options.icon) + "</span></div>" +
    '<div class="ds-kpi-value' + (options.money ? " money-value" : "") + '">' + options.value + "</div>" +
    '<div class="ds-kpi-foot">' + options.foot + "</div></div>";
}

function statsFunnel(items) {
  var top = Math.max(Number((items[0] || {}).value || 0), 1);
  return '<div class="ds-funnel">' + items.map(function (item, index) {
    var previous = index ? Number(items[index - 1].value || 0) : 0;
    var rate = index ? (previous ? Math.round(Number(item.value || 0) / previous * 100) : 0) : null;
    var width = Math.max(Number(item.value || 0) / top * 100, Number(item.value || 0) ? 22 : 10);
    var tip = item.label + "：" + item.value + (index ? "，较上一层 " + rate + "%" : "");
    return '<button type="button" class="ds-funnel-row" data-chart-tip="' + esc(tip) + '">' +
      '<span class="ds-funnel-label">' + esc(item.label) + "</span>" +
      '<span class="ds-funnel-visual"><i style="width:' + width.toFixed(1) + '%"><b>' +
        Number(item.value || 0) + "</b></i></span>" +
      '<span class="ds-funnel-rate">' + (index ? rate + "%" : "起点") + "</span></button>";
  }).join("") + '<div class="ds-chart-legend"><span>百分比为相对上一层转化率</span><span>·</span>' +
    "<span>漏斗只统计当期新建线索</span></div></div>";
}

function statsTrend(trend) {
  var chart = trend || {};
  var labels = chart.labels || [];
  var values = chart.values || [];
  var counts = chart.counts || [];
  var width = 1000;
  var left = 42;
  var right = 970;
  var top = 34;
  var bottom = 258;
  var countTop = 48;
  var countBottom = 226;
  var maxAmount = Math.max.apply(null, values.concat([1]));
  var maxCount = Math.max.apply(null, counts.concat([1]));
  var band = (right - left) / Math.max(labels.length, 1);
  var barWidth = Math.min(58, band * 0.48);
  var centers = labels.map(function (_, index) { return left + band * (index + 0.5); });
  var linePoints = centers.map(function (center, index) {
    var y = countBottom - (Number(counts[index] || 0) / maxCount) * (countBottom - countTop);
    return center.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");

  var bars = labels.map(function (label, index) {
    var value = Number(values[index] || 0);
    var count = Number(counts[index] || 0);
    var height = value ? Math.max(value / maxAmount * (bottom - top), 8) : 2;
    var x = centers[index] - barWidth / 2;
    var y = bottom - height;
    var tip = label + "：" + statsMoney(value) + "，" + count + " 单";
    return '<g class="ds-chart-point" data-chart-tip="' + esc(tip) + '">' +
      '<title>' + esc(tip) + "</title>" +
      '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + barWidth.toFixed(1) +
        '" height="' + height.toFixed(1) + '" rx="7" class="ds-chart-bar' +
        (index === labels.length - 1 ? " highlight" : "") + '"></rect>' +
      '<rect x="' + (centers[index] - band / 2).toFixed(1) + '" y="' + top + '" width="' +
        band.toFixed(1) + '" height="' + (bottom - top) + '" class="ds-chart-hit"></rect>' +
      '<text x="' + centers[index].toFixed(1) + '" y="' + Math.max(y - 11, 18).toFixed(1) +
        '" class="ds-chart-bar-label">' + esc(statsMoney(value, true)) + "</text>" +
      '<text x="' + centers[index].toFixed(1) + '" y="291" class="ds-chart-axis-label">' +
        esc(label) + "</text></g>";
  }).join("");
  var dots = centers.map(function (center, index) {
    var y = countBottom - (Number(counts[index] || 0) / maxCount) * (countBottom - countTop);
    return '<circle class="ds-chart-dot" cx="' + center.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="5"></circle>';
  }).join("");
  var total = values.reduce(function (sum, value) { return sum + Number(value || 0); }, 0);
  var countTotal = counts.reduce(function (sum, value) { return sum + Number(value || 0); }, 0);
  return '<section class="ds-card ds-chart-card"><div class="ds-card-head"><div><h2>' +
    esc(chart.title || "成交趋势") + '</h2></div><span>' + esc(chart.caption || "") + "</span></div>" +
    '<div class="ds-chart-body"><div class="ds-trend-total"><b>' + statsMoney(total) +
      "</b><span>成交金额 · " + countTotal + " 单</span></div>" +
      '<div class="ds-combo-wrap"><svg class="ds-combo-svg" viewBox="0 0 ' + width +
        ' 310" role="img" aria-label="成交金额和单数趋势">' +
        '<g class="ds-chart-grid">' + [0, 1, 2, 3].map(function (index) {
          var y = top + (bottom - top) / 3 * index;
          return '<line x1="' + left + '" y1="' + y + '" x2="' + right + '" y2="' + y + '"></line>';
        }).join("") + "</g>" + bars +
        '<polyline class="ds-chart-line" points="' + linePoints + '"></polyline>' + dots +
      "</svg></div>" +
      '<div class="ds-chart-legend"><span><i class="bar"></i>成交金额</span>' +
        '<span><i class="line"></i>成交单数</span><span><i class="current"></i>当前周期</span>' +
        "<span>悬停或点击查看明细</span></div></div></section>";
}

function statsColors(name) {
  var colors = {
    blue: "#2569e8", green: "#138a64", amber: "#d88a18", red: "#d64545",
    violet: "#7656d8", cyan: "#16849e", grey: "#8c98a8"
  };
  return colors[name] || colors.grey;
}

function statsDonut(items, valueGetter, center, formatValue) {
  var values = items.map(valueGetter);
  var total = values.reduce(function (sum, value) { return sum + Number(value || 0); }, 0);
  var cursor = 0;
  var segments = items.map(function (item, index) {
    var start = total ? cursor / total * 360 : 0;
    cursor += Number(values[index] || 0);
    var end = total ? cursor / total * 360 : 360;
    return statsColors(item.tone) + " " + start.toFixed(1) + "deg " + end.toFixed(1) + "deg";
  }).join(", ");
  return '<div class="ds-donut-panel"><div class="ds-donut" style="background:' +
    (total ? "conic-gradient(" + segments + ")" : "#edf1f5") + '">' +
    '<div class="ds-donut-hole"><b>' + formatValue(total) + "</b><span>" + esc(center) +
    "</span></div></div><div class=\"ds-donut-legend\">" + items.map(function (item, index) {
      var pct = total ? Math.round(Number(values[index] || 0) / total * 100) : 0;
      return '<button type="button" data-chart-tip="' + esc((item.name || item.label) + "：" +
        formatValue(values[index]) + "，" + pct + "%") + '"><i style="background:' +
        statsColors(item.tone) + '"></i><span>' + esc(item.name || item.label) +
        "</span><b>" + pct + "%</b></button>";
    }).join("") + "</div></div>";
}

function statsSources(sources) {
  sources = sources || [];
  var totalAmount = sources.reduce(function (sum, item) { return sum + Number(item.amount || 0); }, 0);
  var maxLeads = Math.max.apply(null, sources.map(function (item) { return Number(item.leads || 0); }).concat([1]));
  var colored = sources.map(function (item, index) {
    var tones = ["green", "violet", "blue", "amber", "cyan", "grey"];
    return Object.assign({}, item, { tone: item.tone || tones[index % tones.length] });
  });
  if (!colored.length) {
    return '<section class="ds-card"><div class="ds-card-head"><div><h2>客源分析</h2></div></div>' +
      '<div class="ds-empty compact"><b>本期暂无新增线索</b><small>切换时间区间或先录一条线索。</small></div></section>';
  }
  return '<section class="ds-card ds-stats-panel"><div class="ds-card-head"><div><h2>客源分析</h2></div>' +
    "<span>成交结构 + 获客转化对比</span></div>" +
    '<div class="ds-source-grid"><div class="ds-source-donut"><div class="ds-subhead"><b>成交金额来源</b>' +
      "<span>按来源成交额占比</span></div>" +
      statsDonut(colored, function (item) { return item.amount; }, "成交金额",
        function (value) { return statsMoney(value, true); }) + "</div>" +
      '<div><div class="ds-subhead"><b>获客与转化</b><span>新增线索 / 已转化</span></div>' +
      '<div class="ds-source-list">' + colored.map(function (item) {
        return '<button type="button" class="ds-source-row" data-chart-tip="' +
          esc(item.name + "：新增 " + item.leads + " 条，转化 " + item.converted + " 条，转化率 " + item.rate + "%") +
          '"><span class="ds-source-name"><i class="' + item.tone + '"></i>' + esc(item.name) + "</span>" +
          '<span class="ds-source-bars"><i class="lead" style="width:' +
            (Number(item.leads || 0) / maxLeads * 100).toFixed(1) + '%"></i><i class="converted" style="width:' +
            (Number(item.converted || 0) / maxLeads * 100).toFixed(1) + '%"></i></span>' +
          '<span class="ds-source-count">' + item.leads + " / " + item.converted + "</span></button>";
      }).join("") + "</div></div></div>" +
    '<div class="ds-source-head"><b>来源明细</b><span>金额单位：元</span></div>' +
    '<div class="ds-table-wrap"><table class="ds-table"><thead><tr><th>来源</th><th>新增线索</th>' +
      "<th>已转化</th><th>转化率</th><th>成交单数</th><th>成交金额</th><th>金额占比</th></tr></thead><tbody>" +
      colored.map(function (item) {
        return "<tr><td><span class=\"ds-source-name\"><i class=\"" + item.tone + "\"></i>" +
          esc(item.name) + "</span></td><td>" + item.leads + "</td><td>" + item.converted +
          "</td><td><span class=\"ds-rate\">" + item.rate + "%</span></td><td>" + item.won +
          "</td><td>" + statsMoney(item.amount) + "</td><td>" +
          (totalAmount ? Math.round(Number(item.amount || 0) / totalAmount * 100) : 0) + "%</td></tr>";
      }).join("") + "</tbody></table></div></section>";
}

function statsProducts(products) {
  products = products || [];
  var max = Math.max.apply(null, products.map(function (item) { return Number(item.amount || 0); }).concat([1]));
  return '<section class="ds-card"><div class="ds-card-head"><div><h2>产品成交排行</h2></div>' +
    "<span>按本期成交金额</span></div>" +
    (products.length ? '<div class="ds-ranking">' + products.map(function (item, index) {
      return '<div class="ds-rank"><span class="ds-rank-no">' + (index + 1) + "</span>" +
        '<span class="ds-rank-name"><b>' + esc(item.name) + "</b><small>" + esc(item.code || "—") +
        " · " + item.count + " 套</small></span><span class=\"ds-rank-track\"><i style=\"width:" +
        (Number(item.amount || 0) ? Math.max(Number(item.amount || 0) / max * 100, 3) : 0) +
        '%"></i></span><span class="ds-rank-amount">' + statsMoney(item.amount) + "</span></div>";
    }).join("") + "</div>" : '<div class="ds-empty compact"><b>本期还没有成交产品</b><small>成交后会生成产品排行。</small></div>') +
    "</section>";
}

function statsStages(stages) {
  stages = stages || [];
  var max = Math.max.apply(null, stages.map(function (item) { return Number(item.value || 0); }).concat([1]));
  return '<section class="ds-card"><div class="ds-card-head"><div><h2>商机阶段</h2></div>' +
    "<span>本期新建商机的当前阶段</span></div><div class=\"ds-stage-chart\">" +
    stages.map(function (item) {
      return '<button type="button" class="ds-stage" data-chart-tip="' + esc(item.label + "：" + item.value + " 个") +
        '"><span class="ds-stage-value">' + item.value + '</span><span class="ds-stage-bar ' +
        esc(item.tone || "blue") + '" style="height:' + Math.max(Number(item.value || 0) / max * 100, 8) +
        '%"></span><span class="ds-stage-label">' + esc(item.label) + "</span></button>";
    }).join("") + "</div></section>";
}

function statsOrders(items) {
  items = items || [];
  var total = Math.max(items.reduce(function (sum, item) { return sum + Number(item.value || 0); }, 0), 1);
  return '<section class="ds-card"><div class="ds-card-head"><div><h2>订单状态</h2></div>' +
    "<span>本期订单的当前履约进度</span></div><div class=\"ds-pipeline\"><div class=\"ds-pipeline-total\">" +
    "<b>" + items.reduce(function (sum, item) { return sum + Number(item.value || 0); }, 0) +
    "</b><span>本期订单</span></div><div class=\"ds-pipeline-bar\" role=\"img\" aria-label=\"订单状态分布\">" +
    items.map(function (item) {
      return '<button type="button" class="' + esc(item.tone || "grey") + '" style="flex:' +
        Math.max(Number(item.value || 0), 1) + '" data-chart-tip="' +
        esc(item.label + "：" + item.value + " 单，占 " + Math.round(Number(item.value || 0) / total * 100) + "%") +
        '">' + item.value + "</button>";
    }).join("") + "</div><div class=\"ds-pipeline-legend\">" + items.map(function (item) {
      return '<span><i style="background:' + statsColors(item.tone) + '"></i>' + esc(item.label) +
        "<b>" + item.value + "</b></span>";
    }).join("") + "</div></div></section>";
}

function statsAftersales(types, statuses, overdue) {
  types = types || [];
  statuses = statuses || [];
  var statusTotal = Math.max(statuses.reduce(function (sum, item) { return sum + Number(item.value || 0); }, 0), 1);
  return '<section class="ds-card"><div class="ds-card-head"><div><h2>售后分析</h2></div>' +
    "<span>" + Number(overdue || 0) + ' 单超过 3 天 SLA</span></div>' +
    '<div class="ds-aftersale-grid"><div><div class="ds-subhead"><b>售后类型</b><span>按单量占比</span></div>' +
      (types.length ? statsDonut(types, function (item) { return item.value; }, "售后单",
        function (value) { return value + " 单"; }) : '<div class="ds-empty compact"><b>本期暂无售后</b></div>') +
      '</div><div><div class="ds-subhead"><b>处理状态</b><span>当前进度</span></div>' +
      '<div class="ds-service-status">' + statuses.map(function (item) {
        return '<button type="button" data-chart-tip="' +
          esc(item.label + "：" + item.value + " 单，占 " + Math.round(Number(item.value || 0) / statusTotal * 100) + "%") +
          '"><span>' + esc(item.label) + "</span><i><b class=\"" + esc(item.tone || "blue") +
          "\" style=\"width:" + Math.max(Number(item.value || 0) / statusTotal * 100, Number(item.value || 0) ? 5 : 0) +
          '%"></b></i><strong>' + item.value + "</strong></button>";
      }).join("") + "</div></div></div></section>";
}

function renderStats(root, data) {
  var summary = data.summary || {};
  var insights = data.insights || [];
  var range = data.range || {};
  root.innerHTML = '<section class="ds-page ds-page-enter">' +
    '<header class="ds-heading"><div><p class="ds-eyebrow">Performance review</p>' +
      "<h1>销售统计</h1><p class=\"ds-subtitle\">从客源、转化、成交到履约，用一段时间的真实结果做判断。 " +
      '<span class="ds-range-note">' + esc(range.start || "") + " 至 " + esc(range.end || "") + "</span></p></div>" +
      '<div class="ds-heading-actions">' + statsRangeTabs(range.key || statsCurrentRange) +
        '<button type="button" class="ds-icon-button" data-stats-money aria-label="切换金额显示" title="切换金额显示">' +
        statsIcon(statsMoneyVisible() ? "eye" : "eyeOff") + "</button></div></header>" +
    '<div class="ds-kpi-grid ds-stats-kpis">' +
      statsKpi({
        label: "新增线索", value: Number(summary.newLeads || 0), tone: "blue", icon: "lead",
        foot: "<span>" + esc(range.label || "") + "新建</span><span>·</span><span>线索池口径</span>"
      }) +
      statsKpi({
        label: "线索转化率", value: Number(summary.leadRate || 0) + "%", tone: "green", icon: "wand",
        foot: "<span>" + Number(summary.convertedLeads || 0) + " 条已转化</span><span>·</span><span>不会超过 100%</span>"
      }) +
      statsKpi({
        label: "成交金额", value: statsMoney(summary.wonAmount, true), tone: "violet", icon: "chart", money: true,
        foot: "<span>" + Number(summary.wonCount || 0) + " 单成交</span><span>·</span><span>按成交日期</span>"
      }) +
      statsKpi({
        label: "成交单数", value: Number(summary.wonCount || 0) + " 单", tone: "amber", icon: "won",
        foot: "<span>平均客单 " + statsMoney(summary.avgDeal) + "</span>"
      }) +
      statsKpi({
        label: "售后单数", value: Number(summary.aftersales || 0), tone: "red", icon: "service",
        foot: "<span>" + Number(summary.overdueAftersales || 0) + " 单超时</span><span>·</span><span>SLA 3 天</span>"
      }) +
    "</div>" +
    (insights.length ? '<div class="ds-insight-band">' + insights.map(function (item) {
      return '<div class="ds-insight"><i>' + esc(item.icon || "数") + "</i><p>" + esc(item.text || "") + "</p></div>";
    }).join("") + "</div>" : "") +
    '<div class="ds-stats-grid">' + statsTrend(data.trend) +
      '<section class="ds-card ds-chart-card"><div class="ds-card-head"><div><h2>转化漏斗</h2></div>' +
        "<span>按本期线索追踪当前结果</span></div><div class=\"ds-chart-body\">" +
        statsFunnel(data.lead_funnel || []) + "</div></section></div>" +
    statsSources(data.sources) +
    '<div class="ds-stats-two">' + statsProducts(data.products) + statsStages(data.deals_by_stage) + "</div>" +
    '<div class="ds-stats-two">' + statsOrders(data.order_status) +
      statsAftersales(data.aftersale_types, data.service_status, summary.overdueAftersales) + "</div>" +
    '<details class="ds-card ds-methodology"><summary>查看统计口径</summary><div>' +
      "「近7天」包含今天在内的 7 个自然日。新增线索、成交金额、订单、售后与分布均按所选区间统计。" +
      "漏斗只统计区间内新建线索，并逐层取上一层子集；成交金额以商机成交时间 closed_at 为准；" +
      "售后超时按待处理或处理中超过 3 天计算。金额默认遮罩，可点右上角眼睛查看。" +
    "</div></details></section>";

  $$("[data-stat-range]", root).forEach(function (button) {
    button.addEventListener("click", function () {
      var rangeKey = button.getAttribute("data-stat-range");
      statsCurrentRange = rangeKey;
      window.__crmStatsRange = rangeKey;
      loadStatsRange(root, rangeKey);
    });
  });
  var moneyButton = $("[data-stats-money]", root);
  if (moneyButton) {
    moneyButton.addEventListener("click", function () {
      window.__crmMoneyVisible = !statsMoneyVisible();
      renderStats(root, statsCurrentData);
      bindStatsChartTips(root);
    });
  }
  bindStatsChartTips(root);
}

function bindStatsChartTips(root) {
  $$("[data-chart-tip]", root).forEach(function (element) {
    element.addEventListener("click", function () {
      toast(element.getAttribute("data-chart-tip") || "已选中图表数据");
    });
  });
}

function loadStatsRange(root, rangeKey) {
  root.innerHTML = '<div class="ds-page"><p class="loading">统计加载中…</p></div>';
  return api("/stats?range=" + encodeURIComponent(rangeKey)).then(function (data) {
    statsCurrentData = data;
    statsCurrentRange = (data.range && data.range.key) || rangeKey;
    window.__crmStatsRange = statsCurrentRange;
    renderStats(root, data);
  });
}

function viewStats(root) {
  return loadStatsRange(root, statsCurrentRange);
}
