/* ============================================================================
 * 客户（Demo 版，覆盖正式版 views/customers.js）
 * 用户 2026-10-31 定稿：
 *   · 客户由线索转化而来，**不提供新增**，页面上说明来源
 *   · 每条可：编辑（细化信息 + 客户画像）、追踪（同线索的跟进页）、转商机
 * ==========================================================================*/

function customerRowOf(c) {
  var deals = (window.DEMO.deals || []).filter(function (d) { return d.customer_id === c.id; });
  var won = deals.filter(function (d) { return d.stage === 'won'; });
  return {
    c: c,
    deals: deals,
    wonCount: won.length,
    dealCount: deals.length,
    amount: won.reduce(function (s, d) { return s + (Number(d.amount) || 0); }, 0)
  };
}

/* ---------------- 客户列表（表格，无新增） ---------------- */
function viewCustomers(root, route) {
  var st = state.filters;
  var rows = (window.DEMO.customers || []).map(customerRowOf).filter(function (r) {
    if (!st.q) { return true; }
    var c = r.c;
    return [c.name, c.phone, c.wechat, c.location, c.company_name].join(' ').indexOf(st.q) >= 0;
  });

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head"><h2>客户档案 <span class="badge muted">' + rows.length + '</span></h2>' +
        '<span class="small muted">客户由线索转化，不在此新建</span></div>' +
      '<div class="searchbar">' +
        '<input id="custSearch" type="search" placeholder="搜姓名 / 电话 / 微信 / 楼盘" value="' + esc(st.q) + '">' +
        '<button type="button" class="btn" id="custSearchBtn">搜索</button>' +
      '</div>' +
    '</div>' +
    '<div class="card">' +
      dataTable([
        { title: '名称', render: function (r) {
            return '<a href="#/customers/' + r.c.id + '">' + esc(r.c.name) + '</a>' +
              (r.c.company_name ? '<div class="small muted">' + esc(r.c.company_name) + '</div>' : '');
          } },
        { title: '类型', render: function (r) { return r.c.customer_type === 'company' ? '公司' : '个人'; } },
        { title: '地区', render: function (r) { return esc(r.c.location || '—'); } },
        { title: '微信号', render: function (r) { return esc(r.c.wechat || '—'); } },
        { title: '联系方式', render: function (r) { return esc(r.c.phone || '—'); }, nowrap: true },
        { title: '标签', render: function (r) {
            return (r.c.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') || '—';
          } },
        { title: '意向', render: function (r) { return leadIntentBadge(r.c.intent_level); } },
        { title: '商机', render: function (r) { return r.dealCount + ' 个'; }, align: 'center' },
        { title: '累计成交', render: function (r) { return money(r.amount); }, align: 'right', nowrap: true },
        { title: '创建时间', render: function (r) { return fmtDateTime(r.c.created_at).slice(0, 10); }, nowrap: true },
        { title: '操作', nowrap: true, render: function (r) {
            return opButtons([
              { op: 'edit', arg: r.c.id, label: '编辑' },
              { op: 'follow', arg: r.c.id, label: '追踪' },
              { op: 'toDeal', arg: r.c.id, label: '转商机' }
            ]);
          } }
      ], rows, '还没有客户：客户由线索转化产生，请先到「线索」把线索转成客户') +
    '</div>';

  $('#custSearchBtn', root).addEventListener('click', function () {
    st.q = $('#custSearch', root).value.trim();
    render();
  });
  $('#custSearch', root).addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') { st.q = ev.target.value.trim(); render(); }
  });

  bindOps(root, {
    edit: function (id) { openCustomerForm(id); },
    follow: function (id) { navigate('#/customers/' + id + '/follow'); },
    toDeal: function (id) { navigate('#/deals/new?customer=' + id); }
  });
}

