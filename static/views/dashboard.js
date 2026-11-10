/* 工作台：按 PAGES-V2 §1 与 dashboard-stats-preview 定稿实现。
 * 真实数据全部来自 GET /dashboard，页面只负责展示与少量派生计算。 */

function dashIcon(name) {
  var icons = {
    calendar: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"></rect><path d="M8 3v4M16 3v4M3 10h18"></path><path d="m9 15 2 2 4-4"></path></svg>',
    alert: '<svg viewBox="0 0 24 24"><path d="M12 3 2.8 20h18.4L12 3Z"></path><path d="M12 9v4M12 17h.01"></path></svg>',
    order: '<svg viewBox="0 0 24 24"><path d="M6 3h12v18H6z"></path><path d="M9 8h6M9 12h6M9 16h4"></path></svg>',
    service: '<svg viewBox="0 0 24 24"><path d="M4 13a8 8 0 0 1 16 0"></path><path d="M4 13v5h3v-5H4Zm13 0h3v5h-3v-5Z"></path><path d="M10 21h4"></path></svg>',
    lead: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"></circle><path d="M5 20c.8-4 3.1-6 7-6s6.2 2 7 6"></path><path d="M18 4v4M16 6h4"></path></svg>',
    customer: '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.2"></circle><path d="M3.5 19c.6-3.7 2.5-5.5 5.5-5.5s4.9 1.8 5.5 5.5"></path><circle cx="17" cy="9" r="2.3"></circle><path d="M15.5 14.8c3.4-.5 5.2 1.2 5.7 4.2"></path></svg>',
    won: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="m8 12 2.5 2.5L16 9"></path></svg>',
    activity: '<svg viewBox="0 0 24 24"><path d="M3 12h4l2.3-6 4.2 12 2.3-6H21"></path></svg>'
  };
  return icons[name] || "";
}

function dashDateLabel() {
  var names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  var date = new Date();
  return date.getFullYear() + "年" + (date.getMonth() + 1) + "月" + date.getDate() + "日 · " +
    names[date.getDay()];
}

function dashGreeting() {
  var hour = new Date().getHours();
  if (hour < 11) { return "早上好"; }
  if (hour < 14) { return "中午好"; }
  if (hour < 18) { return "下午好"; }
  return "晚上好";
}

function dashKpi(options) {
  var tag = options.href ? "a" : "div";
  var attrs = options.href ? ' href="' + esc(options.href) + '"' : "";
  if (options.scrollTarget) {
    attrs += ' data-dashboard-scroll="' + esc(options.scrollTarget) +
      '" aria-controls="' + esc(options.scrollTarget) + '"';
  }
  return "<" + tag + ' class="ds-kpi ' + esc(options.tone) + '"' + attrs + ">" +
    '<div class="ds-kpi-head"><span>' + esc(options.label) + "</span>" +
    '<span class="ds-kpi-icon">' + dashIcon(options.icon) + "</span></div>" +
    '<div class="ds-kpi-value">' + options.value + "</div>" +
    '<div class="ds-kpi-foot">' + options.foot + "</div>" +
  "</" + tag + ">";
}

function dashScrollToTarget(root, targetId) {
  var target = root.querySelector("#" + targetId);
  if (!target) { return; }

  var topbar = document.getElementById("topbar");
  var offset = (topbar ? topbar.getBoundingClientRect().height : 0) + 16;
  var top = target.getBoundingClientRect().top + window.pageYOffset - offset;
  var reduceMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.scrollTo({
    top: Math.max(0, top),
    behavior: reduceMotion ? "auto" : "smooth"
  });

  var heading = target.querySelector("h2");
  if (heading) { heading.focus({ preventScroll: true }); }
}

function dashboardTodoHref(item) {
  return item.deal_id
    ? "#/deals/" + item.deal_id
    : "#/customers/" + item.customer_id;
}

