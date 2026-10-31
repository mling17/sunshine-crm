/* 跨视图共用的小组件（必须在其它 views/*.js 之前加载）
 *
 * 这里只放「多个页面都要用」的渲染片段。依赖 app.js 暴露到 window 上的
 * STAGES / STAGE_LABEL / ORDER_STATUS / api / esc / $ / $$ / toast / render / money。
 * 注意：这些是普通 <script> 的全局函数，不要包 IIFE，否则别的视图拿不到。
 */

/* 阶段下拉选项（商机新增/编辑、跟进顺手改阶段） */
function stageOptions(current) {
  return STAGES.map(function (pair) {
    return '<option value="' + pair[0] + '"' + (pair[0] === current ? ' selected' : '') + '>' +
      pair[1] + '</option>';
  }).join('');
}

/* 逾期徽标：days 为空=不显示，>0=逾期，0=今天到期 */
function overdueBadge(days) {
  if (days === null || days === undefined) { return ''; }
  if (days > 0) { return '<span class="badge danger">逾期 ' + days + ' 天</span>'; }
  return '<span class="badge warn">今天</span>';
}

/* 订单状态徽标文案 */
function orderStatusLabel(status, statusLabel) {
  return statusLabel || ORDER_STATUS_LABEL[status] || status || '';
}

/* 新增商机表单（不含客户选择：客户由调用页面的 select 提供） */
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
      '<select name="stage">' + stageOptions('confirm') + '</select></div>' +
    '<div class="form-actions"><button type="submit" class="btn btn-primary">新增商机</button></div>' +
  '</form>';
}

/* 列表内联改阶段（<select data-deal-stage="ID">） */
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

/* 横向条形图。pairs 省略时按商机阶段；订单状态分布请传 ORDER_STATUS。
 * counts 的值可以是数字，也可以是 {count, amount}（订单统计后端就是这种结构） */
function numOf(v) {
  if (v && typeof v === 'object') { return Number(v.count) || 0; }
  return Number(v) || 0;
}

function barsHtml(counts, pairs) {
  var list = pairs || STAGES;
  var max = 1;
  Object.keys(counts || {}).forEach(function (k) { max = Math.max(max, numOf(counts[k])); });
  return list.map(function (pair) {
    var count = numOf((counts || {})[pair[0]]);
    var width = count ? Math.max(4, Math.round((count / max) * 100)) : 0;
    return '<div class="bar-row">' +
      '<span>' + pair[1] + '</span>' +
      '<span class="bar"><i style="width:' + width + '%"></i></span>' +
      '<span class="bar-num">' + count + '</span>' +
      '</div>';
  }).join('');
}
/* 商机列表项（客户详情页 / 商机页共用） */
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

/* 售后类型 / 状态文案（后端只给英文枚举，V2 未下发 *_label） */
function aftersaleTypeLabel(type, typeOther) {
  if (type === 'other') { return typeOther || '其他'; }
  return AFTERSALE_TYPE_LABEL[type] || type || '';
}

function aftersaleStatusLabel(status, statusLabel) {
  return statusLabel || AFTERSALE_STATUS_LABEL[status] || status || '';
}


/* ================= 表格 / 信息网格（移植自 demo core，真实版多页共用） =================
 * dataTable：移动端横向滚动 + 末列操作
 * opButtons + bindOps：表格「操作」列的事件委托（onclick 覆盖式，不叠加监听）
 * infoGrid：详情页信息网格（第 3 个元素 true = 值已是 HTML，不再转义）
 */
function dataTable(columns, rows, emptyText, tableClass) {
  var head = columns.map(function (c) {
    return '<th' + (c.align ? ' style="text-align:' + c.align + '"' : '') + '>' + esc(c.title) + '</th>';
  }).join('');
  var body = rows.length ? rows.map(function (r) {
    return '<tr>' + columns.map(function (c) {
      var v = c.render ? c.render(r) : esc(r[c.key] === null || r[c.key] === undefined ? '' : r[c.key]);
      return '<td' + (c.align ? ' style="text-align:' + c.align + '"' : '') +
        ' data-label="' + esc(c.title) + '"' +
        (c.nowrap ? ' class="nowrap"' : '') + '>' + v + '</td>';
    }).join('') + '</tr>';
  }).join('') : '<tr class="empty-row"><td colspan="' + columns.length + '"><p class="empty">' +
      esc(emptyText || '暂无数据') + '</p></td></tr>';
  return '<div class="table-wrap"><table class="data-table' +
    (tableClass ? ' ' + esc(tableClass) : '') + '"><thead><tr>' + head +
    '</tr></thead><tbody>' + body + '</tbody></table></div>';
}

