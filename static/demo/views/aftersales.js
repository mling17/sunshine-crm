/* ============================================================================
 * 售后（Demo 版，覆盖正式版 views/aftersales.js）
 * 2026-10-31 定稿：
 *   · **不再有「新建售后单」按钮**，售后单只能从订单页（已完成状态）生成
 *   · 售后单也要能跟进（履历 + 记一条）
 *   · 详情关联订单，可点回去
 * ==========================================================================*/

function aftersaleOrderNo(orderId) {
  var o = (window.DEMO.orders || []).filter(function (x) { return x.id === orderId; })[0];
  return o ? o.order_no : '—';
}

/* ---------------- 售后列表 ---------------- */
function viewAftersales(root, route) {
  var st = (route && route.query.get('status')) || '';
  var tabs = [['', '全部']].concat([
    ['pending', '待处理'], ['processing', '处理中'], ['done', '已完成'], ['rejected', '已拒绝']
  ]);
  var tabHtml = tabs.map(function (t) {
    return '<button type="button" class="tab-btn' + (st === t[0] ? ' active' : '') +
      '" data-status="' + t[0] + '">' + t[1] + '</button>';
  }).join('');

  var list = (window.DEMO.aftersales || []).filter(function (a) { return !st || a.status === st; })
    .sort(function (a, b) { return a.created_at < b.created_at ? 1 : -1; });

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head"><h2>售后 <span class="badge muted">' + list.length + '</span></h2>' +
        '<span class="small muted">售后单从「订单 → 已完成 → 添加售后」生成</span></div>' +
      '<div class="tabs">' + tabHtml + '</div>' +
    '</div>' +
    '<div class="card">' +
      dataTable([
        { title: '售后单号', nowrap: true, render: function (a) {
            return '<a href="#/aftersales/' + a.id + '">' + esc(a.no) + '</a>';
          } },
        { title: '类型', nowrap: true, render: function (a) {
            return esc(aftersaleTypeLabel(a.type, a.type_other));
          } },
        { title: '订单', nowrap: true, render: function (a) {
            return '<a href="#/orders/' + a.order_id + '">' + esc(aftersaleOrderNo(a.order_id)) + '</a>';
          } },
        { title: '客户', render: function (a) { return esc(orderCustomerName(a.customer_id)); } },
        { title: '问题', render: function (a) { return esc(String(a.description || '').slice(0, 22)); } },
        { title: '状态', nowrap: true, render: function (a) {
            var cls = a.status === 'done' ? 'ok' : a.status === 'rejected' ? 'danger' : 'warn';
            return '<span class="badge ' + cls + '">' + esc(AFTERSALE_STATUS_LABEL[a.status] || a.status) + '</span>';
          } },
        { title: '创建时间', nowrap: true, render: function (a) { return fmtDateTime(a.created_at).slice(0, 10); } },
        { title: '操作', nowrap: true, render: function (a) {
            return opButtons([{ op: 'view', arg: a.id, label: '跟进' }]);
          } }
      ], list, '还没有售后单：到已完成订单里点「添加售后」') +
    '</div>';

  $$('.tab-btn', root).forEach(function (b) {
    b.addEventListener('click', function () {
      var s = b.getAttribute('data-status');
      navigate('#/aftersales' + (s ? '?status=' + s : ''));
    });
  });
  bindOps(root, { view: function (id) { navigate('#/aftersales/' + id); } });
}