function dashYesterdayItem(item, all) {
  var maxNew = Math.max.apply(null, all.map(function (entry) { return Number(entry.new_count || 0); }).concat([1]));
  var maxFollow = Math.max.apply(null, all.map(function (entry) { return Number(entry.followups || 0); }).concat([1]));
  var tones = { lead: "blue", customer: "green", deal: "violet", order: "amber", aftersale: "red" };
  var icons = { lead: "lead", customer: "customer", deal: "won", order: "order", aftersale: "service" };
  return '<a class="ds-yesterday ' + esc(tones[item.key] || "blue") + '" href="#/' +
    (item.key === "aftersale" ? "aftersales" : item.key === "deal" ? "deals" : item.key + "s") + '">' +
    '<span class="ds-yesterday-top"><i>' + dashIcon(icons[item.key] || "chart") + "</i><b>" +
      esc(item.name) + "</b></span>" +
    '<span class="ds-yesterday-values">' +
      "<span><b>" + Number(item.new_count || 0) + "</b><small>新增</small></span><i></i>" +
      "<span><b>" + Number(item.followups || 0) + "</b><small>跟进次数</small></span>" +
    "</span>" +
    '<span class="ds-yesterday-tracks" aria-hidden="true">' +
      '<i class="new" style="width:' + (Number(item.new_count || 0) ? Math.max(Number(item.new_count || 0) / maxNew * 100, 8) : 0) + '%"></i>' +
      '<i class="follow" style="width:' + (Number(item.followups || 0) ? Math.max(Number(item.followups || 0) / maxFollow * 100, 8) : 0) + '%"></i>' +
    "</span></a>";
}

function dashTodayItem(item, all) {
  var tones = { lead: "blue", customer: "green", deal: "violet", order: "amber", aftersale: "red" };
  var icons = { lead: "lead", customer: "customer", deal: "won", order: "order", aftersale: "service" };
  var maxFollow = Math.max.apply(null, all.map(function (entry) {
    return Number(entry.followups || 0);
  }).concat([1]));
  var followups = Number(item.followups || 0);
  var newCount = Number(item.new_count || 0);
  return '<a class="ds-today-metric ' + esc(tones[item.key] || "blue") + '" href="#/' +
    (item.key === "aftersale" ? "aftersales" : item.key === "deal" ? "deals" : item.key + "s") + '">' +
    '<span class="ds-today-metric-head"><i>' + dashIcon(icons[item.key] || "activity") + "</i><b>" +
      esc(item.name) + "</b><small>新增 " + newCount + "</small></span>" +
    '<span class="ds-today-metric-value"><strong>' + followups + "</strong><small>次跟进</small></span>" +
    '<span class="ds-today-track"><i style="width:' +
      (followups ? Math.max(followups / maxFollow * 100, 8) : 0) + '%"></i></span>' +
  "</a>";
}

function dashActivity(a) {
  var type = String(a.type || "");
  var tone = type === "follow" ? "follow"
    : type === "pay" ? "pay"
    : type === "aftersale" ? "service"
    : "order";
  var icon = tone === "follow" ? "跟" : tone === "pay" ? "收" : tone === "service" ? "售" : "单";
  var amount = (type === "order" || type === "pay") && Number(a.amount || 0) ? " · " + money(a.amount) : "";
  return '<div class="ds-activity-row">' +
    '<span class="ds-activity-icon ' + tone + '">' + icon + "</span>" +
    '<span class="ds-activity-copy"><p>' + esc(a.text || "业务状态已更新") + esc(amount) +
      "</p><small>" + esc(fmtDateTime(a.at).slice(5)) + "</small></span>" +
  "</div>";
}

