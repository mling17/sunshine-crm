/* ============================================================================
 * 商机（Demo 版，覆盖正式版 views/deals.js）
 * 用户 2026-10-31 定稿：
 *   · 列表展示所有商机，每条可「跟进」
 *   · 跟进 = 新页面：头部商机基本信息 + 下方跟进履历（可上传附件）
 *   · 商机基本信息变动（尺寸/金额等）**自动生成一条履历**
 *   · 客户认可方案 → 「生成订单」按钮 → 模态框表单（继承商机信息 + 物流/收件人）
 *   · 生成订单后商机**不可修改**
 * ==========================================================================*/

function dealTitle(d) {
  return [d.product_type, d.model, d.size].filter(Boolean).join(' ') || ('商机 #' + d.id);
}

function customerNameOf(id) {
  var c = (window.DEMO.customers || []).filter(function (x) { return x.id === id; })[0];
  return c ? c.name : ('客户 #' + id);
}

/* ---------------- 商机列表（表格） ---------------- */
function viewDeals(root, route) {
  var stage = (route && route.query.get('stage')) || '';
  var deals = (window.DEMO.deals || []).slice();

  var tabs = [['', '全部']].concat(STAGES.map(function (p) { return [p[0], p[1]]; }));
  var tabHtml = tabs.map(function (t) {
    return '<button type="button" class="tab-btn' + (stage === t[0] ? ' active' : '') +
      '" data-stage="' + t[0] + '">' + t[1] + '</button>';
  }).join('');

  var filtered = deals.filter(function (d) { return !stage || d.stage === stage; })
    .sort(function (a, b) { return (a.updated_at || a.created_at) < (b.updated_at || b.created_at) ? 1 : -1; });

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head"><h2>商机 <span class="badge muted">' + filtered.length + '</span></h2>' +
        '<span class="small muted">由线索 / 客户转来，不在此新建</span></div>' +
      '<div class="tabs">' + tabHtml + '</div>' +
    '</div>' +
    '<div class="card">' +
      dataTable([
        { title: '客户', render: function (d) {
            return '<a href="#/deals/' + d.id + '">' + esc(customerNameOf(d.customer_id)) + '</a>';
          } },
        { title: '产品', render: function (d) { return esc(d.product_type || '—'); } },
        { title: '型号', render: function (d) { return esc(d.model || '—'); }, nowrap: true },
        { title: '手动/电动', render: function (d) {
            return '<span class="badge ' + (d.drive_type === 'electric' ? 'ok' : 'muted') + '">' +
              (DRIVE_LABEL[d.drive_type] || '—') + '</span>';
          } },
        { title: '尺寸', render: function (d) { return esc(d.size || '—'); }, nowrap: true },
        { title: '金额', render: function (d) { return money(d.amount); }, align: 'right', nowrap: true },
        { title: '阶段', render: function (d) {
            return '<span class="badge ' + (d.stage === 'won' ? 'ok' : d.stage === 'lost' ? 'danger' : 'warn') + '">' +
              esc(STAGE_LABEL[d.stage] || d.stage) + '</span>';
          } },
        { title: '更新时间', render: function (d) { return fmtDateTime(d.updated_at || d.created_at).slice(0, 10); }, nowrap: true },
        { title: '操作', nowrap: true, render: function (d) {
            return opButtons([
              { op: 'follow', arg: d.id, label: '跟进' },
              d.locked
                ? { op: 'order', arg: d.id, label: '已下单', disabled: true, tip: '已生成订单，不能重复生成' }
                : { op: 'order', arg: d.id, label: '生成订单' }
            ]);
          } }
      ], filtered, '还没有商机：请到线索或客户里点「转商机」') +
    '</div>';

  $$('.tab-btn', root).forEach(function (b) {
    b.addEventListener('click', function () {
      navigate('#/deals' + (b.getAttribute('data-stage') ? '?stage=' + b.getAttribute('data-stage') : ''));
    });
  });
  bindOps(root, {
    follow: function (id) { navigate('#/deals/' + id); },
    order: function (id) { openOrderModal(id); }
  });
}

