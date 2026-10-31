/* ============================================================================
 * 订单（Demo 版，覆盖正式版 views/orders.js）
 * 2026-10-31 定稿：
 *   · 订单详情要**关联商机**（能点回去）
 *   · 订单状态到「已完成」才允许**添加售后**；售后单从订单页生成
 *   · 金额 = 押金 + 尾款；物流方式 包邮/代办/自提 + 物流费用；显示收货地址
 * ==========================================================================*/

var ORDER_NEXT = {
  pending_payment: { next: 'deposit_paid', label: '收押金' },
  deposit_paid: { next: 'producing', label: '开始生产' },
  producing: { next: 'balance_paid', label: '收尾款' },
  balance_paid: { next: 'ready_to_ship', label: '备货完成' },
  ready_to_ship: { next: 'shipped', label: '发货' },
  shipped: { next: 'completed', label: '确认收货' },
  completed: null
};

function orderCustomerName(id) {
  var c = (window.DEMO.customers || []).filter(function (x) { return x.id === id; })[0];
  return c ? c.name : ('客户 #' + id);
}

/* ---------------- 订单列表 ---------------- */
function viewOrders(root, route) {
  var st = (route && route.query.get('status')) || '';
  var tabs = [['', '全部']].concat(ORDER_STATUS.map(function (p) { return [p[0], p[1]]; }));
  var tabHtml = tabs.map(function (t) {
    return '<button type="button" class="tab-btn' + (st === t[0] ? ' active' : '') +
      '" data-status="' + t[0] + '">' + t[1] + '</button>';
  }).join('');

  var list = (window.DEMO.orders || []).filter(function (o) { return !st || o.status === st; })
    .sort(function (a, b) { return (a.created_at < b.created_at ? 1 : -1); });

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head"><h2>订单 <span class="badge muted">' + list.length + '</span></h2>' +
        '<span class="small muted">订单由商机「生成订单」产生</span></div>' +
      '<div class="tabs">' + tabHtml + '</div>' +
    '</div>' +
    '<div class="card">' +
      dataTable([
        { title: '订单号', nowrap: true, render: function (o) {
            return '<a href="#/orders/' + o.id + '">' + esc(o.order_no) + '</a>';
          } },
        { title: '客户', render: function (o) { return esc(orderCustomerName(o.customer_id)); } },
        { title: '产品', render: function (o) { return esc([o.product_type, o.model].filter(Boolean).join(' ')); }, nowrap: true },
        { title: '总额', align: 'right', nowrap: true, render: function (o) { return money(o.amount); } },
        { title: '押金', align: 'right', nowrap: true, render: function (o) { return money(o.deposit); } },
        { title: '尾款', align: 'right', nowrap: true, render: function (o) { return money(o.balance); } },
        { title: '物流', nowrap: true, render: function (o) {
            return esc(o.logistics_mode_label || '') +
              (o.logistics_fee ? '<div class="small muted">运费 ' + money(o.logistics_fee) + '</div>' : '');
          } },
        { title: '状态', render: function (o) {
            return '<span class="badge ' + (o.status === 'completed' ? 'ok' : o.status === 'pending_payment' ? 'warn' : 'muted') + '">' +
              esc(ORDER_STATUS_LABEL[o.status] || o.status) + '</span>';
          } },
        { title: '创建时间', nowrap: true, render: function (o) { return fmtDateTime(o.created_at).slice(0, 10); } },
        { title: '操作', nowrap: true, render: function (o) {
            return opButtons([{ op: 'view', arg: o.id, label: '详情' }]);
          } }
      ], list, '还没有订单：商机里点「生成订单」才会产生') +
    '</div>';

  $$('.tab-btn', root).forEach(function (b) {
    b.addEventListener('click', function () {
      var s = b.getAttribute('data-status');
      navigate('#/orders' + (s ? '?status=' + s : ''));
    });
  });
  bindOps(root, { view: function (id) { navigate('#/orders/' + id); } });
}

