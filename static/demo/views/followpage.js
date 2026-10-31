/* ============================================================================
 * 通用「实体跟进页」 —— 线索 / 客户 / 商机三种对象共用同一套结构
 *
 * 布局（用户 2026-10-31 定稿）：
 *   顶部：返回 + 标题 + 状态徽标
 *   卡片①：对象基本信息（各页自己给 infoHtml）
 *   卡片②：操作按钮（编辑 / 转商机 / 生成订单…各页自己给 actionsHtml）
 *   卡片③：跟进履历时间线（含系统自动生成的变更 / 阶段 / 下单记录）
 *   底部：记一条跟进（内容 + 方式 + 下次跟进时间 + 附件）
 * ==========================================================================*/

var RECORD_META = {
  follow: { label: '跟进', cls: 'follow', icon: '💬' },
  create: { label: '创建', cls: 'create', icon: '✨' },
  change: { label: '信息变更', cls: 'change', icon: '✏️' },
  stage: { label: '阶段变更', cls: 'stage', icon: '🚩' },
  order: { label: '生成订单', cls: 'order', icon: '📦' }
};

function recordLabel(type) { return (RECORD_META[type] || RECORD_META.follow).label; }

/* 履历时间线 */
function timelineHtml(records) {
  if (!records || !records.length) { return '<p class="empty">还没有跟进记录</p>'; }
  var sorted = records.slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; });
  return '<div class="tl">' + sorted.map(function (r) {
    var m = RECORD_META[r.type] || RECORD_META.follow;
    var meta = [];
    if (r.method) { meta.push('方式：' + ({ phone: '电话', wechat: '微信', visit: '到面/上门', online: '线上' }[r.method] || r.method)); }
    if (r.next_date) { meta.push('下次跟进：' + r.next_date); }
    var files = (r.files || []).map(function (f) {
      return '<a class="file-chip" href="javascript:void(0)" title="演示环境，附件不可下载">📎 ' + esc(f) + '</a>';
    }).join('');
    return '<div class="tl-item tl-' + m.cls + '">' +
      '<div class="tl-dot">' + m.icon + '</div>' +
      '<div class="tl-body">' +
        '<div class="tl-head"><span class="tl-type">' + m.label + '</span>' +
          '<span class="tl-time">' + fmtDateTime(r.at) + '</span></div>' +
        '<div class="tl-content">' + esc(r.content) + '</div>' +
        (meta.length ? '<div class="tl-meta small muted">' + esc(meta.join(' · ')) + '</div>' : '') +
        (files ? '<div class="tl-files">' + files + '</div>' : '') +
      '</div>' +
    '</div>';
  }).join('') + '</div>';
}

/* 跟进录入表单（可折叠） */
function followFormHtml(placeholder) {
  return '<div class="fu-form-wrap">' +
    '<button type="button" class="btn btn-primary" id="btnOpenFollow">＋ 记一条跟进</button>' +
    '<form id="entityFollowForm" class="fu-form" hidden autocomplete="off">' +
      '<div class="field"><label>跟进内容 *</label>' +
        '<textarea name="content" rows="3" maxlength="2000" required placeholder="' +
          esc(placeholder || '聊了什么、对方什么态度、下一步做什么') + '"></textarea></div>' +
      '<div class="row-2">' +
        '<div class="field"><label>跟进方式</label>' +
          '<select name="method"><option value="phone">电话</option>' +
            '<option value="wechat" selected>微信</option><option value="visit">到面/上门</option>' +
            '<option value="online">线上</option></select></div>' +
        '<div class="field"><label>下次跟进时间</label>' +
          '<input type="date" name="next_date" value="' + dayAfter(3) + '"></div>' +
      '</div>' +
      '<div class="field"><label>附件（图纸 / 现场照片 / 报价单，演示不真上传）</label>' +
        '<input type="file" name="files" multiple></div>' +
      '<div id="fileList" class="small muted"></div>' +
      '<div class="form-actions">' +
        '<button type="button" class="btn" id="btnCancelFollow">取消</button>' +
        '<button type="submit" class="btn btn-primary">保存跟进</button>' +
      '</div>' +
    '</form>' +
  '</div>';
}

/**
 * 渲染实体跟进页
 * opts = {
 *   backHash, backLabel, title, badgesHtml,
 *   infoHtml, actionsHtml, records,
 *   onSubmit(payload)  // {content, method, next_date, files:[name]}
 * }
 */
