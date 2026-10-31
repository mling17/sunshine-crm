/* ============================================================================
 * 通用「实体跟进页」 —— 线索 / 客户 / 商机 / 售后 共用
 *
 * 2026-10-31 用户定稿：
 *   · 跟进方式只有微信/电话，默认微信
 *   · 记一条跟进用**模态框**（不再内联展开）
 *   · 跟进带图片时，履历里显示**缩略图**
 *   · 编辑产生的履历，类型显示「编辑」
 * ==========================================================================*/

var RECORD_META = {
  follow: { label: '跟进', cls: 'follow', icon: '💬' },
  create: { label: '创建', cls: 'create', icon: '✨' },
  change: { label: '编辑', cls: 'change', icon: '✏️' },
  stage: { label: '阶段变更', cls: 'stage', icon: '🚩' },
  order: { label: '生成订单', cls: 'order', icon: '📦' },
  aftersale: { label: '售后', cls: 'after', icon: '🛠' }
};

function recordLabel(type) { return (RECORD_META[type] || RECORD_META.follow).label; }

/* 演示用假照片（data URI SVG），让缩略图有内容可看 */
function mockPhoto(label, color) {
  var c = color || '#4a90d9';
  var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180">' +
    '<rect width="240" height="180" fill="' + c + '"/>' +
    '<rect x="18" y="18" width="204" height="144" fill="none" stroke="rgba(255,255,255,.65)" stroke-width="3"/>' +
    '<circle cx="120" cy="78" r="22" fill="rgba(255,255,255,.28)"/>' +
    '<text x="120" y="140" font-size="18" fill="#fff" text-anchor="middle" font-family="sans-serif">' +
    (label || '现场照片') + '</text></svg>';
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

/* 附件缩略图：files 元素可以是字符串文件名，也可以是 {name,url} */
function photoThumbs(files) {
  if (!files || !files.length) { return ''; }
  return '<div class="thumb-strip">' + files.map(function (f) {
    var name = typeof f === 'string' ? f : (f.name || '图片');
    var url = typeof f === 'string' ? null : f.url;
    if (!url) { return '<span class="file-chip">📎 ' + esc(name) + '</span>'; }
    return '<a class="thumb" href="' + esc(url) + '" target="_blank" rel="noopener">' +
      '<img src="' + esc(url) + '" alt="' + esc(name) + '" loading="lazy"></a>';
  }).join('') + '</div>';
}

/* 履历时间线 */
function timelineHtml(records) {
  if (!records || !records.length) { return '<p class="empty">还没有跟进记录</p>'; }
  var sorted = records.slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; });
  return '<div class="tl">' + sorted.map(function (r) {
    var m = RECORD_META[r.type] || RECORD_META.follow;
    var meta = [];
    if (r.method) { meta.push('方式：' + (FOLLOW_METHOD_LABEL[r.method] || r.method)); }
    if (r.next_date) { meta.push('下次跟进：' + r.next_date); }
    return '<div class="tl-item tl-' + m.cls + '">' +
      '<div class="tl-dot">' + m.icon + '</div>' +
      '<div class="tl-body">' +
        '<div class="tl-head"><span class="tl-type">' + m.label + '</span>' +
          '<span class="tl-time">' + fmtDateTime(r.at) + '</span></div>' +
        '<div class="tl-content">' + esc(r.content) + '</div>' +
        (meta.length ? '<div class="tl-meta small muted">' + esc(meta.join(' · ')) + '</div>' : '') +
        photoThumbs(r.files) +
      '</div>' +
    '</div>';
  }).join('') + '</div>';
}

/* ============================================================================
 * 记一条跟进（模态框）
 * opts = { title, placeholder, defaultNext, onSubmit({content,method,next_date,files}) }
 * ==========================================================================*/
