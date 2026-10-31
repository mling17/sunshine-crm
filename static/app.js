/* 天窗天幕 CRM · 前端（原生 JS，零依赖 / 零构建）
 *
 * 路由：hash 路由（#/customers/3）。原因：nginx 的 /crm/ 是静态 alias，
 *      没有 history fallback，用路径路由一刷新就 404；hash 永远落在 /crm/index.html。
 *
 * 接口：一律走 **绝对路径** /crm/api/crm（见实施计划 §2.4）：
 *      nginx 把 /crm/api/<x> 反代到后端 8010 的 /api/<x>，
 *      所以对外是 /crm/api/crm/... ，后端实际路由是 /api/crm/... 。
 *      写成相对路径 api/crm/... 在深层 hash 里没问题，但任何人改成路径路由就会解析错，
 *      统一绝对路径最稳。
 *
 * 安全：登录密码只存在于登录框的 input 里，登录成功后立即清空；
 *      全程不写任何浏览器本地存储（local / session storage 都没用），
 *      满足“电脑端不允许保存密码”。
 */
(function () {
  'use strict';

  /* 绝对路径：深层路由下相对路径会解析错（计划 §2.4 明确要求照抄） */
  const API_BASE = '/crm/api/crm';
  var PAGE_SIZE = 20;
  var MAX_PHOTOS = 3;
  var MAX_PHOTO_MB = 20;
  var MAX_TAGS = 20;

  /* 定稿阶段：报价 → 待客户确认 → 成交 / 流失（PLANNER-V3 §1.1）
     展示名以数据字典 deal_stage 为准（GET /dicts），这里只是兜底常量 */
  var STAGES = [
    ['quote', '报价'],
    ['confirm', '待客户确认'],
    ['won', '成交'],
    ['lost', '流失']
  ];
  var STAGE_LABEL = {};
  STAGES.forEach(function (pair) { STAGE_LABEL[pair[0]] = pair[1]; });

  /* 订单状态：与后端 enums.py::ORDER_STATUS_LABELS 一致（顺序=状态机推进顺序） */
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
  ORDER_STATUS.forEach(function (pair) { ORDER_STATUS_LABEL[pair[0]] = pair[1]; });

  /* 订单状态机（与后端 enums.py::ORDER_FLOW 一致）；后端不下发 next_status，前端自己算 */
  var ORDER_FLOW = {
    'pending_payment': 'deposit_paid',
    'deposit_paid': 'producing',
    'producing': 'balance_paid',
    'balance_paid': 'ready_to_ship',
    'ready_to_ship': 'shipped',
    'shipped': 'completed',
    'completed': null
  };

  /* 售后类型/状态：与后端 enums.py 一致（后端未下发 *_label，前端映射） */
  var AFTERSALE_TYPE_LABEL = {
    'return': '退货', 'exchange': '换货', 'repair': '维修', 'complaint': '投诉', 'other': '其他'
  };
  var AFTERSALE_STATUS_LABEL = {
    'pending': '待处理', 'processing': '处理中', 'done': '已完成', 'rejected': '已拒绝'
  };

  /* 来源标签映射（兜底；登录后由数据字典 customer_source 覆盖） */
  var SOURCE_LABELS = {
    'wechat': '微信',
    'phone': '电话',
    'referral': '转介绍',
    'existing': '老客户',
    'stock': '存量',
    'other': '其他',
    'video_account': '视频号',
    'xianyu': '咸鱼'
  };

  /* 意向等级标签映射（兜底；登录后由数据字典 intent_level 覆盖） */
  var INTENT_LABELS = {
    'high': '高',
    'medium': '中',
    'low': '低',
    'none': '无意向'
  };

  /* ================= 数据字典（唯一真源：GET /dicts）=================
   * 规矩：前端任何「业务标签/下拉」都必须走这里，不许再硬编码。
   * 反例（2026-10-31 用户报的 bug）：来源下拉写死 5 个 option，用户在
   * 「数据字典」里改了来源，新建线索时还是旧值 —— 因为页面根本没读字典。
   * 字典在登录后加载一次；拉不到就回退上面的兜底常量，不阻塞页面。
   */
  var DICTS = {};
  var dictsReady = false;

  function dictItems(code) {
    return (DICTS[code] || []).filter(function (it) { return it.enabled !== false; });
  }

  function dictLabel(code, key, fallback) {
    if (key === null || key === undefined || key === '') { return fallback || '—'; }
    var hit = (DICTS[code] || []).filter(function (it) { return it.key === key; })[0];
    if (hit) { return hit.label; }
    return fallback || key;
  }

  /* 生成 <option> 串。empty 传字符串则加一个「不选」项；
     当前值在字典里已停用/已删时补一条，避免编辑时把老数据静默清空 */
  function dictOptions(code, current, empty) {
    var items = dictItems(code);
    var html = '';
    if (empty !== undefined && empty !== null) {
      html += '<option value="">' + esc(empty) + '</option>';
    }
    html += items.map(function (it) {
      return '<option value="' + esc(it.key) + '"' +
        (String(current || '') === String(it.key) ? ' selected' : '') + '>' + esc(it.label) + '</option>';
    }).join('');
    var known = items.some(function (it) { return String(it.key) === String(current || ''); });
    if (current && !known && items.length) {
      html += '<option value="' + esc(current) + '" selected>' + esc(current) + '（已停用）</option>';
    }
    return html;
  }

  /* 字典到手后改写 ID→标签 常量（原地改内容，views 里的裸名引用继续有效） */
  function applyDictLabels() {
    if (!dictsReady) { return; }
    function refill(target, code) {
      var items = DICTS[code];
      if (!items || !items.length) { return; }
      Object.keys(target).forEach(function (k) { delete target[k]; });
      items.forEach(function (it) { target[it.key] = it.label; });
    }
    function refillPairs(target, code) {
      var items = DICTS[code];
      if (!items || !items.length) { return; }
      target.length = 0;
      items.slice().sort(function (a, b) { return (a.sort || 0) - (b.sort || 0); })
        .forEach(function (it) { target.push([it.key, it.label]); });
    }
    refill(SOURCE_LABELS, 'customer_source');
    refill(INTENT_LABELS, 'intent_level');
    refill(STAGE_LABEL, 'deal_stage');
    refill(ORDER_STATUS_LABEL, 'order_status');
    refill(AFTERSALE_TYPE_LABEL, 'aftersale_type');
    refill(AFTERSALE_STATUS_LABEL, 'aftersale_status');
    refillPairs(STAGES, 'deal_stage');
    refillPairs(ORDER_STATUS, 'order_status');
  }

  function ensureDicts(force) {
    if (dictsReady && !force) { return Promise.resolve(DICTS); }
    return api('/dicts').then(function (list) {
      var next = {};
      (list || []).forEach(function (d) { next[d.code] = d.items || []; });
      DICTS = next;
      dictsReady = true;
      applyDictLabels();
      return DICTS;
    }).catch(function () {
      return DICTS;  // 降级：用兜底常量；下次进页面再试
    });
  }

  var state = {
    me: null,
    displayName: null,
    customers: { index: null, builtAt: 0 },
    filters: { q: '', tag: '', page: 1 },
    import: { preview: null, result: null }
  };
  var renderSeq = 0;

  /* ================= 基础工具 ================= */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function esc(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"]/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function pad2(n) { return n < 10 ? '0' + n : String(n); }

  function money(value) {
    var num = Number(value || 0);
    var digits = Math.abs(num % 1) > 0.004 ? 2 : 0;
    return '¥' + num.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: 2 });
  }

  function fmtDateTime(value) {
    if (!value) { return ''; }
    var raw = String(value);
    // 后端 created_at 是 UTC（带 Z），转成浏览器本地时间；closed_at 已是本地无时区格式，原样显示
    if (raw.indexOf('T') > 0 && /(Z|[+-]\d{2}:\d{2})$/.test(raw)) {
      var d = new Date(raw);
      if (!isNaN(d.getTime())) {
        return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
          ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
      }
    }
    return raw.replace('T', ' ').slice(0, 16);
  }

  function todayISO() {
    var d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }

  function numOrNull(raw) {
    var text = String(raw === undefined || raw === null ? '' : raw).trim();
    if (!text) { return null; }
    var n = Number(text);
    return isNaN(n) ? null : n;
  }

  var toastTimer = null;
  function toast(message, isError) {
    var el = document.getElementById('toast');
    if (!el) { return; }
    el.textContent = message;
    el.className = 'toast' + (isError ? ' error' : '');
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, isError ? 4200 : 2200);
  }

  function ApiError(message, status, code, data) {
    this.name = 'ApiError';
    this.message = message;
    this.status = status || 0;
    this.code = code || null;   // 后端 {"detail","code"} 里的业务码，前端按码分支
    this.data = data || null;
  }
  ApiError.prototype = Object.create(Error.prototype);

  /* ================= 网络层 ================= */

  function api(path, opts) {
    var init = Object.assign({ credentials: 'include', cache: 'no-store' }, opts || {});
    init.headers = Object.assign({}, init.headers || {});
    if (init.body && !(init.body instanceof FormData)) {
      if (typeof init.body !== 'string') { init.body = JSON.stringify(init.body); }
      if (!init.headers['Content-Type']) { init.headers['Content-Type'] = 'application/json'; }
    }

    return fetch(API_BASE + path, init).then(function (res) {
      var ct = res.headers.get('content-type') || '';
      var parse = ct.indexOf('json') >= 0
        ? res.json().catch(function () { return null; })
        : Promise.resolve(null);

      return parse.then(function (data) {
        if (res.ok) { return data; }

        var detail = data && (data.detail || data.message);
        var msg = 'HTTP ' + res.status;
        if (typeof detail === 'string' && detail) {
          msg = detail;
        } else if (Array.isArray(detail)) {
          msg = detail.map(function (item) { return item.msg || JSON.stringify(item); }).join('；');
        }

        var isLogin = path.indexOf('/login') === 0;
        if (res.status === 401) {
          if (!isLogin) {
            showLogin('登录已过期，请重新登录');
            throw new ApiError('登录已过期', 401);
          }
          throw new ApiError(msg === 'HTTP 401' ? '账号或密码错误' : msg, 401, (data && data.code) || null);
        }
        throw new ApiError(msg, res.status, (data && data.code) || null, data);
      });
    }, function () {
      throw new ApiError('网络异常：连不上服务，请确认连着内网', 0);
    });
  }

  /* ================= 登录 / 会话 ================= */

  function setShown(id, shown) {
    var el = document.getElementById(id);
    if (!el) { return; }
    el.hidden = !shown;
    // 双保险：万一 CSS 里 .login-wrap{display:flex} 之类盖掉了 [hidden]，行内样式也压住
    el.style.display = shown ? '' : 'none';
  }

  function showLogin(reason) {
    state.me = null;
    setShown('loginView', true);
    setShown('app', false);
    setShown('topbar', false);
    var errEl = document.getElementById('loginErr');
    if (reason) { errEl.textContent = reason; errEl.hidden = false; } else { errEl.hidden = true; }
    var userEl = document.getElementById('loginUser');
    if (userEl) { userEl.focus(); }
  }

  function showApp() {
    setShown('loginView', false);
    setShown('app', true);
    setShown('topbar', true);
    document.getElementById('whoami').textContent = state.displayName || state.me || '';
  }

  function doLogin(ev) {
    ev.preventDefault();
    var userEl = document.getElementById('loginUser');
    var passEl = document.getElementById('loginPass');
    var errEl = document.getElementById('loginErr');
    var btn = document.getElementById('loginBtn');
    var username = userEl.value.trim();
    var password = passEl.value;

    errEl.hidden = true;
    if (!username || !password) {
      errEl.textContent = '请输入账号和密码';
      errEl.hidden = false;
      return;
    }

    btn.disabled = true;
    btn.textContent = '登录中…';
    api('/login', { method: 'POST', body: { username: username, password: password } })
      .then(function (res) {
        passEl.value = '';          // 密码不留在 DOM，更不落任何存储
        state.me = (res && res.username) || username;
        state.displayName = state.me;
        showApp();
        // 登录响应只有账号名，再拉一次 /me 取显示名（失败不影响使用）
        api('/me').then(function (me) {
          if (me && me.display_name) {
            state.displayName = me.display_name;
            document.getElementById('whoami').textContent = state.displayName;
          }
        }).catch(function () { /* 忽略 */ });
        // 字典必须用新会话重新拉（登录前 /dicts 是 401）
        return ensureDicts(true).then(render);
      })
      .catch(function (err) {
        errEl.textContent = err.status === 401 ? '账号或密码错误' : err.message;
        errEl.hidden = false;
        passEl.value = '';
        passEl.focus();
      })
      .then(function () {
        btn.disabled = false;
        btn.textContent = '登录';
      });
  }

  function doLogout() {
    api('/logout', { method: 'POST' })
      .catch(function () { /* 登出失败也照样回登录页，本地会话已不可信 */ })
      .then(function () {
        state.customers.index = null;
        state.import.preview = null;
        state.import.result = null;
        location.hash = '';
        showLogin();
      });
  }

  /* ================= 路由 ================= */

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
    $$('#nav a').forEach(function (link) {
      link.classList.toggle('active', link.getAttribute('data-view') === view);
    });
  }

  function render() {
    if (!state.me) { return Promise.resolve(); }
    var route = parseRoute();
    var view = route.parts[0] || 'dashboard';
    var seq = ++renderSeq;
    var root = document.getElementById('app');

    // 脚本版本自检：app.js 与 views/*.js 版本不一致（强缓存混版）时，
    // 页面会调不到 dictOptions/ensureDicts 而表现为「点按钮没反应」，这里提前拦下来。
    if (typeof window.dictOptions !== 'function' || typeof window.ensureDicts !== 'function') {
      root.innerHTML = '<div class="notice warn">页面脚本版本不一致（浏览器缓存了旧文件），' +
        '请按 <b>Ctrl + F5</b> 强制刷新一次再操作。</div>';
      return Promise.resolve();
    }

    setActiveNav(view === 'customers' && route.parts[1] ? 'customers' : view);
    root.innerHTML = '<p class="loading">加载中…</p>';

    var job;
    if (view === 'dashboard') {
      job = viewDashboard(root);
    } else if (view === 'customers') {
      job = route.parts[1] ? viewCustomerDetail(root, route.parts[1]) : viewCustomers(root);
    } else if (view === 'deals') {
      if (route.parts[1] === 'new') { job = viewDealNew(root, route); }
      else if (route.parts[1]) { job = viewDealDetail(root, route.parts[1]); }
      else { job = viewDeals(root, route); }
    } else if (view === 'followups') {
      job = viewFollowups(root, route);
    } else if (view === 'orders') {
      job = route.parts[1] ? viewOrderDetail(root, route.parts[1]) : viewOrders(root, route);
    } else if (view === 'aftersales') {
      job = route.parts[1] ? viewAftersaleDetail(root, route.parts[1]) : viewAftersales(root, route);
    } else if (view === 'logistics') {
      job = viewLogistics(root, route);
    } else if (view === 'stats') {
      job = viewStats(root);
    } else if (view === 'import') {
      job = viewImport(root);
    } else if (view === 'dict') {
      job = viewDict(root, route);
    } else if (view === 'leads') {
      job = route.parts[1] ? viewLeadDetail(root, route.parts[1]) : viewLeads(root);
    } else {
      job = Promise.resolve();
      root.innerHTML = '<div class="card">页面不存在，<a href="#/dashboard">回工作台</a></div>';
    }

    return Promise.resolve(job).catch(function (err) {
      if (err && err.status === 401) { return; }
      if (seq !== renderSeq) { return; }
      root.innerHTML = '<div class="card"><p class="err">加载失败：' + esc(err && err.message ? err.message : err) + '</p></div>';
    });
  }

  /* ================= 客户索引（商机/跟进页要显示客户名） ================= */

  function invalidateCustomerIndex() {
    state.customers.index = null;
    state.customers.builtAt = 0;
  }

  function ensureCustomerIndex(force) {
    var cache = state.customers;
    if (!force && cache.index && Date.now() - cache.builtAt < 60000) {
      return Promise.resolve(cache.index);
    }
    var map = {};
    var page = 1;

    function loadPage() {
      return api('/customers?page=' + page + '&size=100').then(function (res) {
        (res.items || []).forEach(function (c) { map[c.id] = c.name; });
        var loaded = page * 100;
        if (loaded < res.total && page < 50) {
          page += 1;
          return loadPage();
        }
        cache.index = map;
        cache.builtAt = Date.now();
        return map;
      });
    }
    return loadPage();
  }

  function customerOptions(index, selectedId) {
    var ids = Object.keys(index).map(Number).sort(function (a, b) {
      return String(index[a]).localeCompare(String(index[b]), 'zh-Hans-CN');
    });
    return ids.map(function (id) {
      return '<option value="' + id + '"' + (String(id) === String(selectedId) ? ' selected' : '') + '>' +
        esc(index[id]) + '</option>';
    }).join('');
  }

  /* ================= 跨文件共享（views/*.js 以裸名调用这里的工具）=================
   * 视图文件是普通 <script>，与 app.js 的 IIFE 不共享作用域；不显式挂到 window，
   * 视图里的 api() / esc() / state 全是 undefined → 整页 ReferenceError。
   * state 必须挂同一个对象引用（视图会改 state.filters / state.import）。
   */
  Object.assign(window, {
    API_BASE: API_BASE,
    PAGE_SIZE: PAGE_SIZE,
    MAX_PHOTOS: MAX_PHOTOS,
    MAX_PHOTO_MB: MAX_PHOTO_MB,
    MAX_TAGS: MAX_TAGS,
    STAGES: STAGES,
    STAGE_LABEL: STAGE_LABEL,
    ORDER_STATUS: ORDER_STATUS,
    ORDER_STATUS_LABEL: ORDER_STATUS_LABEL,
    ORDER_FLOW: ORDER_FLOW,
    AFTERSALE_TYPE_LABEL: AFTERSALE_TYPE_LABEL,
    AFTERSALE_STATUS_LABEL: AFTERSALE_STATUS_LABEL,
    SOURCE_LABELS: SOURCE_LABELS,
    INTENT_LABELS: INTENT_LABELS,
    ensureDicts: ensureDicts,
    dictItems: dictItems,
    dictLabel: dictLabel,
    dictOptions: dictOptions,
    state: state,
    esc: esc,
    pad2: pad2,
    money: money,
    fmtDateTime: fmtDateTime,
    todayISO: todayISO,
    numOrNull: numOrNull,
    toast: toast,
    ApiError: ApiError,
    api: api,
    $: $,
    $$: $$,
    parseRoute: parseRoute,
    navigate: navigate,
    setActiveNav: setActiveNav,
    render: render,
    invalidateCustomerIndex: invalidateCustomerIndex,
    ensureCustomerIndex: ensureCustomerIndex,
    customerOptions: customerOptions
  });

  /* ================= 启动 ================= */

  /* ================= 右上角用户菜单（个人信息 / 改密码 / 退出）================= */

  function closeUserMenu() {
    setShown('userDropdown', false);
    var btn = document.getElementById('userBtn');
    if (btn) { btn.setAttribute('aria-expanded', 'false'); }
  }

  function toggleUserMenu() {
    var dd = document.getElementById('userDropdown');
    if (!dd) { return; }
    var willOpen = dd.hidden;
    setShown('userDropdown', willOpen);
    var btn = document.getElementById('userBtn');
    if (btn) { btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false'); }
  }

  function openModal(id) { setShown(id, true); }
  function closeModal(id) { setShown(id, false); }

  function openProfileModal() {
    var userEl = document.getElementById('profUser');
    var nameEl = document.getElementById('profName');
    var errEl = document.getElementById('profErr');
    if (errEl) { errEl.hidden = true; }
    if (userEl) { userEl.value = state.me || ''; }
    if (nameEl) {
      nameEl.value = (state.displayName && state.displayName !== state.me) ? state.displayName : '';
    }
    api('/me').then(function (me) {
      if (userEl) { userEl.value = me.username || ''; }
      if (nameEl) {
        nameEl.value = (me.display_name && me.display_name !== me.username) ? me.display_name : '';
      }
    }).catch(function () { /* 拿不到就沿用当前值 */ });
    openModal('profileModal');
    setTimeout(function () { if (nameEl) { nameEl.focus(); } }, 30);
  }

  function submitProfile(ev) {
    ev.preventDefault();
    var errEl = document.getElementById('profErr');
    var nameEl = document.getElementById('profName');
    var btn = document.getElementById('profSubmit');
    var displayName = (nameEl.value || '').trim();
    errEl.hidden = true;
    btn.disabled = true;
    api('/me/profile', { method: 'PUT', body: { display_name: displayName } })
      .then(function (me) {
        state.me = (me && me.username) || state.me;
        state.displayName = (me && me.display_name) || state.me;
        document.getElementById('whoami').textContent = state.displayName;
        closeModal('profileModal');
        toast('个人信息已保存');
      })
      .catch(function (err) {
        errEl.textContent = err.message || '保存失败';
        errEl.hidden = false;
      })
      .then(function () { btn.disabled = false; });
  }

  function openPasswordModal() {
    document.getElementById('pwdOld').value = '';
    document.getElementById('pwdNew').value = '';
    document.getElementById('pwdNew2').value = '';
    var errEl = document.getElementById('pwdErr');
    errEl.hidden = true;
    openModal('passwordModal');
    setTimeout(function () { document.getElementById('pwdOld').focus(); }, 30);
  }

  function submitPassword(ev) {
    ev.preventDefault();
    var errEl = document.getElementById('pwdErr');
    var btn = document.getElementById('pwdSubmit');
    var oldPwd = document.getElementById('pwdOld').value;
    var newPwd = document.getElementById('pwdNew').value;
    var newPwd2 = document.getElementById('pwdNew2').value;
    errEl.hidden = true;
    if (!oldPwd || !newPwd) {
      errEl.textContent = '请填写原密码和新密码';
      errEl.hidden = false;
      return;
    }
    if (newPwd.length < 6) {
      errEl.textContent = '新密码至少 6 位';
      errEl.hidden = false;
      return;
    }
    if (newPwd !== newPwd2) {
      errEl.textContent = '两次输入的新密码不一致';
      errEl.hidden = false;
      return;
    }
    btn.disabled = true;
    api('/me/password', { method: 'PUT', body: { old_password: oldPwd, new_password: newPwd } })
      .then(function () {
        closeModal('passwordModal');
        toast('密码已修改，其它设备需重新登录');
      })
      .catch(function (err) {
        errEl.textContent = err.status === 400 && err.code === 'old_password_invalid'
          ? '原密码不正确'
          : (err.message || '修改失败');
        errEl.hidden = false;
      })
      .then(function () { btn.disabled = false; });
  }

  function boot() {
    document.getElementById('loginForm').addEventListener('submit', doLogin);
    var userBtn = document.getElementById('userBtn');
    if (userBtn) {
      userBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        toggleUserMenu();
      });
    }
    var dropdown = document.getElementById('userDropdown');
    if (dropdown) {
      dropdown.addEventListener('click', function (ev) {
        var target = ev.target && ev.target.closest ? ev.target.closest('[data-user-action]') : null;
        if (!target) { return; }
        closeUserMenu();
        var action = target.getAttribute('data-user-action');
        if (action === 'profile') { openProfileModal(); }
        else if (action === 'password') { openPasswordModal(); }
        else if (action === 'logout') { doLogout(); }
      });
    }
    document.addEventListener('click', function (ev) {
      if (ev.target && ev.target.closest && ev.target.closest('#userMenu')) { return; }
      closeUserMenu();
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        closeUserMenu();
        closeModal('profileModal');
        closeModal('passwordModal');
      }
    });
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-close-modal]'),
      function (el) {
        el.addEventListener('click', function () {
          closeModal(el.getAttribute('data-close-modal'));
        });
      }
    );
    var profileForm = document.getElementById('profileForm');
    if (profileForm) { profileForm.addEventListener('submit', submitProfile); }
    var passwordForm = document.getElementById('passwordForm');
    if (passwordForm) { passwordForm.addEventListener('submit', submitPassword); }
    window.addEventListener('hashchange', function () {
      if (state.me) { render(); }
    });

    // PWA：只做基础壳缓存，失败不影响使用（V1 不追求完整离线）
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', function () {
        navigator.serviceWorker.register('/crm/sw.js').catch(function () { /* 忽略 */ });
      });
    }

    api('/me').then(function (me) {
      state.me = (me && me.username) || '';
      state.displayName = (me && me.display_name) || state.me;
      showApp();
      return ensureDicts(true).then(render);
    }).catch(function (err) {
      if (err.status === 401) { showLogin(); } else { showLogin('连不上服务：' + err.message); }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
