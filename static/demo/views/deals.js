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

function dealStageBadgeText(d) {
  return d.order_id ? '已生成订单' : (STAGE_LABEL[d.stage] || d.stage);
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
            return '<span class="badge ' + (d.order_id || d.stage === 'won' ? 'ok' : d.stage === 'lost' ? 'danger' : 'warn') + '">' +
              esc(dealStageBadgeText(d)) + '</span>';
          } },
        { title: '更新时间', render: function (d) { return fmtDateTime(d.updated_at || d.created_at).slice(0, 10); }, nowrap: true },
        { title: '操作', nowrap: true, render: function (d) {
            /* 2026-10-31 定稿：列表只留「跟进」，生成订单在跟进页里做 */
            return opButtons([{ op: 'follow', arg: d.id, label: '跟进' }]);
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

  var fuRows = (window.DEMO.followups || [])
    .filter(function (f) { return f.deal_id === d.id; })
    .map(function (f) { return { at: f.created_at, files: f.files || [] }; });
  var logRows = (((window.DEMO.dealLogs || {})[d.id]) || []).map(function (g) {
    return { at: g.at, files: g.files || [] };
  });
  var dealFiles = collectFiles(fuRows.concat(logRows));

  renderEntityFollowPage(root, {
    backHash: '#/deals',
    backLabel: '商机',
    title: customerNameOf(d.customer_id) + ' · ' + dealTitle(d),
    badgesHtml: '<span class="badge ' + (d.locked || d.stage === 'won' ? 'ok' : 'warn') + '">' +
      esc(dealStageBadgeText(d)) + '</span>' + orderLink,
    infoHtml: infoGrid([
      ['客户', '<a href="#/customers/' + d.customer_id + '">' + esc(customerNameOf(d.customer_id)) + '</a>', true],
      ['产品类型', d.product_type],
      ['型号', d.model],
      ['手动/电动', DRIVE_LABEL[d.drive_type] || '—', true],
      ['尺寸', d.size],
      ['金额', money(d.amount), true],
      ['定金', money(d.deposit)],
      ['尾款', money(d.balance)],
      ['阶段', dealStageBadgeText(d), true],
      ['创建时间', fmtDateTime(d.created_at)],
      ['成交时间', d.closed_at ? fmtDateTime(d.closed_at) : '—']
    ]),
    placeholder: '报了方案？客户对尺寸/价格什么反馈？下一步做什么？',
    canFollow: !d.locked,
    lockedText: d.locked ? '已生成订单，请在订单中跟进' : '',
    lockedButtonLabel: d.locked ? '已生成订单，请在订单中跟进' : '',
    extraHtml: filesCardHtml(dealFiles, '这个商机还没有上传图纸 / 报价单'),
    actionsHtml:
      (d.locked
        ? '<button type="button" class="btn btn-sm" disabled title="已生成订单，商机不可修改">编辑商机</button>' +
          '<a class="btn btn-sm" href="#/orders/' + d.order_id + '">查看订单</a>'
        : '<button type="button" class="btn btn-sm" id="dealEdit">编辑商机</button>' +
          (d.stage === 'won'
            ? '<button type="button" class="btn btn-sm btn-primary" id="dealToOrder">生成订单</button>'
            : '<button type="button" class="btn btn-sm" disabled title="先把阶段推进到「成交」">生成订单</button>')) +
      '<span class="small muted">' +
        (d.locked ? '已生成订单，商机锁定'
          : (d.stage === 'won' ? '已成交，可以生成订单' : '阶段推进到「成交」后才能生成订单')) + '</span>',
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
        '<div class="field"><label>产品型号（可搜索，共 ' + models.length + ' 个）*</label>' +
          modelComboHtml('') + '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>尺寸（宽×高 mm）*</label>' +
            '<input name="size" id="dpSize" required maxlength="32" placeholder="1200×2400"></div>' +
          '<div class="field"><label>阶段</label>' +
            '<select name="stage" disabled title="新建商机固定为报价">' +
              '<option value="quote" selected>报价</option>' +
            '</select></div>' +
        '</div>' +
        '<div class="field"><label>金额（报价）*</label>' +
          '<input name="amount" type="number" min="0" step="0.01" required placeholder="12000"></div>' +
        '<div class="field"><label>备注</label>' +
          '<textarea name="note" rows="2" maxlength="300" placeholder="客户需求、现场情况、特殊要求…"></textarea></div>' +
        '<p class="small muted">新建商机的初始阶段固定为「报价」，定金/尾款在生成订单时才填。</p>' +
        '<div class="form-actions">' +
          '<button type="button" class="btn" id="dpCancel">取消</button>' +
          '<button type="submit" class="btn btn-primary">创建商机</button>' +
        '</div>' +
      '</form>' +
    '</div>';

  /* 型号：可搜索下拉 */
  var comboEl = document.querySelector('#dealNewForm [data-model-combo]');
  var combo = bindModelCombo(comboEl, models, function (pick) {
    if (pick.size) { $('#dpSize', root).value = pick.size; }
  });
  /* 默认选第一个型号并带出尺寸 */
  if (models.length) {
    combo.set(models[0].key);
    var s0 = (models[0].label.match(/\d+×\d+/) || [''])[0];
    if (s0) { $('#dpSize', root).value = s0; }
  }

  $('#dpCancel', root).addEventListener('click', function () {
    navigate(lead ? '#/leads' : '#/customers');
  });

  $('#dealNewForm', root).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var amount = Number(f.amount.value || 0);
    if (!f.model.value) { toast('请选择产品型号（可输入关键字搜索）', true); return; }
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
      note: String(f.note.value || '').trim() || null,
      deposit: 0, balance: 0,
      stage: 'quote', closed_at: null,
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
          '<div class="field"><label>产品类型</label><select name="product_type">' +
            ((window.DEMO.dicts.filter(function (x) { return x.code === 'product_type'; })[0] || { items: [] }).items || [])
              .filter(function (i) { return i.enabled; })
              .map(function (i) {
                return '<option value="' + esc(i.label) + '"' + (d.product_type === i.label ? ' selected' : '') + '>' +
                  esc(i.label) + '</option>';
              }).join('') +
          '</select></div>' +
          '<div class="field"><label>手动 / 电动</label><select name="drive_type">' +
            DRIVE_TYPE.map(function (p) { return '<option value="' + p[0] + '"' + (d.drive_type === p[0] ? ' selected' : '') + '>' + p[1] + '</option>'; }).join('') +
          '</select></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>型号（可搜索）</label>' +
            modelComboHtml(d.model || '') + '</div>' +
          '<div class="field"><label>尺寸</label><input name="size" value="' + esc(d.size || '') + '" maxlength="32"></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>阶段</label><select name="stage">' +
            STAGES.map(function (p) { return '<option value="' + p[0] + '"' + (d.stage === p[0] ? ' selected' : '') + '>' + p[1] + '</option>'; }).join('') +
          '</select></div>' +
          '<div class="field"><label>金额（报价）</label>' +
            '<input name="amount" type="number" min="0" step="0.01" value="' + (d.amount || 0) + '"></div>' +
        '</div>' +
        '<div class="field"><label>备注</label>' +
          '<textarea name="note" rows="2" maxlength="300">' + esc(d.note || '') + '</textarea></div>' +
        '<p class="small muted">保存后，凡有变化的字段都会自动生成一条「编辑」履历。</p>' +
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

  var editComboEl = modal.querySelector('#dealFormEl [data-model-combo]');
  bindModelCombo(editComboEl, (window.DEMO.models || []), function (pick) {
    if (pick.size) { modal.querySelector('[name="size"]').value = pick.size; }
  });

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
    if (!nModel) { toast('请选择产品型号（可输入关键字搜索）', true); return; }
    var nSize = String(f.size.value || '').trim();
    var nAmount = Number(f.amount.value || 0);
    var nNote = String(f.note ? f.note.value : '').trim() || null;
    var nStage = f.stage.value;
    var nDrive = f.drive_type.value;

    cmp('产品类型', d.product_type, nType);
    cmp('型号', d.model, nModel);
    cmp('尺寸', d.size, nSize);
    cmp('手动/电动', DRIVE_LABEL[d.drive_type], DRIVE_LABEL[nDrive]);
    cmp('金额', d.amount, nAmount, moneyRaw);
    cmp('备注', d.note, nNote);

    d.product_type = nType || d.product_type;
    d.model = nModel; d.model_code = nModel;
    d.size = nSize; d.spec = nSize;
    d.drive_type = nDrive;
    d.amount = nAmount; d.note = nNote;
    d.updated_at = nowIso;

    var logs = window.DEMO.dealLogs[d.id] = window.DEMO.dealLogs[d.id] || [];
    /* 2026-10-31：编辑一定生成一条「编辑」履历（不是「创建」） */
    logs.push({
      at: nowIso,
      type: 'change',
      text: changes.length ? changes.join('；') : '编辑了商机信息（本次无字段变化）'
    });
    if (nStage !== d.stage) {
      logs.push({ at: nowIso, type: 'stage', text: '阶段推进：' + (STAGE_LABEL[d.stage] || d.stage) + ' → ' + (STAGE_LABEL[nStage] || nStage) });
      d.stage = nStage;
      if (nStage === 'won') { d.closed_at = nowIso; }
    }
    toast(changes.length ? ('已保存：' + changes.length + ' 项变更已记入履历') : '已保存（无字段变化，也已记入履历）');
    close();
    render();
  });
}

/* ---------------- 生成订单（模态框）
 * 2026-10-31 定稿：
 *   · 总额继承商机金额（只读）；填押金金额，尾款自动 = 总额 - 押金
 *   · 物流方式：包邮 / 代办 / 自提，另填物流费用
 *   · 收货地址从该客户的历史地址里选，也可新增一条（保存到客户名下，复购可复用）
 * ---------------- */
function openOrderModal(dealId) {
  var d = (window.DEMO.deals || []).filter(function (x) { return x.id === Number(dealId); })[0];
  if (!d) { return; }
  if (d.locked) { toast('该商机已生成订单', true); return; }

  var cust = (window.DEMO.customers || []).filter(function (x) { return x.id === d.customer_id; })[0] || {};
  var addrs = (window.DEMO.addresses || []).filter(function (a) { return a.customer_id === d.customer_id; });
  var carriers = (window.DEMO.carriers || []).filter(function (c) { return c.is_active; });
  var total = Number(d.amount) || 0;

  var addrOptions = addrs.map(function (a) {
    return '<option value="' + a.id + '">' + esc(a.label) + ' · ' + esc(a.receiver_name) + ' · ' +
      esc(a.phone) + ' · ' + esc(a.address) + '</option>';
  }).join('') + '<option value="new">＋ 新增一条收货地址</option>';

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content wide">' +
      '<div class="modal-header"><h3>生成订单</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="orderFormEl" autocomplete="off">' +

        '<p class="small muted" style="margin-top:0">以下信息继承自商机，不能在这里改</p>' +
        '<div class="info-grid">' +
          '<div class="info-cell"><div class="info-k small muted">客户</div><div class="info-v">' + esc(cust.name || '') + '</div></div>' +
          '<div class="info-cell"><div class="info-k small muted">产品 / 型号</div><div class="info-v">' +
            esc([d.product_type, d.model].filter(Boolean).join(' ')) + '</div></div>' +
          '<div class="info-cell"><div class="info-k small muted">尺寸</div><div class="info-v">' + esc(d.size || '—') + '</div></div>' +
          '<div class="info-cell"><div class="info-k small muted">手动 / 电动</div><div class="info-v">' +
            esc(DRIVE_LABEL[d.drive_type] || '—') + '</div></div>' +
          '<div class="info-cell"><div class="info-k small muted">订单总额</div><div class="info-v"><b>' +
            moneyRaw(total) + '</b></div></div>' +
        '</div>' +

        '<p class="small muted">收款</p>' +
        '<div class="row-2">' +
          '<div class="field"><label>押金金额 *</label>' +
            '<input name="deposit" id="ofDeposit" type="number" min="0" step="0.01" required placeholder="' +
              Math.round(total * 0.3) + '"></div>' +
          '<div class="field"><label>尾款（自动计算）</label>' +
            '<input name="balance" id="ofBalance" type="number" readonly value="' + total + '"></div>' +
        '</div>' +
        '<div id="ofWarn" class="notice small" hidden></div>' +

        '<p class="small muted">配送</p>' +
        '<div class="row-3">' +
          '<div class="field"><label>物流方式 *</label>' +
            '<select name="logistics_mode" id="ofMode">' +
              LOGISTICS_MODES.map(function (m) { return '<option value="' + m[0] + '">' + m[1] + '</option>'; }).join('') +
            '</select></div>' +
          '<div class="field"><label>承运公司（选填）</label>' +
            '<select name="carrier_id" id="ofCarrier">' +
              '<option value="">不指定</option>' +
              carriers.map(function (c) { return '<option value="' + c.id + '">' + esc(c.name) + '</option>'; }).join('') +
            '</select></div>' +
          '<div class="field"><label>物流费用（元）</label>' +
            '<input name="logistics_fee" id="ofFee" type="number" min="0" step="0.01" value="0"></div>' +
        '</div>' +

        '<div class="field"><label>收货地址 *</label>' +
          '<select id="ofAddr">' + addrOptions + '</select></div>' +

        '<div id="ofNewAddr" hidden>' +
          '<div class="row-2">' +
            '<div class="field"><label>地址备注（如：家 / 工地）</label>' +
              '<input id="ofAddrLabel" maxlength="32" value="家"></div>' +
            '<div class="field"><label>收件人 *</label>' +
              '<input id="ofRecvName" maxlength="32" value="' + esc(cust.name || '') + '"></div>' +
          '</div>' +
          '<div class="row-2">' +
            '<div class="field"><label>收件电话 *</label>' +
              '<input id="ofRecvPhone" maxlength="32" value="' + esc(cust.phone || '') + '"></div>' +
            '<div class="field"><label>详细地址 *</label>' +
              '<input id="ofRecvAddr" maxlength="200" value="' + esc(cust.location || '') + '"></div>' +
          '</div>' +
        '</div>' +

        '<div class="row-2">' +
          '<div class="field"><label>运单号（可后补）</label>' +
            '<input name="tracking_number" maxlength="64" placeholder="可留空"></div>' +
          '<div class="field"><label>备注</label>' +
            '<input name="note" maxlength="200"></div>' +
        '</div>' +

        '<div class="notice small">生成订单后，该商机会被锁定，不能再修改。</div>' +
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

  /* 押金 → 自动算尾款 / 合计校验 */
  var depEl = $('#ofDeposit', modal);
  function recalc() {
    var dep = Number(depEl.value || 0);
    var bal = Math.max(0, total - dep);
    $('#ofBalance', modal).value = bal;
    var warn = $('#ofWarn', modal);
    if (dep > total) {
      warn.hidden = false;
      warn.textContent = '押金不能大于订单总额 ' + moneyRaw(total);
    } else {
      warn.hidden = true;
    }
  }
  depEl.addEventListener('input', recalc);

  /* 自提时物流费用默认 0 */
  $('#ofMode', modal).addEventListener('change', function (ev) {
    if (ev.target.value === 'self') { $('#ofFee', modal).value = 0; }
  });

  /* 选「新增地址」才展开输入框 */
  $('#ofAddr', modal).addEventListener('change', function (ev) {
    $('#ofNewAddr', modal).hidden = ev.target.value !== 'new';
  });
  if (!addrs.length) {
    $('#ofAddr', modal).value = 'new';
    $('#ofNewAddr', modal).hidden = false;
  }

  $('#orderFormEl', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var dep = Number(f.deposit.value || 0);
    if (!(dep > 0)) { toast('押金金额必填且大于 0', true); return; }
    if (dep > total) { toast('押金不能大于订单总额', true); return; }

    /* 收货地址：选历史 or 新增（新增的存进客户地址簿，复购可复用） */
    var addrPick = $('#ofAddr', modal).value;
    var addrObj;
    if (addrPick === 'new') {
      var nName = String($('#ofRecvName', modal).value || '').trim();
      var nPhone = String($('#ofRecvPhone', modal).value || '').trim();
      var nAddr = String($('#ofRecvAddr', modal).value || '').trim();
      if (!nName || !nPhone || !nAddr) { toast('收件人、电话、详细地址都要填', true); return; }
      addrObj = {
        id: Math.max.apply(null, (window.DEMO.addresses || []).map(function (a) { return a.id; }).concat([0])) + 1,
        customer_id: d.customer_id,
        label: String($('#ofAddrLabel', modal).value || '').trim() || '新地址',
        receiver_name: nName, phone: nPhone, address: nAddr, is_default: false
      };
      window.DEMO.addresses.push(addrObj);
      var cObj = (window.DEMO.customers || []).filter(function (x) { return x.id === d.customer_id; })[0];
      if (cObj) { cObj.addresses = window.DEMO.addresses.filter(function (a) { return a.customer_id === cObj.id; }); }
    } else {
      addrObj = (window.DEMO.addresses || []).filter(function (a) { return String(a.id) === String(addrPick); })[0];
    }
    if (!addrObj) { toast('请选择收货地址', true); return; }

    var mode = f.logistics_mode.value;
    var carrierId = f.carrier_id.value ? Number(f.carrier_id.value) : null;
    var carrierName = f.carrier_id.value
      ? f.carrier_id.options[f.carrier_id.selectedIndex].text : '';
    var nowIso = new Date().toISOString().slice(0, 19);
    var now = new Date();
    var ym = now.getFullYear() + '-' + ((now.getMonth() + 1) < 10 ? '0' : '') + (now.getMonth() + 1);
    var seq = String((window.DEMO.orders || []).length + 1).padStart(3, '0');

    var order = {
      id: Math.max.apply(null, (window.DEMO.orders || []).map(function (x) { return x.id; })) + 1,
      order_no: 'SO-' + ym + '-' + seq,
      customer_id: d.customer_id, deal_id: d.id,
      product_type: d.product_type, model: d.model, spec: d.size,
      amount: total,
      deposit: dep,
      balance: Math.max(0, total - dep),
      paid_amount: 0,
      status: 'pending_payment',
      logistics_mode: mode,
      logistics_mode_label: LOGISTICS_MODE_LABEL[mode] || mode,
      logistics_fee: Number(f.logistics_fee.value || 0),
      carrier_id: carrierId,
      carrier_name: carrierName,
      tracking_number: String(f.tracking_number.value || '').trim() || null,
      address_id: addrObj.id,
      receiver_name: addrObj.receiver_name,
      receiver_phone: addrObj.phone,
      receiver_address: addrObj.address,
      note: String(f.note.value || '').trim() || null,
      created_at: nowIso, updated_at: nowIso
    };
    window.DEMO.orders.push(order);

    /* 商机锁定 + 赢单 + 履历记一条「生成订单」 */
    d.locked = true;
    d.order_id = order.id;
    d.stage = 'won';
    d.closed_at = nowIso;
    d.updated_at = nowIso;
    (window.DEMO.dealLogs[d.id] = window.DEMO.dealLogs[d.id] || []).push({
      at: nowIso, type: 'order',
      text: '生成订单 ' + order.order_no + '：总额 ' + moneyRaw(order.amount) +
        '，押金 ' + moneyRaw(order.deposit) + '，尾款 ' + moneyRaw(order.balance) +
        '，' + order.logistics_mode_label + (order.carrier_name ? '（' + order.carrier_name + '）' : '') +
        (order.logistics_fee ? '，物流费 ' + moneyRaw(order.logistics_fee) : '') +
        '，收货：' + order.receiver_name + ' ' + order.receiver_address
    });

    if (order.carrier_id) {
      var car = (window.DEMO.carriers || []).filter(function (c) { return c.id === order.carrier_id; })[0];
      if (car) { car.used = (car.used || 0) + 1; }
    }

    close();
    toast('订单已生成：' + order.order_no + '（演示：仅本次会话有效）');
    navigate('#/orders/' + order.id);
  });
}