/* ---------------- 商机详情 = 跟进页 ---------------- */
function viewDealDetail(root, rawId) {
  var d = (window.DEMO.deals || []).filter(function (x) { return x.id === Number(rawId); })[0];
  if (!d) { root.innerHTML = '<div class="card">商机不存在，<a href="#/deals">回商机列表</a></div>'; return; }

  /* 履历 = 跟进记录 + 系统自动生成的变更/阶段/下单记录 */
  var records = (window.DEMO.followups || []).filter(function (f) { return f.deal_id === d.id; })
    .map(function (f) {
      return { at: f.created_at, type: 'follow', content: f.content, next_date: f.next_date, method: f.method, files: [] };
    });
  ((window.DEMO.dealLogs || {})[d.id] || []).forEach(function (g) {
    records.push({ at: g.at, type: g.type, content: g.text, files: g.files || [] });
  });

  var orderLink = d.order_id
    ? '<a class="badge ok" href="#/orders/' + d.order_id + '">已生成订单 ›</a>' : '';

  renderEntityFollowPage(root, {
    backHash: '#/deals',
    backLabel: '商机',
    title: customerNameOf(d.customer_id) + ' · ' + dealTitle(d),
    badgesHtml: '<span class="badge ' + (d.stage === 'won' ? 'ok' : 'warn') + '">' +
      esc(STAGE_LABEL[d.stage] || d.stage) + '</span>' + orderLink,
    infoHtml: infoGrid([
      ['客户', '<a href="#/customers/' + d.customer_id + '">' + esc(customerNameOf(d.customer_id)) + '</a>', true],
      ['产品类型', d.product_type],
      ['型号', d.model],
      ['手动/电动', DRIVE_LABEL[d.drive_type] || '—', true],
      ['尺寸', d.size],
      ['金额', money(d.amount), true],
      ['定金', money(d.deposit)],
      ['尾款', money(d.balance)],
      ['阶段', STAGE_LABEL[d.stage] || d.stage, true],
      ['创建时间', fmtDateTime(d.created_at)],
      ['成交时间', d.closed_at ? fmtDateTime(d.closed_at) : '—']
    ]),
    placeholder: '报了方案？客户对尺寸/价格什么反馈？下一步做什么？',
    actionsHtml:
      (d.locked
        ? '<button type="button" class="btn btn-sm" disabled title="已生成订单，商机不可修改">编辑商机</button>' +
          '<a class="btn btn-sm" href="#/orders/' + d.order_id + '">查看订单</a>'
        : '<button type="button" class="btn btn-sm" id="dealEdit">编辑商机</button>' +
          '<button type="button" class="btn btn-sm btn-primary" id="dealToOrder">生成订单</button>') +
      '<span class="small muted">' + (d.locked ? '已生成订单，商机锁定' : '客户认可方案后再生成订单') + '</span>',
    records: records,
    onSubmit: function (p) {
      (window.DEMO.followups || []).push({
        id: Date.now(), object_type: 'deal', object_id: d.id, customer_id: d.customer_id, deal_id: d.id,
        method: p.method, content: p.content, next_date: p.next_date,
        created_at: new Date().toISOString().slice(0, 19)
      });
      toast('已记录跟进（附件：' + (p.files.length || 0) + ' 个）');
      render();
    }
  });

  var editBtn = $('#dealEdit', root);
  if (editBtn) { editBtn.addEventListener('click', function () { openDealForm(d.id); }); }
  var orderBtn = $('#dealToOrder', root);
  if (orderBtn) { orderBtn.addEventListener('click', function () { openOrderModal(d.id); }); }
}

