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
