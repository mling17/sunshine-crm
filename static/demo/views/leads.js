/* ============================================================================
 * 线索（Demo 版，覆盖正式版 views/leads.js）
 * 用户 2026-10-31 定稿：
 *   · 表格展示，字段：名称/来源/地区/微信号/联系方式/标签/意向(默认中)/上次跟进/创建时间/操作
 *   · 操作：编辑、跟进（新页面：顶部信息卡 + 跟进履历）、转商机
 *   · 新增线索 / 批量导入 / 导入模板下载
 * ==========================================================================*/

function leadSourceText(l) {
  return l.source === 'other' && l.source_other ? l.source_other : (SOURCE_LABELS[l.source] || l.source || '—');
}

function leadIntentBadge(level) {
  var map = { high: ['danger', '高'], medium: ['warn', '中'], low: ['muted', '低'], none: ['muted', '无'] };
  var v = map[level] || map.medium;
  return '<span class="badge ' + v[0] + '">' + v[1] + '</span>';
}

function leadStatusBadge(l) {
  var map = { new: ['ok', '新线索'], following: ['warn', '跟进中'], converted: ['muted', '已转化'], invalid: ['danger', '已失效'] };
  var v = map[l.status] || map.new;
  return '<span class="badge ' + v[0] + '">' + v[1] + '</span>';
}

/* ---------------- 线索列表（表格） ---------------- */
function viewLeads(root, route) {
  var st = state.filters;
  var leads = (window.DEMO.leads || []).slice();

  var tabs = [['', '全部'], ['new', '新线索'], ['following', '跟进中'], ['converted', '已转化'], ['invalid', '已失效']];
  var tabHtml = tabs.map(function (t) {
    return '<button type="button" class="tab-btn' + ((st.status || '') === t[0] ? ' active' : '') +
      '" data-status="' + t[0] + '">' + t[1] + '</button>';
  }).join('');

  var filtered = leads.filter(function (l) {
    if (st.status && l.status !== st.status) { return false; }
    if (!st.q) { return true; }
    return [l.name, l.phone, l.wechat, l.company_name, l.location].join(' ').indexOf(st.q) >= 0;
  });

  var converted = filtered.filter(function (l) { return l.status === 'converted'; }).length;

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head"><h2>线索池 <span class="badge muted">' + filtered.length + '</span></h2>' +
        '<div class="btn-row">' +
          '<button type="button" class="btn btn-sm btn-primary" id="btnNewLead">＋ 新增线索</button>' +
          '<button type="button" class="btn btn-sm" id="btnImportLead">⇪ 批量导入</button>' +
          '<a class="btn btn-sm btn-link" id="btnTpl" href="javascript:void(0)">⬇ 导入模板</a>' +
        '</div>' +
      '</div>' +
      '<div class="searchbar">' +
        '<input id="leadSearch" type="search" placeholder="搜姓名 / 电话 / 微信 / 地区" value="' + esc(st.q) + '">' +
        '<button type="button" class="btn" id="leadSearchBtn">搜索</button>' +
      '</div>' +
      '<div class="tabs">' + tabHtml + '</div>' +
    '</div>' +
    '<div class="card">' +
      dataTable([
        { title: '名称', render: function (l) {
            return '<a href="#/leads/' + l.id + '/follow">' + esc(l.name) + '</a>' +
              (l.company_name ? '<div class="small muted">' + esc(l.company_name) + '</div>' : '');
          } },
        { title: '来源', render: function (l) { return esc(leadSourceText(l)); } },
        { title: '地区', render: function (l) { return esc(l.location || '—'); } },
        { title: '微信号', render: function (l) { return esc(l.wechat || '—'); } },
        { title: '联系方式', render: function (l) { return esc(l.phone || '—'); }, nowrap: true },
        { title: '标签', render: function (l) {
            return (l.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') || '—';
          } },
        { title: '意向', render: function (l) { return leadIntentBadge(l.intent_level); } },
        { title: '上次跟进', render: function (l) { return l.last_follow_at ? fmtDateTime(l.last_follow_at).slice(5, 16) : '—'; }, nowrap: true },
        { title: '创建时间', render: function (l) { return fmtDateTime(l.created_at).slice(0, 10); }, nowrap: true },
        { title: '操作', nowrap: true, render: function (l) {
            return opButtons([
              { op: 'edit', arg: l.id, label: '编辑' },
              { op: 'follow', arg: l.id, label: '跟进' },
              l.status === 'converted'
                ? { op: 'toNew', arg: l.id, label: '转商机', disabled: true, tip: '已转化，请在客户里操作' }
                : { op: 'toDeal', arg: l.id, label: '转商机' }
            ]);
          } }
      ], filtered, '还没有线索，点右上「新增线索」开始') +
      (converted ? '<p class="small muted">已转化 ' + converted + ' 条（转商机请在客户模块操作）</p>' : '') +
    '</div>';

  /* --- 搜索 / 页签 --- */
  $('#leadSearchBtn', root).addEventListener('click', function () {
    st.q = $('#leadSearch', root).value.trim();
    render();
  });
  $('#leadSearch', root).addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') { st.q = ev.target.value.trim(); render(); }
  });
  $$('.tab-btn', root).forEach(function (b) {
    b.addEventListener('click', function () {
      st.status = b.getAttribute('data-status');
      render();
    });
  });

  /* --- 操作按钮 --- */
  $$('[data-op]', root).forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (btn.disabled) { return; }
      var op = btn.getAttribute('data-op');
      var id = Number(btn.getAttribute('data-arg'));
      if (op === 'edit') { openLeadForm(id); }
      else if (op === 'follow') { navigate('#/leads/' + id + '/follow'); }
      else if (op === 'toDeal') { navigate('#/deals/new?lead=' + id); }
    });
  });

  $('#btnNewLead', root).addEventListener('click', function () { openLeadForm(null); });
  $('#btnImportLead', root).addEventListener('click', openImportModal);
  $('#btnTpl', root).addEventListener('click', downloadLeadTemplate);
}