function viewDashboard(root) {
  return api("/dashboard").then(function (d) {
    var stats = d.stats || {};
    var todos = d.today_followups || [];
    var orders = stats.orders_by_status || {};
    var today = stats.today_activity || [];
    var yesterday = stats.yesterday_activity || [];
    var recentServices = stats.recent_aftersales || [];
    var activeServices = recentServices.filter(function (item) {
      return item.status === "pending" || item.status === "processing";
    });
    var activeServicesCount = Math.max(
      Number(stats.active_aftersales_count || 0),
      activeServices.length
    );
    var activities = stats.recent_activities || [];
    var alerts = stats.aftersale_sla_alerts || [];
    var overdue = todos.filter(function (item) { return Number(item.days_overdue || 0) > 0; });
    var openStatuses = ORDER_STATUS.filter(function (pair) {
      return pair[0] !== "completed";
    });
    var openOrders = openStatuses.reduce(function (sum, pair) {
      return sum + Number((orders[pair[0]] || {}).count || 0);
    }, 0);
    var todayNew = today.reduce(function (sum, item) {
      return sum + Number(item.new_count || 0);
    }, 0);
    var todayFollowups = today.reduce(function (sum, item) {
      return sum + Number(item.followups || 0);
    }, 0);
    var todayActions = todayNew + todayFollowups;

    var alertHtml = "";
    if (alerts.length) {
      var firstAlert = alerts[0];
      alertHtml = '<div class="ds-alert">' +
        '<span class="ds-alert-icon">' + dashIcon("alert") + "</span>" +
        '<div class="ds-alert-copy"><b>售后单 ' + esc(firstAlert.no) + " 已挂 " +
          esc(firstAlert.days_pending) + " 天未处理</b><span>" +
          esc(firstAlert.customer_name || "") + " · 已超过 3 天 SLA，请优先处理。</span></div>" +
        '<a class="ds-button ds-button-small" href="#/aftersales/' + firstAlert.id + '">去处理</a>' +
      "</div>";
    }

    var todoHtml = todos.length ? todos.map(function (item) {
      var intent = item.intent_level ? (INTENT_LABELS[item.intent_level] || "") : "";
      var intentClass = item.intent_level === "high" ? "high" : item.intent_level === "low" ? "low" : "medium";
      var stage = item.deal_stage_label || STAGE_LABEL[item.deal_stage] || "";
      return '<div class="ds-todo' + (Number(item.days_overdue || 0) > 0 ? " overdue" : "") + '">' +
        '<span class="ds-avatar">' + esc(String(item.customer_name || "?").slice(0, 1)) + "</span>" +
        '<div class="ds-todo-main"><div class="ds-todo-line">' +
          '<a class="ds-person" href="#/customers/' + item.customer_id + '">' + esc(item.customer_name) + "</a>" +
          '<span class="ds-tag">客户</span>' +
          (intent ? '<span class="ds-tag ' + intentClass + '">意向 ' + esc(intent) + "</span>" : "") +
          (stage ? '<span class="ds-tag stage">' + esc(stage) + "</span>" : "") +
        "</div>" +
        '<div class="ds-todo-content">' + esc(item.content) + "</div>" +
        '<div class="ds-todo-meta">' +
          (item.last_follow_at ? "<span>上次跟进 " + esc(fmtDateTime(item.last_follow_at).slice(0, 10)) + "</span><span>·</span>" : "") +
          "<span>约好 " + esc(item.next_date) + "</span>" +
          (Number(item.days_overdue || 0) > 0
            ? '<span class="ds-danger-badge">逾期 ' + item.days_overdue + " 天</span>"
            : "<span>今天</span>") +
        "</div></div>" +
        '<div class="ds-todo-side"><a class="ds-button ds-button-primary ds-button-small" href="' +
          dashboardTodoHref(item) + '">跟进</a></div>' +
      "</div>";
    }).join("") : '<div class="ds-empty"><span>' + dashIcon("won") +
      "</span><b>今天的跟进已经清空</b><small>接下来可以检查订单进度或售后提醒。</small></div>";

    var orderChips = openStatuses.map(function (pair) {
      var count = Number((orders[pair[0]] || {}).count || 0);
      var tone = pair[0] === "pending_payment" ? "red"
        : pair[0] === "producing" ? "violet"
        : pair[0] === "ready_to_ship" ? "cyan"
        : pair[0] === "pending_confirmation" ? "amber"
        : "blue";
      return '<a class="ds-order-chip" href="#/orders?status=' + pair[0] + '">' +
        '<i class="' + tone + '"></i><span><b>' + count + "</b><small>" +
        esc(ORDER_STATUS_LABEL[pair[0]] || pair[1]) + "</small></span></a>";
    }).join("");

    var serviceHtml = activeServices.length ? activeServices.map(function (item) {
      var type = AFTERSALE_TYPE_LABEL[item.type] || item.type || "售后";
      var urgent = item.status === "pending" && Number(item.days_pending || 0) > 3;
      var status = urgent ? "超时 " + item.days_pending + " 天"
        : (AFTERSALE_STATUS_LABEL[item.status] || item.status);
      return '<a class="ds-service' + (urgent ? " urgent" : "") + '" href="#/aftersales/' + item.id + '">' +
        '<span class="ds-service-dot"></span><span class="ds-service-main"><b>' +
          esc(item.customer_name || "客户") + " · " + esc(type) + "</b><small>" +
          esc(item.description || item.no || "") + "</small></span>" +
        '<span class="ds-service-age">' + esc(status) + "</span></a>";
    }).join("") : '<div class="ds-empty compact"><b>没有未完成的售后单</b><small>处理完成后会自动移出这里。</small></div>';

    root.innerHTML = '<section class="ds-page ds-page-enter">' +
      '<header class="ds-heading"><div><p class="ds-eyebrow">' + esc(dashDateLabel()) + "</p>" +
        "<h1>" + esc(dashGreeting()) + "，" + esc(window.state.displayName || window.state.me || "销售") + "</h1>" +
        '<p class="ds-subtitle">今天有 ' + todos.length + " 位客户需要跟进，先处理 " + overdue.length +
          " 条已逾期的，效率最高。</p></div>" +
      "</header>" + alertHtml +
      '<div class="ds-kpi-grid">' +
        dashKpi({
          label: "今日待跟进",
          value: String(todos.length),
          tone: "blue",
          icon: "calendar",
          href: "#/dashboard",
          scrollTarget: "today-followups",
          foot: "<span>" + overdue.length + " 条已逾期</span><span>·</span><span>按最近一条跟进计算</span>"
        }) +
        dashKpi({
          label: "已逾期",
          value: String(overdue.length),
          tone: "red",
          icon: "alert",
          href: "#/dashboard",
          scrollTarget: "today-followups",
          foot: "<span>" + (overdue.length ? "需要优先处理" : "当前没有逾期") + "</span>"
        }) +
        dashKpi({
          label: "进行中订单",
          value: String(openOrders),
          tone: "violet",
          icon: "order",
          href: "#/orders",
          foot: "<span>待支付 " + Number((orders.pending_payment || {}).count || 0) +
            "</span><span>·</span><span>待发货 " + Number((orders.ready_to_ship || {}).count || 0) + "</span>"
        }) +
        dashKpi({
          label: "进行中售后",
          value: String(activeServicesCount),
          tone: "amber",
          icon: "service",
          href: "#/aftersales",
          foot: "<span>待处理</span><span>·</span><span>处理中</span>"
        }) +
      "</div>" +
      '<section class="ds-card ds-today-card"><div class="ds-today-summary">' +
        '<span class="ds-today-kicker">' + dashIcon("activity") + "今日工作统计</span>" +
        '<div class="ds-today-total"><strong>' + todayActions + "</strong><span>次业务动作</span></div>" +
        '<p>从今天 00:00 到现在，新增档案与人工跟进都计入这里。</p>' +
        '<div class="ds-today-split"><span><b>' + todayNew + "</b> 新增</span><i></i><span><b>" +
          todayFollowups + "</b> 次跟进</span></div>" +
      '</div><div class="ds-today-detail"><div class="ds-card-head"><div>' +
        '<h2>业务分布</h2><span class="ds-count">5 个业务入口</span></div>' +
        "<span>点击数字可直达对应业务</span></div>" +
        '<div class="ds-today-grid">' + today.map(function (item) {
          return dashTodayItem(item, today);
        }).join("") + "</div></div></section>" +
      '<section class="ds-card ds-yesterday-card"><div class="ds-card-head"><div><h2>昨日新增与跟进</h2>' +
        "</div><span>昨天 00:00–24:00</span></div>" +
        '<div class="ds-yesterday-grid">' + yesterday.map(function (item) { return dashYesterdayItem(item, yesterday); }).join("") +
      "</div></section>" +
      '<div class="ds-work-grid">' +
        '<section id="today-followups" class="ds-card ds-follow-card" aria-labelledby="today-followups-title">' +
          '<div class="ds-card-head">' +
          '<div><h2 id="today-followups-title" tabindex="-1">今日待跟进</h2><span class="ds-count">' +
            todos.length + "</span></div>" +
          '<a class="ds-text-link" href="#/followups">查看全部</a></div><div>' + todoHtml + "</div></section>" +
        '<div class="ds-side-stack">' +
          '<section class="ds-card"><div class="ds-card-head"><div><h2>订单待办</h2></div><span>' +
            openOrders + ' 单未完成</span></div><div class="ds-order-summary"><b>' + openOrders +
            "<small>进行中订单</small></b><p>当前最需要关注<br><strong>待支付 " +
            Number((orders.pending_payment || {}).count || 0) + " 单 · 待收尾款 " +
            Number((orders.balance_paid || {}).count || 0) + " 单</strong></p></div>" +
            '<div class="ds-order-grid">' + orderChips + "</div></section>" +
          '<section class="ds-card"><div class="ds-card-head"><div><h2>售后提醒</h2></div>' +
            '<span class="ds-count">' + activeServicesCount + "</span></div>" +
            '<div class="ds-service-list">' + serviceHtml + "</div></section>" +
        "</div>" +
        '<section class="ds-card ds-activity-card"><div class="ds-card-head"><div><h2>最近动态</h2></div>' +
          "<span>跟进、收款、订单与售后混排</span></div>" +
          '<div class="ds-activity-list">' + (activities.length
            ? activities.map(dashActivity).join("")
            : '<div class="ds-empty compact"><b>还没有动态</b><small>业务操作后会显示在这里。</small></div>') +
          "</div></section>" +
      "</div></section>";

    $$("[data-dashboard-scroll]", root).forEach(function (control) {
      control.addEventListener("click", function (event) {
        event.preventDefault();
        dashScrollToTarget(root, control.getAttribute("data-dashboard-scroll"));
      });
    });
  });
}