/* ---------------- 转商机：新建商机页面 ---------------- */
function viewDealNew(root, route) {
  var leadId = Number(route.query.get('lead') || 0);
  var custId = Number(route.query.get('customer') || 0);
  var lead = leadId ? (window.DEMO.leads || []).filter(function (x) { return x.id === leadId; })[0] : null;
  var cust = custId ? (window.DEMO.customers || []).filter(function (x) { return x.id === custId; })[0] : null;

  var fromName = lead ? lead.name + '（线索）' : (cust ? cust.name + '（客户）' : '—');
  if (!lead && !cust) {
    root.innerHTML = '<div class="card">缺少来源，请从线索或客户里点「转商机」，' +
      '<a href="#/leads">回线索池</a></div>';
    return;
  }

  var models = (window.DEMO.models || []).slice();

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head"><h2><a class="crumb" href="' + (lead ? '#/leads' : '#/customers') + '">‹ 返回</a> / 转商机</h2>' +
        '<span class="badge muted">来源：' + esc(fromName) + '</span></div>' +
      '<form id="dealNewForm" autocomplete="off">' +
        '<div class="row-2">' +
          '<div class="field"><label>产品类型</label>' +
            '<select name="product_type" id="dpType">' +
              (window.DEMO.dicts.filter(function (x) { return x.code === 'product_type'; })[0].items || [])
                .map(function (i) { return '<option value="' + esc(i.label) + '">' + esc(i.label) + '</option>'; }).join('') +
            '</select></div>' +
          '<div class="field"><label>手动 / 电动 *</label>' +
            '<select name="drive_type">' +
              DRIVE_TYPE.map(function (p) { return '<option value="' + p[0] + '"' + (p[0] === 'electric' ? ' selected' : '') + '>' + p[1] + '</option>'; }).join('') +
            '</select></div>' +
        '</div>' +
        '<div class="field"><label>产品型号（下拉，可在数据字典维护）*</label>' +
          '<select name="model" id="dpModel">' +
            models.map(function (m) {
              return '<option value="' + esc(m.key) + '" data-size="' + esc((m.label.match(/\d+×\d+/) || [''])[0]) + '">' +
                esc(m.label) + '</option>';
            }).join('') +
          '</select></div>' +
        '<div class="row-3">' +
          '<div class="field"><label>尺寸（宽×高 mm）*</label>' +
            '<input name="size" id="dpSize" required maxlength="32" placeholder="1200×2400"></div>' +
          '<div class="field"><label>金额 *</label>' +
            '<input name="amount" type="number" min="0" step="0.01" required placeholder="12000"></div>' +
          '<div class="field"><label>阶段</label>' +
            '<select name="stage">' +
              STAGES.filter(function (p) { return p[0] !== 'lost'; })
                .map(function (p) { return '<option value="' + p[0] + '"' + (p[0] === 'quote' ? ' selected' : '') + '>' + p[1] + '</option>'; }).join('') +
            '</select></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>定金</label><input name="deposit" type="number" min="0" step="0.01" placeholder="0"></div>' +
          '<div class="field"><label>尾款</label><input name="balance" type="number" min="0" step="0.01" placeholder="0"></div>' +
        '</div>' +
        '<p class="small muted">定金 + 尾款 = 金额（不等时系统只提示不拦截）</p>' +
        '<div class="form-actions">' +
          '<button type="button" class="btn" id="dpCancel">取消</button>' +
          '<button type="submit" class="btn btn-primary">创建商机</button>' +
        '</div>' +
      '</form>' +
    '</div>';

  /* 选型号自动带出尺寸 */
  var modelSel = $('#dpModel', root);
  function fillSize() {
    var opt = modelSel.options[modelSel.selectedIndex];
    var s = opt.getAttribute('data-size');
    if (s) { $('#dpSize', root).value = s; }
  }
  modelSel.addEventListener('change', fillSize);
  fillSize();

  $('#dpCancel', root).addEventListener('click', function () {
    navigate(lead ? '#/leads' : '#/customers');
  });

  $('#dealNewForm', root).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var amount = Number(f.amount.value || 0);
    if (!f.size.value.trim()) { toast('尺寸必填', true); return; }
    if (!(amount > 0)) { toast('金额必须大于 0', true); return; }

    /* 线索转商机 = 线索转客户 + 建商机 */
    var targetCustomerId = cust ? cust.id : null;
    if (lead && !lead.converted_customer_id) {
      var newCustId = Math.max.apply(null, (window.DEMO.customers || []).map(function (x) { return x.id; })) + 1;
      var nowIso = new Date().toISOString().slice(0, 19);
      window.DEMO.customers.push({
        id: newCustId, name: lead.name, customer_type: lead.lead_type,
        phone: lead.phone, wechat: lead.wechat, location: lead.location,
        note: lead.note, source: lead.source, source_other: lead.source_other,
        intent_level: lead.intent_level, company_name: lead.company_name,
        tags: lead.tags || [], created_at: nowIso, updated_at: nowIso,
        profile: {}, source_lead_id: lead.id
      });
      lead.converted_customer_id = newCustId;
      lead.status = 'converted';
      targetCustomerId = newCustId;
    } else if (lead) {
      targetCustomerId = lead.converted_customer_id;
    }

    var newDealId = Math.max.apply(null, (window.DEMO.deals || []).map(function (x) { return x.id; })) + 1;
    var nowIso2 = new Date().toISOString().slice(0, 19);
    var deal = {
      id: newDealId, customer_id: targetCustomerId,
      product_type: f.product_type.value, model: f.model.value, model_code: f.model.value,
      size: f.size.value.trim(), spec: f.size.value.trim(),
      drive_type: f.drive_type.value,
      amount: amount,
      deposit: Number(f.deposit.value || 0), balance: Number(f.balance.value || 0),
      stage: f.stage.value, closed_at: f.stage.value === 'won' ? nowIso2 : null,
      created_at: nowIso2, updated_at: nowIso2, order_id: null, locked: false
    };
    window.DEMO.deals.push(deal);
    window.DEMO.dealLogs[newDealId] = [{
      at: nowIso2, type: 'create',
      text: '创建商机：' + dealTitle(deal) + '，' + DRIVE_LABEL[deal.drive_type] + '，报价 ' + moneyRaw(amount) +
        (lead ? '（由线索「' + lead.name + '」转化）' : '')
    }];
    if (lead) {
      window.DEMO.leadFollows.push({
        lead_id: lead.id, method: 'online', content: '已转商机：' + dealTitle(deal) + '，报价 ' + moneyRaw(amount),
        next_date: null, created_at: nowIso2, files: []
      });
    }
    toast('商机已创建（演示：仅本次会话有效）');
    navigate('#/deals/' + newDealId);
  });
}

