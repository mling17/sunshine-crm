/* 跨视图共用的小组件（必须在其它 views/*.js 之前加载）
 *
 * 这里只放「多个页面都要用」的渲染片段。依赖 app.js 暴露到 window 上的
 * STAGES / STAGE_LABEL / ORDER_STATUS / api / esc / $ / $$ / toast / render / money。
 * 注意：这些是普通 <script> 的全局函数，不要包 IIFE，否则别的视图拿不到。
 */

/* 阶段下拉选项（商机新增/编辑、跟进顺手改阶段） */
function stageOptions(current) {
  return STAGES.filter(function (pair) {
    return pair[0] === 'quote' || pair[0] === 'confirm' || pair[0] === current;
  }).map(function (pair) {
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
  var parts = [deal.product_name_snapshot, deal.product_code_snapshot || deal.model, deal.spec]
    .filter(Boolean).join(' / ') || [deal.product_type, deal.model, deal.spec].filter(Boolean).join(' / ') || '未填产品';
  var amounts = '报价 ' + money(deal.amount);
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
function dataTable(columns, rows, emptyText) {
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
  return '<div class="table-wrap"><table class="data-table"><thead><tr>' + head +
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
  quote: { label: '报价单', cls: 'quote', icon: '📋' },
  confirm: { label: '客户确认', cls: 'confirm', icon: '✅' },
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

function timelineQuoteDetailHtml(detail) {
  if (!detail || !detail.quote || !Array.isArray(detail.items)) { return ''; }
  var quote = detail.quote;
  var changes = Array.isArray(detail.changes) ? detail.changes : [];
  var itemHtml = detail.items.map(function (item) {
    var product = [item.product_code, item.product_name].filter(Boolean).join(' · ') || '未关联产品';
    var attrs = [
      item.product_type,
      item.model,
      item.drive_type_label,
      item.quantity ? ('×' + item.quantity) : null
    ].filter(Boolean);
    var formMeta = item.form_file_name
      ? [
          item.form_file_name,
          item.sheet_name,
          item.row_count ? item.row_count + ' 行' : null,
          item.column_count ? item.column_count + ' 列' : null,
          item.a1_value ? 'A1 ' + item.a1_value : null
        ].filter(Boolean).join(' · ')
      : '未上传下单表';
    var preview = item.form_preview_url
      ? '<button type="button" class="thumb tl-quote-form-thumb" data-img="/crm' +
        esc(item.form_preview_url) + '" data-name="' + esc(product + ' · 下单表') + '">' +
        '<img src="/crm' + esc(item.form_preview_url) + '" alt="下单表内容缩略图" loading="lazy"></button>'
      : '';
    var download = item.form_url
      ? '<a class="btn btn-sm" href="/crm' + esc(item.form_url) + '">下载已上传下单表</a>'
      : '';
    return '<div class="tl-quote-product">' +
      '<div class="tl-quote-product-head"><b>' + esc(product) + '</b>' +
        '<span>' + money(item.amount) + '</span></div>' +
      (attrs.length ? '<div class="small muted">' + esc(attrs.join(' · ')) + '</div>' : '') +
      (item.product_config ? '<div class="small muted">' + esc(item.product_config) + '</div>' : '') +
      '<div class="tl-quote-facts"><span>报价 ' + money(item.amount) + '</span>' +
        '<span>识别合计 ' + money(item.recognized_total) + '</span>' +
        (item.note ? '<span>备注：' + esc(item.note) + '</span>' : '') + '</div>' +
      '<div class="small muted tl-quote-form-meta">' + esc(formMeta) + '</div>' +
      (preview || download ? '<div class="tl-quote-form-actions">' + preview + download + '</div>' : '') +
    '</div>';
  }).join('');
  var changeHtml = changes.length
    ? '<div class="tl-quote-changes">' + changes.map(function (change) {
        var before = change.from === null || change.from === undefined || change.from === ''
          ? '未填写' : String(change.from);
        var after = change.to === null || change.to === undefined || change.to === ''
          ? '未填写' : String(change.to);
        return '<div><b>' + esc(change.label || '字段') + '</b>：' +
          esc(before) + ' → ' + esc(after) + '</div>';
      }).join('') + '</div>'
    : '';
  return '<div class="tl-quote-detail">' +
    '<div class="tl-quote-detail-head"><b>' + esc(quote.quote_no || '报价单') + '</b>' +
      '<span>' + esc(quote.title || '') + '</span>' +
      '<span class="badge quote">' + esc(quote.status_label || quote.status || '') + '</span>' +
      '<strong>合计 ' + money(quote.amount) + '</strong></div>' +
    (quote.note ? '<div class="small muted">报价备注：' + esc(quote.note) + '</div>' : '') +
    changeHtml +
    (itemHtml ? '<div class="tl-quote-products">' + itemHtml + '</div>' : '') +
  '</div>';
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
    if (r.quote_no) { meta.push('关联报价单：' + r.quote_no); }
    return '<div class="tl-item tl-' + m.cls + '">' +
      '<div class="tl-dot">' + m.icon + '</div>' +
      '<div class="tl-body">' +
      '<div class="tl-head"><span class="tl-type">' + m.label + '</span>' +
      '<span class="tl-time">' + fmtDateTime(r.at) + '</span></div>' +
      '<div class="tl-content">' + esc(r.content) + '</div>' +
      (meta.length ? '<div class="tl-meta small muted">' + esc(meta.join(' · ')) + '</div>' : '') +
      timelineQuoteDetailHtml(r.detail) +
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

/* 跟进接口记录 → 通用跟进页时间线。线索、客户、商机统一使用同一套结构。 */
function followupRecordsFromApi(records) {
  var TYPE_MAP = {
    follow: 'follow', create: 'create', change: 'change', update: 'change',
    stage: 'stage', quote: 'quote', confirm: 'confirm', order: 'order',
    aftersale: 'aftersale', pay: 'pay', ship: 'ship'
  };
  return (records || []).map(function (r) {
    var photos = (r.photos || []).map(function (ph) {
      var url = ph.url ? '/crm' + ph.url : null;
      return {
        name: ph.file_name || ph.name || '附件',
        url: url,
        isImage: /\.(jpg|jpeg|png|gif|webp|bmp|heic)$/i.test(ph.file_name || ph.name || '')
      };
    });
    return {
      at: r.created_at,
      type: TYPE_MAP[r.kind] || 'follow',
      content: r.content || '',
      next_date: r.next_date,
      method: r.method,
      quote_no: r.quote_no,
      detail: r.detail || null,
      files: photos
    };
  });
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
    '<div class="modal-content followup-modal">' +
    '<div class="modal-header">' +
    '<div class="followup-modal-heading">' +
    '<span class="followup-modal-mark" aria-hidden="true">' +
    '<svg viewBox="0 0 24 24" fill="none"><path d="M8 3v3M16 3v3M4 9h16M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="m9 14 2 2 4-4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
    '</span>' +
    '<div class="followup-modal-heading-copy">' +
    '<span class="followup-modal-kicker">客户沟通</span>' +
    '<h3>' + esc(opts.title || '记一条跟进') + '</h3>' +
    '<p>记录沟通结果，安排下一次联系</p>' +
    '</div></div>' +
    '<button type="button" class="btn btn-link modal-close" aria-label="关闭跟进弹窗">×</button></div>' +
    '<div class="modal-body">' +
    '<form id="fuModalForm" class="form-grid" autocomplete="off">' +
    '<div class="field followup-content-field">' +
    '<div class="followup-label-line"><label for="fuModalContent">跟进内容 <span class="followup-required">*</span></label>' +
    '<span class="followup-field-note">最多 2000 字</span></div>' +
    '<textarea id="fuModalContent" name="content" rows="4" maxlength="2000" required placeholder="' +
    esc(opts.placeholder || '聊了什么？对方什么态度？下一步做什么？') + '"></textarea></div>' +
    '<div class="row-2 followup-options">' +
    '<div class="field followup-option-card">' +
    '<label for="fuMethod">跟进方式</label>' +
    '<select id="fuMethod" name="method">' + dictOptions('follow_method', 'wechat') + '</select>' +
    '<div class="followup-option-hint"><span class="followup-hint-dot" aria-hidden="true"></span>选择本次沟通渠道</div></div>' +
    '<div class="field followup-option-card followup-schedule">' +
    '<div class="followup-schedule-head"><label for="fuNextDate">下次跟进时间</label>' +
    '<label class="next-followup-toggle" for="fuNextOn">' +
    '<input type="checkbox" id="fuNextOn" checked aria-label="安排下次跟进">' +
    '<span class="next-followup-track" aria-hidden="true"><span class="next-followup-knob"></span></span>' +
    '<span class="next-followup-state">需要</span></label></div>' +
    '<div class="followup-date-control">' +
    '<span class="followup-date-icon" aria-hidden="true">' +
    '<svg viewBox="0 0 24 24" fill="none"><path d="M8 3v3M16 3v3M4 9h16M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>' +
    '</span>' +
    '<input type="date" name="next_date" id="fuNextDate" value="' + (opts.defaultNext || followDayAfter(3)) + '">' +
    '</div>' +
    '<div class="small muted followup-option-hint" id="fuNextHint"><span class="followup-hint-dot" aria-hidden="true"></span><span id="fuNextHintText">会显示在今日与后续待办中</span></div></div>' +
    '</div>' +
    (opts.extraHtml || '') +
    '<div class="field followup-attachment-field">' +
    '<div class="followup-label-line"><label for="fuPhotos">附件</label>' +
    '<span class="followup-field-note">图片 / Excel / PDF · 最多 10 个 · 单个 ≤20MB</span></div>' +
    '<input id="fuPhotos" type="file" name="photos" multiple></div>' +
    '<div id="fuThumbs" class="attach-strip"></div>' +
    '<div class="form-actions followup-actions">' +
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
  var schedule = modal.querySelector('.followup-schedule');
  var hintText = modal.querySelector('#fuNextHintText');
  function syncNext() {
    nextDate.disabled = !nextOn.checked;
    schedule.classList.toggle('is-off', !nextOn.checked);
    hintText.textContent = nextOn.checked ? '会显示在今日与后续待办中' : '本次不再安排跟进提醒';
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
    var quoteSelect = modal.querySelector('[name="quote_id"]');
    if (quoteSelect && quoteSelect.value) { payload.quote_id = Number(quoteSelect.value); }
    close();
    if (typeof opts.onSubmit === 'function') { opts.onSubmit(payload); }
  });
}

/* 渲染实体跟进页 */
function renderEntityFollowPage(root, opts) {
  var titleHtml = opts.titleHtml || (
    '<div class="entity-title-main"><h2><a class="crumb" href="' + opts.backHash + '">‹ ' +
    esc(opts.backLabel) + '</a> / ' + esc(opts.title) + '</h2></div>'
  );
  root.innerHTML =
    (opts.hideEntityCard ? '' :
      '<div class="card">' +
      '<div class="card-head entity-title-head">' +
      titleHtml +
      (opts.badgesHtml ? '<div class="entity-title-badges">' + opts.badgesHtml + '</div>' : '') +
      '</div>' +
      (opts.infoHtml || '') +
      (opts.actionsHtml ? '<div class="form-actions" style="justify-content:flex-start;flex-wrap:wrap">' + opts.actionsHtml + '</div>' : '') +
      '</div>') +
    (opts.beforeTimelineHtml || '') +
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
        extraHtml: opts.followExtraHtml || '',
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

/* ===== 产品主档选择器（商机必须从产品库选，旧商机保留型号兜底） ===== */
var PRODUCT_CATALOG_CACHE = null;

function loadProductCatalog(force) {
  if (PRODUCT_CATALOG_CACHE && !force) {
    return Promise.resolve(PRODUCT_CATALOG_CACHE);
  }
  return api('/products').then(function (items) {
    PRODUCT_CATALOG_CACHE = items || [];
    return PRODUCT_CATALOG_CACHE;
  });
}

function findProduct(products, productId) {
  return (products || []).filter(function (product) {
    return String(product.id) === String(productId || '');
  })[0] || null;
}

/* 产品搜索选择器：123 个产品不适合继续用原生 select，按编码/名称/配置即时筛选。 */
var PRODUCT_PICKER_SEQ = 0;

function productDriveText(product) {
  if (!product || !product.drive_type) { return ''; }
  return product.drive_type === 'electric' ? '电动' : '手动';
}

function syncProductDriveField(product, driveSelect, hint) {
  var linkedDrive = product && product.drive_type ? product.drive_type : '';
  if (product) {
    driveSelect.value = linkedDrive;
  }
  driveSelect.disabled = !!linkedDrive;
  driveSelect.setAttribute('aria-disabled', linkedDrive ? 'true' : 'false');
  var field = driveSelect.closest('.field');
  if (field) {
    field.classList.toggle('deal-field-product-locked', !!linkedDrive);
  }
  if (hint) {
    hint.textContent = linkedDrive
      ? '已与关联产品一致，不可单独修改'
      : (product ? '该产品未标注驱动方式，请补充后创建' : '选择产品后会同步产品驱动方式');
  }
  return linkedDrive;
}

function productSearchText(product) {
  return [
    product.code,
    product.name,
    product.category,
    product.series,
    product.structure,
    product.opening_mode,
    product.frame_type,
    product.leaf_type,
    product.edge_type,
    product.config_summary,
    productDriveText(product)
  ].filter(Boolean).join(' ').toUpperCase();
}

function productPickerSelectionHtml(product, emptyLabel) {
  if (!product) {
    return '<button type="button" class="product-picker-placeholder" data-picker-open-search>' +
      '<span class="product-picker-empty-mark">未选</span>' +
      '<div><b>尚未关联产品</b>' +
      '<span>请在上方搜索框输入产品编码、名称或配置</span></div>' +
      '<span class="product-picker-placeholder-action">去搜索 ›</span>' +
      '</button>';
  }
  var unavailable = product.is_active === false || product.form_available === false;
  var meta = [
    product.category,
    product.series,
    product.structure,
    product.opening_mode,
    productDriveText(product)
  ].filter(Boolean);
  return '<div class="product-picker-card">' +
    '<div class="product-picker-card-main">' +
    '<div class="product-picker-card-title">' +
    '<span class="product-picker-code">' + esc(product.code) + '</span>' +
    '<strong>' + esc(product.name) + '</strong>' +
    (unavailable ? '<span class="product-picker-unavailable">不可关联</span>' : '') +
    '</div>' +
    '<div class="product-picker-meta">' + meta.map(function (value) {
      return '<span>' + esc(value) + '</span>';
    }).join('') + '</div>' +
    '<div class="product-picker-config">' +
      esc(product.config_summary || '按产品参数配置') + '</div>' +
    '</div>' +
    '<button type="button" class="product-picker-clear" data-picker-clear ' +
      'aria-label="清除已选产品">×</button>' +
    '</div>';
}

function productPickerHtml(products, currentId, emptyLabel) {
  var selected = findProduct(products, currentId);
  var pickerId = 'productPicker' + (++PRODUCT_PICKER_SEQ);
  var activeCount = (products || []).filter(function (product) {
    return product.is_active !== false && product.form_available !== false;
  }).length;
  var placeholder = '搜索 ' + activeCount + ' 个产品：编码、名称、系列或配置';
  return '<div class="product-picker" data-product-picker data-picker-id="' + pickerId + '" ' +
    'data-empty-label="' + esc(emptyLabel || '搜索并选择产品') + '">' +
    '<input type="hidden" name="product_id" value="' + esc(selected ? selected.id : '') + '">' +
    '<div class="product-picker-search">' +
      '<span class="product-picker-search-icon" aria-hidden="true">⌕</span>' +
      '<input type="search" class="product-picker-input" autocomplete="off" ' +
        'placeholder="' + esc(placeholder) + '" role="combobox" aria-autocomplete="list" ' +
        'aria-label="搜索关联产品" aria-expanded="false" aria-controls="' + pickerId + 'List">' +
      '<span class="product-picker-shortcut" aria-hidden="true">键入筛选</span>' +
    '</div>' +
    '<div class="product-picker-list" id="' + pickerId + 'List" role="listbox" hidden></div>' +
    '<div class="product-picker-selection" data-picker-selection>' +
      productPickerSelectionHtml(selected, emptyLabel) +
    '</div>' +
  '</div>';
}

function bindProductPicker(pickerEl, products, options) {
  options = options || {};
  var input = pickerEl.querySelector('.product-picker-input');
  var hidden = pickerEl.querySelector('input[name="product_id"]');
  var list = pickerEl.querySelector('.product-picker-list');
  var selection = pickerEl.querySelector('[data-picker-selection]');
  var emptyLabel = pickerEl.getAttribute('data-empty-label') || '搜索并选择产品';
  var activeIndex = -1;
  var currentProduct = findProduct(products, hidden.value);

  function available(product) {
    return product.is_active !== false && product.form_available !== false;
  }

  function emitChange(product) {
    if (typeof options.onChange === 'function') {
      options.onChange(product || null);
    }
  }

  function optionsInList() {
    return Array.prototype.slice.call(
      list.querySelectorAll('[data-product-id]:not([disabled])')
    );
  }

  function setActive(nextIndex) {
    var items = optionsInList();
    items.forEach(function (item) { item.classList.remove('active'); });
    if (!items.length) { activeIndex = -1; return; }
    activeIndex = Math.max(0, Math.min(nextIndex, items.length - 1));
    items[activeIndex].classList.add('active');
    input.setAttribute('aria-activedescendant', items[activeIndex].id);
    items[activeIndex].scrollIntoView({ block: 'nearest' });
  }

  function close() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    activeIndex = -1;
  }

  function render() {
    var query = String(input.value || '').trim().toUpperCase();
    var allHits = (products || []).filter(function (product) {
      return !query || productSearchText(product).indexOf(query) >= 0;
    });
    var hits = allHits.slice(0, 12);
    list.innerHTML = hits.length ? hits.map(function (product, index) {
      var enabled = available(product);
      var detail = [product.category, product.series, product.structure,
        product.opening_mode, productDriveText(product), product.config_summary]
        .filter(Boolean).join(' · ');
      return '<button type="button" class="product-picker-option' +
        (enabled ? '' : ' is-disabled') + '" id="' + pickerEl.getAttribute('data-picker-id') +
        'Option' + index + '" data-product-id="' + product.id + '" role="option" ' +
        (enabled ? '' : 'disabled ') + 'aria-selected="' +
        (String(product.id) === String(hidden.value) ? 'true' : 'false') + '">' +
        '<span class="product-picker-option-head">' +
          '<span class="product-picker-code">' + esc(product.code) + '</span>' +
          '<strong>' + esc(product.name) + '</strong>' +
          (productDriveText(product) ? '<span class="product-picker-drive">' +
            esc(productDriveText(product)) + '</span>' : '') +
          (enabled ? '' : '<span class="product-picker-unavailable">不可关联</span>') +
        '</span>' +
        '<span class="product-picker-option-detail">' + esc(detail || '产品参数待补充') +
        '</span></button>';
    }).join('') : '<div class="product-picker-empty">' +
      '<b>没有匹配的产品</b><span>试试产品编码的一部分，或换用系列/结构关键词。</span></div>';
    list.insertAdjacentHTML('beforeend',
      '<div class="product-picker-result-count">' +
      (allHits.length > hits.length
        ? '匹配 ' + allHits.length + ' 个，显示前 ' + hits.length + ' 个'
        : '共 ' + allHits.length + ' 个结果') + '</div>');
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    activeIndex = -1;
  }

  function refreshSelection(product) {
    currentProduct = product || null;
    hidden.value = currentProduct ? String(currentProduct.id) : '';
    selection.innerHTML = productPickerSelectionHtml(currentProduct, emptyLabel);
    emitChange(currentProduct);
  }

  function choose(product) {
    if (!product || !available(product)) { return; }
    input.value = '';
    refreshSelection(product);
    close();
  }

  input.addEventListener('focus', function () {
    input.removeAttribute('aria-activedescendant');
    render();
  });
  input.addEventListener('input', render);
  input.addEventListener('keydown', function (ev) {
    var items = optionsInList();
    if (ev.key === 'ArrowDown') {
      ev.preventDefault();
      if (list.hidden) { render(); }
      setActive(activeIndex + 1);
    } else if (ev.key === 'ArrowUp') {
      ev.preventDefault();
      setActive(activeIndex <= 0 ? items.length - 1 : activeIndex - 1);
    } else if (ev.key === 'Enter' && activeIndex >= 0 && !list.hidden) {
      ev.preventDefault();
      var active = items[activeIndex];
      if (active) { choose(findProduct(products, active.getAttribute('data-product-id'))); }
    } else if (ev.key === 'Escape') {
      close();
    }
  });
  input.addEventListener('blur', function () {
    setTimeout(close, 160);
  });
  list.addEventListener('click', function (ev) {
    var option = ev.target.closest('[data-product-id]');
    if (!option || option.disabled) { return; }
    choose(findProduct(products, option.getAttribute('data-product-id')));
  });
  selection.addEventListener('click', function (ev) {
    if (ev.target.closest('[data-picker-clear]')) {
      input.value = '';
      refreshSelection(null);
      input.focus();
      return;
    }
    if (ev.target.closest('[data-picker-open-search]')) {
      input.focus();
    }
  });

  return {
    getProduct: function () { return currentProduct; },
    getValue: function () { return hidden.value; },
    clear: function () { input.value = ''; refreshSelection(null); close(); },
    focus: function () { input.focus(); }
  };
}

function dealConvertSourceHtml(sourceName, sourceType) {
  var isCustomer = sourceType === 'customer';
  return '<div class="deal-convert-source">' +
    '<span class="deal-convert-source-mark">' + (isCustomer ? '客' : '线') + '</span>' +
    '<div><span class="deal-convert-source-label">' +
      (isCustomer ? '从客户跟进转商机' : '从线索跟进转商机') + '</span>' +
      '<strong>' + esc(sourceName) + '</strong></div>' +
    '<span class="deal-convert-source-note">' +
      (isCustomer ? '商机将归入当前客户' : '将自动建立客户档案') + '</span>' +
    '</div>';
}

function dealConvertFormHtml(formId, products, sourceName, sourceType) {
  var isCustomer = sourceType === 'customer';
  return '<form id="' + formId + '" class="form-grid deal-convert-form" autocomplete="off">' +
    dealConvertSourceHtml(sourceName, sourceType) +
    '<section class="deal-convert-section">' +
      '<div class="deal-convert-section-head">' +
        '<div><span class="deal-convert-step">01</span>' +
          '<div><h4>确认创建商机</h4><p>商机用于汇总本轮报价与跟进，无需先填写备注</p></div></div>' +
      '</div>' +
      (isCustomer
        ? '<div class="deal-convert-confirm-copy">将从当前客户创建一条新商机，之后可继续添加报价单。</div>'
        : '<div class="deal-convert-warning"><b>线索将移出线索池</b>' +
          '<span>创建商机后，这条记录不再在线索中显示，请到客户档案中继续跟进。</span></div>') +
    '</section>' +
    '<p class="deal-convert-footnote">' +
      (isCustomer
        ? '商机创建后，在商机页创建报价单并关联合适的产品。'
        : '商机创建后会同时建立客户档案，原线索及其标签、跟进记录会迁移到客户名下。') +
    '</p>' +
    '<div class="form-actions">' +
      '<button type="button" class="btn modal-cancel">取消</button>' +
      '<button type="submit" class="btn btn-primary">确定创建商机</button>' +
    '</div>' +
  '</form>';
}

function bindDealConvertForm(form, products, onSubmit) {
  var submitButton = form.querySelector('button[type="submit"]');

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var payload = { note: null };
    submitButton.disabled = true;
    var request = onSubmit(payload);
    if (request && typeof request.catch === 'function') {
      request.catch(function (err) {
        toast(err && err.message ? err.message : '创建商机失败', true);
        submitButton.disabled = false;
      });
    }
  });

  return null;
}

/* 线索 / 客户转商机共用弹层，确保字段与交互完全一致。 */
function openDealConvertModal(source, sourceType) {
  var isCustomer = sourceType === 'customer';
  var sourceId = Number(source && source.id);
  if (!sourceId) {
    toast('来源记录不存在', true);
    return;
  }

  var sourceName = isCustomer
    ? (source.name || source.company_name || ('客户 #' + sourceId))
    : (source.name || source.company_name || ('线索 #' + sourceId));

  var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
    '<div class="modal-overlay"></div>' +
    '<div class="modal-content wide deal-convert-modal">' +
    '<div class="modal-header deal-convert-modal-head">' +
      '<div><span class="deal-convert-kicker">销售流程 · 新建商机</span>' +
      '<h3>转商机</h3><p>确认后创建商机，产品与金额在报价单中维护</p></div>' +
      '<button type="button" class="btn btn-link modal-close" aria-label="关闭">×</button>' +
    '</div>' +
    '<div class="modal-body">' +
      dealConvertFormHtml('dealConvertForm', [], sourceName, sourceType) +
    '</div></div>';
    document.body.appendChild(modal);

    function close() {
      if (modal.parentNode) { document.body.removeChild(modal); }
    }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);

    var form = modal.querySelector('form');
    bindDealConvertForm(form, [], function (deal) {
      var request = isCustomer
        ? api('/deals', {
          method: 'POST',
          body: {
            customer_id: sourceId,
            note: null
          }
        })
        : api('/leads/' + sourceId + '/convert', {
          method: 'POST',
          body: { mode: 'new', deal: deal }
        });
      return request.then(function (res) {
        var created = isCustomer ? res : (res && res.deal);
        toast('已转商机');
        close();
        invalidateCustomerIndex();
        if (created && created.id) { navigate('#/deals/' + created.id); }
        else { navigate('#/deals'); }
        return res;
      });
    });
}
