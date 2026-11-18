/* 跟进历史页面（Ticket #16）
 *
 * 定稿口径：
 *   · 本页只做「跟进流水」：纯历史表格 + 共享列表外壳（三态排序 + 页码 + 每页条数）
 *   · 「记一条跟进」不再放这里 —— 走各业务对象详情页的跟进弹层（openFollowModal）
 *   · 默认只看人工跟进（kind='follow'），与接口默认语义一致；系统履历在详情页看
 *   · page/size/sort/order 与 customer/deal 筛选一起写 #/followups hash URL，
 *     改排序/条数/筛选回第 1 页
 */

/* 排序白名单（与服务端 _FOLLOWUP_SORT_SQL 一致，Ticket #16） */
var FOLLOWUP_SORT_KEYS = ['customer', 'deal_stage', 'content', 'next_date', 'created_at'];

function readFollowupListQuery(query) {
  var page = parseInt(query.get('page'), 10);
  var size = parseInt(query.get('size'), 10);
  var sort = query.get('sort') || '';
  var order = query.get('order') || '';
  if (!(page >= 1)) { page = 1; }
  if (LIST_PAGE_SIZES.indexOf(size) < 0) { size = 20; }
  if (FOLLOWUP_SORT_KEYS.indexOf(sort) < 0) { sort = ''; }
  if (order !== 'asc' && order !== 'desc') { order = 'desc'; }
  return {
    customer: query.get('customer') || '',
    deal: query.get('deal') || '',
    page: page, size: size, sort: sort, order: order
  };
}

function followupListHash(list) {
  var p = new URLSearchParams();
  if (list.customer) { p.set('customer', list.customer); }
  if (list.deal) { p.set('deal', list.deal); }
  p.set('page', String(list.page));
  p.set('size', String(list.size));
  if (list.sort) {
    p.set('sort', list.sort);
    p.set('order', list.order);
  }
  return '#/followups?' + p.toString();
}

/* 状态变更统一入口：合并 patch 写 hash；除翻页外任何变更（条数/排序/筛选）都回第 1 页 */
function updateFollowupListState(root, patch) {
  var cur = readFollowupListQuery(parseRoute().query);
  var next = {
    customer: cur.customer, deal: cur.deal,
    page: cur.page, size: cur.size, sort: cur.sort, order: cur.order
  };
  Object.keys(patch).forEach(function (k) { next[k] = patch[k]; });
  if (patch.page === undefined) { next.page = 1; }
  if (!next.sort) { next.order = 'desc'; }
  history.replaceState(null, '', followupListHash(next));
  return next;
}

function viewFollowups(root) {
  root.innerHTML =
    '<div class="card">' +
    '<div class="card-head"><h2>跟进历史 <span class="badge muted" id="fuTotal"></span></h2>' +
    '<span class="small muted">记跟进请进客户 / 商机 / 订单 / 售后详情页，用「＋ 记一条跟进」弹层</span></div>' +
    '<div id="fuFilter"></div>' +
    '</div>' +
    '<div class="card"><div id="fuShell">' +
    '<div id="fuList"><p class="loading">加载中…</p></div>' +
    '<div id="fuPager"></div>' +
    '</div></div>';

  bindListShell($('#fuShell', root), {
    onPage: function (p) { updateFollowupListState(root, { page: p }); loadFollowups(root); },
    onSize: function (sz) { updateFollowupListState(root, { size: sz }); loadFollowups(root); },
    onSort: function (key, order) {
      var nextOrder = cycleSortOrder(order);
      if (nextOrder) { updateFollowupListState(root, { sort: key, order: nextOrder }); }
      else { updateFollowupListState(root, { sort: '' }); }
      loadFollowups(root);
    }
  });

  bindOps(root, {
    del: function (id) {
      if (!window.confirm('删除这条跟进？')) { return; }
      api('/follow-ups/' + id, { method: 'DELETE' })
        .then(function () { toast('已删除'); return loadFollowups(root); })
        .catch(function (err) { toast(err.message, true); });
    },
    clearFilter: function () {
      updateFollowupListState(root, { customer: '', deal: '' });
      loadFollowups(root);
    }
  });

  return loadFollowups(root);
}

function loadFollowups(root) {
  var listEl = $('#fuList', root);
  var pagerEl = $('#fuPager', root);
  if (!listEl) { return Promise.resolve(); }
  listEl.innerHTML = '<p class="loading">加载中…</p>';

  var list = readFollowupListQuery(parseRoute().query);
  var params = new URLSearchParams();
  if (list.customer) { params.set('customer_id', list.customer); }
  if (list.deal) { params.set('deal_id', list.deal); }
  params.set('page', String(list.page));
  params.set('size', String(list.size));
  if (list.sort) {
    params.set('sort', list.sort);
    params.set('order', list.order);
  }

  return api('/follow-ups?' + params.toString()).then(function (res) {
    var items = (res && res.items) || [];
    var totalEl = $('#fuTotal', root);
    if (totalEl) { totalEl.textContent = String((res && res.total) || 0); }

    /* 深链筛选提示：?customer=N / ?deal=N 进来时给出可清除的筛选条 */
    var filterEl = $('#fuFilter', root);
    if (filterEl) {
      filterEl.innerHTML = (list.customer || list.deal)
        ? '<p class="small muted">已筛选' +
          (list.customer ? '客户 #' + esc(list.customer) : '') +
          (list.deal ? ' 商机 #' + esc(list.deal) : '') +
          ' · <button type="button" class="btn-link" data-op="clearFilter">查看全部跟进</button></p>'
        : '';
    }

    var columns = [
      { title: '客户', sortKey: 'customer', render: function (f) {
        return f.customer_id
          ? '<a href="#/customers/' + f.customer_id + '">' +
            esc(f.customer_name || ('客户 #' + f.customer_id)) + '</a>'
          : esc(f.customer_name || '—');
      } },
      { title: '商机阶段', sortKey: 'deal_stage', nowrap: true, render: function (f) {
        return f.deal_stage && STAGE_LABEL[f.deal_stage]
          ? '<span class="tag">' + esc(STAGE_LABEL[f.deal_stage]) + '</span>' : '—';
      } },
      { title: '跟进内容', sortKey: 'content', render: function (f) { return esc(f.content); } },
      { title: '下次跟进', sortKey: 'next_date', nowrap: true, render: function (f) {
        return esc(f.next_date || '—');
      } },
      { title: '记录时间', sortKey: 'created_at', nowrap: true, render: function (f) {
        return fmtDateTime(f.created_at);
      } },
      { title: '附件', nowrap: true, render: function (f) {
        var photos = (f.photos || []).map(function (p) {
          var url = '/crm' + p.url;
          return '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' +
            '<img src="' + esc(url) + '" alt="' + esc(p.file_name || '照片') + '" loading="lazy" ' +
            'style="max-height:36px;max-width:54px;border-radius:4px"></a>';
        }).join('');
        return photos || (f.photo_count ? '📷 ' + f.photo_count : '—');
      } },
      { title: '操作', nowrap: true, render: function (f) {
        return opButtons([{ op: 'del', arg: f.id, label: '删除' }]);
      } }
    ];

    listEl.innerHTML = dataTable(columns, items,
      (list.customer || list.deal) ? '这个筛选条件下没有跟进记录' : '还没有跟进记录',
      '', '', { key: list.sort, order: list.order });
    pagerEl.innerHTML = listPagerHtml(res);
  }).catch(function (err) {
    listEl.innerHTML = '<p class="err">' + esc(err.message) + '</p>';
  });
}