/* ---------------- 售后详情（含跟进履历） ---------------- */
function viewAftersaleDetail(root, rawId) {
  var a = (window.DEMO.aftersales || []).filter(function (x) { return x.id === Number(rawId); })[0];
  if (!a) { root.innerHTML = '<div class="card">售后单不存在，<a href="#/aftersales">回售后列表</a></div>'; return; }

  var records = (window.DEMO.aftersaleFollows || [])
    .filter(function (f) { return f.aftersale_id === a.id; })
    .map(function (f) {
      return {
        at: f.created_at,
        type: f.isStatus ? 'stage' : 'follow',
        content: f.content,
        next_date: f.next_date,
        method: f.isStatus ? null : f.method,
        files: f.files || []
      };
    });

  /* 2026-10-31：不再需要「开始处理」——加了跟进记录就自动进入处理中 */
  var ops = [];
  if (a.status === 'pending') {
    ops.push('<button type="button" class="btn btn-sm" id="asReject">拒绝</button>');
    ops.push('<span class="small muted">记一条跟进后会自动进入「处理中」</span>');
  } else if (a.status === 'processing') {
    ops.push('<button type="button" class="btn btn-sm btn-primary" id="asFinish">标记完成</button>');
  }

  renderEntityFollowPage(root, {
    backHash: '#/aftersales',
    backLabel: '售后',
    title: a.no,
    badgesHtml: '<span class="badge ' + (a.status === 'done' ? 'ok' : a.status === 'rejected' ? 'danger' : 'warn') + '">' +
      esc(AFTERSALE_STATUS_LABEL[a.status] || a.status) + '</span>',
    infoHtml: infoGrid([
      ['关联订单', '<a href="#/orders/' + a.order_id + '">' + esc(aftersaleOrderNo(a.order_id)) + ' ›</a>', true],
      ['客户', '<a href="#/customers/' + a.customer_id + '">' + esc(orderCustomerName(a.customer_id)) + '</a>', true],
      ['类型', aftersaleTypeLabel(a.type, a.type_other)],
      ['状态', AFTERSALE_STATUS_LABEL[a.status] || a.status],
      ['创建时间', fmtDateTime(a.created_at)],
      ['完成时间', a.closed_at ? fmtDateTime(a.closed_at) : '—'],
      ['问题描述', a.description],
      ['处理结果', a.result]
    ]),
    actionsHtml: ops.join(''),
    placeholder: '和客户沟通了什么？处理到哪一步了？',
    records: records,
    onSubmit: function (p) {
      (window.DEMO.aftersaleFollows = window.DEMO.aftersaleFollows || []).push({
        aftersale_id: a.id, method: p.method, content: p.content, next_date: p.next_date,
        created_at: new Date().toISOString().slice(0, 19), files: p.files
      });
      /* 2026-10-31：售后一旦有了跟进记录，自动进入「处理中」，直到手动标记完成 */
      if (a.status === 'pending') {
        a.status = 'processing';
        a.updated_at = new Date().toISOString().slice(0, 19);
        addStatusLog('状态变更：待处理 → 处理中（已记录跟进）');
      }
      toast('已记录跟进' + (a.status === 'processing' ? '，售后自动进入「处理中」' : ''));
      render();
    }
  });

  /* 状态变更统一写一条履历 */
  function addStatusLog(text) {
    (window.DEMO.aftersaleFollows = window.DEMO.aftersaleFollows || []).push({
      aftersale_id: a.id,
      method: 'phone',
      content: text,
      next_date: null,
      created_at: new Date().toISOString().slice(0, 19),
      files: [],
      isStatus: true
    });
  }

  var start = $('#asStart', root);
  if (start) {
    start.addEventListener('click', function () {
      a.status = 'processing';
      a.updated_at = new Date().toISOString().slice(0, 19);
      addStatusLog('状态变更：待处理 → 处理中');
      toast('已开始处理');
      render();
    });
  }
  var finish = $('#asFinish', root);
  if (finish) {
    finish.addEventListener('click', function () {
      a.status = 'done';
      a.closed_at = new Date().toISOString().slice(0, 19);
      a.result = a.result || '已处理完成（演示）';
      addStatusLog('状态变更：处理中 → 已完成' + (a.result ? '（' + a.result + '）' : ''));
      toast('售后已完成');
      render();
    });
  }
  var reject = $('#asReject', root);
  if (reject) {
    reject.addEventListener('click', function () {
      a.status = 'rejected';
      a.reject_reason = a.reject_reason || '不符合售后条件（演示）';
      addStatusLog('状态变更：待处理 → 已拒绝（' + a.reject_reason + '）');
      toast('已拒绝');
      render();
    });
  }
}