/* ---------------- 编辑商机（变更自动生成履历） ---------------- */
function openDealForm(id) {
  var d = (window.DEMO.deals || []).filter(function (x) { return x.id === Number(id); })[0];
  if (!d || d.locked) { toast('已生成订单，商机不可修改', true); return; }

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content wide">' +
      '<div class="modal-header"><h3>编辑商机 · ' + esc(customerNameOf(d.customer_id)) + '</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="dealFormEl" autocomplete="off">' +
        '<div class="row-2">' +
          '<div class="field"><label>产品类型</label><input name="product_type" value="' + esc(d.product_type || '') + '" maxlength="32"></div>' +
          '<div class="field"><label>手动 / 电动</label><select name="drive_type">' +
            DRIVE_TYPE.map(function (p) { return '<option value="' + p[0] + '"' + (d.drive_type === p[0] ? ' selected' : '') + '>' + p[1] + '</option>'; }).join('') +
          '</select></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>型号</label><select name="model">' +
            (window.DEMO.models || []).map(function (m) {
              return '<option value="' + esc(m.key) + '"' + (d.model === m.key ? ' selected' : '') + '>' + esc(m.label) + '</option>';
            }).join('') + '</select></div>' +
          '<div class="field"><label>尺寸</label><input name="size" value="' + esc(d.size || '') + '" maxlength="32"></div>' +
        '</div>' +
        '<div class="row-3">' +
          '<div class="field"><label>金额</label><input name="amount" type="number" min="0" step="0.01" value="' + (d.amount || 0) + '"></div>' +
          '<div class="field"><label>定金</label><input name="deposit" type="number" min="0" step="0.01" value="' + (d.deposit || 0) + '"></div>' +
          '<div class="field"><label>尾款</label><input name="balance" type="number" min="0" step="0.01" value="' + (d.balance || 0) + '"></div>' +
        '</div>' +
        '<div class="field"><label>阶段</label><select name="stage">' +
          STAGES.map(function (p) { return '<option value="' + p[0] + '"' + (d.stage === p[0] ? ' selected' : '') + '>' + p[1] + '</option>'; }).join('') +
        '</select></div>' +
        '<p class="small muted">保存后，凡有变化的字段都会自动生成一条「信息变更」履历。</p>' +
        '<div class="form-actions">' +
          '<button type="button" class="btn modal-cancel">取消</button>' +
          '<button type="submit" class="btn btn-primary">保存</button>' +
        '</div>' +
      '</form>' +
    '</div>';
  document.body.appendChild(modal);
  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  $('.modal-close', modal).addEventListener('click', close);
  $('.modal-cancel', modal).addEventListener('click', close);

  $('#dealFormEl', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var nowIso = new Date().toISOString().slice(0, 19);
    var changes = [];

    function cmp(label, oldV, newV, fmt) {
      if (String(oldV === null || oldV === undefined ? '' : oldV) === String(newV === null || newV === undefined ? '' : newV)) { return; }
      changes.push(label + '由 ' + (fmt ? fmt(oldV) : (oldV || '空')) + ' 改为 ' + (fmt ? fmt(newV) : (newV || '空')));
    }

    var nType = String(f.product_type.value || '').trim();
    var nModel = f.model.value;
    var nSize = String(f.size.value || '').trim();
    var nAmount = Number(f.amount.value || 0);
    var nDeposit = Number(f.deposit.value || 0);
    var nBalance = Number(f.balance.value || 0);
    var nStage = f.stage.value;
    var nDrive = f.drive_type.value;

    cmp('产品类型', d.product_type, nType);
    cmp('型号', d.model, nModel);
    cmp('尺寸', d.size, nSize);
    cmp('手动/电动', DRIVE_LABEL[d.drive_type], DRIVE_LABEL[nDrive]);
    cmp('金额', d.amount, nAmount, moneyRaw);
    cmp('定金', d.deposit, nDeposit, moneyRaw);
    cmp('尾款', d.balance, nBalance, moneyRaw);

    d.product_type = nType || d.product_type;
    d.model = nModel; d.model_code = nModel;
    d.size = nSize; d.spec = nSize;
    d.drive_type = nDrive;
    d.amount = nAmount; d.deposit = nDeposit; d.balance = nBalance;
    d.updated_at = nowIso;

    var logs = window.DEMO.dealLogs[d.id] = window.DEMO.dealLogs[d.id] || [];
    if (changes.length) {
      logs.push({ at: nowIso, type: 'change', text: changes.join('；') });
    }
    if (nStage !== d.stage) {
      logs.push({ at: nowIso, type: 'stage', text: '阶段推进：' + (STAGE_LABEL[d.stage] || d.stage) + ' → ' + (STAGE_LABEL[nStage] || nStage) });
      d.stage = nStage;
      if (nStage === 'won') { d.closed_at = nowIso; }
    }
    if (nDeposit + nBalance !== nAmount) {
      toast('提示：定金 + 尾款 ≠ 金额（已保存，不拦截）', true);
    } else {
      toast('已保存：' + changes.length + ' 项变更已记入履历');
    }
    close();
    render();
  });
}