/* ---------------- 订单详情 ---------------- */
function viewOrderDetail(root, rawId) {
  var o = (window.DEMO.orders || []).filter(function (x) { return x.id === Number(rawId); })[0];
  if (!o) { root.innerHTML = '<div class="card">订单不存在，<a href="#/orders">回订单列表</a></div>'; return; }

  var deal = (window.DEMO.deals || []).filter(function (d) { return d.id === o.deal_id; })[0];
  var aftersales = (window.DEMO.aftersales || []).filter(function (a) { return a.order_id === o.id; });
  var paid = Number(o.paid_amount) || 0;
  var unpaid = Math.max(0, Number(o.amount) - paid);
  var stepIdx = ORDER_STATUS.map(function (p) { return p[0]; }).indexOf(o.status);

  /* 进度条 */
  var progress = '<div class="progress-bar">' + ORDER_STATUS.map(function (p, i) {
    var cls = 'step' + (i === stepIdx ? ' active' : (i < stepIdx ? ' done' : ''));
    return '<div class="' + cls + '"><div class="step-label">' + p[1] + '</div></div>';
  }).join('') + '</div>';

  var aftersaleHtml = aftersales.length ? aftersales.map(function (a) {
    return '<div class="item"><div class="item-main">' +
      '<div class="item-title"><a href="#/aftersales/' + a.id + '">' + esc(a.no) + '</a>' +
        '<span class="badge ' + (a.status === 'done' ? 'ok' : a.status === 'rejected' ? 'danger' : 'warn') + '">' +
        esc(AFTERSALE_STATUS_LABEL[a.status] || a.status) + '</span></div>' +
      '<div class="item-sub small muted">' + esc(AFTERSALE_TYPE_LABEL[a.type] || a.type) + ' · ' +
        fmtDateTime(a.created_at).slice(0, 10) + ' · ' + esc(a.description.slice(0, 24)) + '</div>' +
      '</div><div class="item-side muted">›</div></div>';
  }).join('') : '<p class="empty">暂无售后单</p>';

  var next = ORDER_NEXT[o.status];
  var actionBtns = '';
  if (next) {
    actionBtns += '<button type="button" class="btn btn-primary" id="btnOrderNext">' + next.label + '</button>';
  }
  if (o.status === 'completed') {
    actionBtns += '<button type="button" class="btn" id="btnAddAftersale">＋ 添加售后</button>';
  } else {
    actionBtns += '<button type="button" class="btn" disabled title="订单完成后才能申请售后">添加售后</button>';
  }

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head"><h2><a class="crumb" href="#/orders">‹ 订单</a> / ' + esc(o.order_no) + '</h2>' +
        '<span class="badge ' + (o.status === 'completed' ? 'ok' : 'warn') + '">' +
          esc(ORDER_STATUS_LABEL[o.status] || o.status) + '</span></div>' +
      infoGrid([
        ['客户', '<a href="#/customers/' + o.customer_id + '">' + esc(orderCustomerName(o.customer_id)) + '</a>', true],
        ['关联商机', deal
          ? '<button type="button" class="btn-link" id="btnDealPreview">' + esc(dealTitle(deal)) + ' ›</button>'
          : '—', true],
        ['产品 / 型号', [o.product_type, o.model, o.spec].filter(Boolean).join(' ')],
        ['物流方式', o.logistics_mode_label],
        ['承运公司', o.carrier_name || '不指定'],
        ['运单号', o.tracking_number || '待补'],
        ['创建时间', fmtDateTime(o.created_at)],
        ['完成时间', o.completed_at ? fmtDateTime(o.completed_at) : '—']
      ]) +
      progress +
      '<div class="form-actions" style="justify-content:flex-start;flex-wrap:wrap">' + actionBtns + '</div>' +
    '</div>' +
    '<div class="card">' +
      '<div class="card-head"><h2>收款</h2></div>' +
      '<div class="grid-kpi">' +
        '<div class="kpi"><div class="label">订单总额</div><div class="value">' + money(o.amount) + '</div></div>' +
        '<div class="kpi"><div class="label">押金</div><div class="value">' + money(o.deposit) + '</div></div>' +
        '<div class="kpi"><div class="label">尾款</div><div class="value">' + money(o.balance) + '</div></div>' +
        '<div class="kpi"><div class="label">已收</div><div class="value">' + money(paid) + '</div></div>' +
        '<div class="kpi' + (unpaid ? ' kpi-danger' : '') + '"><div class="label">未收</div>' +
          '<div class="value">' + money(unpaid) + '</div></div>' +
      '</div>' +
    '</div>' +
    '<div class="card">' +
      '<div class="card-head"><h2>收货 / 配送</h2>' +
        '<button type="button" class="btn btn-sm" id="btnEditAddr">修改收货信息</button></div>' +
      infoGrid([
        ['收件人', o.receiver_name],
        ['收件电话', o.receiver_phone],
        ['收件地址', o.receiver_address],
        ['物流费用', o.logistics_fee ? money(o.logistics_fee) : '—']
      ]) +
    '</div>' +
    '<div class="card">' +
      '<div class="card-head"><h2>售后单（' + aftersales.length + '）</h2>' +
        (o.status === 'completed'
          ? '<button type="button" class="btn btn-sm" id="btnAddAftersale2">＋ 添加售后</button>'
          : '<span class="small muted">订单完成后可申请</span>') +
      '</div>' + aftersaleHtml +
    '</div>';

  var previewBtn = $('#btnDealPreview', root);
  if (previewBtn && deal) {
    previewBtn.addEventListener('click', function () { openDealPreviewModal(deal.id); });
  }
  var nextBtn = $('#btnOrderNext', root);
  if (nextBtn) {
    nextBtn.addEventListener('click', function () { advanceOrder(o); });
  }
  ['#btnAddAftersale', '#btnAddAftersale2'].forEach(function (sel) {
    var b = $(sel, root);
    if (b) { b.addEventListener('click', function () { openAftersaleModal(o); }); }
  });
  var editAddr = $('#btnEditAddr', root);
  if (editAddr) {
    editAddr.addEventListener('click', function () {
      toast('演示环境：真实版本可从客户地址簿重选或新建');
      openAddressPicker(o);
    });
  }
}