function renderEntityFollowPage(root, opts) {
  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head">' +
        '<h2><a class="crumb" href="' + opts.backHash + '">‹ ' + esc(opts.backLabel) + '</a> / ' +
          esc(opts.title) + '</h2>' +
        (opts.badgesHtml || '') +
      '</div>' +
      (opts.infoHtml || '') +
      (opts.actionsHtml ? '<div class="form-actions" style="justify-content:flex-start;flex-wrap:wrap">' + opts.actionsHtml + '</div>' : '') +
    '</div>' +
    '<div class="card">' +
      '<div class="card-head"><h2>跟进履历 <span class="badge muted">' +
        (opts.records || []).length + '</span></h2>' +
        '<span class="small muted">信息变更 / 阶段变化会自动生成一条</span></div>' +
      timelineHtml(opts.records) +
      followFormHtml(opts.placeholder) +
    '</div>';

  var form = $('#entityFollowForm', root);
  var openBtn = $('#btnOpenFollow', root);
  if (openBtn) {
    openBtn.addEventListener('click', function () {
      form.hidden = false;
      openBtn.hidden = true;
      $('textarea', form).focus();
    });
  }
  var cancelBtn = $('#btnCancelFollow', root);
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () {
      form.reset();
      $('#fileList', root).textContent = '';
      form.hidden = true;
      if (openBtn) { openBtn.hidden = false; }
    });
  }
  var fileInput = form.querySelector('[name="files"]');
  fileInput.addEventListener('change', function () {
    var names = Array.prototype.map.call(fileInput.files, function (f) { return f.name; });
    $('#fileList', root).textContent = names.length ? ('已选：' + names.join('、')) : '';
  });

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var content = String(form.querySelector('[name="content"]').value || '').trim();
    if (!content) { toast('跟进内容不能为空', true); return; }
    var files = Array.prototype.map.call(fileInput.files, function (f) { return f.name; });
    opts.onSubmit({
      content: content,
      method: form.querySelector('[name="method"]').value,
      next_date: form.querySelector('[name="next_date"]').value || null,
      files: files
    });
  });
}

function dayAfter(n) {
  var dt = new Date();
  dt.setDate(dt.getDate() + n);
  return dt.getFullYear() + '-' + ((dt.getMonth() + 1) < 10 ? '0' : '') + (dt.getMonth() + 1) +
    '-' + (dt.getDate() < 10 ? '0' : '') + dt.getDate();
}

/* 通用：把一行 key/value 渲染成信息网格 */
function infoGrid(pairs) {
  return '<div class="info-grid">' + pairs.map(function (p) {
    if (!p) { return ''; }
    return '<div class="info-cell"><div class="info-k small muted">' + esc(p[0]) + '</div>' +
      '<div class="info-v">' + (p[2] === true ? p[1] : esc(p[1] === null || p[1] === undefined || p[1] === '' ? '—' : p[1])) + '</div></div>';
  }).join('') + '</div>';
}

/* 通用：数据表（移动端横向滚动） */
function dataTable(columns, rows, emptyText) {
  var head = columns.map(function (c) {
    return '<th' + (c.align ? ' style="text-align:' + c.align + '"' : '') + '>' + esc(c.title) + '</th>';
  }).join('');
  var body = rows.length ? rows.map(function (r) {
    return '<tr>' + columns.map(function (c) {
      var v = c.render ? c.render(r) : esc(r[c.key] === null || r[c.key] === undefined ? '' : r[c.key]);
      return '<td' + (c.align ? ' style="text-align:' + c.align + '"' : '') +
        (c.nowrap ? ' class="nowrap"' : '') + '>' + v + '</td>';
    }).join('') + '</tr>';
  }).join('') : '<tr><td colspan="' + columns.length + '"><p class="empty">' +
      esc(emptyText || '暂无数据') + '</p></td></tr>';
  return '<div class="table-wrap"><table class="data-table"><thead><tr>' + head +
    '</tr></thead><tbody>' + body + '</tbody></table></div>';
}

/* 通用：危险/普通操作按钮组 */
function opButtons(items) {
  return '<div class="op-group">' + items.map(function (b) {
    if (b.disabled) {
      return '<button type="button" class="btn-link" disabled title="' + esc(b.tip || '') + '">' + esc(b.label) + '</button>';
    }
    return '<button type="button" class="btn-link' + (b.danger ? ' danger' : '') + '" data-op="' +
      esc(b.op) + '"' + (b.arg !== undefined ? ' data-arg="' + esc(b.arg) + '"' : '') + '>' + esc(b.label) + '</button>';
  }).join('') + '</div>';
}
/* 分页条（正式版原来在 views/customers.js 里，demo 没加载它，搬过来） */
function pagerHtml(res) {
  if (!res || !res.total) { return ''; }
  var size = res.size || PAGE_SIZE || 20;
  var pages = Math.max(1, Math.ceil((res.total || 0) / size));
  return '<div class="form-actions" style="justify-content:space-between;align-items:center">' +
    '<button type="button" class="btn btn-sm" data-page="' + ((res.page || 1) - 1) + '"' +
    ((res.page || 1) <= 1 ? ' disabled' : '') + '>上一页</button>' +
    '<span class="small muted">第 ' + (res.page || 1) + ' / ' + pages + ' 页 · 共 ' + res.total + ' 项</span>' +
    '<button type="button" class="btn btn-sm" data-page="' + ((res.page || 1) + 1) + '"' +
    ((res.page || 1) >= pages ? ' disabled' : '') + '>下一页</button>' +
    '</div>';
}


/* 表格「操作」列的事件委托：绑在 #app 上（onclick 覆盖式，多次 render 不会叠加监听） */
function bindOps(root, map) {
  root.onclick = function (ev) {
    var btn = ev.target && ev.target.closest ? ev.target.closest('[data-op]') : null;
    if (!btn || btn.disabled || !root.contains(btn)) { return; }
    var fn = map[btn.getAttribute('data-op')];
    if (!fn) { return; }
    ev.preventDefault();
    try {
      fn(Number(btn.getAttribute('data-arg')), btn);
    } catch (e) {
      toast('操作失败：' + (e && e.message ? e.message : e), true);
    }
  };
}