/* ---------------- 线索详情 = 跟进页 ---------------- */
function viewLeadDetail(root, rawId) { return viewLeadFollow(root, rawId); }

function viewLeadFollow(root, rawId) {
  var l = (window.DEMO.leads || []).filter(function (x) { return x.id === Number(rawId); })[0];
  if (!l) { root.innerHTML = '<div class="card">线索不存在，<a href="#/leads">回线索池</a></div>'; return; }

  var records = (window.DEMO.leadFollows || []).filter(function (f) { return f.lead_id === l.id; })
    .map(function (f) {
      return { at: f.created_at, type: 'follow', content: f.content, next_date: f.next_date, method: f.method, files: f.files || [] };
    });

  var infoHtml = infoGrid([
    ['来源', leadSourceText(l), true],
    ['地区', l.location],
    ['微信号', l.wechat],
    ['联系方式', l.phone],
    ['公司', l.company_name],
    ['意向', leadIntentBadge(l.intent_level), true],
    ['状态', leadStatusBadge(l), true],
    ['标签', (l.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') || '—', true],
    ['创建时间', fmtDateTime(l.created_at)],
    ['备注', l.note]
  ]);

  renderEntityFollowPage(root, {
    backHash: '#/leads',
    backLabel: '线索池',
    title: l.name,
    badgesHtml: leadStatusBadge(l) + leadIntentBadge(l.intent_level),
    infoHtml: infoHtml,
    placeholder: '这次沟通聊了什么？对方什么态度？下一步做什么？',
    actionsHtml:
      '<button type="button" class="btn btn-sm" id="leadEdit">编辑线索</button>' +
      (l.status === 'converted'
        ? '<button type="button" class="btn btn-sm" disabled title="已转化">转商机</button>'
        : '<button type="button" class="btn btn-sm btn-primary" id="leadToDeal">转商机</button>'),
    records: records,
    onSubmit: function (p) {
      (window.DEMO.leadFollows || []).push({
        lead_id: l.id, method: p.method, content: p.content, next_date: p.next_date,
        created_at: new Date().toISOString().slice(0, 19), files: p.files
      });
      l.last_follow_at = new Date().toISOString().slice(0, 19);
      if (l.status === 'new') { l.status = 'following'; }
      toast('已记录跟进（演示：仅本次会话有效）');
      render();
    }
  });

  $('#leadEdit', root).addEventListener('click', function () { openLeadForm(l.id); });
  var toDeal = $('#leadToDeal', root);
  if (toDeal) {
    toDeal.addEventListener('click', function () { navigate('#/deals/new?lead=' + l.id); });
  }
}

/* ---------------- 新增 / 编辑线索 ---------------- */
function openLeadForm(editId) {
  var l = editId ? (window.DEMO.leads || []).filter(function (x) { return x.id === Number(editId); })[0] : null;
  var isEdit = !!l;
  var d = l || { lead_type: 'personal', intent_level: 'medium', source: 'wechat', status: 'new' };

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content wide">' +
      '<div class="modal-header"><h3>' + (isEdit ? '编辑线索' : '新增线索') + '</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="leadFormEl" autocomplete="off">' +
        '<div class="row-2">' +
          '<div class="field"><label>名称 *</label>' +
            '<input name="name" required maxlength="64" value="' + esc(d.name || '') + '"></div>' +
          '<div class="field"><label>类型</label>' +
            '<select name="lead_type">' +
              '<option value="personal"' + (d.lead_type === 'personal' ? ' selected' : '') + '>个人</option>' +
              '<option value="company"' + (d.lead_type === 'company' ? ' selected' : '') + '>公司</option>' +
            '</select></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>联系方式（手机）</label>' +
            '<input name="phone" maxlength="32" value="' + esc(d.phone || '') + '"></div>' +
          '<div class="field"><label>微信号</label>' +
            '<input name="wechat" maxlength="64" value="' + esc(d.wechat || '') + '"></div>' +
        '</div>' +
        '<div class="row-2">' +
          '<div class="field"><label>地区 / 安装地址</label>' +
            '<input name="location" maxlength="200" value="' + esc(d.location || '') + '"></div>' +
          '<div class="field"><label>公司名（公司类型填）</label>' +
            '<input name="company_name" maxlength="100" value="' + esc(d.company_name || '') + '"></div>' +
        '</div>' +
        '<div class="row-3">' +
          '<div class="field"><label>来源</label>' +
            '<select name="source">' +
              ['wechat|微信', 'phone|电话', 'referral|转介绍', 'existing|老客户', 'other|其他'].map(function (o) {
                var kv = o.split('|');
                return '<option value="' + kv[0] + '"' + (d.source === kv[0] ? ' selected' : '') + '>' + kv[1] + '</option>';
              }).join('') +
            '</select></div>' +
          '<div class="field"><label>来源补充（选\"其他\"填）</label>' +
            '<input name="source_other" maxlength="100" value="' + esc(d.source_other || '') + '" placeholder="如 抖音 / 小红书"></div>' +
          '<div class="field"><label>意向（默认中）</label>' +
            '<select name="intent_level">' +
              ['high|高', 'medium|中', 'low|低', 'none|无'].map(function (o) {
                var kv = o.split('|');
                var sel = (d.intent_level || 'medium') === kv[0];
                return '<option value="' + kv[0] + '"' + (sel ? ' selected' : '') + '>' + kv[1] + '</option>';
              }).join('') +
            '</select></div>' +
        '</div>' +
        '<div class="field"><label>标签（逗号分隔）</label>' +
          '<input name="tags" maxlength="200" value="' + esc((d.tags || []).join('、')) + '"></div>' +
        '<div class="field"><label>备注</label>' +
          '<textarea name="note" rows="2" maxlength="500">' + esc(d.note || '') + '</textarea></div>' +
        '<div class="form-actions">' +
          '<button type="button" class="btn modal-cancel">取消</button>' +
          '<button type="submit" class="btn btn-primary">' + (isEdit ? '保存' : '新增') + '</button>' +
        '</div>' +
      '</form>' +
    '</div>';
  document.body.appendChild(modal);

  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  $('.modal-close', modal).addEventListener('click', close);
  $('.modal-cancel', modal).addEventListener('click', close);

  $('#leadFormEl', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var name = String(f.name.value || '').trim();
    if (!name) { toast('名称必填', true); return; }
    var phone = String(f.phone.value || '').trim();
    var wechat = String(f.wechat.value || '').trim();
    if (!phone && !wechat) { toast('手机和微信至少填一个', true); return; }

    var payload = {
      name: name,
      lead_type: f.lead_type.value,
      phone: phone || null,
      wechat: wechat || null,
      location: String(f.location.value || '').trim() || null,
      company_name: String(f.company_name.value || '').trim() || null,
      source: f.source.value,
      source_other: String(f.source_other.value || '').trim() || null,
      intent_level: f.intent_level.value,
      tags: String(f.tags.value || '').split(/[,，、\s]+/).filter(Boolean),
      note: String(f.note.value || '').trim() || null
    };

    if (isEdit) {
      Object.keys(payload).forEach(function (k) { l[k] = payload[k]; });
      l.updated_at = new Date().toISOString().slice(0, 19);
      toast('已保存（演示：仅本次会话有效）');
    } else {
      payload.id = Math.max.apply(null, window.DEMO.leads.map(function (x) { return x.id; })) + 1;
      payload.status = 'new';
      payload.created_at = new Date().toISOString().slice(0, 19);
      payload.last_follow_at = null;
      window.DEMO.leads.unshift(payload);
      toast('已新增线索（演示：仅本次会话有效）');
    }
    close();
    render();
  });
}

/* ---------------- 批量导入 ---------------- */
function openImportModal() {
  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content">' +
      '<div class="modal-header"><h3>批量导入线索</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<ol class="small muted" style="padding-left:18px;line-height:1.9;margin-top:0">' +
        '<li>下载模板 → 按列填好（<b>名称必填</b>，手机和微信至少一个）</li>' +
        '<li>保存为 CSV（Excel 里「另存为 → CSV 逗号分隔」）</li>' +
        '<li>上传 → 预览前 5 行 → 确认导入</li>' +
      '</ol>' +
      '<div class="field"><label>选择文件</label>' +
        '<input type="file" id="impFileEl" accept=".csv,text/csv"></div>' +
      '<div id="impPreview"></div>' +
      '<div class="form-actions">' +
        '<button type="button" class="btn" id="impTpl2">⬇ 下载模板</button>' +
        '<button type="button" class="btn btn-primary" id="impGo">导入（演示）</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(modal);
  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  $('.modal-close', modal).addEventListener('click', close);
  $('#impTpl2', modal).addEventListener('click', downloadLeadTemplate);

  $('#impFileEl', modal).addEventListener('change', function (ev) {
    var f = ev.target.files[0];
    if (!f) { return; }
    $('#impPreview', modal).innerHTML = '<div class="notice small">已选择：' + esc(f.name) +
      '（演示环境不解析文件，真实版本会显示前 5 行预览 + 列映射）</div>';
  });

  $('#impGo', modal).addEventListener('click', function () {
    close();
    toast('演示环境：真实版本会逐行导入并提示成功/跳过条数');
  });
}

/* 生成并下载 CSV 模板（纯前端，不请求后端） */
function downloadLeadTemplate() {
  var header = ['名称', '类型', '联系方式', '微信号', '地区', '公司名', '来源', '意向', '标签', '备注'];
  var rows = [
    ['张三', '个人', '13800000000', 'zhangsan', '济南·万科城', '', '微信', '中', '重点', '示例行，可删'],
    ['某某装饰公司', '公司', '0531-88888888', 'abc888', '青岛·崂山区', '某某装饰', '转介绍', '高', '工程商', '']
  ];
  var csv = '\ufeff' + [header].concat(rows).map(function (r) {
    return r.map(function (c) { return '"' + String(c).replace(/"/g, '""') + '"'; }).join(',');
  }).join('\r\n');
  var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '线索导入模板.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  toast('模板已下载（演示环境，文件真实生成）');
}