/* 状态推进（演示：直接改内存） */
function advanceOrder(o) {
  var step = ORDER_NEXT[o.status];
  if (!step) { return; }
  var nowIso = new Date().toISOString().slice(0, 19);

  if (step.next === 'deposit_paid') {
    o.paid_amount = Number(o.deposit) || 0;
  } else if (step.next === 'balance_paid') {
    o.paid_amount = Number(o.amount) || 0;
  } else if (step.next === 'shipped') {
    if (!o.tracking_number) { o.tracking_number = 'SF' + Date.now().toString().slice(-10); }
  } else if (step.next === 'completed') {
    o.completed_at = nowIso;
  }
  o.status = step.next;
  o.updated_at = nowIso;
  toast('订单已推进到「' + (ORDER_STATUS_LABEL[o.status] || o.status) + '」（演示）');
  render();
}

/* 从订单生成售后单（订单完成后才允许） */
function openAftersaleModal(o) {
  if (o.status !== 'completed') { toast('订单完成后才能申请售后', true); return; }

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content">' +
      '<div class="modal-header"><h3>添加售后 · ' + esc(o.order_no) + '</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="asFormEl" autocomplete="off">' +
        '<div class="row-2">' +
          '<div class="field"><label>售后类型 *</label>' +
            '<select name="type">' +
              ['repair|维修', 'exchange|换货', 'return|退货', 'complaint|投诉', 'other|其他']
                .map(function (x) { var kv = x.split('|'); return '<option value="' + kv[0] + '">' + kv[1] + '</option>'; }).join('') +
            '</select></div>' +
          '<div class="field"><label>其它说明（选"其他"填）</label>' +
            '<input name="type_other" maxlength="64"></div>' +
        '</div>' +
        '<div class="field"><label>问题描述 *</label>' +
          '<textarea name="description" rows="3" maxlength="1000" required placeholder="如：天窗关不严、下雨渗水"></textarea></div>' +
        '<div class="form-actions">' +
          '<button type="button" class="btn modal-cancel">取消</button>' +
          '<button type="submit" class="btn btn-primary">提交售后</button>' +
        '</div>' +
      '</form>' +
    '</div>';
  document.body.appendChild(modal);
  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  $('.modal-close', modal).addEventListener('click', close);
  $('.modal-cancel', modal).addEventListener('click', close);

  $('#asFormEl', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var desc = String(f.description.value || '').trim();
    if (!desc) { toast('问题描述必填', true); return; }
    var now = new Date();
    var ymd = now.getFullYear() + '' + ('0' + (now.getMonth() + 1)).slice(-2) + ('0' + now.getDate()).slice(-2);
    var no = 'AS-' + ymd + '-' + String((window.DEMO.aftersales || []).length + 1).padStart(3, '0');
    var as = {
      id: Math.max.apply(null, (window.DEMO.aftersales || []).map(function (x) { return x.id; }).concat([0])) + 1,
      no: no,
      order_id: o.id,
      customer_id: o.customer_id,
      type: f.type.value,
      type_other: String(f.type_other.value || '').trim() || null,
      description: desc,
      status: 'pending',
      created_at: new Date().toISOString().slice(0, 19),
      updated_at: new Date().toISOString().slice(0, 19)
    };
    window.DEMO.aftersales.push(as);
    close();
    toast('售后单已生成：' + no);
    navigate('#/aftersales/' + as.id);
  });
}

