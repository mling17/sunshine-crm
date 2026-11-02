(function () {
  "use strict";

  const app = document.getElementById("app");
  const modalRoot = document.getElementById("modalRoot");
  const drawerRoot = document.getElementById("drawerRoot");
  const toastEl = document.getElementById("toast");

  const state = {
    page: "dashboard",
    range: "6m",
    moneyVisible: false,
    followups: [
      {
        id: 1,
        name: "王志远",
        type: "客户",
        phone: "138 5312 7745",
        intent: "高",
        intentKey: "high",
        stage: "待客户确认",
        lastFollow: "10月29日",
        due: "11月2日",
        daysOverdue: 0,
        content: "已发最终报价单，等他确认玻璃升级和遮阳帘颜色",
        note: "济南·万科城，主卧 1200×2400 天窗。客户重点关注隔音和遮阳效果。"
      },
      {
        id: 2,
        name: "韩雪",
        type: "线索",
        phone: "187 5311 2299",
        intent: "高",
        intentKey: "high",
        stage: "新线索",
        lastFollow: "11月1日",
        due: "11月2日",
        daysOverdue: 0,
        content: "抖音案例咨询，约好今天下午发顶楼现场照片和尺寸",
        note: "济南·中海国际，90 平方米顶楼，考虑天窗和遮阳一体方案。"
      },
      {
        id: 3,
        name: "刘俊峰",
        type: "客户",
        phone: "139 0532 8811",
        intent: "高",
        intentKey: "high",
        stage: "报价",
        lastFollow: "10月27日",
        due: "11月1日",
        daysOverdue: 1,
        content: "海尔路工地第二套天窗，等甲方确认图纸",
        note: "青岛海景装饰工程有限公司，今年已合作两单，走对公付款。"
      },
      {
        id: 4,
        name: "陈国强",
        type: "客户",
        phone: "137 0636 5566",
        intent: "低",
        intentKey: "low",
        stage: "待客户确认",
        lastFollow: "10月26日",
        due: "10月30日",
        daysOverdue: 3,
        content: "客户持续压价，要求再让 200 元/平方",
        note: "潍坊鲁中建材，阳光房定制项目。价格敏感，需明确交付边界。"
      }
    ],
    orders: [
      { key: "pending_confirmation", label: "待客户确认", count: 2, sub: "下单表待回签" },
      { key: "pending_payment", label: "待支付", count: 3, sub: "押金待核实" },
      { key: "deposit_paid", label: "已付押金", count: 1, sub: "可安排生产" },
      { key: "producing", label: "生产中", count: 4, sub: "等待车间完工" },
      { key: "balance_paid", label: "待收尾款", count: 2, sub: "完工后待收款" },
      { key: "ready_to_ship", label: "待发货", count: 1, sub: "尾款已核实" },
      { key: "shipped", label: "已发货", count: 3, sub: "等待客户签收" }
    ],
    services: [
      {
        id: 1,
        no: "AS-20261028-001",
        customer: "陈国强",
        type: "维修",
        summary: "阳光房右侧推拉门关不严，下雨渗水",
        age: 5,
        status: "待处理"
      },
      {
        id: 2,
        no: "AS-20261101-002",
        customer: "李秀娟",
        type: "退货",
        summary: "客户反馈遮阳帘电机运行噪音偏大",
        age: 1,
        status: "处理中"
      }
    ],
    activities: [
      { icon: "收", tone: "pay", text: "收到王志远尾款 ¥8,400", time: "今天 10:42" },
      { icon: "跟", tone: "follow", text: "给韩雪发送了 3 个顶楼天窗案例", time: "今天 09:28" },
      { icon: "单", tone: "order", text: "SO-2026-11-003 已进入待发货", time: "昨天 17:36" },
      { icon: "售", tone: "service", text: "李秀娟售后单已进入处理中", time: "昨天 14:20" },
      { icon: "单", tone: "order", text: "刘俊峰第二套天幕下单表已生成", time: "10月31日 16:08" },
      { icon: "跟", tone: "follow", text: "陈国强报价跟进已记录", time: "10月30日 11:15" }
    ],
    stats: {
      month: {
        label: "本月",
        summary: {
          newLeads: 12,
          leadRate: 33.3,
          convertedLeads: 4,
          wonAmount: 32500,
          wonCount: 3,
          avgDeal: 10833,
          aftersales: 2,
          overdueAftersales: 1
        },
        trend: {
          title: "近 8 日成交走势",
          caption: "按成交日期统计",
          labels: ["10/26", "10/27", "10/28", "10/29", "10/30", "10/31", "11/01", "11/02"],
          values: [0, 8600, 0, 0, 0, 0, 11900, 12000],
          counts: [0, 1, 0, 0, 0, 0, 1, 1]
        },
        funnel: [
          { label: "新增线索", value: 12 },
          { label: "已转化", value: 4 },
          { label: "客户已确认", value: 3 },
          { label: "已生成订单", value: 3 },
          { label: "已完成订单", value: 1 }
        ],
        sources: [
          { name: "抖音", leads: 5, converted: 2, rate: 40, won: 1, amount: 12000, tone: "green" },
          { name: "转介绍", leads: 3, converted: 1, rate: 33.3, won: 1, amount: 13500, tone: "violet" },
          { name: "微信", leads: 2, converted: 1, rate: 50, won: 1, amount: 7000, tone: "blue" },
          { name: "电话", leads: 1, converted: 0, rate: 0, won: 0, amount: 0, tone: "amber" },
          { name: "其他", leads: 1, converted: 0, rate: 0, won: 0, amount: 0, tone: "grey" }
        ],
        products: [
          { name: "XC-120 电动天窗", code: "TS-023", count: 2, amount: 19000 },
          { name: "TM-240 天幕系统", code: "TS-041", count: 1, amount: 13500 },
          { name: "XC-90 手动天窗", code: "TS-011", count: 1, amount: 8600 },
          { name: "ZY-15 遮阳帘", code: "TS-076", count: 2, amount: 3200 },
          { name: "YG-30 阳光房", code: "TS-086", count: 1, amount: 0 }
        ],
        dealStages: [
          { label: "报价", value: 3, tone: "blue" },
          { label: "待客户确认", value: 5, tone: "amber" },
          { label: "客户已确认", value: 3, tone: "green" },
          { label: "已作废", value: 1, tone: "red" }
        ],
        lostReasons: [
          { label: "价格", value: 1, tone: "red" },
          { label: "竞品", value: 0, tone: "amber" },
          { label: "客户放弃", value: 0, tone: "violet" },
          { label: "其他", value: 0, tone: "cyan" }
        ],
        orderStatus: [
          { label: "待确认", value: 2, tone: "amber" },
          { label: "待支付", value: 3, tone: "red" },
          { label: "生产中", value: 4, tone: "violet" },
          { label: "待发货", value: 1, tone: "cyan" },
          { label: "已发货", value: 3, tone: "blue" },
          { label: "已完成", value: 5, tone: "green" }
        ],
        serviceStatus: [
          { label: "待处理", value: 1, tone: "red" },
          { label: "处理中", value: 1, tone: "amber" },
          { label: "已完成", value: 4, tone: "green" }
        ],
        serviceTypes: [
          { label: "维修", value: 2, tone: "blue" },
          { label: "退货", value: 1, tone: "amber" },
          { label: "投诉", value: 1, tone: "red" }
        ],
        insights: [
          { icon: "源", text: "<b>微信来源</b>本期转化率最高，达到 50%" },
          { icon: "品", text: "<b>XC-120 电动天窗</b>是本月成交主力，占成交额 58%" },
          { icon: "单", text: "当前有 <b>2 单待收尾款</b>，建议今天优先确认完工节点" }
        ]
      },
      "3m": {
        label: "近 3 月",
        summary: {
          newLeads: 47,
          leadRate: 29.8,
          convertedLeads: 14,
          wonAmount: 186800,
          wonCount: 12,
          avgDeal: 15567,
          aftersales: 7,
          overdueAftersales: 1
        },
        trend: {
          title: "月度成交趋势",
          caption: "9 月至 11 月，按成交金额",
          labels: ["9月", "10月", "11月"],
          values: [78600, 75700, 32500],
          counts: [5, 4, 3]
        },
        funnel: [
          { label: "新增线索", value: 47 },
          { label: "已转化", value: 14 },
          { label: "客户已确认", value: 12 },
          { label: "已生成订单", value: 12 },
          { label: "已完成订单", value: 8 }
        ],
        sources: [
          { name: "转介绍", leads: 16, converted: 6, rate: 37.5, won: 5, amount: 74200, tone: "violet" },
          { name: "抖音", leads: 13, converted: 4, rate: 30.8, won: 3, amount: 48600, tone: "green" },
          { name: "微信", leads: 9, converted: 2, rate: 22.2, won: 2, amount: 32000, tone: "blue" },
          { name: "电话", leads: 6, converted: 1, rate: 16.7, won: 1, amount: 18500, tone: "amber" },
          { name: "其他", leads: 3, converted: 1, rate: 33.3, won: 1, amount: 13500, tone: "grey" }
        ],
        products: [
          { name: "XC-120 电动天窗", code: "TS-023", count: 5, amount: 68600 },
          { name: "TM-240 天幕系统", code: "TS-041", count: 2, amount: 39200 },
          { name: "YG-30 阳光房", code: "TS-086", count: 1, amount: 28000 },
          { name: "XC-90 手动天窗", code: "TS-011", count: 3, amount: 26400 },
          { name: "TM-180 天幕系统", code: "TS-038", count: 1, amount: 16500 },
          { name: "ZY-15 遮阳帘", code: "TS-076", count: 4, amount: 8100 }
        ],
        dealStages: [
          { label: "报价", value: 8, tone: "blue" },
          { label: "待客户确认", value: 11, tone: "amber" },
          { label: "客户已确认", value: 12, tone: "green" },
          { label: "已作废", value: 3, tone: "red" }
        ],
        lostReasons: [
          { label: "价格", value: 2, tone: "red" },
          { label: "竞品", value: 1, tone: "amber" },
          { label: "客户放弃", value: 0, tone: "violet" },
          { label: "其他", value: 0, tone: "cyan" }
        ],
        orderStatus: [
          { label: "待确认", value: 2, tone: "amber" },
          { label: "待支付", value: 3, tone: "red" },
          { label: "生产中", value: 4, tone: "violet" },
          { label: "待发货", value: 1, tone: "cyan" },
          { label: "已发货", value: 3, tone: "blue" },
          { label: "已完成", value: 18, tone: "green" }
        ],
        serviceStatus: [
          { label: "待处理", value: 1, tone: "red" },
          { label: "处理中", value: 1, tone: "amber" },
          { label: "已完成", value: 5, tone: "green" }
        ],
        serviceTypes: [
          { label: "维修", value: 3, tone: "blue" },
          { label: "退货", value: 2, tone: "amber" },
          { label: "投诉", value: 1, tone: "red" },
          { label: "其他", value: 1, tone: "cyan" }
        ],
        insights: [
          { icon: "源", text: "<b>转介绍</b>贡献成交额 ¥74,200，是近 3 月最稳定的来源" },
          { icon: "品", text: "<b>电动天窗</b>成交 5 单，占产品销售额 37%" },
          { icon: "流", text: "报价阶段仍有 <b>8 个商机</b>，建议优先处理停留超过 7 天的客户" }
        ]
      },
      "6m": {
        label: "近 6 月",
        summary: {
          newLeads: 93,
          leadRate: 31.2,
          convertedLeads: 29,
          wonAmount: 428600,
          wonCount: 27,
          avgDeal: 15874,
          aftersales: 14,
          overdueAftersales: 1
        },
        trend: {
          title: "月度成交趋势",
          caption: "6 月至 11 月，按成交金额",
          labels: ["6月", "7月", "8月", "9月", "10月", "11月"],
          values: [48600, 63900, 68900, 78600, 75700, 32500],
          counts: [3, 4, 4, 5, 4, 3]
        },
        funnel: [
          { label: "新增线索", value: 93 },
          { label: "已转化", value: 29 },
          { label: "客户已确认", value: 27 },
          { label: "已生成订单", value: 25 },
          { label: "已完成订单", value: 20 }
        ],
        sources: [
          { name: "转介绍", leads: 31, converted: 12, rate: 38.7, won: 11, amount: 168500, tone: "violet" },
          { name: "抖音", leads: 25, converted: 8, rate: 32, won: 7, amount: 112600, tone: "green" },
          { name: "微信", leads: 18, converted: 5, rate: 27.8, won: 5, amount: 76400, tone: "blue" },
          { name: "电话", leads: 12, converted: 2, rate: 16.7, won: 2, amount: 42800, tone: "amber" },
          { name: "其他", leads: 7, converted: 2, rate: 28.6, won: 2, amount: 28300, tone: "grey" }
        ],
        products: [
          { name: "XC-120 电动天窗", code: "TS-023", count: 11, amount: 146800 },
          { name: "TM-240 天幕系统", code: "TS-041", count: 5, amount: 91800 },
          { name: "YG-30 阳光房", code: "TS-086", count: 2, amount: 64200 },
          { name: "XC-90 手动天窗", code: "TS-011", count: 6, amount: 52600 },
          { name: "TM-180 天幕系统", code: "TS-038", count: 3, amount: 42800 },
          { name: "ZY-15 遮阳帘", code: "TS-076", count: 8, amount: 18600 },
          { name: "定制遮阳篷", code: "TS-095", count: 2, amount: 11800 }
        ],
        dealStages: [
          { label: "报价", value: 14, tone: "blue" },
          { label: "待客户确认", value: 18, tone: "amber" },
          { label: "客户已确认", value: 27, tone: "green" },
          { label: "已作废", value: 6, tone: "red" }
        ],
        lostReasons: [
          { label: "价格", value: 3, tone: "red" },
          { label: "竞品", value: 2, tone: "amber" },
          { label: "客户放弃", value: 1, tone: "violet" },
          { label: "其他", value: 0, tone: "cyan" }
        ],
        orderStatus: [
          { label: "待确认", value: 2, tone: "amber" },
          { label: "待支付", value: 3, tone: "red" },
          { label: "生产中", value: 4, tone: "violet" },
          { label: "待发货", value: 1, tone: "cyan" },
          { label: "已发货", value: 3, tone: "blue" },
          { label: "已完成", value: 32, tone: "green" }
        ],
        serviceStatus: [
          { label: "待处理", value: 1, tone: "red" },
          { label: "处理中", value: 1, tone: "amber" },
          { label: "已完成", value: 12, tone: "green" }
        ],
        serviceTypes: [
          { label: "维修", value: 6, tone: "blue" },
          { label: "退货", value: 3, tone: "amber" },
          { label: "投诉", value: 2, tone: "red" },
          { label: "其他", value: 3, tone: "cyan" }
        ],
        insights: [
          { icon: "源", text: "<b>转介绍</b>成交额最高，贡献近 6 月成交额的 39%" },
          { icon: "品", text: "<b>XC-120 电动天窗</b>累计成交 11 单，是核心产品" },
          { icon: "流", text: "线索到客户确认的转化率为 <b>29%</b>，比报价到确认高 4 个百分点" }
        ]
      },
      year: {
        label: "今年",
        summary: {
          newLeads: 171,
          leadRate: 30.4,
          convertedLeads: 52,
          wonAmount: 824900,
          wonCount: 49,
          avgDeal: 16835,
          aftersales: 26,
          overdueAftersales: 1
        },
        trend: {
          title: "年度成交趋势",
          caption: "1 月至 11 月，按成交金额",
          labels: ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月"],
          values: [42800, 51600, 68400, 73600, 82600, 48600, 63900, 68900, 78600, 75700, 32500],
          counts: [3, 3, 4, 4, 5, 3, 4, 4, 5, 4, 3]
        },
        funnel: [
          { label: "新增线索", value: 171 },
          { label: "已转化", value: 52 },
          { label: "客户已确认", value: 49 },
          { label: "已生成订单", value: 46 },
          { label: "已完成订单", value: 38 }
        ],
        sources: [
          { name: "转介绍", leads: 58, converted: 21, rate: 36.2, won: 19, amount: 318400, tone: "violet" },
          { name: "抖音", leads: 44, converted: 14, rate: 31.8, won: 13, amount: 214600, tone: "green" },
          { name: "微信", leads: 34, converted: 9, rate: 26.5, won: 9, amount: 146800, tone: "blue" },
          { name: "电话", leads: 22, converted: 5, rate: 22.7, won: 5, amount: 88600, tone: "amber" },
          { name: "其他", leads: 13, converted: 3, rate: 23.1, won: 3, amount: 56500, tone: "grey" }
        ],
        products: [
          { name: "XC-120 电动天窗", code: "TS-023", count: 21, amount: 278600 },
          { name: "TM-240 天幕系统", code: "TS-041", count: 9, amount: 168200 },
          { name: "YG-30 阳光房", code: "TS-086", count: 4, amount: 126400 },
          { name: "XC-90 手动天窗", code: "TS-011", count: 12, amount: 108600 },
          { name: "TM-180 天幕系统", code: "TS-038", count: 6, amount: 86400 },
          { name: "ZY-15 遮阳帘", code: "TS-076", count: 15, amount: 34600 },
          { name: "定制遮阳篷", code: "TS-095", count: 4, amount: 22100 }
        ],
        dealStages: [
          { label: "报价", value: 21, tone: "blue" },
          { label: "待客户确认", value: 28, tone: "amber" },
          { label: "客户已确认", value: 49, tone: "green" },
          { label: "已作废", value: 11, tone: "red" }
        ],
        lostReasons: [
          { label: "价格", value: 5, tone: "red" },
          { label: "竞品", value: 3, tone: "amber" },
          { label: "客户放弃", value: 2, tone: "violet" },
          { label: "其他", value: 1, tone: "cyan" }
        ],
        orderStatus: [
          { label: "待确认", value: 2, tone: "amber" },
          { label: "待支付", value: 3, tone: "red" },
          { label: "生产中", value: 4, tone: "violet" },
          { label: "待发货", value: 1, tone: "cyan" },
          { label: "已发货", value: 3, tone: "blue" },
          { label: "已完成", value: 54, tone: "green" }
        ],
        serviceStatus: [
          { label: "待处理", value: 1, tone: "red" },
          { label: "处理中", value: 1, tone: "amber" },
          { label: "已完成", value: 24, tone: "green" }
        ],
        serviceTypes: [
          { label: "维修", value: 11, tone: "blue" },
          { label: "退货", value: 5, tone: "amber" },
          { label: "投诉", value: 4, tone: "red" },
          { label: "其他", value: 6, tone: "cyan" }
        ],
        insights: [
          { icon: "源", text: "<b>转介绍</b>今年累计成交 ¥318,400，是最有价值的获客来源" },
          { icon: "品", text: "<b>电动天窗</b>成交额占年度总额的 34%，产品集中度持续提升" },
          { icon: "服", text: "售后主要集中在维修类型，今年共 <b>11 单</b>，需持续关注安装质量" }
        ]
      }
    }
  };

  const icons = {
    calendar: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"></rect><path d="M8 3v4M16 3v4M3 10h18"></path><path d="m9 15 2 2 4-4"></path></svg>',
    alert: '<svg viewBox="0 0 24 24"><path d="M12 3 2.8 20h18.4L12 3Z"></path><path d="M12 9v4M12 17h.01"></path></svg>',
    arrow: '<svg viewBox="0 0 24 24"><path d="M5 12h14M14 7l5 5-5 5"></path></svg>',
    plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"></path></svg>',
    clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>',
    order: '<svg viewBox="0 0 24 24"><path d="M6 3h12v18H6z"></path><path d="M9 8h6M9 12h6M9 16h4"></path></svg>',
    service: '<svg viewBox="0 0 24 24"><path d="M4 13a8 8 0 0 1 16 0"></path><path d="M4 13v5h3v-5H4Zm13 0h3v5h-3v-5Z"></path><path d="M10 21h4"></path></svg>',
    lead: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"></circle><path d="M5 20c.8-4 3.1-6 7-6s6.2 2 7 6"></path><path d="M18 4v4M16 6h4"></path></svg>',
    customer: '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.2"></circle><path d="M3.5 19c.6-3.7 2.5-5.5 5.5-5.5s4.9 1.8 5.5 5.5"></path><circle cx="17" cy="9" r="2.3"></circle><path d="M15.5 14.8c3.4-.5 5.2 1.2 5.7 4.2"></path></svg>',
    won: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="m8 12 2.5 2.5L16 9"></path></svg>',
    chart: '<svg viewBox="0 0 24 24"><path d="M5 20V10m7 10V4m7 16v-7M3 20h18"></path></svg>',
    spark: '<svg viewBox="0 0 24 24"><path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z"></path></svg>',
    wand: '<svg viewBox="0 0 24 24"><path d="m4 20 12-12M14 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2ZM19 13l.7 1.3L21 15l-1.3.7L19 17l-.7-1.3L17 15l1.3-.7L19 13Z"></path></svg>'
  };

  const weekdayNames = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatMoney(value, compact) {
    const number = Number(value) || 0;
    if (!state.moneyVisible) return compact ? "¥••" : "¥••••";
    if (compact && Math.abs(number) >= 10000) {
      return `¥${(number / 10000).toFixed(number % 10000 === 0 ? 0 : 1)}万`;
    }
    return `¥${number.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
  }

  function todayLabel() {
    const date = new Date();
    return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 · ${weekdayNames[date.getDay()]}`;
  }

  function currentGreeting() {
    const hour = new Date().getHours();
    if (hour < 11) return "早上好";
    if (hour < 14) return "中午好";
    if (hour < 18) return "下午好";
    return "晚上好";
  }

  function pageHeading() {
    if (state.page === "stats") {
      return `
        <div class="page-heading">
          <div>
            <p class="eyebrow">Performance review</p>
            <h1>销售统计</h1>
            <p class="subtitle">从客源、转化、成交到履约，用一段时间的真实结果做判断。</p>
          </div>
          <div class="heading-actions">
            <div class="segmented" aria-label="统计区间">
              ${Object.entries(state.stats).map(([key, item]) => `
                <button type="button" class="${state.range === key ? "is-active" : ""}" data-action="range" data-range="${key}">
                  ${item.label}
                </button>
              `).join("")}
            </div>
          </div>
        </div>
      `;
    }

    return `
      <div class="page-heading">
        <div>
          <p class="eyebrow">${todayLabel()}</p>
          <h1>${currentGreeting()}，陈明</h1>
          <p class="subtitle">今天有 ${state.followups.length} 位客户需要跟进，先处理 ${state.followups.filter((item) => item.daysOverdue > 0).length} 条已逾期的，效率最高。</p>
        </div>
        <div class="heading-actions">
          <button type="button" class="button" data-action="refresh">
            ${icons.clock}
            刚刚同步
          </button>
          <button type="button" class="button button-primary" data-action="quick-lead">
            ${icons.plus}
            新增线索
          </button>
        </div>
      </div>
    `;
  }

  function miniBars(values) {
    return `<span class="mini-bars" aria-hidden="true">${values.map((value) => `<i style="height:${value}%"></i>`).join("")}</span>`;
  }

  function kpiCard(options) {
    const tag = options.action ? "button" : "div";
    const attrs = options.action
      ? `type="button" data-action="${options.action}"${options.value ? ` data-value="${escapeHtml(options.value)}"` : ""}`
      : "";
    return `
      <${tag} class="kpi-card ${options.tone}${options.money ? " money-value" : ""}" ${attrs}>
        <div class="kpi-head">
          <span>${escapeHtml(options.label)}</span>
          <span class="kpi-icon">${options.icon}</span>
        </div>
        <div class="kpi-value">${options.valueHtml}</div>
        <div class="kpi-foot">${options.footHtml || ""}</div>
        ${options.bars ? miniBars(options.bars) : ""}
      </${tag}>
    `;
  }

  function renderDashboard() {
    const overdue = state.followups.filter((item) => item.daysOverdue > 0);
    const openOrders = state.orders.reduce((sum, item) => sum + item.count, 0);
    const overdueServices = state.services.filter((item) => item.age > 3).length;
    const followupRows = state.followups.map(todoRow).join("");

    app.innerHTML = `
      <section class="page-enter">
        ${pageHeading()}

        <div class="alert-strip">
          <span class="alert-icon">${icons.alert}</span>
          <div class="alert-copy">
            <b>售后单 AS-20261028-001 已挂 5 天未处理</b>
            <span>陈国强 · 阳光房推拉门渗水，已超过 3 天 SLA，请优先处理。</span>
          </div>
          <button type="button" class="button button-small" data-action="service" data-id="1">去处理</button>
        </div>

        <div class="kpi-grid">
          ${kpiCard({
            label: "今日待跟进",
            valueHtml: state.followups.length,
            tone: "blue",
            icon: icons.calendar,
            footHtml: `<span>${overdue.length} 条已逾期</span><span class="dot-sep">·</span><span>全部需要今天闭环</span>`,
            bars: [32, 48, 42, 60, 70, 64, 86],
            action: "focus-followups"
          })}
          ${kpiCard({
            label: "已逾期",
            valueHtml: overdue.length,
            tone: "red",
            icon: icons.alert,
            footHtml: `<span>最长逾期 3 天</span><span class="dot-sep">·</span><span class="trend-down">需优先处理</span>`,
            bars: [26, 35, 40, 32, 46, 58, 62],
            action: "focus-followups"
          })}
          ${kpiCard({
            label: "进行中订单",
            valueHtml: openOrders,
            tone: "violet",
            icon: icons.order,
            footHtml: `<span>待发货 1 单</span><span class="dot-sep">·</span><span>已发货 3 单</span>`,
            bars: [55, 45, 56, 62, 58, 72, 66],
            action: "focus-orders"
          })}
          ${kpiCard({
            label: "超时售后",
            valueHtml: overdueServices,
            tone: "amber",
            icon: icons.service,
            footHtml: `<span>当前售后 2 单</span><span class="dot-sep">·</span><span>SLA 3 天</span>`,
            bars: [18, 20, 34, 28, 30, 46, 52],
            action: "focus-services"
          })}
        </div>

        <div class="work-grid">
          <section class="card" id="followupCard">
            <div class="card-head">
              <div class="card-title">
                <h2>今日待跟进</h2>
                <span class="count-badge">${state.followups.length}</span>
              </div>
              <button type="button" class="button button-plain button-small" data-action="all-followups">查看全部 ${icons.arrow}</button>
            </div>
            <div class="todo-list">
              ${followupRows || emptyFollowups()}
            </div>
          </section>

          <div class="side-stack">
            <section class="card" id="ordersCard">
              <div class="card-head">
                <div class="card-title"><h2>订单待办</h2></div>
                <span class="card-meta">${openOrders} 单未完成</span>
              </div>
              <div class="order-summary">
                <div class="big">${openOrders}<small>进行中订单</small></div>
                <p>当前最需要关注<br><b>3 单待支付 · 2 单待收尾款</b></p>
              </div>
              <div class="order-grid">
                ${state.orders.map(orderChip).join("")}
              </div>
            </section>

            <section class="card" id="serviceCard">
              <div class="card-head">
                <div class="card-title"><h2>售后提醒</h2></div>
                <span class="count-badge">${state.services.length}</span>
              </div>
              <div class="service-list">
                ${state.services.map(serviceRow).join("")}
              </div>
            </section>
          </div>

          <section class="card activity-card">
            <div class="card-head">
              <div class="card-title"><h2>最近动态</h2></div>
              <span class="card-meta">跟进、收款、订单与售后混排</span>
            </div>
            <div class="activity-list">
              ${state.activities.map(activityRow).join("")}
            </div>
          </section>
        </div>
      </section>
    `;
  }

  function todoRow(item) {
    return `
      <div class="todo-row${item.daysOverdue > 0 ? " is-overdue" : ""}">
        <span class="todo-avatar">${escapeHtml(item.name.slice(0, 1))}</span>
        <div class="todo-main">
          <div class="todo-topline">
            <button type="button" class="person-link" data-action="customer" data-id="${item.id}">${escapeHtml(item.name)}</button>
            <span class="tag">${escapeHtml(item.type)}</span>
            <span class="tag ${item.intentKey === "high" ? "high" : item.intentKey === "low" ? "" : "medium"}">意向 ${escapeHtml(item.intent)}</span>
            <span class="tag stage">${escapeHtml(item.stage)}</span>
          </div>
          <div class="todo-content">${escapeHtml(item.content)}</div>
          <div class="todo-meta">
            <span>上次跟进 ${item.lastFollow}</span>
            <span>·</span>
            <span>约好 ${item.due}</span>
            ${item.daysOverdue > 0 ? `<span class="badge-danger">逾期 ${item.daysOverdue} 天</span>` : `<span>今天</span>`}
          </div>
        </div>
        <div class="todo-side">
          <button type="button" class="button button-primary button-small" data-action="record" data-id="${item.id}">记一条</button>
        </div>
      </div>
    `;
  }

  function emptyFollowups() {
    return `
      <div class="card-empty">
        <span class="empty-icon">${icons.won}</span>
        <b>今天的跟进已经清空</b>
        <span>团队协作很顺畅，接下来可以检查订单进度。</span>
      </div>
    `;
  }

  function orderChip(item) {
    return `
      <button type="button" class="order-chip" data-action="order-status" data-value="${item.key}">
        <i></i>
        <span><b>${item.count}</b><small>${item.label}</small></span>
      </button>
    `;
  }

  function serviceRow(item) {
    const urgent = item.age > 3;
    return `
      <button type="button" class="service-row${urgent ? " urgent" : ""}" data-action="service" data-id="${item.id}" style="width:100%;text-align:left;background:transparent;border-left:0;border-right:0;border-top:0;">
        <span class="service-dot"></span>
        <span class="service-main">
          <b>${escapeHtml(item.customer)} · ${escapeHtml(item.type)}</b>
          <small>${escapeHtml(item.summary)}</small>
        </span>
        <span class="service-age">${urgent ? `超时 ${item.age} 天` : item.status}</span>
      </button>
    `;
  }

  function activityRow(item) {
    return `
      <div class="activity-row">
        <span class="activity-icon ${item.tone}">${item.icon}</span>
        <span class="activity-copy">
          <p>${escapeHtml(item.text)}</p>
          <small>${escapeHtml(item.time)}</small>
        </span>
      </div>
    `;
  }

  function statKpis(data) {
    const summary = data.summary;
    return `
      <div class="kpi-grid stats-kpis">
        ${kpiCard({
          label: "新增线索",
          valueHtml: summary.newLeads,
          tone: "blue",
          icon: icons.lead,
          footHtml: `<span class="trend-up">↑ 18.6%</span><span>较上周期</span>`,
          bars: [38, 46, 54, 49, 66, 74, 69]
        })}
        ${kpiCard({
          label: "线索转化率",
          valueHtml: `${summary.leadRate}%`,
          tone: "green",
          icon: icons.wand,
          footHtml: `<span>${summary.convertedLeads} 条已转化</span><span class="dot-sep">·</span><span>按本期线索</span>`,
          bars: [36, 42, 58, 51, 64, 62, 72]
        })}
        ${kpiCard({
          label: "成交金额",
          valueHtml: formatMoney(summary.wonAmount, true),
          tone: "violet",
          icon: icons.chart,
          footHtml: `<span class="trend-up">↑ 12.4%</span><span>较上周期</span>`,
          bars: [44, 50, 48, 61, 57, 70, 64],
          money: true
        })}
        ${kpiCard({
          label: "成交单数",
          valueHtml: `${summary.wonCount} 单`,
          tone: "amber",
          icon: icons.won,
          footHtml: `<span>平均客单 ${formatMoney(summary.avgDeal)}</span>`,
          bars: [35, 48, 43, 58, 52, 66, 63]
        })}
        ${kpiCard({
          label: "售后单数",
          valueHtml: summary.aftersales,
          tone: "red",
          icon: icons.service,
          footHtml: `<span>${summary.overdueAftersales} 单超时</span><span class="dot-sep">·</span><span>SLA 3 天</span>`,
          bars: [20, 34, 28, 31, 36, 28, 34]
        })}
      </div>
    `;
  }

  function renderTrendCombo(trend) {
    const width = 1000;
    const plotLeft = 40;
    const plotRight = 970;
    const plotTop = 34;
    const plotBottom = 258;
    const countTop = 48;
    const countBottom = 226;
    const maxAmount = Math.max(...trend.values, 1);
    const maxCount = Math.max(...trend.counts, 1);
    const band = (plotRight - plotLeft) / trend.labels.length;
    const barWidth = Math.min(58, band * 0.48);
    const centers = trend.labels.map((_, index) => plotLeft + band * (index + 0.5));
    const linePoints = centers.map((center, index) => {
      const value = Number(trend.counts[index]) || 0;
      const y = countBottom - (value / maxCount) * (countBottom - countTop);
      return `${center.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    return `
      <section class="card chart-card">
        <div class="card-head">
          <div class="card-title">
            <h2>${escapeHtml(trend.title)}</h2>
          </div>
          <span class="card-meta">${escapeHtml(trend.caption)}</span>
        </div>
        <div class="chart-body">
          <div class="trend-total">
            <b>${formatMoney(trend.values.reduce((sum, value) => sum + value, 0))}</b>
            <span>成交金额 · ${trend.counts.reduce((sum, value) => sum + value, 0)} 单</span>
          </div>
          <div class="combo-chart-wrap">
            <svg class="combo-chart-svg" viewBox="0 0 ${width} 310" role="img" aria-label="${escapeHtml(trend.title)}">
              <g class="svg-grid">
                ${[0, 1, 2, 3].map((index) => {
                  const y = plotTop + ((plotBottom - plotTop) / 3) * index;
                  return `<line x1="${plotLeft}" y1="${y}" x2="${plotRight}" y2="${y}"></line>`;
                }).join("")}
              </g>
              ${trend.labels.map((label, index) => {
                const value = trend.values[index];
                const count = trend.counts[index] || 0;
                const barHeight = value ? Math.max((value / maxAmount) * (plotBottom - plotTop), 8) : 2;
                const x = centers[index] - barWidth / 2;
                const y = plotBottom - barHeight;
                const tip = `${label}：${formatMoney(value)}，${count} 单`;
                return `
                  <g class="svg-series-item" data-action="chart-detail" data-tip="${escapeHtml(tip)}">
                    <title>${escapeHtml(tip)}</title>
                    <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}"
                      rx="7" class="svg-bar${index === trend.labels.length - 1 ? " highlight" : ""}"></rect>
                    <rect x="${(centers[index] - band / 2).toFixed(1)}" y="${plotTop}" width="${band.toFixed(1)}" height="${plotBottom - plotTop}"
                      class="chart-hit-area"></rect>
                    <text x="${centers[index].toFixed(1)}" y="${Math.max(y - 11, 18).toFixed(1)}" class="svg-bar-label">${formatMoney(value, true)}</text>
                    <text x="${centers[index].toFixed(1)}" y="291" class="svg-axis-label">${escapeHtml(label)}</text>
                  </g>
                `;
              }).join("")}
              <polyline class="svg-count-line" points="${linePoints}"></polyline>
              ${centers.map((center, index) => {
                const count = trend.counts[index] || 0;
                const y = countBottom - (count / maxCount) * (countBottom - countTop);
                return `<circle class="svg-count-dot" cx="${center.toFixed(1)}" cy="${y.toFixed(1)}" r="5"></circle>`;
              }).join("")}
            </svg>
          </div>
          <div class="chart-legend">
            <span><i class="legend-dot"></i>成交金额</span>
            <span><i class="legend-line"></i>成交单数</span>
            <span><i class="legend-dot green"></i>当前周期</span>
            <span>悬停或点击查看明细</span>
          </div>
        </div>
      </section>
    `;
  }

  function renderFunnel(funnel) {
    const top = Math.max(funnel[0].value, 1);
    return `
      <section class="card chart-card">
        <div class="card-head">
          <div class="card-title"><h2>销售漏斗</h2></div>
          <span class="card-meta">按本期线索追踪当前结果</span>
        </div>
        <div class="funnel-body stepped-funnel">
          ${funnel.map((item, index) => {
            const previous = index === 0 ? null : funnel[index - 1].value;
            const stepRate = index === 0 ? null : previous ? Math.round((item.value / previous) * 100) : 0;
            const width = Math.max((item.value / top) * 100, item.value ? 22 : 10);
            return `
              <div class="stepped-funnel-row" data-action="chart-detail" data-tip="${escapeHtml(item.label)}：${item.value}${index === 0 ? "" : `，较上一层 ${stepRate}%`}">
                <span class="stepped-funnel-label">${escapeHtml(item.label)}</span>
                <div class="stepped-funnel-visual">
                  <div class="stepped-funnel-band" style="width:${width.toFixed(1)}%">
                    <span>${item.value}</span>
                  </div>
                </div>
                <span class="stepped-funnel-rate">${index === 0 ? "起点" : `${stepRate}%`}</span>
              </div>
            `;
          }).join("")}
          <div class="chart-legend">
            <span>百分比为相对上一层转化率</span>
            <span>·</span>
            <span>本期手工建档客户不计入线索漏斗</span>
          </div>
        </div>
      </section>
    `;
  }

  const chartColors = {
    blue: "#2569e8",
    green: "#138a64",
    amber: "#d88a18",
    red: "#d64545",
    violet: "#7656d8",
    cyan: "#16849e",
    grey: "#8c98a8"
  };

  function renderDonut(items, valueGetter, centerLabel, formatValue) {
    const values = items.map(valueGetter);
    const total = values.reduce((sum, value) => sum + value, 0);
    let cursor = 0;
    const segments = items.map((item, index) => {
      const start = total ? (cursor / total) * 360 : 0;
      cursor += values[index];
      const end = total ? (cursor / total) * 360 : 360;
      return `${chartColors[item.tone] || chartColors.grey} ${start.toFixed(1)}deg ${end.toFixed(1)}deg`;
    }).join(", ");
    return `
      <div class="donut-panel">
        <div class="donut-chart" style="background:${total ? `conic-gradient(${segments})` : "#edf1f5"}">
          <div class="donut-hole">
            <b>${formatValue(total)}</b>
            <span>${escapeHtml(centerLabel)}</span>
          </div>
        </div>
        <div class="donut-legend">
          ${items.map((item, index) => `
            <button type="button" class="donut-legend-item" data-action="chart-detail"
              data-tip="${escapeHtml(item.name || item.label)}：${formatValue(values[index])}，${total ? Math.round(values[index] / total * 100) : 0}%">
              <i style="background:${chartColors[item.tone] || chartColors.grey}"></i>
              <span>${escapeHtml(item.name || item.label)}</span>
              <b>${total ? Math.round(values[index] / total * 100) : 0}%</b>
            </button>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderSources(sources) {
    const totalAmount = sources.reduce((sum, item) => sum + item.amount, 0);
    const maxLeads = Math.max(...sources.map((item) => item.leads), 1);
    return `
      <section class="card stats-panel">
        <div class="card-head">
          <div class="card-title"><h2>客源分析</h2></div>
          <span class="card-meta">成交结构 + 获客转化对比</span>
        </div>
        <div class="source-chart-grid">
          <div class="source-donut-block">
            <div class="subchart-head">
              <b>成交金额来源</b>
              <span>按来源成交额占比</span>
            </div>
            ${renderDonut(sources, (item) => item.amount, "成交金额", (value) => formatMoney(value, true))}
          </div>
          <div class="source-compare-block">
            <div class="subchart-head">
              <b>获客与转化</b>
              <span><i class="legend-dot"></i>新增线索　<i class="legend-dot green"></i>已转化</span>
            </div>
            <div class="source-compare-list">
              ${sources.map((item) => `
                <button type="button" class="source-compare-row" data-action="chart-detail"
                  data-tip="${escapeHtml(item.name)}：新增 ${item.leads} 条，转化 ${item.converted} 条，转化率 ${item.rate}%">
                  <span class="source-compare-name"><i class="source-mark ${item.tone}"></i>${escapeHtml(item.name)}</span>
                  <span class="source-compare-bars">
                    <i class="source-compare-bar leads" style="width:${(item.leads / maxLeads) * 100}%"></i>
                    <i class="source-compare-bar converted" style="width:${(item.converted / maxLeads) * 100}%"></i>
                  </span>
                  <span class="source-compare-count">${item.leads} / ${item.converted}</span>
                </button>
              `).join("")}
            </div>
          </div>
        </div>
        <div class="source-table-head">
          <b>来源明细</b>
          <span>金额单位：元</span>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>来源</th>
                <th>新增线索</th>
                <th>已转化</th>
                <th>转化率</th>
                <th>成交单数</th>
                <th>成交金额</th>
                <th>金额占比</th>
              </tr>
            </thead>
            <tbody>
              ${sources.map((item) => `
                <tr>
                  <td data-label="来源"><span class="source-name"><i class="source-mark ${item.tone}"></i>${escapeHtml(item.name)}</span></td>
                  <td data-label="新增线索">${item.leads}</td>
                  <td data-label="已转化">${item.converted}</td>
                  <td data-label="转化率"><span class="rate-pill${item.rate < 25 ? " low" : ""}">${item.rate}%</span></td>
                  <td data-label="成交单数">${item.won}</td>
                  <td data-label="成交金额">${formatMoney(item.amount)}</td>
                  <td data-label="金额占比">${totalAmount ? Math.round((item.amount / totalAmount) * 100) : 0}%</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }

  function renderProductRanking(products) {
    const max = Math.max(...products.map((item) => item.amount), 1);
    return `
      <section class="card">
        <div class="card-head">
          <div class="card-title"><h2>产品成交排行</h2></div>
          <span class="card-meta">按本期成交金额</span>
        </div>
        <div class="ranking-list">
          ${products.map((item, index) => `
            <div class="rank-row">
              <span class="rank-no">${index + 1}</span>
              <span class="rank-name"><b>${escapeHtml(item.name)}</b><small>${escapeHtml(item.code)} · ${item.count} 套</small></span>
              <span class="rank-track"><span class="rank-fill" style="width:${item.amount ? Math.max((item.amount / max) * 100, 3) : 0}%"></span></span>
              <span class="rank-amount">${formatMoney(item.amount)}</span>
            </div>
          `).join("")}
        </div>
      </section>
    `;
  }

  function renderStageSteps(items) {
    const max = Math.max(...items.map((item) => item.value), 1);
    return `
      <section class="card">
        <div class="card-head">
          <div class="card-title"><h2>商机阶段</h2></div>
          <span class="card-meta">本期新建商机的当前阶段</span>
        </div>
        <div class="stage-step-chart">
          ${items.map((item) => `
            <button type="button" class="stage-step" data-action="chart-detail"
              data-tip="${escapeHtml(item.label)}：${item.value} 个">
              <span class="stage-step-value">${item.value}</span>
              <span class="stage-step-bar ${item.tone}" style="height:${Math.max((item.value / max) * 100, 8)}%"></span>
              <span class="stage-step-label">${escapeHtml(item.label)}</span>
            </button>
          `).join("")}
          <svg class="stage-flow-line" viewBox="0 0 400 80" preserveAspectRatio="none" aria-hidden="true">
            <path d="M30 41 C90 15 120 15 160 34 S250 63 290 42 S340 20 370 25"></path>
            <path d="m360 18 11 7-10 7"></path>
          </svg>
        </div>
      </section>
    `;
  }

  function renderOrderPipeline(items) {
    const total = Math.max(items.reduce((sum, item) => sum + item.value, 0), 1);
    return `
      <section class="card">
        <div class="card-head">
          <div class="card-title"><h2>订单状态</h2></div>
          <span class="card-meta">本期订单的当前履约进度</span>
        </div>
        <div class="pipeline-chart">
          <div class="pipeline-total">
            <b>${items.reduce((sum, item) => sum + item.value, 0)}</b>
            <span>本期订单</span>
          </div>
          <div class="pipeline-bar" role="img" aria-label="订单状态分布">
            ${items.map((item) => `
              <button type="button" class="pipeline-segment ${item.tone}"
                style="flex:${Math.max(item.value, 1)}"
                data-action="chart-detail"
                data-tip="${escapeHtml(item.label)}：${item.value} 单，占 ${Math.round(item.value / total * 100)}%"
                title="${escapeHtml(item.label)}：${item.value} 单">
                <span>${item.value}</span>
              </button>
            `).join("")}
          </div>
          <div class="pipeline-legend">
            ${items.map((item) => `
              <span><i style="background:${chartColors[item.tone] || chartColors.grey}"></i>${escapeHtml(item.label)} <b>${item.value}</b></span>
            `).join("")}
          </div>
        </div>
      </section>
    `;
  }

  function renderAftersales(types, statuses, overdue) {
    const statusTotal = Math.max(statuses.reduce((sum, item) => sum + item.value, 0), 1);
    return `
      <section class="card">
        <div class="card-head">
          <div class="card-title"><h2>售后分析</h2></div>
          <span class="card-meta">${overdue} 单超过 3 天 SLA</span>
        </div>
        <div class="aftersale-chart-grid">
          <div>
            <div class="subchart-head"><b>售后类型</b><span>按单量占比</span></div>
            ${renderDonut(types, (item) => item.value, "售后单", (value) => `${value} 单`)}
          </div>
          <div class="service-status-panel">
            <div class="subchart-head"><b>处理状态</b><span>当前进度</span></div>
            ${statuses.map((item) => `
              <button type="button" class="service-status-row" data-action="chart-detail"
                data-tip="${escapeHtml(item.label)}：${item.value} 单，占 ${Math.round(item.value / statusTotal * 100)}%">
                <span>${escapeHtml(item.label)}</span>
                <i><b class="${item.tone}" style="width:${Math.max((item.value / statusTotal) * 100, item.value ? 5 : 0)}%"></b></i>
                <strong>${item.value}</strong>
              </button>
            `).join("")}
          </div>
        </div>
      </section>
    `;
  }

  function renderStats() {
    const data = state.stats[state.range];
    app.innerHTML = `
      <section class="page-enter">
        ${pageHeading()}

        ${statKpis(data)}

        <div class="insight-band">
          ${data.insights.map((item) => `
            <div class="insight">
              <span class="insight-icon">${item.icon}</span>
              <p>${item.text}</p>
            </div>
          `).join("")}
        </div>

        <div class="stats-grid">
          ${renderTrendCombo(data.trend)}
          ${renderFunnel(data.funnel)}
        </div>

        ${renderSources(data.sources)}

        <div class="stats-two">
          ${renderProductRanking(data.products)}
          ${renderStageSteps(data.dealStages)}
        </div>

        <div class="stats-two">
          ${renderOrderPipeline(data.orderStatus)}
          ${renderAftersales(data.serviceTypes, data.serviceStatus, data.summary.overdueAftersales)}
        </div>

        <details class="card methodology">
          <summary>查看统计口径</summary>
          <div>
            本期新增线索、成交金额、订单和售后均按所选自然时间区间统计。线索转化率按“本期新建线索的当前转化结果”计算，分母只包含线索池，因此不会超过 100%。成交金额以商机确认成交时记录的成交时间为准；售后超时按待处理超过 3 天计算。金额默认遮罩，点击右上角眼睛可查看真实数值。
          </div>
        </details>
      </section>
    `;
  }

  function render() {
    document.querySelectorAll(".nav-item").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.page === state.page);
    });
    document.body.classList.toggle("money-hidden", !state.moneyVisible);
    if (state.page === "stats") {
      renderStats();
    } else {
      renderDashboard();
    }
  }

  function scrollToCard(id) {
    const card = document.getElementById(id);
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.animate(
      [
        { outline: "0 solid rgba(37, 105, 232, 0)" },
        { outline: "3px solid rgba(37, 105, 232, 0.18)" },
        { outline: "0 solid rgba(37, 105, 232, 0)" }
      ],
      { duration: 900, easing: "ease-out" }
    );
  }

  function openFollowupModal(id) {
    const item = state.followups.find((followup) => followup.id === id);
    if (!item) return;
    modalRoot.innerHTML = `
      <div class="modal-backdrop" data-action="close-modal">
        <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="modalTitle" data-modal-panel>
          <div class="modal-head">
            <h3 id="modalTitle">给 ${escapeHtml(item.name)} 记一条跟进</h3>
            <button type="button" class="close-button" data-action="close-modal" aria-label="关闭">×</button>
          </div>
          <form class="modal-body" id="followupForm">
            <div class="field">
              <label for="followContent">跟进内容 *</label>
              <textarea id="followContent" required placeholder="聊了什么、客户什么态度、下一步做什么"></textarea>
            </div>
            <div class="form-two">
              <div class="field">
                <label for="followMethod">跟进方式</label>
                <select id="followMethod">
                  <option value="微信">微信</option>
                  <option value="电话">电话</option>
                </select>
              </div>
              <div class="field">
                <label for="nextDate">下次跟进</label>
                <input id="nextDate" type="date">
              </div>
            </div>
            <div class="modal-actions">
              <button type="button" class="button" data-action="close-modal">取消</button>
              <button type="submit" class="button button-primary">保存跟进</button>
            </div>
          </form>
        </div>
      </div>
    `;

    const form = document.getElementById("followupForm");
    const content = document.getElementById("followContent");
    content.focus();
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const text = content.value.trim();
      if (!text) {
        content.focus();
        showToast("请填写跟进内容");
        return;
      }
      state.followups = state.followups.filter((followup) => followup.id !== id);
      state.activities.unshift({
        icon: "跟",
        tone: "follow",
        text: `跟进 ${item.name}：${text}`,
        time: "刚刚"
      });
      state.activities = state.activities.slice(0, 6);
      closeModal();
      render();
      showToast(`已记录 ${item.name} 的跟进`);
    });
  }

  function closeModal() {
    modalRoot.innerHTML = "";
  }

  function openCustomerDrawer(id) {
    const item = state.followups.find((followup) => followup.id === id);
    if (!item) return;
    openDrawer(`
      <span class="drawer-kicker">${escapeHtml(item.type)}概况</span>
      <div class="drawer-top">
        <h3>${escapeHtml(item.name)}</h3>
        <button type="button" class="close-button" data-action="close-drawer" aria-label="关闭">×</button>
      </div>
      <div class="drawer-summary">${escapeHtml(item.note)}</div>
      <div class="drawer-grid">
        <div class="drawer-cell"><small>联系电话</small><b>${escapeHtml(item.phone)}</b></div>
        <div class="drawer-cell"><small>意向等级</small><b>${escapeHtml(item.intent)}</b></div>
        <div class="drawer-cell"><small>当前阶段</small><b>${escapeHtml(item.stage)}</b></div>
        <div class="drawer-cell"><small>下次跟进</small><b>${escapeHtml(item.due)}</b></div>
      </div>
      <div class="drawer-note">
        <h4>最近一次沟通</h4>
        <p>${escapeHtml(item.content)}</p>
      </div>
      <div class="modal-actions" style="margin-top:24px;">
        <button type="button" class="button" data-action="close-drawer">关闭</button>
        <button type="button" class="button button-primary" data-action="record" data-id="${item.id}">继续跟进</button>
      </div>
    `);
  }

  function openServiceDrawer(id) {
    const item = state.services.find((service) => service.id === id);
    if (!item) return;
    const urgent = item.age > 3;
    openDrawer(`
      <span class="drawer-kicker">售后服务单</span>
      <div class="drawer-top">
        <h3>${escapeHtml(item.no)}</h3>
        <button type="button" class="close-button" data-action="close-drawer" aria-label="关闭">×</button>
      </div>
      <div class="drawer-summary" style="${urgent ? "background:#fff3f3;border-color:#f3d1d1;color:#914545;" : ""}">
        ${urgent ? `<b>已超过 3 天 SLA</b><br>` : ""}${escapeHtml(item.summary)}
      </div>
      <div class="drawer-grid">
        <div class="drawer-cell"><small>客户</small><b>${escapeHtml(item.customer)}</b></div>
        <div class="drawer-cell"><small>售后类型</small><b>${escapeHtml(item.type)}</b></div>
        <div class="drawer-cell"><small>当前状态</small><b>${escapeHtml(item.status)}</b></div>
        <div class="drawer-cell"><small>挂起时间</small><b>${item.age} 天</b></div>
      </div>
      <div class="drawer-note">
        <h4>推荐处理</h4>
        <p>先电话确认现场情况和客户可接受的上门时间，然后在售后详情中记录沟通结果。售后单保存跟进后会自动进入“处理中”。</p>
      </div>
      <div class="modal-actions" style="margin-top:24px;">
        <button type="button" class="button" data-action="close-drawer">稍后处理</button>
        <button type="button" class="button button-primary" data-action="service-confirm">立即处理</button>
      </div>
    `);
  }

  function openOrderDrawer(status) {
    const order = state.orders.find((item) => item.key === status);
    if (!order) return;
    const samples = {
      pending_confirmation: ["SO-2026-11-001 · 王志远 · 待回签下单表", "SO-2026-11-004 · 韩雪 · 等待尺寸确认"],
      pending_payment: ["SO-2026-10-003 · 孙丽华 · 押金 ¥2,600", "SO-2026-10-006 · 赵明辉 · 押金 ¥3,000", "SO-2026-10-007 · 马晓东 · 押金 ¥5,000"],
      deposit_paid: ["SO-2026-10-002 · 陈国强 · 可排产"],
      producing: ["SO-2026-10-002 · 刘俊峰 · 预计 11/08 完工", "SO-2026-10-005 · 周建军 · 预计 11/10 完工"],
      balance_paid: ["SO-2026-10-001 · 王志远 · 已收尾款 ¥8,400", "SO-2026-10-004 · 李秀娟 · 已收尾款 ¥9,500"],
      ready_to_ship: ["SO-2026-10-004 · 李秀娟 · 等待安排物流"],
      shipped: ["SO-2026-10-008 · 赵明辉 · 顺丰 SF1234567890", "SO-2026-10-009 · 周建军 · 德邦待签收"]
    };
    openDrawer(`
      <span class="drawer-kicker">订单阶段</span>
      <div class="drawer-top">
        <h3>${escapeHtml(order.label)}</h3>
        <button type="button" class="close-button" data-action="close-drawer" aria-label="关闭">×</button>
      </div>
      <div class="drawer-summary">
        当前该阶段共有 <b>${order.count} 单</b>。${escapeHtml(order.sub)}。正式页面点击后会把状态作为筛选条件带入订单列表。
      </div>
      <div class="drawer-note" style="margin-top:20px;">
        <h4>代表性订单</h4>
        ${samples[status].map((line) => `<p style="padding:10px 0;border-bottom:1px solid #eef1f5;">${escapeHtml(line)}</p>`).join("")}
      </div>
      <div class="modal-actions" style="margin-top:24px;">
        <button type="button" class="button" data-action="close-drawer">关闭</button>
        <button type="button" class="button button-primary" data-action="demo-jump">进入订单列表</button>
      </div>
    `);
  }

  function openDrawer(content) {
    drawerRoot.innerHTML = `
      <div class="drawer-backdrop" data-action="close-drawer">
        <aside class="drawer-panel" role="dialog" aria-modal="true" data-drawer-panel>
          ${content}
        </aside>
      </div>
    `;
  }

  function closeDrawer() {
    drawerRoot.innerHTML = "";
  }

  let toastTimer = null;
  function showToast(message) {
    clearTimeout(toastTimer);
    toastEl.textContent = message;
    toastEl.classList.add("show");
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2200);
  }

  function switchPage(page, updateHash) {
    state.page = page;
    if (updateHash) {
      history.replaceState(null, "", `#/${page}`);
    }
    closeDrawer();
    closeModal();
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.addEventListener("click", function (event) {
    const pageButton = event.target.closest(".nav-item[data-page]");
    if (pageButton) {
      switchPage(pageButton.dataset.page, true);
      return;
    }

    const actionEl = event.target.closest("[data-action]");
    if (!actionEl) return;
    const action = actionEl.dataset.action;

    if (action === "range") {
      state.range = actionEl.dataset.range;
      render();
      return;
    }

    if (action === "record") {
      closeDrawer();
      openFollowupModal(Number(actionEl.dataset.id));
      return;
    }

    if (action === "customer") {
      openCustomerDrawer(Number(actionEl.dataset.id));
      return;
    }

    if (action === "service") {
      openServiceDrawer(Number(actionEl.dataset.id));
      return;
    }

    if (action === "service-confirm") {
      closeDrawer();
      showToast("演示：正式页面将进入售后处理并记录沟通结果");
      return;
    }

    if (action === "order-status") {
      openOrderDrawer(actionEl.dataset.value);
      return;
    }

    if (action === "focus-followups") {
      scrollToCard("followupCard");
      return;
    }

    if (action === "focus-orders") {
      scrollToCard("ordersCard");
      return;
    }

    if (action === "focus-services") {
      scrollToCard("serviceCard");
      return;
    }

    if (action === "all-followups" || action === "quick-lead") {
      showToast(action === "quick-lead" ? "演示：正式页面将打开线索新增表单" : "演示：正式页面将进入完整跟进列表");
      return;
    }

    if (action === "refresh") {
      showToast("演示数据已是最新");
      return;
    }

    if (action === "demo-jump") {
      showToast("演示版仅展示入口，不会跳转到真实订单");
      return;
    }

    if (action === "chart-detail") {
      showToast(actionEl.dataset.tip || "已选中图表数据");
      return;
    }

    if (action === "close-modal") {
      if (actionEl.classList.contains("modal-backdrop") && event.target.closest("[data-modal-panel]")) return;
      closeModal();
      return;
    }

    if (action === "close-drawer") {
      if (actionEl.classList.contains("drawer-backdrop") && event.target.closest("[data-drawer-panel]")) return;
      closeDrawer();
    }
  });

  document.getElementById("moneyToggle").addEventListener("click", function () {
    state.moneyVisible = !state.moneyVisible;
    render();
    showToast(state.moneyVisible ? "金额已显示" : "金额已隐藏");
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeModal();
      closeDrawer();
    }
  });

  window.addEventListener("hashchange", function () {
    const page = location.hash.replace(/^#\//, "");
    if ((page === "dashboard" || page === "stats") && page !== state.page) {
      switchPage(page, false);
    }
  });

  const initialPage = location.hash.replace(/^#\//, "");
  state.page = initialPage === "stats" ? "stats" : "dashboard";
  render();
})();