function opButtons(items) {
  return '<div class="op-group">' + items.map(function (b) {
    if (b.disabled) {
      return '<button type="button" class="btn-link" disabled title="' + esc(b.tip || '') + '">' + esc(b.label) + '</button>';
    }
    return '<button type="button" class="btn-link' + (b.danger ? ' danger' : '') + '" data-op="' +
      esc(b.op) + '"' + (b.arg !== undefined ? ' data-arg="' + esc(b.arg) + '"' : '') + '>' + esc(b.label) + '</button>';
  }).join('') + '</div>';
}

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

function infoGrid(pairs) {
  return '<div class="info-grid">' + pairs.filter(Boolean).map(function (p) {
    var raw = p[1];
    var html = p[2] === true ? raw : esc(raw === null || raw === undefined || raw === '' ? '—' : raw);
    return '<div class="info-cell"><div class="info-k small muted">' + esc(p[0]) + '</div>' +
      '<div class="info-v">' + html + '</div></div>';
  }).join('') + '</div>';
}


/* ============================================================================
 * 通用「实体跟进页」—— 线索 / 客户 / 商机 / 售后共用（移植自 demo followpage，2026-10-31）
 *   记录类型：跟进 / 创建 / 编辑 / 状态变更 / 生成订单 / 售后 / 收款 / 发货
 *   记一条跟进走**模态框**（含下次跟进开关 + 多附件），不再内联展开
 *   图片附件显示缩略图，点开在弹层看大图（不开新标签页）
 * ==========================================================================*/

var RECORD_META = {
  follow: { label: '跟进', cls: 'follow', icon: '💬' },
  create: { label: '创建', cls: 'create', icon: '✨' },
  change: { label: '编辑', cls: 'change', icon: '✏️' },
  stage: { label: '状态变更', cls: 'stage', icon: '🚩' },
  order: { label: '生成订单', cls: 'order', icon: '📦' },
  aftersale: { label: '售后', cls: 'after', icon: '🛠' },
  pay: { label: '收款', cls: 'pay', icon: '💰' },
  ship: { label: '发货', cls: 'ship', icon: '🚚' }
};

function recordLabel(type) { return (RECORD_META[type] || RECORD_META.follow).label; }

function followDayAfter(n) {
  var dt = new Date();
  dt.setDate(dt.getDate() + n);
  return dt.getFullYear() + '-' + ((dt.getMonth() + 1) < 10 ? '0' : '') + (dt.getMonth() + 1) +
    '-' + (dt.getDate() < 10 ? '0' : '') + dt.getDate();
}

function fileIcon(name) {
  var ext = String(name || '').split('.').pop().toLowerCase();
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic'].indexOf(ext) >= 0) { return '🖼'; }
  if (['xlsx', 'xls', 'csv'].indexOf(ext) >= 0) { return '📊'; }
  if (ext === 'pdf') { return '📕'; }
  if (['doc', 'docx'].indexOf(ext) >= 0) { return '📄'; }
  if (['zip', 'rar', '7z'].indexOf(ext) >= 0) { return '🗜️'; }
  if (['dwg', 'dxf'].indexOf(ext) >= 0) { return '📐'; }
  return '📎';
}

