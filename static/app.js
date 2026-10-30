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

  /* 与后端 app/models.py::STAGE_LABELS 一致（唯一来源在后端，这里只做展示映射） */
  var STAGES = [
    ['lead', '线索'],
    ['quoted', '已报价'],
    ['confirmed', '客户确认'],
    ['deposit', '已收定金'],
    ['producing', '已下单生产'],
    ['balance', '待付尾款'],
    ['shipped', '已发货'],
    ['won', '已成交'],
    ['lost', '已流失']
  ];
  var STAGE_LABEL = {};
  STAGES.forEach(function (pair) { STAGE_LABEL[pair[0]] = pair[1]; });

  /* 来源标签映射 */
  var SOURCE_LABELS = {
    'wechat': '微信',
    'phone': '电话',
    'referral': '转介绍',
    'existing': '老客户',
    'other': '其他'
  };

  /* 意向等级标签映射 */
  var INTENT_LABELS = {
    'high': '高',
    'medium': '中',
    'low': '低',
    'none': '无意向'
  };

  var state = {
    me: null,
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

  function ApiError(message, status) {
    this.name = 'ApiError';
    this.message = message;
    this.status = status || 0;
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
          throw new ApiError(msg === 'HTTP 401' ? '账号或密码错误' : msg, 401);
        }
        throw new ApiError(msg, res.status);
      });
    }, function () {
      throw new ApiError('网络异常：连不上服务，请确认连着内网', 0);
    });
  }

  /* ================= 登录 / 会话 ================= */

  function showLogin(reason) {
    state.me = null;
    document.getElementById('loginView').hidden = false;
    document.getElementById('app').hidden = true;
    document.getElementById('topbar').hidden = true;
    var errEl = document.getElementById('loginErr');
    if (reason) { errEl.textContent = reason; errEl.hidden = false; } else { errEl.hidden = true; }
    var userEl = document.getElementById('loginUser');
    if (userEl) { userEl.focus(); }
  }

  function showApp() {
    document.getElementById('loginView').hidden = true;
    document.getElementById('app').hidden = false;
    document.getElementById('topbar').hidden = false;
    document.getElementById('whoami').textContent = state.me || '';
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
        showApp();
        return render();
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

    setActiveNav(view === 'customers' && route.parts[1] ? 'customers' : view);
    root.innerHTML = '<p class="loading">加载中…</p>';

    var job;
    if (view === 'dashboard') {
      job = viewDashboard(root);
    } else if (view === 'customers') {
      job = route.parts[1] ? viewCustomerDetail(root, route.parts[1]) : viewCustomers(root);
    } else if (view === 'deals') {
      job = viewDeals(root, route);
    } else if (view === 'followups') {
      job = viewFollowups(root, route);
    } else if (view === 'stats') {
      job = viewStats(root);
    } else if (view === 'import') {
      job = viewImport(root);
    } else if (view === 'leads') {
      job = route.parts[1] ? viewLeadDetail(root, route.parts[1]) : viewLeads(root);
    } else {
      job = Promise.resolve();
      root.innerHTML = '<div class="card">页面不存在，<a href="#/dashboard">回看板</a></div>';
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

  /* ================= 启动 ================= */

  function boot() {
    document.getElementById('loginForm').addEventListener('submit', doLogin);
    document.getElementById('logoutBtn').addEventListener('click', doLogout);
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
      showApp();
      return render();
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