/* 修改收货信息：从客户地址簿重选 */
function openAddressPicker(o) {
  var addrs = (window.DEMO.addresses || []).filter(function (a) { return a.customer_id === o.customer_id; });
  if (!addrs.length) { toast('该客户还没有历史地址', true); return; }
  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content">' +
      '<div class="modal-header"><h3>选择收货地址</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<div class="dict-list">' + addrs.map(function (a) {
        return '<label class="dict-row" style="cursor:pointer">' +
          '<div class="dict-row-main"><div class="dict-row-name">' + esc(a.label) + '</div>' +
          '<div class="small muted">' + esc(a.receiver_name) + ' · ' + esc(a.phone) + ' · ' + esc(a.address) + '</div></div>' +
          '<input type="radio" name="addr" value="' + a.id + '"' + (String(a.id) === String(o.address_id) ? ' checked' : '') + '>' +
          '</label>';
      }).join('') + '</div>' +
      '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="button" class="btn btn-primary" id="addrOk">确定</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(modal);
  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  $('.modal-close', modal).addEventListener('click', close);
  $('.modal-cancel', modal).addEventListener('click', close);
  $('#addrOk', modal).addEventListener('click', function () {
    var sel = modal.querySelector('input[name="addr"]:checked');
    if (!sel) { toast('请选一个地址', true); return; }
    var a = addrs.filter(function (x) { return String(x.id) === sel.value; })[0];
    o.address_id = a.id;
    o.receiver_name = a.receiver_name;
    o.receiver_phone = a.phone;
    o.receiver_address = a.address;
    close();
    toast('收货地址已更换（演示）');
    render();
  });
}

/* 商机预览（模态框，不跳页） */
function openDealPreviewModal(dealId) {
  var d = (window.DEMO.deals || []).filter(function (x) { return x.id === Number(dealId); })[0];
  if (!d) { return; }
  var logs = ((window.DEMO.dealLogs || {})[d.id] || []).slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; });
  var records = (window.DEMO.followups || []).filter(function (f) { return f.deal_id === d.id; })
    .map(function (f) {
      return { at: f.created_at, type: 'follow', content: f.content, next_date: f.next_date, method: f.method, files: [] };
    })
    .concat(logs.map(function (g) { return { at: g.at, type: g.type, content: g.text, files: g.files || [] }; }));

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content wide">' +
      '<div class="modal-header"><h3>商机 · ' + esc(customerNameOf(d.customer_id)) + '</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<div class="modal-body">' +
        '<div class="badge-row"><span class="badge ' + (d.stage === 'won' ? 'ok' : 'warn') + '">' +
          esc(STAGE_LABEL[d.stage] || d.stage) + '</span>' +
          (d.locked ? '<span class="badge muted">已下单</span>' : '') + '</div>' +
        infoGrid([
          ['产品类型', d.product_type], ['型号', d.model],
          ['手动/电动', DRIVE_LABEL[d.drive_type] || '—'],
          ['尺寸', d.size], ['金额', money(d.amount), true],
          ['备注', d.note]
        ]) +
        '<p class="small muted" style="margin:14px 0 6px">跟进履历（' + records.length + '）</p>' +
        timelineHtml(records) +
      '</div>' +
      '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">关闭</button>' +
        '<a class="btn btn-primary" href="#/deals/' + d.id + '">进入商机跟进页</a>' +
      '</div>' +
    '</div>';
  document.body.appendChild(modal);
  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  $('.modal-close', modal).addEventListener('click', close);
  $('.modal-cancel', modal).addEventListener('click', close);
}