function isImageFile(f) {
  if (typeof f === 'string') { return /\.(jpg|jpeg|png|gif|webp|bmp|heic)$/i.test(f); }
  if (typeof f.isImage === 'boolean') { return f.isImage; }
  if (f.url && /^data:image\//.test(f.url)) { return true; }
  return /\.(jpg|jpeg|png|gif|webp|bmp|heic)$/i.test(f.name || '');
}

/* 图片查看器：点缩略图在当前页弹大图 */
function openImageModal(url, name) {
  var modal = document.createElement('div');
  modal.className = 'modal img-modal';
  modal.innerHTML =
    '<div class="img-viewer">' +
    '<div class="img-viewer-bar"><span>' + esc(name || '图片') + '</span>' +
    '<button type="button" class="btn btn-link modal-close">×</button></div>' +
    '<img src="' + esc(url) + '" alt="' + esc(name || '') + '">' +
    '</div>';
  document.body.appendChild(modal);
  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  modal.querySelector('.modal-close').addEventListener('click', close);
  modal.addEventListener('click', function (ev) { if (ev.target === modal) { close(); } });
}

function photoThumbs(files) {
  if (!files || !files.length) { return ''; }
  return '<div class="attach-strip">' + files.map(function (f) {
    var name = typeof f === 'string' ? f : (f.name || '附件');
    var url = typeof f === 'string' ? null : f.url;
    if (url && isImageFile(f)) {
      return '<button type="button" class="thumb" data-img="' + esc(url) + '" data-name="' + esc(name) + '" ' +
        'title="点击查看大图"><img src="' + esc(url) + '" alt="' + esc(name) + '" loading="lazy"></button>';
    }
    if (url) {
      return '<a class="file-chip" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer" ' +
        'title="' + esc(name) + '">' + fileIcon(name) + ' ' + esc(name) + '</a>';
    }
    return '<span class="file-chip" title="' + esc(name) + '">' + fileIcon(name) + ' ' + esc(name) + '</span>';
  }).join('') + '</div>';
}

/* 缩略图点击委托（全页统一） */
document.addEventListener('click', function (ev) {
  var el = ev.target && ev.target.closest ? ev.target.closest('[data-img]') : null;
  if (!el) { return; }
  ev.preventDefault();
  openImageModal(el.getAttribute('data-img'), el.getAttribute('data-name'));
});

/* 履历时间线 */
function timelineHtml(records) {
  if (!records || !records.length) { return '<p class="empty">还没有跟进记录</p>'; }
  var sorted = records.slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; });
  return '<div class="tl">' + sorted.map(function (r) {
    var m = RECORD_META[r.type] || RECORD_META.follow;
    var meta = [];
    if (r.method) { meta.push('方式：' + (dictLabel('follow_method', r.method, r.method))); }
    if (r.next_date) { meta.push('下次跟进：' + r.next_date); }
    return '<div class="tl-item tl-' + m.cls + '">' +
      '<div class="tl-dot">' + m.icon + '</div>' +
      '<div class="tl-body">' +
      '<div class="tl-head"><span class="tl-type">' + m.label + '</span>' +
      '<span class="tl-time">' + fmtDateTime(r.at) + '</span></div>' +
      '<div class="tl-content">' + esc(r.content) + '</div>' +
      (meta.length ? '<div class="tl-meta small muted">' + esc(meta.join(' · ')) + '</div>' : '') +
      photoThumbs(r.files) +
      '</div></div>';
  }).join('') + '</div>';
}

function collectFiles(records) {
  var out = [];
  (records || []).forEach(function (r) {
    (r.files || []).forEach(function (f) {
      if (!f || (!f.url && !f.name)) { return; }
      out.push({
        name: typeof f === 'string' ? f : f.name,
        url: typeof f === 'string' ? null : f.url,
        isImage: typeof f === 'string' ? /\.(jpg|jpeg|png|gif|webp)$/i.test(f) : f.isImage,
        at: r.at || r.created_at
      });
    });
  });
  return out.sort(function (a, b) { return String(a.at) < String(b.at) ? 1 : -1; });
}

function filesCardHtml(files, emptyText) {
  if (!files.length) {
    return '<div class="card"><div class="card-head"><h2>资料 <span class="badge muted">0</span></h2></div>' +
      '<p class="empty">' + esc(emptyText || '还没有上传过图纸 / 报价单 / 现场照片') + '</p></div>';
  }
  return '<div class="card">' +
    '<div class="card-head"><h2>资料 <span class="badge muted">' + files.length + '</span></h2>' +
    '<span class="small muted">来自各条跟进，按时间倒序</span></div>' +
    '<div class="files-grid">' + files.map(function (f) {
      var body = (f.url && isImageFile(f))
        ? '<button type="button" class="thumb" data-img="' + esc(f.url) + '" data-name="' + esc(f.name) + '">' +
        '<img src="' + esc(f.url) + '" alt="' + esc(f.name) + '" loading="lazy"></button>'
        : '<a class="file-chip" href="' + esc(f.url || '#') + '" target="_blank" rel="noopener noreferrer">' +
        fileIcon(f.name) + ' ' + esc(f.name) + '</a>';
      return '<div class="files-item">' + body +
        '<div class="files-meta small muted">' + esc(fmtDateTime(f.at).slice(5, 10)) + '</div></div>';
    }).join('') + '</div></div>';
}

