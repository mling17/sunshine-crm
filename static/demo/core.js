/* ============================================================================
 * CRM V2 · 前端 Demo 内核（纯 mock，不发任何网络请求）
 *
 * 用途：给用户定稿页面样式/字段/交互用。所有数据来自下面的 MOCK 常量。
 * 与正式版的关系：正式版 static/app.js 里的工具函数、枚举、路由在这里原样复刻，
 *                 views/*.js 直接复用，只有 api() 换成了本文件的 mock 实现。
 * 地址：http://10.113.9.77:8000/crm/demo/
 * ==========================================================================*/
(function () {
  'use strict';

  /* ---------------- 常量（与正式版 app.js 保持一致） ---------------- */
  var PAGE_SIZE = 20;
  var MAX_PHOTOS = 3;
  var MAX_PHOTO_MB = 20;
  var MAX_TAGS = 20;

  var STAGES = [
    ['confirm', '需求确认'],
    ['quote', '报价'],
    ['negotiate', '成交洽谈'],
    ['won', '赢单'],
    ['lost', '流失']
  ];
  var STAGE_LABEL = {};
  STAGES.forEach(function (p) { STAGE_LABEL[p[0]] = p[1]; });

  var ORDER_STATUS = [
    ['pending_payment', '待支付'],
    ['deposit_paid', '已付押金'],
    ['producing', '生产中'],
    ['balance_paid', '已付尾款'],
    ['ready_to_ship', '待发货'],
    ['shipped', '已发货'],
    ['completed', '已完成']
  ];
  var ORDER_STATUS_LABEL = {};
  ORDER_STATUS.forEach(function (p) { ORDER_STATUS_LABEL[p[0]] = p[1]; });

  var ORDER_FLOW = {
    pending_payment: 'deposit_paid', deposit_paid: 'producing', producing: 'balance_paid',
    balance_paid: 'ready_to_ship', ready_to_ship: 'shipped', shipped: 'completed', completed: null
  };

  var AFTERSALE_TYPE_LABEL = { return: '退货', exchange: '换货', repair: '维修', complaint: '投诉', other: '其他' };
  var AFTERSALE_STATUS_LABEL = { pending: '待处理', processing: '处理中', done: '已完成', rejected: '已拒绝' };
  var SOURCE_LABELS = { wechat: '微信', phone: '电话', referral: '转介绍', existing: '老客户', stock: '存量', other: '其他' };
  var INTENT_LABELS = { high: '高', medium: '中', low: '低', none: '无意向' };

  /* ---------------- 工具 ---------------- */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(v) {
    return String(v === null || v === undefined ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function pad2(n) { return n < 10 ? '0' + n : String(n); }
  function iso(d) { return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()); }
  function todayISO() { return iso(new Date()); }
  /** n 天前/后（正数=过去） */
  function dayOff(n) { var d = new Date(); d.setDate(d.getDate() - n); return iso(d); }
  function money(value) {
    var n = Number(value) || 0;
    if (!state.showMoney) { return '¥••••'; }
    return '¥' + n.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  }
  function moneyRaw(value) { return '¥' + (Number(value) || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 }); }
  function fmtDateTime(v) {
    if (!v) { return '—'; }
    return String(v).replace('T', ' ').replace('Z', '').slice(0, 16);
  }
  function numOrNull(raw) {
    var s = String(raw === null || raw === undefined ? '' : raw).trim();
    if (!s) { return null; }
    var n = Number(s);
    return isNaN(n) ? null : n;
  }
  var toastTimer = null;
  function toast(msg, isError) {
    var el = document.getElementById('toast');
    if (!el) { return; }
    el.textContent = msg;
    el.className = 'toast show' + (isError ? ' toast-error' : '');
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 2400);
  }

  /* ---------------- 全局状态 ---------------- */
  var state = {
    me: '陈明（演示账号）',
    showMoney: false,          // 金额遮罩：默认遮住，点 👁 显示（Q6 ✅）
    filters: { q: '', tag: '', page: 1, status: '' },
    import: { preview: null, result: null },
    customers: { index: null, builtAt: 0 }
  };
  var renderSeq = 0;

  /* ============================================================================
   * MOCK 数据（天窗/天幕/阳光房真实业务场景，非 foo/bar）
   * ==========================================================================*/

  function d(n, hm) { return dayOff(n) + 'T' + (hm || '10:00') + ':00'; }

  var TAG_NAMES = ['重点', '转介绍', '工程商', '老客户', '价格敏感', '沉睡'];

  var CUSTOMERS = [
    { id: 1, name: '王志远', customer_type: 'personal', phone: '138 5312 7745', wechat: 'wzy5312', location: '济南·万科城 12-3-1801', note: '主卧天窗，老婆要遮阳帘', source: 'wechat', intent_level: 'high', company_name: null, tags: ['重点', '转介绍'], created_at: d(46, '09:12'), updated_at: d(2, '16:20') },
    { id: 2, name: '刘俊峰', customer_type: 'company', phone: '139 0532 8811', wechat: 'hJZS888', location: '青岛·崂山区海尔路', note: '装饰公司，工地用量大，走对公', source: 'referral', intent_level: 'high', company_name: '青岛海景装饰工程有限公司', tags: ['重点', '工程商'], created_at: d(120, '11:00'), updated_at: d(1, '09:40') },
    { id: 3, name: '孙丽华', customer_type: 'personal', phone: '150 5337 2210', wechat: null, location: '淄博·张店区齐悦花园', note: '二次复购，去年装过天幕', source: 'existing', intent_level: 'medium', company_name: null, tags: ['老客户'], created_at: d(210, '15:30'), updated_at: d(1, '18:05') },
    { id: 4, name: '陈国强', customer_type: 'company', phone: '137 0636 5566', wechat: 'cgq_wf', location: '潍坊·奎文区建材市场', note: '一直压价，说同行便宜200/平', source: 'phone', intent_level: 'low', company_name: '潍坊鲁中建材有限公司', tags: ['价格敏感'], created_at: d(80, '10:20'), updated_at: d(8, '14:00') },
    { id: 5, name: '李秀娟', customer_type: 'personal', phone: '186 5388 9012', wechat: 'lxj9012', location: '泰安·泰山公馆 6-1-901', note: '妹妹介绍来的，看重隔音', source: 'referral', intent_level: 'high', company_name: null, tags: ['转介绍', '重点'], created_at: d(24, '20:10'), updated_at: d(2, '10:30') },
    { id: 6, name: '赵明辉', customer_type: 'personal', phone: '135 5311 4408', wechat: 'zhaomh01', location: '济南·绿城百合 3-2-1202', note: '顶楼，考虑天窗+遮阳一体', source: 'wechat', intent_level: 'medium', company_name: null, tags: [], created_at: d(38, '08:45'), updated_at: d(5, '17:10') },
    { id: 7, name: '周建军', customer_type: 'company', phone: '133 0535 7788', wechat: 'yjygf6688', location: '烟台·芝罘区幸福路', note: '阳光房工程商，长期合作', source: 'existing', intent_level: 'high', company_name: '烟台宜居阳光房工程有限公司', tags: ['工程商', '老客户'], created_at: d(300, '09:00'), updated_at: d(6, '11:20') },
    { id: 8, name: '吴红梅', customer_type: 'personal', phone: '158 5399 3321', wechat: null, location: '临沂·兰山区书香门第', note: '只问价，说再考虑', source: 'phone', intent_level: 'none', company_name: null, tags: ['沉睡'], created_at: d(95, '16:40'), updated_at: d(60, '09:00') },
    { id: 9, name: '郑海涛', customer_type: 'personal', phone: '151 5316 6688', wechat: 'zht_6688', location: '济南·汉峪金谷 A7', note: '新客，抖音看到案例来的', source: 'other', source_other: '抖音', intent_level: 'high', company_name: null, tags: ['重点'], created_at: d(5, '21:15'), updated_at: d(1, '12:00') },
    { id: 10, name: '马晓东', customer_type: 'company', phone: '136 0534 2233', wechat: 'dfmc2024', location: '德州·经济开发区', note: '门窗同行，问批量价', source: 'referral', intent_level: 'medium', company_name: '德州东方门窗有限公司', tags: ['工程商', '价格敏感'], created_at: d(16, '14:30'), updated_at: d(3, '16:00') }
  ];

  var DEALS = [
    { id: 1, customer_id: 1, product_type: '天窗', model: 'XW-120', spec: '1200×2400', amount: 12000, deposit: 3600, balance: 8400, stage: 'won', closed_at: d(16, '15:20'), created_at: d(46, '09:30'), deposit_paid: 3600, balance_paid: 8400 },
    { id: 2, customer_id: 2, product_type: '天幕', model: 'TM-240', spec: '2400×3000', amount: 45000, deposit: 13500, balance: 31500, stage: 'won', closed_at: d(11, '10:10'), created_at: d(60, '11:00'), deposit_paid: 13500, balance_paid: 0 },
    { id: 3, customer_id: 3, product_type: '天窗', model: 'XW-90', spec: '900×1800', amount: 8600, deposit: 2600, balance: 6000, stage: 'won', closed_at: d(3, '09:05'), created_at: d(9, '15:30'), deposit_paid: 0, balance_paid: 0 },
    { id: 4, customer_id: 4, product_type: '阳光房', model: 'YG-30', spec: '3000×4000 定制', amount: 68000, deposit: 20000, balance: 48000, stage: 'won', closed_at: d(49, '14:00'), created_at: d(80, '10:40'), deposit_paid: 20000, balance_paid: 0 },
    { id: 5, customer_id: 5, product_type: '天窗', model: 'XW-120', spec: '1200×2400 双层中空', amount: 13500, deposit: 4000, balance: 9500, stage: 'won', closed_at: d(7, '16:40'), created_at: d(24, '20:30'), deposit_paid: 4000, balance_paid: 9500 },
    { id: 6, customer_id: 6, product_type: '天窗', model: 'XW-90', spec: '900×2000', amount: 9800, deposit: 3000, balance: 6800, stage: 'won', closed_at: d(5, '11:15'), created_at: d(38, '09:00'), deposit_paid: 3000, balance_paid: 6800 },
    { id: 7, customer_id: 7, product_type: '天幕', model: 'TM-300', spec: '3000×3500', amount: 52000, deposit: 15000, balance: 37000, stage: 'won', closed_at: d(36, '10:30'), created_at: d(55, '09:20'), deposit_paid: 15000, balance_paid: 37000 },
    { id: 8, customer_id: 9, product_type: '天窗', model: 'XW-120', spec: '1200×2400', amount: 22000, deposit: 0, balance: 0, stage: 'confirm', closed_at: null, created_at: d(4, '21:40') },
    { id: 9, customer_id: 10, product_type: '天幕', model: 'TM-180', spec: '1800×2600 ×6套', amount: 16500, deposit: 0, balance: 0, stage: 'quote', closed_at: null, created_at: d(15, '14:40') },
    { id: 10, customer_id: 2, product_type: '天窗', model: 'XW-150', spec: '1500×2800', amount: 58000, deposit: 0, balance: 0, stage: 'quote', closed_at: null, created_at: d(6, '10:00') },
    { id: 11, customer_id: 3, product_type: '天窗', model: 'XW-90', spec: '900×1800 阳台', amount: 9200, deposit: 0, balance: 0, stage: 'confirm', closed_at: null, created_at: d(2, '18:10') },
    { id: 12, customer_id: 4, product_type: '阳光房', model: 'YG-30', spec: '3000×4200 定制', amount: 68000, deposit: 0, balance: 0, stage: 'negotiate', closed_at: null, created_at: d(8, '14:10') },
    { id: 13, customer_id: 8, product_type: '遮阳帘', model: 'ZY-15', spec: '1500×2000', amount: 3200, deposit: 0, balance: 0, stage: 'lost', closed_at: d(60, '09:30'), created_at: d(95, '17:00'), lost_reason: 'price', lost_reason_other: null }
  ];

  var ORDERS = [
    { id: 1, order_no: 'SO-2026-09-001', customer_id: 4, deal_id: 4, product_type: '阳光房', model: 'YG-30', spec: '3000×4000 定制', amount: 68000, paid_amount: 20000, status: 'deposit_paid', created_at: d(49, '14:20'), updated_at: d(46, '10:00') },
    { id: 2, order_no: 'SO-2026-09-002', customer_id: 7, deal_id: 7, product_type: '天幕', model: 'TM-300', spec: '3000×3500', amount: 52000, paid_amount: 52000, status: 'completed', created_at: d(36, '10:40'), updated_at: d(12, '15:30') },
    { id: 3, order_no: 'SO-2026-10-001', customer_id: 1, deal_id: 1, product_type: '天窗', model: 'XW-120', spec: '1200×2400', amount: 12000, paid_amount: 12000, status: 'balance_paid', created_at: d(16, '15:30'), updated_at: d(6, '11:00') },
    { id: 4, order_no: 'SO-2026-10-002', customer_id: 2, deal_id: 2, product_type: '天幕', model: 'TM-240', spec: '2400×3000', amount: 45000, paid_amount: 13500, status: 'producing', created_at: d(11, '10:20'), updated_at: d(9, '09:00') },
    { id: 5, order_no: 'SO-2026-10-003', customer_id: 3, deal_id: 3, product_type: '天窗', model: 'XW-90', spec: '900×1800', amount: 8600, paid_amount: 0, status: 'pending_payment', created_at: d(3, '09:10'), updated_at: d(3, '09:10') },
    { id: 6, order_no: 'SO-2026-10-004', customer_id: 5, deal_id: 5, product_type: '天窗', model: 'XW-120', spec: '1200×2400 双层中空', amount: 13500, paid_amount: 13500, status: 'ready_to_ship', created_at: d(7, '16:50'), updated_at: d(2, '10:00') },
    { id: 7, order_no: 'SO-2026-10-005', customer_id: 6, deal_id: 6, product_type: '天窗', model: 'XW-90', spec: '900×2000', amount: 9800, paid_amount: 9800, status: 'shipped', created_at: d(5, '11:20'), updated_at: d(1, '16:00'), tracking_number: 'SF1234567890' }
  ];

  var AFTERSALES = [
    { id: 1, no: 'AS-20261020-001', order_id: 1, customer_id: 4, type: 'repair', description: '阳光房右侧推拉门关不严，下雨渗水', status: 'pending', created_at: d(5, '09:30'), updated_at: d(5, '09:30') },
    { id: 2, no: 'AS-20261025-002', order_id: 2, customer_id: 7, type: 'return', description: '客户要求更换遮阳帘电机（噪音大）', status: 'processing', created_at: d(3, '14:00'), updated_at: d(1, '10:20') },
    { id: 3, no: 'AS-20261015-003', order_id: 6, customer_id: 5, type: 'complaint', description: '安装师傅迟到两小时，客户投诉', status: 'done', result: '已道歉并赠送保养一次', closed_at: d(4, '17:00'), created_at: d(9, '11:00'), updated_at: d(4, '17:00') }
  ];

  var CARRIERS = [
    { id: 1, name: '顺丰快运', contact: '李经理', phone: '95338', note: '大件走顺丰快运，含装卸', is_active: true },
    { id: 2, name: '德邦物流', contact: '王师傅', phone: '138 0000 1234', note: '德州/潍坊方向常走', is_active: true },
    { id: 3, name: '济南本地专线', contact: '老张', phone: '139 5311 0001', note: '济南市区当日达', is_active: true },
    { id: 4, name: '安能物流（已停用）', contact: '—', phone: '—', note: '2026 年起不再合作', is_active: false }
  ];

  /* 跟进记录：注意「今日待跟进」是按客户取最近一条计算的（对应 PAGES-V2 §1.2） */
  var FOLLOWUPS = [
    { id: 1, object_type: 'customer', object_id: 4, customer_id: 4, deal_id: 12, method: 'phone', content: '又压价，说隔壁报 620/平；我强调型材厚度不一样', next_date: dayOff(8), created_at: d(8, '14:00') },
    { id: 2, object_type: 'customer', object_id: 1, customer_id: 1, deal_id: null, method: 'wechat', content: '尾款已收到，约下周三上门安装（安装提醒）', next_date: dayOff(2), created_at: d(2, '16:20') },
    { id: 3, object_type: 'customer', object_id: 3, customer_id: 3, deal_id: 11, method: 'wechat', content: '阳台天窗尺寸已确认 900×1800，等她老公周末回来定颜色', next_date: todayISO(), created_at: d(1, '18:05') },
    { id: 4, object_type: 'customer', object_id: 5, customer_id: 5, deal_id: null, method: 'visit', content: '上门量尺，客户关注隔音，推荐双层中空玻璃', next_date: todayISO(), created_at: d(2, '10:30') },
    { id: 5, object_type: 'customer', object_id: 6, customer_id: 6, deal_id: 6, method: 'phone', content: '货已发出，运单号发她微信了', next_date: dayOff(-4), created_at: d(1, '16:10') },
    { id: 6, object_type: 'customer', object_id: 9, customer_id: 9, deal_id: 8, method: 'wechat', content: '抖音来的新客，发了 3 个案例视频，约周日上午到店', next_date: dayOff(-2), created_at: d(1, '12:00') },
    { id: 7, object_type: 'customer', object_id: 10, customer_id: 10, deal_id: 9, method: 'phone', content: '批量 6 套，要求开票，报了 16500 含安装', next_date: dayOff(-6), created_at: d(3, '16:00') },
    { id: 8, object_type: 'customer', object_id: 2, customer_id: 2, deal_id: 10, method: 'wechat', content: '海尔路工地第二套天窗，等甲方确认图纸', next_date: dayOff(-3), created_at: d(1, '09:40') },
    { id: 9, object_type: 'customer', object_id: 7, customer_id: 7, deal_id: 7, method: 'phone', content: '工程款已结清，明年还有两栋楼', next_date: null, created_at: d(6, '11:20') },
    { id: 10, object_type: 'customer', object_id: 8, customer_id: 8, deal_id: 13, method: 'phone', content: '只问价，说再考虑，已流失', next_date: null, created_at: d(60, '09:30') },
    { id: 11, object_type: 'customer', object_id: 9, customer_id: 9, deal_id: 8, method: 'visit', content: '到店看了样窗，很想做，问能不能月底前装', next_date: dayOff(-1), created_at: d(1, '12:00') }
  ];

  var LEADS = [
    { id: 1, name: '韩雪', phone: '187 5311 2299', wechat: 'hanxue88', lead_type: 'personal', company_name: null, source: 'other', source_other: '抖音', location: '济南·中海国际', note: '刷到案例，问 90 平顶楼能不能做', intent_level: 'high', status: 'new', tags: ['重点'], created_at: d(0, '08:30'), next_date: null },
    { id: 2, name: '高建华', phone: '133 0538 7712', wechat: null, lead_type: 'company', company_name: '泰安恒基装饰', source: 'referral', location: '泰安·高新区', note: '同行介绍，说手上有 5 套要装', intent_level: 'high', status: 'following', tags: ['工程商'], created_at: d(3, '10:10'), next_date: dayOff(-1) },
    { id: 3, name: '徐婷', phone: '159 0531 3344', wechat: 'xt_3344', lead_type: 'personal', company_name: null, source: 'wechat', location: '济南·奥体西路', note: '想装天幕，预算 3 万内', intent_level: 'medium', status: 'following', tags: [], created_at: d(6, '19:40'), next_date: todayISO() },
    { id: 4, name: '孟凡', phone: '135 0537 9988', wechat: null, lead_type: 'personal', company_name: null, source: 'phone', location: '济宁·任城区', note: '电销名单，电话空号', intent_level: 'none', status: 'invalid', invalid_reason: 'invalid_phone', tags: [], created_at: d(9, '11:00'), next_date: null },
    { id: 5, name: '于振国', phone: '138 0535 6677', wechat: 'yzg5353', lead_type: 'personal', company_name: null, source: 'referral', location: '烟台·龙口', note: '已转化，签了 900×2000 天窗', intent_level: 'high', status: 'converted', converted_customer_id: 6, tags: ['转介绍'], created_at: d(40, '09:00'), next_date: null }
  ];

  var DICTS = [
    { code: 'customer_source', name: '客户来源', level: 'A', desc: '客户建档/线索来源', items: [
      { key: 'wechat', label: '微信', sort: 1, enabled: true, used: 4 },
      { key: 'phone', label: '电话', sort: 2, enabled: true, used: 3 },
      { key: 'referral', label: '转介绍', sort: 3, enabled: true, used: 4 },
      { key: 'existing', label: '老客户', sort: 4, enabled: true, used: 2 },
      { key: 'stock', label: '存量导入', sort: 5, enabled: true, used: 0 },
      { key: 'other', label: '其他', sort: 6, enabled: true, used: 1 }
    ] },
    { code: 'intent_level', name: '意向等级', level: 'A', desc: '客户/线索的购买意向', items: [
      { key: 'high', label: '高', sort: 1, enabled: true, used: 6 },
      { key: 'medium', label: '中', sort: 2, enabled: true, used: 3 },
      { key: 'low', label: '低', sort: 3, enabled: true, used: 1 },
      { key: 'none', label: '无意向', sort: 4, enabled: true, used: 1 }
    ] },
    { code: 'product_type', name: '产品类型', level: 'A', desc: '商机/订单的产品分类（Q8 ✅ 改为下拉可新增）', items: [
      { key: 'tianchuang', label: '天窗', sort: 1, enabled: true, used: 6 },
      { key: 'tianmu', label: '天幕', sort: 2, enabled: true, used: 3 },
      { key: 'yangguangfang', label: '阳光房', sort: 3, enabled: true, used: 2 },
      { key: 'zheyanglian', label: '遮阳帘', sort: 4, enabled: true, used: 1 }
    ] },
    { code: 'lost_reason', name: '商机流失原因', level: 'A', desc: '商机判流失时必选', items: [
      { key: 'price', label: '价格', sort: 1, enabled: true, used: 1 },
      { key: 'competitor', label: '竞品', sort: 2, enabled: true, used: 0 },
      { key: 'give_up', label: '客户放弃', sort: 3, enabled: true, used: 0 },
      { key: 'budget', label: '预算不足', sort: 4, enabled: true, used: 0 },
      { key: 'other', label: '其他', sort: 5, enabled: true, used: 0 }
    ] },
    { code: 'aftersale_type', name: '售后类型', level: 'A', desc: '售后单类型', items: [
      { key: 'return', label: '退货', sort: 1, enabled: true, used: 1 },
      { key: 'exchange', label: '换货', sort: 2, enabled: true, used: 0 },
      { key: 'repair', label: '维修', sort: 3, enabled: true, used: 1 },
      { key: 'complaint', label: '投诉', sort: 4, enabled: true, used: 1 },
      { key: 'other', label: '其他', sort: 5, enabled: true, used: 0 }
    ] },
    { code: 'follow_method', name: '跟进方式', level: 'A', desc: '记跟进时的方式', items: [
      { key: 'phone', label: '电话', sort: 1, enabled: true, used: 4 },
      { key: 'wechat', label: '微信', sort: 2, enabled: true, used: 3 },
      { key: 'visit', label: '到面/上门', sort: 3, enabled: true, used: 1 },
      { key: 'online', label: '线上', sort: 4, enabled: true, used: 0 }
    ] },
    { code: 'deal_stage', name: '商机阶段', level: 'B', desc: '状态机，只能改名/排序，不能增删', items: [
      { key: 'confirm', label: '需求确认', sort: 1, enabled: true, used: 3 },
      { key: 'quote', label: '报价', sort: 2, enabled: true, used: 2 },
      { key: 'negotiate', label: '成交洽谈', sort: 3, enabled: true, used: 1 },
      { key: 'won', label: '赢单', sort: 4, enabled: true, used: 7 },
      { key: 'lost', label: '流失', sort: 5, enabled: true, used: 1 }
    ] },
    { code: 'order_status', name: '订单状态', level: 'B', desc: '状态机，只能改名，不能增删', items: [
      { key: 'pending_payment', label: '待支付', sort: 1, enabled: true, used: 1 },
      { key: 'deposit_paid', label: '已付押金', sort: 2, enabled: true, used: 1 },
      { key: 'producing', label: '生产中', sort: 3, enabled: true, used: 1 },
      { key: 'balance_paid', label: '已付尾款', sort: 4, enabled: true, used: 1 },
      { key: 'ready_to_ship', label: '待发货', sort: 5, enabled: true, used: 1 },
      { key: 'shipped', label: '已发货', sort: 6, enabled: true, used: 1 },
      { key: 'completed', label: '已完成', sort: 7, enabled: true, used: 1 }
    ] },
    { code: 'aftersale_status', name: '售后状态', level: 'B', desc: '状态机，只能改名', items: [
      { key: 'pending', label: '待处理', sort: 1, enabled: true, used: 1 },
      { key: 'processing', label: '处理中', sort: 2, enabled: true, used: 1 },
      { key: 'done', label: '已完成', sort: 3, enabled: true, used: 1 },
      { key: 'rejected', label: '已拒绝', sort: 4, enabled: true, used: 0 }
    ] },
    { code: 'customer_type', name: '客户类型', level: 'C', desc: '绑定「公司名是否必填」，只能改名', items: [
      { key: 'personal', label: '个人', sort: 1, enabled: true, used: 7 },
      { key: 'company', label: '公司', sort: 2, enabled: true, used: 3 }
    ] },
    { code: 'follow_object', name: '跟进对象类型', level: 'D', desc: '系统定义，只读', items: [
      { key: 'lead', label: '线索', sort: 1, enabled: true, used: 2 },
      { key: 'customer', label: '客户', sort: 2, enabled: true, used: 10 },
      { key: 'deal', label: '商机', sort: 3, enabled: true, used: 0 },
      { key: 'order', label: '订单', sort: 4, enabled: true, used: 0 },
      { key: 'aftersale', label: '售后', sort: 5, enabled: true, used: 0 }
    ] }
  ];


  /* ============================================================================
   * V2.1 页面规格（2026-10-31 用户定稿）新增字段
   *   · 商机：手动/电动、型号字典、尺寸、变更履历、订单生成后锁定
   *   · 订单：物流方式、收件人、承运公司、运单号
   *   · 线索：地区、上次跟进时间、意向默认「中」
   *   · 客户：客户画像
   *   · 物流公司：被订单关联次数
   * ==========================================================================*/

  /* 产品型号字典（下拉来源，走数据字典 A 类） */
  var PRODUCT_MODELS = [
    { key: 'XW-90', label: 'XW-90 天窗 900×1800', product: '天窗', used: 3 },
    { key: 'XW-120', label: 'XW-120 天窗 1200×2400', product: '天窗', used: 5 },
    { key: 'XW-150', label: 'XW-150 天窗 1500×2800', product: '天窗', used: 1 },
    { key: 'TM-180', label: 'TM-180 天幕 1800×2600', product: '天幕', used: 1 },
    { key: 'TM-240', label: 'TM-240 天幕 2400×3000', product: '天幕', used: 2 },
    { key: 'TM-300', label: 'TM-300 天幕 3000×3500', product: '天幕', used: 1 },
    { key: 'YG-30', label: 'YG-30 阳光房 3000×4000', product: '阳光房', used: 2 },
    { key: 'ZY-15', label: 'ZY-15 遮阳帘 1500×2000', product: '遮阳帘', used: 1 }
  ];

  /* 手动 / 电动（商机必填） */
  var DRIVE_TYPE = [['manual', '手动'], ['electric', '电动']];
  var DRIVE_LABEL = { manual: '手动', electric: '电动' };

  /* 商机补充字段 + 变更履历 */
  var DEAL_LOGS = {
    1: [{ at: d(46, '09:30'), type: 'create', text: '创建商机：天窗 XW-120 1200×2400，报价 ¥12,000' },
        { at: d(30, '10:20'), type: 'change', text: '尺寸由 1200×2200 改为 1200×2400（现场复尺）' },
        { at: d(16, '15:20'), type: 'stage', text: '阶段推进：成交洽谈 → 赢单' }],
    2: [{ at: d(60, '11:00'), type: 'create', text: '创建商机：天幕 TM-240 2400×3000，报价 ¥45,000' },
        { at: d(20, '16:40'), type: 'change', text: '金额由 ¥42,000 改为 ¥45,000（增加电动开合）' },
        { at: d(11, '10:10'), type: 'stage', text: '阶段推进：成交洽谈 → 赢单' }],
    4: [{ at: d(80, '10:40'), type: 'create', text: '创建商机：阳光房 YG-30 3000×4000，报价 ¥68,000' },
        { at: d(49, '14:00'), type: 'stage', text: '阶段推进：成交洽谈 → 赢单' }],
    12: [{ at: d(8, '14:10'), type: 'create', text: '创建商机：阳光房 YG-30 3000×4200，报价 ¥68,000' },
         { at: d(3, '09:20'), type: 'change', text: '尺寸由 3000×4000 改为 3000×4200（客户要求加宽）' }]
  };
  DEALS.forEach(function (x) {
    /* 手动/电动：天窗多为电动，遮阳帘手动 */
    x.drive_type = (x.product_type === '遮阳帘') ? 'manual' : (x.id % 3 === 0 ? 'manual' : 'electric');
    x.model_code = x.model;
    x.size = x.spec ? x.spec.replace(/\s*定制$/, '') : '';
    x.order_id = null;
    x.locked = false;
  });
  /* 已赢单且有订单的商机 → 锁定 */
  ORDERS.forEach(function (o) {
    var dl = DEALS.filter(function (x) { return x.id === o.deal_id; })[0];
    if (dl) { dl.order_id = o.id; dl.locked = true; }
  });

  /* 订单补充：物流方式 / 收件人 / 承运公司 / 运单号 */
  var RECEIVERS = {
    1: { receiver_name: '陈国强', receiver_phone: '137 0636 5566', receiver_address: '潍坊市奎文区建材市场 3 号库', carrier_id: 2, logistics_mode: 'carrier', tracking_number: null },
    2: { receiver_name: '周建军', receiver_phone: '133 0535 7788', receiver_address: '烟台市芝罘区幸福路 88 号工地', carrier_id: 1, logistics_mode: 'carrier', tracking_number: 'SF7788123400' },
    3: { receiver_name: '王志远', receiver_phone: '138 5312 7745', receiver_address: '济南市历下区万科城 12-3-1801', carrier_id: 3, logistics_mode: 'carrier', tracking_number: 'JN2026100101' },
    4: { receiver_name: '刘俊峰', receiver_phone: '139 0532 8811', receiver_address: '青岛市崂山区海尔路 12 号工地', carrier_id: 1, logistics_mode: 'carrier', tracking_number: null },
    5: { receiver_name: '孙丽华', receiver_phone: '150 5337 2210', receiver_address: '淄博市张店区齐悦花园 8-2-601', carrier_id: null, logistics_mode: 'self', tracking_number: null },
    6: { receiver_name: '李秀娟', receiver_phone: '186 5388 9012', receiver_address: '泰安市泰山区泰山公馆 6-1-901', carrier_id: 2, logistics_mode: 'carrier', tracking_number: null },
    7: { receiver_name: '赵明辉', receiver_phone: '135 5311 4408', receiver_address: '济南市历下区绿城百合 3-2-1202', carrier_id: 3, logistics_mode: 'carrier', tracking_number: 'SF1234567890' }
  };
  ORDERS.forEach(function (o) {
    var r = RECEIVERS[o.id] || {};
    Object.keys(r).forEach(function (k) { o[k] = r[k]; });
    o.logistics_mode_label = o.logistics_mode === 'self' ? '自送' : '物流公司';
    o.carrier_name = o.carrier_id ? ((CARRIERS.filter(function (c) { return c.id === o.carrier_id; })[0] || {}).name || '') : '';
  });

  /* 线索跟进履历（和客户跟进分开存，转客户后一次性带过去） */
  var LEAD_FOLLOWS = [
    { lead_id: 1, method: 'wechat', content: '抖音私信，发了 3 个顶楼案例，问能不能做 90 平露台', next_date: dayOff(-1), created_at: d(0, '08:40'), files: [] },
    { lead_id: 1, method: 'phone', content: '电话沟通 10 分钟，预算 2 万左右，约周末到店', next_date: dayOff(-3), created_at: d(0, '10:20'), files: ['户型图.jpg'] },
    { lead_id: 2, method: 'phone', content: '同行介绍的装饰公司，说手上有 5 套要装', next_date: dayOff(2), created_at: d(3, '10:20'), files: [] },
    { lead_id: 2, method: 'visit', content: '去了他们工地，甲方要求电动开合', next_date: dayOff(-1), created_at: d(1, '15:00'), files: ['现场1.jpg', '现场2.jpg'] },
    { lead_id: 3, method: 'wechat', content: '微信咨询天幕，预算 3 万内，发了 TM-180 报价', next_date: todayISO(), created_at: d(2, '19:50'), files: [] },
    { lead_id: 5, method: 'wechat', content: '已成交，天窗 900×2000，转入客户档案', next_date: null, created_at: d(40, '09:10'), files: [] }
  ];

  /* 线索补充：地区、上次跟进时间、默认意向「中」 */
  LEADS.forEach(function (l) {
    l.region = l.location;
    l.intent_level = l.intent_level || 'medium';
    l.drive_type = null;
    var fs = LEAD_FOLLOWS.filter(function (f) { return f.lead_id === l.id; });
    l.last_follow_at = fs.length ? fs.map(function (f) { return f.created_at; }).sort().slice(-1)[0] : null;
  });

  /* 客户画像（天窗/天幕业务实际会问的几个点） */
  var PROFILES = {
    1: { house_type: '高层公寓', floor: '18/32 顶楼', install_at: '主卧', stage: '安装中', budget: '1–1.5 万', decider: '本人+太太', care: ['防水', '颜值'] },
    2: { house_type: '工地/工程', floor: '—', install_at: '客厅+露台', stage: '水电', budget: '5 万+', decider: '项目负责人', care: ['工期', '开票'] },
    3: { house_type: '高层公寓', floor: '6/18', install_at: '阳台', stage: '泥木', budget: '1 万内', decider: '本人+先生', care: ['采光', '价格'] },
    4: { house_type: '自建商铺', floor: '1层', install_at: '阳光房', stage: '未开工', budget: '6–7 万', decider: '本人', care: ['价格'] },
    5: { house_type: '别墅', floor: '3层', install_at: '主卧+书房', stage: '安装中', budget: '1.5 万', decider: '本人', care: ['隔音', '防水'] },
    6: { house_type: '高层公寓', floor: '12/26', install_at: '客厅', stage: '泥木', budget: '1 万', decider: '本人', care: ['颜值'] },
    7: { house_type: '工地/工程', floor: '—', install_at: '整栋阳光房', stage: '安装中', budget: '5 万+', decider: '项目经理', care: ['工期', '售后'] },
    8: { house_type: '高层公寓', floor: '9/18', install_at: '阳台', stage: '未开工', budget: '3000 左右', decider: '本人', care: ['价格'] },
    9: { house_type: '高层公寓', floor: '7/30 顶楼', install_at: '客厅', stage: '未开工', budget: '2 万', decider: '本人', care: ['采光', '颜值'] },
    10: { house_type: '工地/工程', floor: '—', install_at: '批量 6 套', stage: '水电', budget: '1.5 万/套', decider: '老板', care: ['价格', '交期'] }
  };
  CUSTOMERS.forEach(function (c) { c.profile = PROFILES[c.id] || {}; c.source_lead_id = c.id <= 8 ? c.id : null; });

  /* 物流公司被订单关联次数 */
  function carrierUsed(id) {
    return ORDERS.filter(function (o) { return o.carrier_id === id; }).length;
  }
  CARRIERS.forEach(function (c) { c.used = carrierUsed(c.id); });

  /* 产品型号字典补进 DICTS（Q8：产品类型/型号下拉可维护） */
  DICTS.unshift({
    code: 'product_model', name: '产品型号', level: 'A', desc: '商机/订单的型号下拉（Q8 ✅ 下拉可新增）',
    items: PRODUCT_MODELS.map(function (m, i) { return { key: m.key, label: m.label, sort: i + 1, enabled: true, used: m.used }; })
  });

  /* ============================================================================
   * mock api：把 URL 路由到上面的数据，全部同步返回 Promise
   * ==========================================================================*/
  function num(v) { return Number(v) || 0; }

  function customerById(id) { return CUSTOMERS.filter(function (c) { return c.id === Number(id); })[0]; }
  function dealById(id) { return DEALS.filter(function (x) { return x.id === Number(id); })[0]; }
  function orderById(id) { return ORDERS.filter(function (x) { return x.id === Number(id); })[0]; }
  function aftersaleById(id) { return AFTERSALES.filter(function (x) { return x.id === Number(id); })[0]; }

  function customerRow(c) {
    var ds = DEALS.filter(function (d) { return d.customer_id === c.id; });
    var won = ds.filter(function (d) { return d.stage === 'won'; });
    var row = {};
    Object.keys(c).forEach(function (k) { row[k] = c[k]; });
    row.deals_total = ds.length;
    row.deals_won_total = won.length;
    row.deal_amount_total = won.reduce(function (s, d) { return s + num(d.amount); }, 0);
    row.is_repeat = ds.length >= 2;
    row.source_label = SOURCE_LABELS[c.source] || c.source;
    row.intent_level_label = INTENT_LABELS[c.intent_level] || '';
    return row;
  }

  function dealRow(d) {
    var row = {};
    Object.keys(d).forEach(function (k) { row[k] = d[k]; });
    row.stage_label = STAGE_LABEL[d.stage] || d.stage;
    row.customer_name = (customerById(d.customer_id) || {}).name || '未关联客户';
    return row;
  }

  function orderRow(o) {
    var row = {};
    Object.keys(o).forEach(function (k) { row[k] = o[k]; });
    row.status_label = ORDER_STATUS_LABEL[o.status] || o.status;
    row.customer_name = (customerById(o.customer_id) || {}).name || '未关联客户';
    return row;
  }

  function aftersaleRow(a) {
    var row = {};
    Object.keys(a).forEach(function (k) { row[k] = a[k]; });
    row.status_label = AFTERSALE_STATUS_LABEL[a.status] || a.status;
    row.type_label = AFTERSALE_TYPE_LABEL[a.type] || a.type;
    row.order_no = (orderById(a.order_id) || {}).order_no || '';
    row.customer_name = (customerById(a.customer_id) || {}).name || '';
    return row;
  }

  /** 今日待跟进：按客户取最近一条跟进（PAGES-V2 §1.2 定稿口径） */
  function todayFollowups() {
    var latest = {};
    FOLLOWUPS.forEach(function (f) {
      if (!f.customer_id || !f.next_date) { return; }
      var cur = latest[f.customer_id];
      if (!cur || f.created_at > cur.created_at) { latest[f.customer_id] = f; }
    });
    var today = todayISO();
    var out = [];
    Object.keys(latest).forEach(function (cid) {
      var f = latest[cid];
      if (f.next_date > today) { return; }
      var deal = f.deal_id ? dealById(f.deal_id) : null;
      if (deal && (deal.stage === 'won' || deal.stage === 'lost')) { return; }
      var days = Math.round((new Date(today) - new Date(f.next_date)) / 86400000);
      out.push({
        id: f.id,
        customer_id: f.customer_id,
        customer_name: (customerById(f.customer_id) || {}).name || '',
        intent_level: (customerById(f.customer_id) || {}).intent_level || '',
        last_follow_at: f.created_at,
        deal_id: f.deal_id,
        deal_stage: deal ? deal.stage : null,
        deal_stage_label: deal ? (STAGE_LABEL[deal.stage] || deal.stage) : null,
        content: f.content,
        next_date: f.next_date,
        days_overdue: days > 0 ? days : 0,
        is_overdue: days > 0
      });
    });
    out.sort(function (a, b) { return a.next_date < b.next_date ? -1 : 1; });
    return out;
  }

  function buildDashboard() {
    var today = todayISO();
    var todos = todayFollowups();
    var monthKey = today.slice(0, 7);

    var wonThisMonth = DEALS.filter(function (d) {
      return d.stage === 'won' && d.closed_at && d.closed_at.slice(0, 7) === monthKey;
    });
    var monthWon = {
      count: wonThisMonth.length,
      amount: wonThisMonth.reduce(function (s, d) { return s + num(d.amount); }, 0)
    };

    var dealsByStage = {};
    STAGES.forEach(function (p) { dealsByStage[p[0]] = 0; });
    DEALS.forEach(function (d) { dealsByStage[d.stage] = (dealsByStage[d.stage] || 0) + 1; });

    var ordersByStatus = {};
    ORDER_STATUS.forEach(function (p) { ordersByStatus[p[0]] = { count: 0, amount: 0 }; });
    ORDERS.forEach(function (o) {
      ordersByStatus[o.status].count += 1;
      ordersByStatus[o.status].amount += num(o.amount);
    });

    var inProgress = DEALS.filter(function (d) { return d.stage !== 'won' && d.stage !== 'lost'; });

    var recentOrders = ORDERS.slice().sort(function (a, b) { return a.updated_at < b.updated_at ? 1 : -1; })
      .slice(0, 5).map(function (o) {
        var r = orderRow(o);
        return { id: r.id, order_no: r.order_no, customer_name: r.customer_name, amount: r.amount, status: r.status, status_label: r.status_label, created_at: r.created_at };
      });

    /* 最近动态：跟进 + 订单状态变更，时间倒序 */
    var acts = [];
    FOLLOWUPS.forEach(function (f) {
      acts.push({ at: f.created_at, type: 'followup', text: (customerById(f.customer_id) || {}).name + ' · 记了一条跟进：' + f.content.slice(0, 22), customer_id: f.customer_id });
    });
    ORDERS.forEach(function (o) {
      acts.push({ at: o.updated_at, type: 'order', text: (customerById(o.customer_id) || {}).name + ' 订单 ' + o.order_no + ' → ' + (ORDER_STATUS_LABEL[o.status] || o.status), amount: o.amount, order_id: o.id });
    });
    acts.sort(function (a, b) { return a.at < b.at ? 1 : -1; });

    var monthNewCustomers = CUSTOMERS.filter(function (c) { return String(c.created_at).slice(0, 7) === monthKey; }).length;

    return {
      today_followups: todos,
      month_won: monthWon,
      stats: {
        customers_total: CUSTOMERS.length,
        customers_this_month: monthNewCustomers,
        month_new_customers: monthNewCustomers,
        deals_by_stage: dealsByStage,
        month_won: monthWon,
        repeat_customers: DEALS.reduce(function (m, d) { m[d.customer_id] = (m[d.customer_id] || 0) + 1; return m; }, {}) &&
          Object.keys(DEALS.reduce(function (m, d) { m[d.customer_id] = (m[d.customer_id] || 0) + 1; return m; }, {}))
            .filter(function (cid) { return DEALS.filter(function (d) { return d.customer_id === Number(cid); }).length >= 2; }).length,
        in_progress_deals: { count: inProgress.length, amount: inProgress.reduce(function (s, d) { return s + num(d.amount); }, 0) },
        orders_by_status: ordersByStatus,
        recent_orders: recentOrders,
        recent_activities: acts.slice(0, 10),
        aftersale_sla_alerts: AFTERSALES.filter(function (a) {
          if (a.status !== 'pending') { return false; }
          var days = Math.round((new Date(today) - new Date(String(a.created_at).slice(0, 10))) / 86400000);
          return days >= 3;
        }).map(function (a) {
          return { id: a.id, no: a.no, days_pending: Math.round((new Date(today) - new Date(String(a.created_at).slice(0, 10))) / 86400000), order_no: (orderById(a.order_id) || {}).order_no, customer_name: (customerById(a.customer_id) || {}).name };
        })
      }
    };
  }

  function qs(path) {
    var i = path.indexOf('?');
    return new URLSearchParams(i >= 0 ? path.slice(i + 1) : '');
  }
  function p0(path) { return path.split('?')[0]; }

  function mockGet(path) {
    var p = p0(path), q = qs(path);
    var m;

    if (p === '/me') { return { username: state.me, demo: true }; }
    if (p === '/dashboard') { return buildDashboard(); }
    if (p === '/tags') { return TAG_NAMES; }

    if (p === '/customers') {
      var kw = (q.get('q') || '').trim();
      var tag = q.get('tag') || '';
      var list = CUSTOMERS.map(customerRow).filter(function (c) {
        if (tag && !(c.tags || []).some(function (t) { return String(t.id) === tag; })) { return false; }
        if (!kw) { return true; }
        return [c.name, c.phone, c.location, c.company_name].join(' ').indexOf(kw) >= 0;
      });
      return { items: list, total: list.length, page: Number(q.get('page') || 1), size: PageSize(), demo: true };
    }
    if ((m = p.match(/^\/customers\/(\d+)$/))) {
      var c = customerById(m[1]);
      if (!c) { throw apiError('客户不存在', 404); }
      var detail = customerRow(c);
      detail.deals = DEALS.filter(function (d) { return d.customer_id === c.id; }).map(dealRow);
      detail.follow_ups = FOLLOWUPS.filter(function (f) { return f.customer_id === c.id; });
      detail.orders = ORDERS.filter(function (o) { return o.customer_id === c.id; }).map(orderRow);
      detail.aftersales = AFTERSALES.filter(function (a) { return a.customer_id === c.id; }).map(aftersaleRow);
      return detail;
    }

    if (p === '/deals') {
      var stage = q.get('stage') || '', cid = q.get('customer_id') || '';
      return DEALS.filter(function (d) {
        if (stage && d.stage !== stage) { return false; }
        if (cid && String(d.customer_id) !== String(cid)) { return false; }
        return true;
      }).map(dealRow);
    }
    if ((m = p.match(/^\/deals\/(\d+)$/))) {
      var dd = dealById(m[1]);
      if (!dd) { throw apiError('商机不存在', 404); }
      var dr = dealRow(dd);
      dr.order = ORDERS.filter(function (o) { return o.deal_id === dd.id; }).map(orderRow)[0] || null;
      dr.follow_ups = FOLLOWUPS.filter(function (f) { return f.deal_id === dd.id; });
      return dr;
    }

    if (p === '/orders') {
      var st = q.get('status') || '', ocid = q.get('customer_id') || '';
      return ORDERS.filter(function (o) {
        if (st && o.status !== st) { return false; }
        if (ocid && String(o.customer_id) !== String(ocid)) { return false; }
        return true;
      }).map(orderRow);
    }
    if ((m = p.match(/^\/orders\/(\d+)$/))) {
      var oo = orderById(m[1]);
      if (!oo) { throw apiError('订单不存在', 404); }
      var orow = orderRow(oo);
      orow.status_log = [
        { to_status: oo.status, to_status_label: ORDER_STATUS_LABEL[oo.status], note: '演示数据：状态变更记录', created_at: oo.updated_at }
      ];
      return orow;
    }

    if (p === '/aftersales') {
      var as = q.get('status') || '', oid = q.get('order_id') || '';
      var alist = AFTERSALES.filter(function (a) {
        if (as && a.status !== as) { return false; }
        if (oid && String(a.order_id) !== String(oid)) { return false; }
        return true;
      }).map(aftersaleRow);
      return { items: alist, total: alist.length, page: 1, size: PageSize(), demo: true };
    }
    if ((m = p.match(/^\/aftersales\/(\d+)$/))) {
      var af = aftersaleById(m[1]);
      if (!af) { throw apiError('售后单不存在', 404); }
      return aftersaleRow(af);
    }

    if (p === '/carriers') {
      var only = q.get('active_only') === 'true';
      return CARRIERS.filter(function (c) { return only ? c.is_active : true; });
    }

    if (p === '/follow-ups') {
      var fcid = q.get('customer_id') || '', fdid = q.get('deal_id') || '';
      return FOLLOWUPS.filter(function (f) {
        if (fcid && String(f.customer_id) !== String(fcid)) { return false; }
        if (fdid && String(f.deal_id) !== String(fdid)) { return false; }
        return true;
      }).map(function (f) {
        var r = {};
        Object.keys(f).forEach(function (k) { r[k] = f[k]; });
        r.customer_name = (customerById(f.customer_id) || {}).name || '';
        r.deal_stage = f.deal_id ? (dealById(f.deal_id) || {}).stage : null;
        r.photo_count = 0;
        r.photos = [];
        return r;
      }).sort(function (a, b) { return a.created_at < b.created_at ? 1 : -1; });
    }

    if (p === '/leads') {
      var lstatus = q.get('status') || '', lkw = (q.get('search') || q.get('q') || '').trim();
      var llist = LEADS.filter(function (l) {
        if (lstatus && l.status !== lstatus) { return false; }
        if (!lkw) { return true; }
        return [l.name, l.phone, l.wechat, l.company_name].join(' ').indexOf(lkw) >= 0;
      });
      /* 线索页也要看板式字段：意向中文、状态中文、逾期天数 */
      llist = llist.map(function (l) {
        var r = {};
        Object.keys(l).forEach(function (k) { r[k] = l[k]; });
        r.intent_level_label = INTENT_LABELS[l.intent_level] || '';
        r.source_label = l.source === 'other' ? (l.source_other || '其他') : (SOURCE_LABELS[l.source] || l.source);
        return r;
      });
      return { items: llist, total: llist.length, page: Number(q.get('page') || 1), size: PageSize(), demo: true };
    }
    if ((m = p.match(/^\/leads\/(\d+)$/))) {
      var l = LEADS.filter(function (x) { return x.id === Number(m[1]); })[0];
      if (!l) { throw apiError('线索不存在', 404); }
      return l;
    }

    if (p === '/dicts') { return DICTS; }
    if ((m = p.match(/^\/dicts\/([a-z_]+)$/))) {
      var dct = DICTS.filter(function (x) { return x.code === m[1]; })[0];
      if (!dct) { throw apiError('字典不存在', 404); }
      return dct;
    }

    throw apiError('演示环境未提供该接口：' + p, 501);
  }

  function PageSize() { return PAGE_SIZE; }

  function apiError(message, status) {
    var e = new Error(message);
    e.status = status || 400;
    return e;
  }

  /** 写操作在 demo 里一律「假成功」，不落盘、不发网络 */
  function mockWrite(path, opts) {
    var p = p0(path), method = (opts && opts.method) || 'POST';
    return { ok: true, demo: true, message: '演示环境：' + method + ' ' + p + ' 已模拟成功（不会真的保存）' };
  }

  function api(path, opts) {
    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        try {
          if (opts && opts.method && opts.method !== 'GET') { resolve(mockWrite(path, opts)); return; }
          resolve(mockGet(path));
        } catch (e) { reject(e); }
      }, 120);
    });
  }

  /* ---------------- 客户索引（商机/跟进页显示客户名） ---------------- */
  function invalidateCustomerIndex() { state.customers.index = null; state.customers.builtAt = 0; }
  function ensureCustomerIndex() {
    var map = {};
    CUSTOMERS.forEach(function (c) { map[c.id] = c.name; });
    state.customers.index = map;
    state.customers.builtAt = Date.now();
    return Promise.resolve(map);
  }
  function customerOptions(index, selectedId) {
    var ids = Object.keys(index || {}).map(Number).sort(function (a, b) {
      return String((index || {})[a]).localeCompare(String((index || {})[b]), 'zh-Hans-CN');
    });
    return ids.map(function (id) {
      return '<option value="' + id + '"' + (String(id) === String(selectedId) ? ' selected' : '') + '>' +
        esc(index[id]) + '</option>';
    }).join('');
  }

  /* ---------------- 路由 ---------------- */
  function parseRoute() {
    var raw = (location.hash || '#/dashboard').replace(/^#/, '');
    var parts = raw.split('?');
    return {
      parts: parts[0].split('/').filter(Boolean),
      query: new URLSearchParams(parts[1] || '')
    };
  }
  function navigate(hash) {
    if (location.hash === hash) { render(); } else { location.hash = hash; }
  }
  function setActiveNav(view) {
    $$('#nav a').forEach(function (a) {
      a.classList.toggle('active', a.getAttribute('data-view') === view);
    });
  }

  function render() {
    var route = parseRoute();
    var view = route.parts[0] || 'dashboard';
    var seq = ++renderSeq;
    var root = document.getElementById('app');
    setActiveNav(view);
    root.innerHTML = '<p class="loading">加载中…</p>';

    var job;
    if (view === 'dashboard') { job = viewDashboard(root); }
    else if (view === 'leads') {
      if (route.parts[2] === 'follow') { job = viewLeadFollow(root, route.parts[1]); }
      else { job = route.parts[1] ? viewLeadDetail(root, route.parts[1]) : viewLeads(root, route); }
    }
    else if (view === 'customers') {
      if (route.parts[2] === 'follow') { job = viewCustomerFollow(root, route.parts[1]); }
      else { job = route.parts[1] ? viewCustomerDetail(root, route.parts[1]) : viewCustomers(root, route); }
    }
    else if (view === 'deals') {
      if (route.parts[1] === 'new') { job = viewDealNew(root, route); }
      else { job = route.parts[1] ? viewDealDetail(root, route.parts[1]) : viewDeals(root, route); }
    }
    else if (view === 'orders') { job = route.parts[1] ? viewOrderDetail(root, route.parts[1]) : viewOrders(root, route); }
    else if (view === 'aftersales') { job = route.parts[1] ? viewAftersaleDetail(root, route.parts[1]) : viewAftersales(root, route); }
    else if (view === 'logistics') { job = viewLogistics(root, route); }
    else if (view === 'followups') { job = viewFollowups(root, route); }
    else if (view === 'stats') { job = viewStats(root); }
    else if (view === 'import') { job = viewImport(root); }
    else if (view === 'dict') { job = viewDict(root, route); }
    else if (view === 'more') { job = viewMore(root); }
    else {
      job = Promise.resolve();
      root.innerHTML = '<div class="card">页面不存在，<a href="#/dashboard">回工作台</a></div>';
    }

    return Promise.resolve(job).catch(function (err) {
      if (seq !== renderSeq) { return; }
      root.innerHTML = '<div class="card"><p class="err">加载失败：' + esc(err && err.message ? err.message : err) + '</p></div>';
    });
  }

  /* ---------------- 「更多」页 ---------------- */
  function viewMore(root) {
    var items = [
      ['#/logistics', '物流公司', '发货用哪家、联系谁'],
      ['#/followups', '跟进记录', '所有客户的跟进流水 + 记一条'],
      ['#/stats', '统计', '客户数、成交、阶段分布'],
      ['#/dict', '数据字典', '来源 / 意向 / 产品类型等选项，自己维护'],
      ['#/import', '导入', '从 Excel/CSV 导入存量客户']
    ];
    root.innerHTML = '<div class="card"><div class="card-head"><h2>更多</h2></div>' +
      items.map(function (it) {
        return '<a class="item" href="' + it[0] + '" style="text-decoration:none;color:inherit">' +
          '<div class="item-main"><div class="item-title">' + it[1] + '</div>' +
          '<div class="item-sub small">' + it[2] + '</div></div>' +
          '<div class="item-side muted">›</div></a>';
      }).join('') + '</div>';
  }

  /* ---------------- 顶部：金额眼睛 ---------------- */
  function toggleMoney() {
    state.showMoney = !state.showMoney;
    var btn = document.getElementById('btnMoney');
    if (btn) {
      btn.textContent = state.showMoney ? '🙈' : '👁';
      btn.title = state.showMoney ? '点一下遮住金额' : '点一下查看金额';
    }
    render();
    toast(state.showMoney ? '金额已显示' : '金额已遮罩');
  }

  /* ---------------- 启动 ---------------- */
  function boot() {
    document.getElementById('whoami').textContent = state.me;
    document.getElementById('btnMoney').addEventListener('click', toggleMoney);
    window.addEventListener('hashchange', function () { render(); });
    render();
  }

  /* ---------------- 暴露到 window（views/*.js 用裸名调用） ---------------- */
  Object.assign(window, {
    PAGE_SIZE: PAGE_SIZE, MAX_PHOTOS: MAX_PHOTOS, MAX_PHOTO_MB: MAX_PHOTO_MB, MAX_TAGS: MAX_TAGS,
    STAGES: STAGES, STAGE_LABEL: STAGE_LABEL,
    ORDER_STATUS: ORDER_STATUS, ORDER_STATUS_LABEL: ORDER_STATUS_LABEL, ORDER_FLOW: ORDER_FLOW,
    AFTERSALE_TYPE_LABEL: AFTERSALE_TYPE_LABEL, AFTERSALE_STATUS_LABEL: AFTERSALE_STATUS_LABEL,
    SOURCE_LABELS: SOURCE_LABELS, INTENT_LABELS: INTENT_LABELS,
    state: state,
    esc: esc, pad2: pad2, money: money, moneyRaw: moneyRaw, fmtDateTime: fmtDateTime,
    todayISO: todayISO, numOrNull: numOrNull, toast: toast,
    api: api, $: $, $$: $$,
    parseRoute: parseRoute, navigate: navigate, render: render,
    ensureCustomerIndex: ensureCustomerIndex, invalidateCustomerIndex: invalidateCustomerIndex,
    customerOptions: customerOptions,
    DRIVE_TYPE: DRIVE_TYPE, DRIVE_LABEL: DRIVE_LABEL,
    DEMO: { customers: CUSTOMERS, deals: DEALS, orders: ORDERS, aftersales: AFTERSALES, followups: FOLLOWUPS, leads: LEADS, dicts: DICTS, tags: TAG_NAMES, models: PRODUCT_MODELS, leadFollows: LEAD_FOLLOWS, dealLogs: DEAL_LOGS, carriers: CARRIERS, receivers: RECEIVERS }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();