/* ---------------- 生成订单（模态框，继承商机信息） ---------------- */
function openOrderModal(dealId) {
  var d = (window.DEMO.deals || []).filter(function (x) { return x.id === Number(dealId); })[0];
  if (!d) { return; }
  if (d.locked) { toast('该商机已生成订单', true); return; }
  var carriers = (window.DEMO.carriers || []).filter(function (c) { return c.is_active; });
  var cust = (window.DEMO.customers || []).filter(function (x) { return x.id === d.customer_id; })[0] || {};

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content wide">' +
      '<div class="modal-header"><h3>生成订单</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="orderFormEl" autocomplete="off">' +
        '<p class="small muted" style="margin-top:0">以下信息继承自商机最新信息，可在此确认</p>' +
        '<div class="row-2">' +
          '<div class="field"><label>客户</label><input value="' + esc(cust.name || '') + '" disabled></div>' +
          '<div class="field"><label>产品 / 型号</label><input value="' + esc([d.product_type, d.model].filter(Boolean).join(' ')) + '" disabled></div>' +
        '</div>' +
        '<div class="row-3">' +
          '<div class="field"><label>尺寸</label><input value="' + esc(d.size || '') + '" disabled></div>' +
          '<div class="field"><label>手动 / 电动</label><input value="' + esc(DRIVE_LABEL[d.drive_type] || '') + '" disabled></div>' +
          '<div class="field"><label>订单金额 *</label><input name="amount" type="number" min="0" step="0.01" value="' + (d.amount || 0) + '"></div>' +
        '</div>' +
        '<p class="small muted">配送信息（新填）</p>' +
        '<div class="row-2">' +
          '<div class="field"><label>物流方式 *</label><select name="logistics_mode" id="ofMode">' +
            '<option value="carrier" selected>物流公司</option><option value="self">自送</option></select></div>' +
          '<div class="field" id="ofCarrierWrap"><label>承运公司 *</label><select name="carrier_id">' +
            carriers.map(function (c) { return '<option value="' + c.id + '">' + esc(c.name) + '</option>'; }).join('') +
          '</select></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>收件人 *</label><input name="receiver_name" required maxlength="32" value="' + esc(cust.name || '') + '"></div>' +
          '<div class="field"><label>收件电话 *</label><input name="receiver_phone" required maxlength="32" value="' + esc(cust.phone || '') + '"></div>' +
        '</div>' +
        '<div class="field"><label>收件地址 *</label><input name="receiver_address" required maxlength="200" value="' + esc(cust.location || '') + '"></div>' +
        '<div class="field"><label>运单号（可后补）</label><input name="tracking_number" maxlength="64" placeholder="可留空"></div>' +
        '<div class="field"><label>备注</label><textarea name="note" rows="2" maxlength="300"></textarea></div>' +
        '<div class="notice small">生成订单后，该商机将锁定，不能再修改。</div>' +
        '<div class="form-actions">' +
          '<button type="button" class="btn modal-cancel">取消</button>' +
          '<button type="submit" class="btn btn-primary">确认生成订单</button>' +
        '</div>' +
      '</form>' +
    '</div>';
  document.body.appendChild(modal);
  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  $('.modal-close', modal).addEventListener('click', close);
  $('.modal-cancel', modal).addEventListener('click', close);

  $('#ofMode', modal).addEventListener('change', function (ev) {
    $('#ofCarrierWrap', modal).style.display = ev.target.value === 'self' ? 'none' : '';
  });

  $('#orderFormEl', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var mode = f.logistics_mode.value;
    var now = new Date();
    var ym = now.getFullYear() + '-' + ((now.getMonth() + 1) < 10 ? '0' : '') + (now.getMonth() + 1);
    var seq = String((window.DEMO.orders || []).length + 1).padStart(3, '0');
    var nowIso = new Date().toISOString().slice(0, 19);

    var order = {
      id: Math.max.apply(null, (window.DEMO.orders || []).map(function (x) { return x.id; })) + 1,
      order_no: 'SO-' + ym + '-' + seq,
      customer_id: d.customer_id, deal_id: d.id,
      product_type: d.product_type, model: d.model, spec: d.size,
      amount: Number(f.amount.value || 0), paid_amount: 0,
      status: 'pending_payment',
      logistics_mode: mode,
      logistics_mode_label: mode === 'self' ? '自送' : '物流公司',
      carrier_id: mode === 'carrier' ? Number(f.carrier_id.value) : null,
      carrier_name: mode === 'carrier' ? f.carrier_id.options[f.carrier_id.selectedIndex].text : '',
      tracking_number: String(f.tracking_number.value || '').trim() || null,
      receiver_name: String(f.receiver_name.value || '').trim(),
      receiver_phone: String(f.receiver_phone.value || '').trim(),
      receiver_address: String(f.receiver_address.value || '').trim(),
      note: String(f.note.value || '').trim() || null,
      created_at: nowIso, updated_at: nowIso
    };
    window.DEMO.orders.push(order);

    /* 商机锁定 + 记为赢单 + 自动生成履历 */
    d.locked = true;
    d.order_id = order.id;
    d.stage = 'won';
    d.closed_at = nowIso;
    d.updated_at = nowIso;
    (window.DEMO.dealLogs[d.id] = window.DEMO.dealLogs[d.id] || []).push({
      at: nowIso, type: 'order',
      text: '生成订单 ' + order.order_no + '，金额 ' + moneyRaw(order.amount) +
        '，' + order.logistics_mode_label + (order.carrier_name ? '（' + order.carrier_name + '）' : '') +
        '，收件人 ' + order.receiver_name
    });

    /* 物流公司关联次数 +1 */
    if (order.carrier_id) {
      var car = (window.DEMO.carriers || []).filter(function (c) { return c.id === order.carrier_id; })[0];
      if (car) { car.used = (car.used || 0) + 1; }
    }

    close();
    toast('订单已生成：' + order.order_no + '（演示：仅本次会话有效）');
    navigate('#/orders/' + order.id);
  });
}