function openFollowModal(opts) {
  opts = opts || {};
  var picked = [];

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content">' +
      '<div class="modal-header"><h3>' + esc(opts.title || '记一条跟进') + '</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="fuModalForm" autocomplete="off">' +
        '<div class="field"><label>跟进内容 *</label>' +
          '<textarea name="content" rows="4" maxlength="2000" required placeholder="' +
            esc(opts.placeholder || '聊了什么？对方什么态度？下一步做什么？') + '"></textarea></div>' +
        '<div class="row-2">' +
          '<div class="field"><label>跟进方式</label>' +
            '<select name="method">' +
              FOLLOW_METHODS.map(function (m) {
                return '<option value="' + m[0] + '"' + (m[0] === 'wechat' ? ' selected' : '') + '>' + m[1] + '</option>';
              }).join('') +
            '</select></div>' +
          '<div class="field"><label>下次跟进时间</label>' +
            '<input type="date" name="next_date" value="' + (opts.defaultNext || dayAfter(3)) + '"></div>' +
        '</div>' +
        '<div class="field"><label>图片（图纸 / 现场照片，可多选）</label>' +
          '<input type="file" name="photos" accept="image/*" multiple></div>' +
        '<div id="fuThumbs" class="thumb-strip"></div>' +
        '<div class="form-actions">' +
          '<button type="button" class="btn modal-cancel">取消</button>' +
          '<button type="submit" class="btn btn-primary">保存跟进</button>' +
        '</div>' +
      '</form>' +
    '</div>';
  document.body.appendChild(modal);

  function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
  $('.modal-close', modal).addEventListener('click', close);
  $('.modal-cancel', modal).addEventListener('click', close);

  /* 选图 → 立即出缩略图 */
  var input = modal.querySelector('[name="photos"]');
  input.addEventListener('change', function () {
    picked = Array.prototype.map.call(input.files, function (f) {
      return { name: f.name, url: URL.createObjectURL(f) };
    });
    $('#fuThumbs', modal).innerHTML = picked.map(function (p) {
      return '<a class="thumb" href="' + esc(p.url) + '" target="_blank" rel="noopener">' +
        '<img src="' + esc(p.url) + '" alt="' + esc(p.name) + '"></a>';
    }).join('');
  });

  $('#fuModalForm', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var content = String(f.content.value || '').trim();
    if (!content) { toast('跟进内容不能为空', true); return; }
    var payload = {
      content: content,
      method: f.method.value,
      next_date: f.next_date.value || null,
      files: picked
    };
    close();
    if (typeof opts.onSubmit === 'function') { opts.onSubmit(payload); }
  });
}

/**
 * 渲染实体跟进页
 * opts = { backHash, backLabel, title, badgesHtml, infoHtml, actionsHtml, records,
 *          onSubmit(payload), placeholder, addLabel, modalTitle }
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
        '<button type="button" class="btn btn-sm btn-primary" id="btnAddFollow">' +
          esc(opts.addLabel || '＋ 记一条跟进') + '</button></div>' +
      timelineHtml(opts.records) +
    '</div>';

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

function dayAfter(n) {
  var dt = new Date();
  dt.setDate(dt.getDate() + n);
  return dt.getFullYear() + '-' + ((dt.getMonth() + 1) < 10 ? '0' : '') + (dt.getMonth() + 1) +
    '-' + (dt.getDate() < 10 ? '0' : '') + dt.getDate();
}

/* 通用：信息网格 */
function infoGrid(pairs) {
  return '<div class="info-grid">' + pairs.map(function (p) {
    if (!p) { return ''; }
    return '<div class="info-cell"><div class="info-k small muted">' + esc(p[0]) + '</div>' +
      '<div class="info-v">' + (p[2] === true ? p[1] : esc(p[1] === null || p[1] === undefined || p[1] === '' ? '—' : p[1])) + '</div></div>';
  }).join('') + '</div>';
}

/* 通用：数据表（移动端横向滚动，末列吸右） */
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

/* 通用：操作按钮组 */
function opButtons(items) {
  return '<div class="op-group">' + items.map(function (b) {
    if (b.disabled) {
      return '<button type="button" class="btn-link" disabled title="' + esc(b.tip || '') + '">' + esc(b.label) + '</button>';
    }
    return '<button type="button" class="btn-link' + (b.danger ? ' danger' : '') + '" data-op="' +
      esc(b.op) + '"' + (b.arg !== undefined ? ' data-arg="' + esc(b.arg) + '"' : '') + '>' + esc(b.label) + '</button>';
  }).join('') + '</div>';
}

/* 表格「操作」列事件委托：绑在 #app 上（onclick 覆盖式，不叠加监听） */
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

/* 分页条 */
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