/* ---------------- 客户详情：档案 + 画像 + 商机 ---------------- */
function viewCustomerDetail(root, rawId) {
  var c = (window.DEMO.customers || []).filter(function (x) { return x.id === Number(rawId); })[0];
  if (!c) { root.innerHTML = '<div class="card">客户不存在，<a href="#/customers">回客户列表</a></div>'; return; }

  var r = customerRowOf(c);
  var p = c.profile || {};

  var profileHtml = infoGrid([
    ['房屋类型', p.house_type], ['楼层', p.floor], ['安装位置', p.install_at],
    ['装修阶段', p.stage], ['预算', p.budget], ['决策人', p.decider],
    ['关注点', (p.care || []).map(function (x) { return '<span class="tag">' + esc(x) + '</span>'; }).join('') || '—', true]
  ]);

  var dealsHtml = r.deals.length ? r.deals.map(function (d) {
    return '<div class="item"><div class="item-main">' +
      '<div class="item-title"><a href="#/deals/' + d.id + '">' +
        esc([d.product_type, d.model, d.size].filter(Boolean).join(' ')) + '</a>' +
        '<span class="badge muted">' + esc(STAGE_LABEL[d.stage] || d.stage) + '</span></div>' +
      '<div class="item-sub small muted">' + DRIVE_LABEL[d.drive_type] + ' · ' + money(d.amount) +
        ' · ' + fmtDateTime(d.created_at).slice(0, 10) + '</div>' +
      '</div><div class="item-side muted">›</div></div>';
  }).join('') : '<p class="empty">还没有商机</p>';

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head">' +
        '<h2><a class="crumb" href="#/customers">‹ 客户</a> / ' + esc(c.name) + '</h2>' +
        '<div class="btn-row">' +
          '<button type="button" class="btn btn-sm" id="custFollow">追踪</button>' +
          '<button type="button" class="btn btn-sm" id="custEdit">编辑</button>' +
          '<button type="button" class="btn btn-sm btn-primary" id="custToDeal">转商机</button>' +
        '</div>' +
      '</div>' +
      infoGrid([
        ['类型', c.customer_type === 'company' ? '公司' : '个人'],
        ['联系方式', c.phone], ['微信号', c.wechat],
        ['地区 / 安装地址', c.location], ['公司名', c.company_name],
        ['来源', c.source_other || SOURCE_LABELS[c.source] || c.source],
        ['意向', leadIntentBadge(c.intent_level), true],
        ['标签', (c.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') || '—', true],
        ['建档', fmtDateTime(c.created_at).slice(0, 10)],
        ['商机 / 成交', r.dealCount + ' 个 / ' + r.wonCount + ' 单', true],
        ['累计成交', money(r.amount), true]
      ]) +
      (c.note ? '<p class="small muted">备注：' + esc(c.note) + '</p>' : '') +
    '</div>' +
    '<div class="card">' +
      '<div class="card-head"><h2>客户画像</h2><span class="small muted">编辑里可修改</span></div>' +
      profileHtml +
    '</div>' +
    '<div class="card">' +
      '<div class="card-head"><h2>商机（' + r.deals.length + '）</h2>' +
        '<button type="button" class="btn btn-sm" id="custToDeal2">＋ 转商机</button></div>' +
      dealsHtml +
    '</div>';

  $('#custEdit', root).addEventListener('click', function () { openCustomerForm(c.id); });
  $('#custFollow', root).addEventListener('click', function () { navigate('#/customers/' + c.id + '/follow'); });
  $('#custToDeal', root).addEventListener('click', function () { navigate('#/deals/new?customer=' + c.id); });
  var d2 = $('#custToDeal2', root);
  if (d2) { d2.addEventListener('click', function () { navigate('#/deals/new?customer=' + c.id); }); }
}

/* ---------------- 客户追踪（跟进页） ---------------- */
function viewCustomerFollow(root, rawId) {
  var c = (window.DEMO.customers || []).filter(function (x) { return x.id === Number(rawId); })[0];
  if (!c) { root.innerHTML = '<div class="card">客户不存在，<a href="#/customers">回客户列表</a></div>'; return; }

  var records = (window.DEMO.followups || []).filter(function (f) { return f.customer_id === c.id; })
    .map(function (f) {
      return { at: f.created_at, type: 'follow', content: f.content, next_date: f.next_date, method: f.method, files: [] };
    });
  /* 该客户商机的变更/下单记录也一起显示，避免"履历断片" */
  (window.DEMO.deals || []).filter(function (d) { return d.customer_id === c.id; }).forEach(function (d) {
    ((window.DEMO.dealLogs || {})[d.id] || []).forEach(function (g) {
      records.push({ at: g.at, type: g.type, content: g.text, files: [] });
    });
  });

  renderEntityFollowPage(root, {
    backHash: '#/customers',
    backLabel: '客户',
    title: c.name,
    badgesHtml: leadIntentBadge(c.intent_level),
    infoHtml: infoGrid([
      ['联系方式', c.phone], ['微信号', c.wechat],
      ['地区', c.location], ['公司名', c.company_name],
      ['来源', c.source_other || SOURCE_LABELS[c.source] || c.source],
      ['建档', fmtDateTime(c.created_at).slice(0, 10)]
    ]),
    placeholder: '这次沟通聊了什么？客户什么反馈？下一步做什么？',
    actionsHtml:
      '<button type="button" class="btn btn-sm" id="cfEdit">编辑客户</button>' +
      '<button type="button" class="btn btn-sm btn-primary" id="cfToDeal">转商机</button>',
    records: records,
    onSubmit: function (p) {
      (window.DEMO.followups || []).push({
        id: Date.now(), object_type: 'customer', object_id: c.id, customer_id: c.id, deal_id: null,
        method: p.method, content: p.content, next_date: p.next_date,
        created_at: new Date().toISOString().slice(0, 19)
      });
      toast('已记录跟进（演示：仅本次会话有效）');
      render();
    }
  });

  $('#cfEdit', root).addEventListener('click', function () { openCustomerForm(c.id); });
  $('#cfToDeal', root).addEventListener('click', function () { navigate('#/deals/new?customer=' + c.id); });
}

/* ---------------- 编辑客户（档案 + 画像） ---------------- */
function openCustomerForm(id) {
  var c = (window.DEMO.customers || []).filter(function (x) { return x.id === Number(id); })[0];
  if (!c) { return; }
  var p = c.profile || {};

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content wide">' +
      '<div class="modal-header"><h3>编辑客户 · ' + esc(c.name) + '</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="custFormEl" autocomplete="off">' +
        '<p class="small muted" style="margin-top:0">客户档案</p>' +
        '<div class="row-2">' +
          '<div class="field"><label>名称 *</label><input name="name" required maxlength="64" value="' + esc(c.name) + '"></div>' +
          '<div class="field"><label>类型</label><select name="customer_type">' +
            '<option value="personal"' + (c.customer_type === 'personal' ? ' selected' : '') + '>个人</option>' +
            '<option value="company"' + (c.customer_type === 'company' ? ' selected' : '') + '>公司</option></select></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>联系方式</label><input name="phone" maxlength="32" value="' + esc(c.phone || '') + '"></div>' +
          '<div class="field"><label>微信号</label><input name="wechat" maxlength="64" value="' + esc(c.wechat || '') + '"></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>地区 / 安装地址</label><input name="location" maxlength="200" value="' + esc(c.location || '') + '"></div>' +
          '<div class="field"><label>公司名</label><input name="company_name" maxlength="100" value="' + esc(c.company_name || '') + '"></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>意向</label><select name="intent_level">' +
            ['high|高', 'medium|中', 'low|低', 'none|无'].map(function (o) {
              var kv = o.split('|');
              return '<option value="' + kv[0] + '"' + (c.intent_level === kv[0] ? ' selected' : '') + '>' + kv[1] + '</option>';
            }).join('') + '</select></div>' +
          '<div class="field"><label>标签（逗号分隔）</label><input name="tags" value="' + esc((c.tags || []).join('、')) + '"></div>' +
        '</div>' +
        '<div class="field"><label>备注</label><textarea name="note" rows="2">' + esc(c.note || '') + '</textarea></div>' +
        '<p class="small muted">客户画像（销售判断依据，越细越好跟进）</p>' +
        '<div class="row-3">' +
          '<div class="field"><label>房屋类型</label><input name="house_type" value="' + esc(p.house_type || '') + '" placeholder="公寓/别墅/自建房"></div>' +
          '<div class="field"><label>楼层</label><input name="floor" value="' + esc(p.floor || '') + '" placeholder="18/32 顶楼"></div>' +
          '<div class="field"><label>安装位置</label><input name="install_at" value="' + esc(p.install_at || '') + '" placeholder="主卧/客厅/阳台"></div>' +
        '</div>' +
        '<div class="row-3">' +
          '<div class="field"><label>装修阶段</label><input name="stage" value="' + esc(p.stage || '') + '" placeholder="未开工/水电/泥木/安装中"></div>' +
          '<div class="field"><label>预算</label><input name="budget" value="' + esc(p.budget || '') + '"></div>' +
          '<div class="field"><label>决策人</label><input name="decider" value="' + esc(p.decider || '') + '"></div>' +
        '</div>' +
        '<div class="field"><label>关注点（逗号分隔）</label>' +
          '<input name="care" value="' + esc((p.care || []).join('、')) + '" placeholder="防水、隔音、采光、价格、颜值"></div>' +
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

  $('#custFormEl', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    c.name = String(f.name.value || '').trim() || c.name;
    c.customer_type = f.customer_type.value;
    c.phone = String(f.phone.value || '').trim() || null;
    c.wechat = String(f.wechat.value || '').trim() || null;
    c.location = String(f.location.value || '').trim() || null;
    c.company_name = String(f.company_name.value || '').trim() || null;
    c.intent_level = f.intent_level.value;
    c.tags = String(f.tags.value || '').split(/[,，、\s]+/).filter(Boolean);
    c.note = String(f.note.value || '').trim() || null;
    c.profile = {
      house_type: String(f.house_type.value || '').trim(),
      floor: String(f.floor.value || '').trim(),
      install_at: String(f.install_at.value || '').trim(),
      stage: String(f.stage.value || '').trim(),
      budget: String(f.budget.value || '').trim(),
      decider: String(f.decider.value || '').trim(),
      care: String(f.care.value || '').split(/[,，、\s]+/).filter(Boolean)
    };
    c.updated_at = new Date().toISOString().slice(0, 19);
    close();
    toast('已保存（演示：仅本次会话有效）');
    render();
  });
}