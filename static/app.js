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
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
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

  /* ================= 看板 ================= */

  function overdueBadge(days) {
    if (days === null || days === undefined) { return ''; }
    if (days > 0) { return '<span class="badge danger">逾期 ' + days + ' 天</span>'; }
    return '<span class="badge warn">今天</span>';
  }

  function barsHtml(byStage) {
    var max = 1;
    Object.keys(byStage || {}).forEach(function (k) { max = Math.max(max, Number(byStage[k]) || 0); });
    return STAGES.map(function (pair) {
      var count = Number((byStage || {})[pair[0]] || 0);
      var width = count ? Math.max(4, Math.round((count / max) * 100)) : 0;
      return '<div class="bar-row">' +
        '<span>' + pair[1] + '</span>' +
        '<span class="bar"><i style="width:' + width + '%"></i></span>' +
        '<span class="bar-num">' + count + '</span>' +
        '</div>';
    }).join('');
  }

  function viewDashboard(root) {
    return api('/dashboard').then(function (d) {
      var stats = d.stats || {};
      var monthWon = d.month_won || stats.month_won || { count: 0, amount: 0 };
      var todos = d.today_followups || [];

      var todoHtml = todos.length ? todos.map(function (item) {
        var stageTag = item.deal_stage_label
          ? '<span class="tag">' + esc(item.deal_stage_label) + '</span>' : '';
        var link = '#/followups?customer=' + item.customer_id +
          (item.deal_id ? '&deal=' + item.deal_id : '');
        return '<div class="item">' +
          '<div class="item-main">' +
            '<div class="item-title"><a href="#/customers/' + item.customer_id + '">' +
              esc(item.customer_name) + '</a>' + overdueBadge(item.days_overdue) + stageTag + '</div>' +
            '<div class="item-sub">' + esc(item.content) + '</div>' +
            '<div class="item-sub small">约好 ' + esc(item.next_date) + '</div>' +
          '</div>' +
          '<div class="item-side"><a class="btn btn-sm" href="' + link + '">记跟进</a></div>' +
        '</div>';
      }).join('') : '<p class="empty">今天没有待跟进，清爽 👌</p>';

      root.innerHTML =
        '<div class="grid-kpi">' +
          '<div class="kpi"><div class="label">本月成交</div><div class="value">' + money(monthWon.amount) +
            '</div><div class="sub">' + (monthWon.count || 0) + ' 单</div></div>' +
          '<div class="kpi"><div class="label">待跟进</div><div class="value">' + todos.length +
            '</div><div class="sub">含逾期</div></div>' +
          '<div class="kpi"><div class="label">客户总数</div><div class="value">' + (stats.customers_total || 0) +
            '</div><div class="sub">本月新增 ' + (stats.month_new_customers || 0) + '</div></div>' +
          '<div class="kpi"><div class="label">老客</div><div class="value">' + (stats.repeat_customers || 0) +
            '</div><div class="sub">名下 ≥2 个商机</div></div>' +
        '</div>' +
        '<div class="card">' +
          '<div class="card-head"><h2>今日待跟进 <span class="badge warn">' + todos.length + '</span></h2>' +
            '<a class="btn btn-sm" href="#/followups">全部跟进</a></div>' +
          todoHtml +
        '</div>' +
        '<div class="card">' +
          '<div class="card-head"><h2>商机阶段分布</h2><a class="btn btn-sm" href="#/deals">管理商机</a></div>' +
          barsHtml(stats.deals_by_stage) +
        '</div>';
    });
  }

  /* ================= 客户列表 ================= */

  function customerFormHtml(customer) {
    var c = customer || {};
    return '<form class="customer-form" autocomplete="off">' +
      '<div class="row-2">' +
        '<div class="field"><label>姓名 *</label>' +
          '<input name="name" type="text" maxlength="64" required value="' + esc(c.name || '') + '"></div>' +
        '<div class="field"><label>电话</label>' +
          '<input name="phone" type="tel" maxlength="32" inputmode="tel" value="' + esc(c.phone || '') + '"></div>' +
      '</div>' +
      '<div class="row-2">' +
        '<div class="field"><label>微信</label>' +
          '<input name="wechat" type="text" maxlength="64" value="' + esc(c.wechat || '') + '"></div>' +
        '<div class="field"><label>楼盘 / 安装地址</label>' +
          '<input name="location" type="text" maxlength="200" value="' + esc(c.location || '') + '"></div>' +
      '</div>' +
      '<div class="field"><label>户型 / 备注</label>' +
        '<textarea name="house_note" maxlength="500">' + esc(c.house_note || '') + '</textarea></div>' +
      '<div class="field"><label>标签（逗号分隔，如：重点、转介绍）</label>' +
        '<input name="tags" type="text" maxlength="400" value="' + esc((c.tags || []).join('、')) + '"></div>' +
      '<div class="form-actions"><button type="submit" class="btn btn-primary">保存</button></div>' +
    '</form>';
  }

  function readCustomerForm(form) {
    function val(name) {
      var el = form.querySelector('[name="' + name + '"]');
      return el ? String(el.value || '').trim() : '';
    }
    var tags = val('tags').split(/[,，、;；\s]+/).filter(Boolean).slice(0, MAX_TAGS);
    return {
      name: val('name'),
      phone: val('phone') || null,
      wechat: val('wechat') || null,
      location: val('location') || null,
      house_note: val('house_note') || null,
      tags: tags
    };
  }

  function customerItemHtml(c) {
    var tags = (c.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('');
    var repeat = c.is_repeat ? '<span class="badge ok">老客</span>' : '';
    return '<div class="item">' +
      '<div class="item-main">' +
        '<div class="item-title"><a href="#/customers/' + c.id + '">' + esc(c.name) + '</a>' + repeat + '</div>' +
        '<div class="item-sub">' + esc(c.phone || '无电话') +
          (c.location ? ' · ' + esc(c.location) : '') + '</div>' +
        (tags ? '<div class="tags">' + tags + '</div>' : '') +
      '</div>' +
      '<div class="item-side"><div>' + (c.deals_total || 0) + ' 个商机</div>' +
        '<div class="muted small">成交 ' + money(c.total_closed_amount) + '</div></div>' +
    '</div>';
  }

  function chipHtml(tags, active) {
    var html = '<button type="button" class="chip' + (active ? '' : ' active') + '" data-tag="">全部</button>';
    return html + (tags || []).map(function (tag) {
      return '<button type="button" class="chip' + (active === tag ? ' active' : '') +
        '" data-tag="' + esc(tag) + '">' + esc(tag) + '</button>';
    }).join('');
  }

  function viewCustomers(root) {
    var st = state.filters;
    return api('/tags').catch(function () { return []; }).then(function (tags) {
      root.innerHTML =
        '<div class="card">' +
          '<div class="card-head"><h2>客户档案</h2>' +
            '<button type="button" class="btn btn-primary btn-sm" id="toggleNewCustomer">+ 新增客户</button></div>' +
          '<div class="searchbar">' +
            '<input id="custSearch" type="search" placeholder="搜姓名 / 电话 / 楼盘" autocomplete="off" value="' + esc(st.q) + '">' +
            '<button type="button" class="btn" id="custSearchBtn">搜索</button>' +
          '</div>' +
          '<div class="chips" id="tagChips">' + chipHtml(tags, st.tag) + '</div>' +
          '<div id="newCustomerWrap" hidden>' + customerFormHtml(null) + '</div>' +
        '</div>' +
        '<div class="card"><div id="custList"><p class="loading">加载中…</p></div><div id="custPager"></div></div>';

      var wrap = $('#newCustomerWrap', root);
      $('#toggleNewCustomer', root).addEventListener('click', function () {
        wrap.hidden = !wrap.hidden;
        if (!wrap.hidden) { wrap.querySelector('[name="name"]').focus(); }
      });

      wrap.querySelector('form').addEventListener('submit', function (ev) {
        ev.preventDefault();
        var form = ev.target;
        var btn = form.querySelector('button[type="submit"]');
        var payload = readCustomerForm(form);
        if (!payload.name) { toast('姓名必填', true); return; }
        btn.disabled = true;
        api('/customers', { method: 'POST', body: payload }).then(function () {
          invalidateCustomerIndex();
          toast('已新增客户');
          form.reset();
          wrap.hidden = true;
          return api('/tags').catch(function () { return []; });
        }).then(function (newTags) {
          var chips = $('#tagChips', root);
          if (chips) { chips.innerHTML = chipHtml(newTags, st.tag); }
          st.page = 1;
          return loadCustomers(root);
        }).catch(function (err) {
          toast(err.message, true);
        }).then(function () { btn.disabled = false; });
      });

      var searchEl = $('#custSearch', root);
      var timer = null;
      function applySearch() {
        st.q = String(searchEl.value || '').trim();
        st.page = 1;
        loadCustomers(root);
      }
      searchEl.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(applySearch, 300);
      });
      searchEl.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') { ev.preventDefault(); clearTimeout(timer); applySearch(); }
      });
      $('#custSearchBtn', root).addEventListener('click', applySearch);

      $('#tagChips', root).addEventListener('click', function (ev) {
        var btn = ev.target.closest('button[data-tag]');
        if (!btn) { return; }
        st.tag = btn.getAttribute('data-tag') || '';
        st.page = 1;
        $$('#tagChips .chip', root).forEach(function (chip) {
          chip.classList.toggle('active', (chip.getAttribute('data-tag') || '') === st.tag);
        });
        loadCustomers(root);
      });

      return loadCustomers(root);
    });
  }

  function pagerHtml(res) {
    var pages = Math.max(1, Math.ceil((res.total || 0) / (res.size || PAGE_SIZE)));
    if (!res.total) { return ''; }
    return '<div class="form-actions" style="justify-content:space-between;align-items:center">' +
      '<button type="button" class="btn btn-sm" data-page="' + (res.page - 1) + '"' +
        (res.page <= 1 ? ' disabled' : '') + '>上一页</button>' +
      '<span class="small muted">第 ' + res.page + ' / ' + pages + ' 页 · 共 ' + res.total + ' 位</span>' +
      '<button type="button" class="btn btn-sm" data-page="' + (res.page + 1) + '"' +
        (res.page >= pages ? ' disabled' : '') + '>下一页</button>' +
    '</div>';
  }

  function loadCustomers(root) {
    var st = state.filters;
    var listEl = $('#custList', root);
    var pagerEl = $('#custPager', root);
    if (!listEl) { return Promise.resolve(); }
    listEl.innerHTML = '<p class="loading">加载中…</p>';

    var params = new URLSearchParams();
    params.set('page', String(st.page));
    params.set('size', String(PAGE_SIZE));
    if (st.q) { params.set('search', st.q); }
    if (st.tag) { params.set('tag', st.tag); }

    return api('/customers?' + params.toString()).then(function (res) {
      var items = res.items || [];
      if (!items.length) {
        listEl.innerHTML = '<p class="empty">' +
          (st.q || st.tag ? '没有匹配的客户，换个条件试试' : '还没有客户，点右上「新增客户」开始') + '</p>';
      } else {
        listEl.innerHTML = items.map(customerItemHtml).join('');
      }
      pagerEl.innerHTML = pagerHtml(res);
      pagerEl.onclick = function (ev) {
        var btn = ev.target.closest('button[data-page]');
        if (!btn || btn.disabled) { return; }
        st.page = Number(btn.getAttribute('data-page')) || 1;
        loadCustomers(root);
      };
    }).catch(function (err) {
      listEl.innerHTML = '<p class="err">' + esc(err.message) + '</p>';
    });
  }

  /* ================= 客户详情 ================= */

  function stageOptions(current) {
    return STAGES.map(function (pair) {
      return '<option value="' + pair[0] + '"' + (pair[0] === current ? ' selected' : '') + '>' +
        pair[1] + '</option>';
    }).join('');
  }

  function followupItemHtml(item, opts) {
    opts = opts || {};
    var photos = (item.photos || []).map(function (p) {
      var url = '/crm' + p.url;
      return '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' +
        '<img src="' + esc(url) + '" alt="' + esc(p.file_name || '照片') + '" loading="lazy"></a>';
    }).join('');
    var deleteBtn = opts.withDelete
      ? '<button type="button" class="btn-link" data-del-followup="' + item.id + '">删除</button>' : '';
    return '<div class="item">' +
      '<div class="item-main">' +
        '<div class="item-title">' +
          (opts.showCustomer && item.customer_name
            ? '<a href="#/customers/' + item.customer_id + '">' + esc(item.customer_name) + '</a>'
            : '<span class="muted small">' + fmtDateTime(item.created_at) + '</span>') +
          (item.deal_stage && STAGE_LABEL[item.deal_stage]
            ? '<span class="tag">' + esc(STAGE_LABEL[item.deal_stage]) + '</span>' : '') +
        '</div>' +
        '<div class="item-sub">' + esc(item.content) + '</div>' +
        '<div class="item-sub small">' +
          fmtDateTime(item.created_at) +
          (item.next_date ? ' · 下次 ' + esc(item.next_date) : '') +
          (item.photo_count ? ' · 📷 ' + item.photo_count : '') +
        '</div>' +
        (photos ? '<div class="photos">' + photos + '</div>' : '') +
      '</div>' +
      '<div class="item-side">' + deleteBtn + '</div>' +
    '</div>';
  }

  function dealItemHtml(deal) {
    var parts = [deal.product_type, deal.model, deal.spec].filter(Boolean).join(' / ') || '未填产品';
    var amounts = '报价 ' + money(deal.amount);
    if (deal.deposit) { amounts += ' · 定金 ' + money(deal.deposit); }
    if (deal.balance) { amounts += ' · 尾款 ' + money(deal.balance); }
    return '<div class="item">' +
      '<div class="item-main">' +
        '<div class="item-title">' + esc(parts) +
          '<span class="badge muted">' + esc(deal.stage_label || STAGE_LABEL[deal.stage] || deal.stage) + '</span></div>' +
        '<div class="item-sub">' + esc(amounts) + '</div>' +
        '<div class="item-sub small">' +
          (deal.closed_at ? '成交于 ' + fmtDateTime(deal.closed_at) : '创建于 ' + fmtDateTime(deal.created_at)) +
        '</div>' +
      '</div>' +
      '<div class="item-side">' +
        '<select data-deal-stage="' + deal.id + '" aria-label="切换阶段">' + stageOptions(deal.stage) + '</select>' +
      '</div>' +
    '</div>';
  }

  function dealFormHtml() {
    return '<form id="newDealForm" autocomplete="off">' +
      '<div class="row-2">' +
        '<div class="field"><label>产品类型</label>' +
          '<input name="product_type" type="text" maxlength="32" placeholder="天窗 / 天幕"></div>' +
        '<div class="field"><label>型号</label>' +
          '<input name="model" type="text" maxlength="64" placeholder="如 XW-120"></div>' +
      '</div>' +
      '<div class="field"><label>尺寸 / 洞口</label>' +
        '<input name="spec" type="text" maxlength="200" placeholder="如 1200×2400"></div>' +
      '<div class="row-3">' +
        '<div class="field"><label>报价金额 *</label>' +
          '<input name="amount" type="number" min="0" step="0.01" inputmode="decimal" required></div>' +
        '<div class="field"><label>定金</label>' +
          '<input name="deposit" type="number" min="0" step="0.01" inputmode="decimal"></div>' +
        '<div class="field"><label>尾款</label>' +
          '<input name="balance" type="number" min="0" step="0.01" inputmode="decimal"></div>' +
      '</div>' +
      '<div class="field"><label>阶段</label>' +
        '<select name="stage">' + stageOptions('lead') + '</select></div>' +
      '<div class="form-actions"><button type="submit" class="btn btn-primary">新增商机</button></div>' +
    '</form>';
  }

  function bindDealStageSelects(root) {
    $$('select[data-deal-stage]', root).forEach(function (sel) {
      sel.addEventListener('change', function () {
        sel.disabled = true;
        api('/deals/' + sel.getAttribute('data-deal-stage'), {
          method: 'PUT',
          body: { stage: sel.value }
        }).then(function () {
          toast('阶段已更新');
          return render();
        }).catch(function (err) {
          toast(err.message, true);
          sel.disabled = false;
        });
      });
    });
  }

  function viewCustomerDetail(root, rawId) {
    var id = Number(rawId);
    if (!id || isNaN(id)) {
      root.innerHTML = '<div class="card">客户 id 不合法，<a href="#/customers">回客户列表</a></div>';
      return Promise.resolve();
    }

    return Promise.all([
      api('/customers/' + id),
      api('/follow-ups?customer_id=' + id)
    ]).then(function (all) {
      var c = all[0];
      var followups = all[1] || [];
      var deals = c.deals || [];

      var dealHtml = deals.length
        ? '<div id="dealList">' + deals.map(function (d) {
            var item = dealItemHtml(d);
            // 详情页的商机卡片里额外给一个“记跟进”入口（带 deal_id）
            return item.replace('<div class="item-side">',
              '<div class="item-side"><a class="btn btn-sm" href="#/followups?customer=' + c.id +
              '&deal=' + d.id + '">记跟进</a>');
          }).join('') + '</div>'
        : '<p class="empty">还没有商机</p>';

      var fuHtml = followups.length
        ? followups.map(function (f) { return followupItemHtml(f, { withDelete: true }); }).join('')
        : '<p class="empty">还没有跟进记录</p>';

      root.innerHTML =
        '<div class="card">' +
          '<div class="card-head">' +
            '<h2><a href="#/customers">‹ 客户</a> ' + esc(c.name) +
              (c.is_repeat ? ' <span class="badge ok">老客</span>' : '') + '</h2>' +
            '<div>' +
              '<a class="btn btn-sm" href="#/followups?customer=' + c.id + '">记跟进</a> ' +
              '<button type="button" class="btn btn-sm" id="toggleEditCustomer">编辑</button> ' +
              '<button type="button" class="btn btn-sm btn-danger" id="deleteCustomer">删除</button>' +
            '</div>' +
          '</div>' +
          '<div class="tags">' + (c.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') + '</div>' +
          '<div class="item-sub" style="margin-top:8px">' +
            '电话：' + esc(c.phone || '—') + '<br>' +
            '微信：' + esc(c.wechat || '—') + '<br>' +
            '楼盘：' + esc(c.location || '—') + '<br>' +
            '户型/备注：' + esc(c.house_note || '—') + '<br>' +
            '<span class="muted small">建档 ' + fmtDateTime(c.created_at) + ' · 最近更新 ' + fmtDateTime(c.updated_at) + '</span>' +
          '</div>' +
          '<div id="editCustomerWrap" hidden style="margin-top:12px">' + customerFormHtml(c) + '</div>' +
        '</div>' +
        '<div class="card">' +
          '<div class="card-head"><h2>商机（' + deals.length + '）</h2>' +
            '<button type="button" class="btn btn-sm" id="toggleNewDeal">+ 新增商机</button></div>' +
          '<div id="newDealWrap" hidden>' + dealFormHtml() + '</div>' +
          dealHtml +
        '</div>' +
        '<div class="card">' +
          '<div class="card-head"><h2>跟进记录（' + followups.length + '）</h2>' +
            '<a class="btn btn-sm" href="#/followups?customer=' + c.id + '">+ 记一条</a></div>' +
          fuHtml +
        '</div>';

      /* 编辑客户 */
      var editWrap = $('#editCustomerWrap', root);
      $('#toggleEditCustomer', root).addEventListener('click', function () {
        editWrap.hidden = !editWrap.hidden;
        if (!editWrap.hidden) { editWrap.querySelector('[name="name"]').focus(); }
      });
      editWrap.querySelector('form').addEventListener('submit', function (ev) {
        ev.preventDefault();
        var form = ev.target;
        var btn = form.querySelector('button[type="submit"]');
        var payload = readCustomerForm(form);
        if (!payload.name) { toast('姓名必填', true); return; }
        btn.disabled = true;
        api('/customers/' + c.id, { method: 'PUT', body: payload }).then(function () {
          invalidateCustomerIndex();
          toast('已保存');
          return render();
        }).catch(function (err) {
          toast(err.message, true);
          btn.disabled = false;
        });
      });

      /* 删除客户（级联删商机/跟进/标签） */
      $('#deleteCustomer', root).addEventListener('click', function () {
        if (!window.confirm('删除客户「' + c.name + '」？其商机、跟进记录会一起删掉，不可恢复。')) { return; }
        api('/customers/' + c.id, { method: 'DELETE' }).then(function () {
          invalidateCustomerIndex();
          toast('已删除客户');
          navigate('#/customers');
        }).catch(function (err) { toast(err.message, true); });
      });

      /* 新增商机 */
      var newDealWrap = $('#newDealWrap', root);
      $('#toggleNewDeal', root).addEventListener('click', function () {
        newDealWrap.hidden = !newDealWrap.hidden;
      });
      $('#newDealForm', root).addEventListener('submit', function (ev) {
        ev.preventDefault();
        var form = ev.target;
        var btn = form.querySelector('button[type="submit"]');
        var amount = numOrNull(form.querySelector('[name="amount"]').value);
        if (amount === null || amount < 0) { toast('报价金额必填且 ≥0', true); return; }
        var payload = {
          customer_id: c.id,
          product_type: form.querySelector('[name="product_type"]').value.trim() || null,
          model: form.querySelector('[name="model"]').value.trim() || null,
          spec: form.querySelector('[name="spec"]').value.trim() || null,
          amount: amount,
          deposit: numOrNull(form.querySelector('[name="deposit"]').value) || 0,
          balance: numOrNull(form.querySelector('[name="balance"]').value) || 0,
          stage: form.querySelector('[name="stage"]').value
        };
        btn.disabled = true;
        api('/deals', { method: 'POST', body: payload }).then(function () {
          toast('已新增商机');
          return render();
        }).catch(function (err) {
          toast(err.message, true);
          btn.disabled = false;
        });
      });

      bindDealStageSelects(root);

      $$('button[data-del-followup]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
          if (!window.confirm('删除这条跟进？照片也会一并无法查看（文件留存于备份）。')) { return; }
          api('/follow-ups/' + btn.getAttribute('data-del-followup'), { method: 'DELETE' })
            .then(function () { toast('已删除'); return render(); })
            .catch(function (err) { toast(err.message, true); });
        });
      });
    });
  }

  /* ================= 商机列表 ================= */

  function viewDeals(root, route) {
    var stage = route.query.get('stage') || '';
    var path = '/deals' + (stage ? '?stage=' + encodeURIComponent(stage) : '');

    return Promise.all([api(path), ensureCustomerIndex()]).then(function (all) {
      var deals = all[0] || [];
      var index = all[1];

      var listHtml = deals.length ? deals.map(function (d) {
        var name = index[d.customer_id] || ('客户 #' + d.customer_id);
        var parts = [d.product_type, d.model, d.spec].filter(Boolean).join(' / ') || '未填产品';
        var amounts = '报价 ' + money(d.amount);
        if (d.deposit) { amounts += ' · 定金 ' + money(d.deposit); }
        if (d.balance) { amounts += ' · 尾款 ' + money(d.balance); }
        return '<div class="item">' +
          '<div class="item-main">' +
            '<div class="item-title"><a href="#/customers/' + d.customer_id + '">' + esc(name) + '</a>' +
              '<span class="badge muted">' + esc(d.stage_label || STAGE_LABEL[d.stage] || d.stage) + '</span></div>' +
            '<div class="item-sub">' + esc(parts) + '</div>' +
            '<div class="item-sub small">' + esc(amounts) +
              (d.closed_at ? ' · 成交 ' + fmtDateTime(d.closed_at) : '') + '</div>' +
          '</div>' +
          '<div class="item-side"><select data-deal-stage="' + d.id + '" aria-label="切换阶段">' +
            stageOptions(d.stage) + '</select></div>' +
        '</div>';
      }).join('') : '<p class="empty">' + (stage ? '这个阶段还没有商机' : '还没有商机') + '</p>';

      var customerIds = Object.keys(index).map(Number);
      var newDealCard = customerIds.length
        ? '<div class="card"><div class="card-head"><h2>新增商机</h2></div>' +
            '<div class="field"><label>客户 *</label><select id="dealCustomer">' +
              customerOptions(index, '') + '</select></div>' +
            dealFormHtml() + '</div>'
        : '<div class="card"><p class="empty">还没有客户，先 <a href="#/customers">建客户</a></p></div>';

      root.innerHTML =
        '<div class="card">' +
          '<div class="card-head"><h2>商机管道（' + deals.length + '）</h2>' +
            '<select id="dealStageFilter" aria-label="按阶段筛选" style="width:auto">' +
              '<option value="">全部阶段</option>' +
              STAGES.map(function (pair) {
                return '<option value="' + pair[0] + '"' + (pair[0] === stage ? ' selected' : '') + '>' +
                  pair[1] + '</option>';
              }).join('') +
            '</select>' +
          '</div>' +
          listHtml +
        '</div>' + newDealCard;

      $('#dealStageFilter', root).addEventListener('change', function (ev) {
        var value = ev.target.value;
        navigate('#/deals' + (value ? '?stage=' + encodeURIComponent(value) : ''));
      });

      bindDealStageSelects(root);

      var form = $('#newDealForm', root);
      if (form) {
        form.addEventListener('submit', function (ev) {
          ev.preventDefault();
          var btn = form.querySelector('button[type="submit"]');
          var customerId = Number($('#dealCustomer', root).value);
          var amount = numOrNull(form.querySelector('[name="amount"]').value);
          if (!customerId) { toast('先选客户', true); return; }
          if (amount === null || amount < 0) { toast('报价金额必填且 ≥0', true); return; }
          var payload = {
            customer_id: customerId,
            product_type: form.querySelector('[name="product_type"]').value.trim() || null,
            model: form.querySelector('[name="model"]').value.trim() || null,
            spec: form.querySelector('[name="spec"]').value.trim() || null,
            amount: amount,
            deposit: numOrNull(form.querySelector('[name="deposit"]').value) || 0,
            balance: numOrNull(form.querySelector('[name="balance"]').value) || 0,
            stage: form.querySelector('[name="stage"]').value
          };
          btn.disabled = true;
          api('/deals', { method: 'POST', body: payload }).then(function () {
            toast('已新增商机');
            return render();
          }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
          });
        });
      }
    });
  }

  /* ================= 跟进 ================= */

  function followupFormHtml(index, preCustomer, preDeal) {
    var hasCustomers = Object.keys(index).length > 0;
    return '<form id="fuForm" autocomplete="off">' +
      '<div class="row-2">' +
        '<div class="field"><label>客户 *</label>' +
          (hasCustomers
            ? '<select id="fuCustomer" name="customer_id">' + customerOptions(index, preCustomer) + '</select>'
            : '<p class="small muted">还没有客户，先 <a href="#/customers">建一个</a></p>') +
        '</div>' +
        '<div class="field"><label>关联商机</label>' +
          '<select id="fuDeal" name="deal_id"><option value="">不关联</option></select></div>' +
      '</div>' +
      '<div class="field"><label>跟进内容 *（≤2000 字）</label>' +
        '<textarea name="content" maxlength="2000" required placeholder="聊了什么、客户什么态度、下一步做什么"></textarea></div>' +
      '<div class="row-2">' +
        '<div class="field"><label>下次跟进日期</label>' +
          '<input type="date" name="next_date" value="' + todayISO() + '"></div>' +
        '<div class="field"><label>顺手改阶段（选了商机才生效）</label>' +
          '<select id="fuStage" name="stage" disabled><option value="">不改阶段</option>' +
            STAGES.map(function (p) { return '<option value="' + p[0] + '">' + p[1] + '</option>'; }).join('') +
          '</select></div>' +
      '</div>' +
      '<div class="field"><label>照片（最多 ' + MAX_PHOTOS + ' 张，单张 ≤' + MAX_PHOTO_MB + 'MB）</label>' +
        '<input type="file" id="fuPhotos" name="photos" accept="image/*" capture="environment" multiple></div>' +
      '<div class="form-actions"><button type="submit" class="btn btn-primary">保存跟进</button></div>' +
    '</form>';
  }

  function viewFollowups(root, route) {
    var preCustomer = route.query.get('customer') || '';
    var preDeal = route.query.get('deal') || '';

    return Promise.all([api('/follow-ups'), ensureCustomerIndex()]).then(function (all) {
      var list = all[0] || [];
      var index = all[1];

      var listHtml = list.length ? list.map(function (f) {
        return followupItemHtml(f, { withDelete: true, showCustomer: true });
      }).join('') : '<p class="empty">还没有跟进记录</p>';

      root.innerHTML =
        '<div class="card">' + '<div class="card-head"><h2>记一条跟进</h2></div>' +
          followupFormHtml(index, preCustomer, preDeal) +
        '</div>' +
        '<div class="card"><div class="card-head"><h2>全部跟进（' + list.length + '）</h2></div>' +
          listHtml + '</div>';

      var customerSel = $('#fuCustomer', root);
      var dealSel = $('#fuDeal', root);
      var stageSel = $('#fuStage', root);
      var photosInput = $('#fuPhotos', root);
      var form = $('#fuForm', root);
      if (!form || !customerSel) { return; }

      function loadDealsForCustomer(customerId) {
        dealSel.innerHTML = '<option value="">不关联</option>';
        stageSel.disabled = true;
        stageSel.value = '';
        if (!customerId) { return Promise.resolve(); }
        return api('/deals?customer_id=' + encodeURIComponent(customerId)).then(function (deals) {
          dealSel.innerHTML = '<option value="">不关联</option>' + (deals || []).map(function (d) {
            var label = [d.product_type, d.model].filter(Boolean).join(' ') || ('商机 #' + d.id);
            return '<option value="' + d.id + '">' + esc(label) + ' · ' +
              esc(d.stage_label || STAGE_LABEL[d.stage] || d.stage) + ' · ' + money(d.amount) + '</option>';
          }).join('');
          if (preDeal && deals && deals.some(function (d) { return String(d.id) === String(preDeal); })) {
            dealSel.value = String(preDeal);
            stageSel.disabled = false;
          }
          return null;
        });
      }

      customerSel.addEventListener('change', function () {
        loadDealsForCustomer(customerSel.value);
      });
      dealSel.addEventListener('change', function () {
        stageSel.disabled = !dealSel.value;
        if (!dealSel.value) { stageSel.value = ''; }
      });
      photosInput.addEventListener('change', function () {
        if (photosInput.files.length > MAX_PHOTOS) {
          toast('一条跟进最多 ' + MAX_PHOTOS + ' 张照片，已清空选择', true);
          photosInput.value = '';
        }
      });

      loadDealsForCustomer(customerSel.value).catch(function (err) { toast(err.message, true); });

      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var content = String(form.querySelector('[name="content"]').value || '').trim();
        var customerId = customerSel.value;
        if (!customerId) { toast('先选客户', true); return; }
        if (!content) { toast('跟进内容不能为空', true); return; }
        if (photosInput.files.length > MAX_PHOTOS) { toast('照片最多 ' + MAX_PHOTOS + ' 张', true); return; }

        var tooBig = Array.prototype.some.call(photosInput.files, function (f) {
          return f.size > MAX_PHOTO_MB * 1024 * 1024;
        });
        if (tooBig) { toast('有照片超过 ' + MAX_PHOTO_MB + 'MB', true); return; }

        var fd = new FormData();
        fd.append('customer_id', customerId);
        fd.append('content', content);
        var nextDate = form.querySelector('[name="next_date"]').value;
        if (nextDate) { fd.append('next_date', nextDate); }
        if (dealSel.value) {
          fd.append('deal_id', dealSel.value);
          if (stageSel.value) { fd.append('stage', stageSel.value); }
        }
        Array.prototype.forEach.call(photosInput.files, function (file) { fd.append('photos', file); });

        btn.disabled = true;
        btn.textContent = '保存中…';
        api('/follow-ups', { method: 'POST', body: fd }).then(function (item) {
          toast('已记录跟进' + (item && item.photo_count ? '（' + item.photo_count + ' 张照片）' : ''));
          // 提交后清掉 URL 里的预填参数，避免表单又被填上一次
          navigate('#/followups');
        }).catch(function (err) {
          toast(err.message, true);
          btn.disabled = false;
          btn.textContent = '保存跟进';
        });
      });

      $$('button[data-del-followup]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
          if (!window.confirm('删除这条跟进？')) { return; }
          api('/follow-ups/' + btn.getAttribute('data-del-followup'), { method: 'DELETE' })
            .then(function () { toast('已删除'); return render(); })
            .catch(function (err) { toast(err.message, true); });
        });
      });
    });
  }

  /* ================= 统计 ================= */

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

  function importMappingHtml(pv) {
    var fields = pv.system_fields || [];
    var suggested = pv.suggested_mapping || {};
    var last = pv.last_mapping || {};
    var initial = Object.keys(suggested).length ? suggested : last;
    var usedLast = !Object.keys(suggested).length && Object.keys(last).length;

    var rows = (pv.headers || []).map(function (header) {
      var current = initial[header] || '';
      var options = '<option value="">不导入</option>' + fields.map(function (f) {
        return '<option value="' + esc(f.key) + '"' + (f.key === current ? ' selected' : '') + '>' +
          esc(f.label) + (f.required ? ' *' : '') + '</option>';
      }).join('');
      return '<div class="row-2"><div class="field"><label>CSV 列：' + esc(header) + '</label>' +
        '<select data-imp-header="' + esc(header) + '">' + options + '</select></div></div>';
    }).join('');

    var previewHead = (pv.headers || []).map(function (h) { return '<th>' + esc(h) + '</th>'; }).join('');
    var previewRows = (pv.preview || []).map(function (row) {
      return '<tr>' + (pv.headers || []).map(function (h) {
        return '<td>' + esc(row[h] === undefined ? '' : row[h]) + '</td>';
      }).join('') + '</tr>';
    }).join('');

    return '<div class="card">' +
      '<div class="card-head"><h2>列映射</h2>' +
        (usedLast && pv.last_mapping
          ? '<button type="button" class="btn btn-sm" id="useLastMapping">用上次映射</button>' : '') +
      '</div>' +
      '<p class="small muted">文件：' + esc(pv.file_name) + ' · 共 ' + (pv.total_rows || 0) + ' 行数据 · ' +
        '编码 ' + esc(pv.encoding || '?') + ' · 分隔符 ' + esc(pv.delimiter || ',') + '</p>' +
      rows +
      '<div class="table-wrap" style="margin-top:10px"><table><thead><tr>' + previewHead +
        '</tr></thead><tbody>' + previewRows + '</tbody></table></div>' +
      '<div class="form-actions"><button type="button" class="btn btn-primary" id="impCommit">确认导入</button></div>' +
      '<div id="impResult"></div>' +
    '</div>';
  }

  function viewImport(root) {
    var pv = state.import.preview;
    var result = state.import.result;

    var body = '<div class="card">' +
      '<div class="card-head"><h2>导入存量客户</h2></div>' +
      '<p class="small muted">Excel 里「另存为 → CSV（逗号分隔）」再上传；V1 不支持直接读 .xlsx。</p>' +
      '<div class="field"><input type="file" id="impFile" accept=".csv,text/csv"></div>' +
      '<div class="form-actions"><button type="button" class="btn btn-primary" id="impPreview">上传并预览</button></div>' +
      '<div id="impMsg"></div>' +
    '</div>';

    if (pv && pv.kind === 'xlsx_unsupported') {
      body += '<div class="card"><p class="notice">' + esc(pv.message) + '</p></div>';
    } else if (pv) {
      body += importMappingHtml(pv);
    }

    if (result) {
      body += '<div class="card"><div class="card-head"><h2>导入结果</h2></div>' +
        '<p>成功导入 <b>' + result.imported + '</b> 行' +
        (result.skipped ? '，跳过 <b>' + result.skipped + '</b> 行（姓名为空）' : '') +
        '；文件共 ' + result.total_rows + ' 行。' +
        (result.mapping_reused ? '（本次复用了上次的列映射）' : '') + '</p>' +
        '<p><a href="#/customers">去看客户列表 →</a></p></div>';
    }

    root.innerHTML = body;

    var fileEl = $('#impFile', root);
    var previewBtn = $('#impPreview', root);

    previewBtn.addEventListener('click', function () {
      var file = fileEl.files && fileEl.files[0];
      if (!file) { toast('先选一个 CSV 文件', true); return; }
      var fd = new FormData();
      fd.append('file', file);
      previewBtn.disabled = true;
      previewBtn.textContent = '上传中…';
      state.import.result = null;
      api('/import/preview', { method: 'POST', body: fd }).then(function (res) {
        state.import.preview = res;
        if (res.kind === 'xlsx_unsupported') {
          toast('Excel 需要先另存为 CSV', true);
        } else {
          toast('解析成功，共 ' + (res.total_rows || 0) + ' 行');
        }
        return render();
      }).catch(function (err) {
        toast(err.message, true);
        previewBtn.disabled = false;
        previewBtn.textContent = '上传并预览';
      });
    });

    var useLast = $('#useLastMapping', root);
    if (useLast) {
      useLast.addEventListener('click', function () {
        var last = (state.import.preview && state.import.preview.last_mapping) || {};
        $$('select[data-imp-header]', root).forEach(function (sel) {
          var header = sel.getAttribute('data-imp-header');
          sel.value = last[header] || '';
        });
        toast('已套用上次映射');
      });
    }

    var commitBtn = $('#impCommit', root);
    if (commitBtn) {
      commitBtn.addEventListener('click', function () {
        var preview = state.import.preview;
        if (!preview || !preview.file_ref) { toast('先上传预览', true); return; }
        var mapping = {};
        $$('select[data-imp-header]', root).forEach(function (sel) {
          if (sel.value) { mapping[sel.getAttribute('data-imp-header')] = sel.value; }
        });
        var mapped = Object.keys(mapping).map(function (k) { return mapping[k]; });
        if (mapped.indexOf('name') < 0) { toast('必须把某一列映射到「姓名」', true); return; }

        commitBtn.disabled = true;
        commitBtn.textContent = '导入中…';
        api('/import/commit', {
          method: 'POST',
          body: { file_ref: preview.file_ref, column_mapping: mapping, source_name: preview.file_name }
        }).then(function (res) {
          state.import.preview = null;
          state.import.result = res;
          invalidateCustomerIndex();
          toast('导入完成：' + res.imported + ' 行');
          return render();
        }).catch(function (err) {
          toast(err.message, true);
          commitBtn.disabled = false;
          commitBtn.textContent = '确认导入';
        });
      });
    }
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