/* 记一条跟进（模态框）。picked 里的 file 是真实 File，提交时由调用方上传 */
function openFollowModal(opts) {
  opts = opts || {};
  var picked = [];

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-overlay"></div>' +
    '<div class="modal-content">' +
    '<div class="modal-header"><h3>' + esc(opts.title || '记一条跟进') + '</h3>' +
    '<button type="button" class="btn btn-link modal-close">×</button></div>' +
    '<div class="modal-body">' +
    '<form id="fuModalForm" autocomplete="off">' +
    '<div class="field"><label>跟进内容 *</label>' +
    '<textarea name="content" rows="4" maxlength="2000" required placeholder="' +
    esc(opts.placeholder || '聊了什么？对方什么态度？下一步做什么？') + '"></textarea></div>' +
    '<div class="row-2">' +
    '<div class="field"><label>跟进方式</label>' +
    '<select name="method">' + dictOptions('follow_method', 'wechat') + '</select></div>' +
    '<div class="field"><label class="label-with-switch">下次跟进时间' +
    '<span class="switch"><input type="checkbox" id="fuNextOn" checked><span>需要</span></span></label>' +
    '<input type="date" name="next_date" id="fuNextDate" value="' + (opts.defaultNext || followDayAfter(3)) + '">' +
    '<div class="small muted" id="fuNextHint">关掉表示这次不用再跟进</div></div>' +
    '</div>' +
    '<div class="field"><label>附件（图片 / Excel / PDF，最多 10 个、单个 ≤20MB）</label>' +
    '<input type="file" name="photos" multiple></div>' +
    '<div id="fuThumbs" class="attach-strip"></div>' +
    '<div class="form-actions">' +
    '<button type="button" class="btn modal-cancel">取消</button>' +
    '<button type="submit" class="btn btn-primary">保存跟进</button>' +
    '</div>' +
    '</form>' +
    '</div></div>';
  document.body.appendChild(modal);

  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  modal.querySelector('.modal-close').addEventListener('click', close);
  modal.querySelector('.modal-cancel').addEventListener('click', close);

  var input = modal.querySelector('[name="photos"]');
  var box = modal.querySelector('#fuThumbs');
  var MAX_FILES = 10;
  var MAX_MB = 20;

  function renderPicked() {
    if (!picked.length) { box.innerHTML = ''; return; }
    box.innerHTML = picked.map(function (p, i) {
      var body = (p.url && isImageFile(p))
        ? '<button type="button" class="thumb" data-img="' + esc(p.url) + '" data-name="' + esc(p.name) + '">' +
        '<img src="' + esc(p.url) + '" alt="' + esc(p.name) + '"></button>'
        : '<span class="file-chip" title="' + esc(p.name) + '">' + fileIcon(p.name) + ' ' + esc(p.name) + '</span>';
      return '<span class="attach-item">' + body +
        '<button type="button" class="attach-del" data-del-idx="' + i + '" title="移除这个附件">×</button></span>';
    }).join('');
  }

  input.addEventListener('change', function () {
    var skipped = [];
    Array.prototype.forEach.call(input.files, function (f) {
      if (f.size > MAX_MB * 1024 * 1024) { skipped.push(f.name + '（超过 ' + MAX_MB + 'MB）'); return; }
      if (picked.length >= MAX_FILES) { skipped.push(f.name + '（已达 ' + MAX_FILES + ' 个上限）'); return; }
      picked.push({ name: f.name, url: URL.createObjectURL(f), isImage: /^image\//.test(f.type || ''), file: f });
    });
    input.value = '';
    renderPicked();
    if (skipped.length) { toast('未添加：' + skipped.join('、'), true); }
  });

  box.addEventListener('click', function (ev) {
    var del = ev.target.closest('[data-del-idx]');
    if (!del) { return; }
    ev.preventDefault();
    ev.stopPropagation();
    picked.splice(Number(del.getAttribute('data-del-idx')), 1);
    renderPicked();
  });

  var nextOn = modal.querySelector('#fuNextOn');
  var nextDate = modal.querySelector('#fuNextDate');
  function syncNext() {
    nextDate.disabled = !nextOn.checked;
    nextDate.style.opacity = nextOn.checked ? '1' : '.45';
  }
  nextOn.addEventListener('change', syncNext);
  syncNext();

  modal.querySelector('#fuModalForm').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var content = String(modal.querySelector('[name="content"]').value || '').trim();
    if (!content) { toast('跟进内容不能为空', true); return; }
    var payload = {
      content: content,
      method: modal.querySelector('[name="method"]').value || 'wechat',
      next_date: nextOn.checked ? (nextDate.value || null) : null,
      files: picked
    };
    close();
    if (typeof opts.onSubmit === 'function') { opts.onSubmit(payload); }
  });
}

/* 渲染实体跟进页 */
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
    '<div class="card-head"><h2>跟进履历 <span class="badge muted">' + (opts.records || []).length + '</span></h2>' +
    (opts.canFollow === false
      ? '<span class="small muted">' + esc(opts.lockedText || '已完成，不能再添加跟进') + '</span>'
      : '<button type="button" class="btn btn-sm btn-primary" id="btnAddFollow">' +
      esc(opts.addLabel || '＋ 记一条跟进') + '</button>') +
    '</div>' +
    timelineHtml(opts.records) +
    '</div>' +
    (opts.extraHtml || '');

  var btn = $('#btnAddFollow', root);
  if (btn) {
    btn.addEventListener('click', function () {
      openFollowModal({
        title: opts.modalTitle || ('记一条跟进 · ' + opts.title),
        placeholder: opts.placeholder,
        onSubmit: opts.onSubmit
      });
    });
  }
}


/* ===== 可搜索下拉（产品型号）：替代 31 项原生 select =====
 * modelComboHtml(currentKey) + bindModelCombo(comboEl, items, onPick)
 * items 用 dictItems('product_model')，onPick 拿到 {key,label,meta}
 * 注意：**不自动填尺寸**（定制天窗尺寸不固定，由业务手填）
 */
function modelComboHtml(currentKey) {
  return '<div class="combo" data-model-combo>' +
    '<input type="text" class="combo-input" autocomplete="off" ' +
    'placeholder="输入型号 / 尺寸 搜索，如 XW 或 1200" value="' + esc(currentKey || '') + '">' +
    '<input type="hidden" name="model" value="' + esc(currentKey || '') + '">' +
    '<div class="combo-list"></div>' +
  '</div>';
}

function bindModelCombo(comboEl, items, onPick) {
  var input = comboEl.querySelector('.combo-input');
  var hidden = comboEl.querySelector('input[name="model"]');
  var list = comboEl.querySelector('.combo-list');

  function render(kw) {
    var q = String(kw || '').trim().toUpperCase();
    var hits = (items || []).filter(function (it) {
      if (!q) { return true; }
      return (String(it.key) + ' ' + String(it.label)).toUpperCase().indexOf(q) >= 0;
    }).slice(0, 40);
    list.innerHTML = hits.length ? hits.map(function (it) {
      return '<button type="button" class="combo-item" data-key="' + esc(it.key) + '">' +
        '<span class="combo-key">' + esc(it.key) + '</span>' +
        '<span class="combo-label">' + esc(it.label) + '</span></button>';
    }).join('') : '<div class="combo-empty small muted">没有匹配的型号</div>';
  }

  input.addEventListener('focus', function () { list.classList.add('open'); render(input.value); });
  input.addEventListener('input', function () { list.classList.add('open'); render(input.value); hidden.value = ''; });
  input.addEventListener('blur', function () { setTimeout(function () { list.classList.remove('open'); }, 180); });

  list.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-key]');
    if (!b) { return; }
    var key = b.getAttribute('data-key');
    hidden.value = key;
    input.value = key;
    list.classList.remove('open');
    var hit = (items || []).filter(function (it) { return it.key === key; })[0];
    if (typeof onPick === 'function') { onPick(hit || { key: key }); }
  });

  return {
    value: function () { return hidden.value; },
    set: function (key) { hidden.value = key || ''; input.value = key || ''; }
  };
}
