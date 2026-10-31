/* ============================================================================
 * 数据字典（V2 正式版 · 移植自 static/demo/views/dict.js）
 * 规格：docs/PAGES-V2.md §2（Q7 分级 / Q8 产品类型下拉 / Q9 不做修改日志）
 *       docs/PLAN-menu-dict-align.md（D2：照 demo 移植，写操作接真实 API）
 *
 * 分级口径（服务端 app/routers/dicts.py 强制，前端只是顺手给出可用控件）：
 *   A=可增删改（业务标签） B=只能改名/排序（状态机） C=只能改名（绑逻辑） D=只读
 *
 * 与 demo 版的关键差异（唯一差异）：
 *   写操作全部走真实 API —— POST /dicts/{code}/items、PUT /dicts/{code}/items/{key}、
 *   DELETE /dicts/{code}/items/{key}；**每次写成功或失败后都重新 GET 服务器数据**，
 *   绝不在本地对象上改 label/sort/enabled 冒充成功。
 *   因此没有「保存修改」按钮：单字段 change 即时落库（demo 里的「保存」在真实后端下
 *   等于第二个假动作），底部提示改为「改动即时生效」。
 *
 * 依赖 app.js 暴露到 window 的裸名：api / $ / $$ / esc / toast / render
 * ==========================================================================*/

var DICT_LEVEL = {
  A: { name: '可自由维护', cls: 'ok', tip: '可以新增、改名、排序、停用' },
  B: { name: '状态机·仅改名', cls: 'warn', tip: '可以改名和调顺序，不能新增/删除（系统靠它推进流程）' },
  C: { name: '仅改名', cls: 'warn', tip: '可以改名，不能增删（背后绑定必填规则）' },
  D: { name: '系统只读', cls: 'muted', tip: '系统定义，只展示' }
};

function dictItemUrl(code, key) {
  var url = '/dicts/' + encodeURIComponent(code) + '/items';
  return key === undefined || key === null || key === '' ? url : url + '/' + encodeURIComponent(key);
}

function dictUsedTotal(dict) {
  return (dict.items || []).reduce(function (sum, item) { return sum + (item.used || 0); }, 0);
}

/* ---------------- 入口 ---------------- */

function viewDict(root, route) {
  var code = route && route.parts[1] ? route.parts[1] : '';
  return api('/dicts').then(function (dicts) {
    var list = dicts || [];
    renderDictOverview(root, list);
    /* 维护一律在模态框里做；#/dict/{code} 直达时自动打开弹窗 */
    if (code) {
      var target = list.filter(function (d) { return d.code === code; })[0];
      if (target) { openDictModal(target); }
      else { toast('字典 ' + code + ' 不存在', true); }
    }
  });
}

/* ---------------- 总览 ---------------- */

function renderDictOverview(root, dicts) {
  var rows = dicts.map(function (d) {
    var lv = DICT_LEVEL[d.level] || DICT_LEVEL.D;
    var items = d.items || [];
    var used = dictUsedTotal(d);
    return '<button type="button" class="dict-row" data-dict="' + esc(d.code) + '">' +
      '<div class="dict-row-main">' +
        '<div class="dict-row-name">' + esc(d.name) +
          ' <span class="badge ' + lv.cls + '">' + esc(d.level) + ' · ' + esc(lv.name) + '</span></div>' +
        '<div class="dict-row-sub small muted">' + esc(d.desc || '') + ' · ' + items.length + ' 个选项</div>' +
      '</div>' +
      '<div class="dict-row-side small muted">被引用 ' + used + ' 次 ›</div>' +
    '</button>';
  }).join('');

  var aCount = dicts.filter(function (d) { return d.level === 'A'; }).length;

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head"><h2>数据字典</h2><span class="small muted">共 ' + dicts.length + ' 张</span></div>' +
      '<p class="small muted" style="margin-top:0">' +
        '系统里所有下拉选项都在这里。<b>' + aCount + ' 张可以自己增删改</b>（来源、意向、产品类型…），' +
        '状态机类的只能改名不能增删，避免流程走不通。' +
      '</p>' +
      '<div class="dict-legend">' +
        Object.keys(DICT_LEVEL).map(function (k) {
          var v = DICT_LEVEL[k];
          return '<span class="dict-legend-item"><span class="badge ' + v.cls + '">' + k + '</span> ' +
            esc(v.name) + '<span class="small muted">（' + esc(v.tip) + '）</span></span>';
        }).join('') +
      '</div>' +
    '</div>' +
    '<div class="card"><div class="dict-list">' +
      (rows || '<p class="small muted">暂无字典</p>') +
    '</div></div>';

  $$('[data-dict]', root).forEach(function (btn) {
    btn.addEventListener('click', function () {
      var code = btn.getAttribute('data-dict');
      var d = dicts.filter(function (x) { return x.code === code; })[0];
      if (d) { openDictModal(d); }
    });
  });
}

/* ---------------- 单张字典维护（模态框） ---------------- */

function openDictModal(dict) {
  var lv = DICT_LEVEL[dict.level] || DICT_LEVEL.D;
  var editable = dict.level === 'A';                               // 增删改
  var canRename = dict.level === 'A' || dict.level === 'B' || dict.level === 'C';
  var canSort = dict.level === 'A' || dict.level === 'B';          // 与服务端 _LEVEL_FIELDS 一致
  var busy = false;

  var modal = document.createElement('div');
  modal.className = 'modal';
  document.body.appendChild(modal);

  function close() {
    document.removeEventListener('keydown', onKeydown);
    if (modal.parentNode) { document.body.removeChild(modal); }
  }

  function onKeydown(ev) {
    if (ev.key === 'Escape') { close(); }
  }
  document.addEventListener('keydown', onKeydown);

  function itemsSorted() {
    return (dict.items || []).slice().sort(function (a, b) { return (a.sort || 0) - (b.sort || 0); });
  }

  /* 从服务器重新拉这张字典（写操作的唯一收尾动作：成功失败都回读，绝不本地直改） */
  function reload() {
    return api('/dicts/' + encodeURIComponent(dict.code)).then(function (fresh) {
      /* 保留原对象引用，关闭后再次打开也不会拿总览里的旧顺序。 */
      if (fresh && fresh.code) { Object.assign(dict, fresh); }
      renderBody();
      /* 排序会影响线索/客户等页面的下拉顺序，同步刷新全局字典缓存。 */
      if (typeof ensureDicts === 'function') {
        ensureDicts(true).catch(function () {});
      }
    });
  }

  /* 统一写操作包装：busy 防重复提交，失败 toast 后端原文并回读真实状态 */
  function write(makeRequest, okMessage) {
    if (busy) { return Promise.resolve(); }
    busy = true;
    return makeRequest().then(function () {
      busy = false;
      if (okMessage) { toast(okMessage); }
      return reload();
    }).catch(function (err) {
      busy = false;
      toast(err && err.message ? err.message : '保存失败', true);
      return reload();
    });
  }

  function putItem(key, patch, okMessage) {
    return write(function () {
      return api(dictItemUrl(dict.code, key), { method: 'PUT', body: patch });
    }, okMessage);
  }

  function renderBody() {
    var items = itemsSorted();
    var rows = items.map(function (it, index) {
      var delDisabled = !editable || (it.used || 0) > 0;
      var delTip = (it.used || 0) > 0
        ? ('有 ' + it.used + ' 条数据在用，只能停用')
        : (editable ? '删除' : '该字典不允许删除');
      var orderCell = canSort
        ? '<div class="dict-order-control">' +
            '<span class="dict-order-no">' + (index + 1) + '</span>' +
            '<button type="button" class="dict-order-btn" data-move="up" data-key="' + esc(it.key) + '"' +
              (index === 0 ? ' disabled' : '') + ' aria-label="上移 ' + esc(it.label) + '" title="上移">↑</button>' +
            '<button type="button" class="dict-order-btn" data-move="down" data-key="' + esc(it.key) + '"' +
              (index === items.length - 1 ? ' disabled' : '') + ' aria-label="下移 ' + esc(it.label) + '" title="下移">↓</button>' +
          '</div>'
        : '<span class="dict-order-no" title="该字典不允许排序">' + (index + 1) + '</span>';
      return '<tr>' +
        '<td><code class="dict-key">' + esc(it.key) + '</code></td>' +
        '<td>' + (canRename
          ? '<input class="dict-input" data-rename="' + esc(it.key) + '" value="' + esc(it.label) + '" maxlength="20">'
          : esc(it.label)) + '</td>' +
        '<td class="dict-order-cell">' + orderCell + '</td>' +
        '<td>' + (editable
          ? '<label class="switch"><input type="checkbox" data-toggle="' + esc(it.key) + '"' + (it.enabled ? ' checked' : '') +
            '><span>' + (it.enabled ? '启用' : '停用') + '</span></label>'
          : (it.enabled ? '启用' : '停用')) + '</td>' +
        '<td class="' + (it.used ? '' : 'muted') + '">' + (it.used || 0) + ' 条</td>' +
        '<td>' + (editable
          ? '<button type="button" class="btn-link danger" data-del="' + esc(it.key) + '"' +
              (delDisabled ? ' disabled title="' + esc(delTip) + '"' : '') + '>删除</button>'
          : '<span class="small muted">—</span>') + '</td>' +
      '</tr>';
    }).join('');

    var newRow = editable
      ? '<div class="dict-new">' +
          '<input id="newKey" class="dict-input" placeholder="值（英文/拼音，保存后不可改）" maxlength="24">' +
          '<input id="newLabel" class="dict-input" placeholder="中文显示名" maxlength="20">' +
          '<button type="button" class="btn btn-sm" id="btnAddItem">＋ 新增选项</button>' +
        '</div>'
      : '<p class="small muted">该字典为「' + esc(lv.name) + '」，' + esc(lv.tip) + '。</p>';

    modal.innerHTML =
      '<div class="modal-content wide">' +
        '<div class="modal-header">' +
          '<h3>' + esc(dict.name) + ' <span class="badge ' + lv.cls + '">' + esc(dict.level) + ' · ' + esc(lv.name) + '</span></h3>' +
          '<button type="button" class="btn-link modal-close" aria-label="关闭">×</button>' +
        '</div>' +
        '<div class="modal-body">' +
          (dict.desc ? '<p class="small muted" style="margin-top:0">' + esc(dict.desc) + '</p>' : '') +
          (canSort
            ? '<div class="dict-order-tip"><b>调整顺序：</b>直接点 ↑ / ↓，整组顺序会立即保存，不用再填数字。</div>'
            : '') +
          '<div class="table-wrap"><table class="dict-table">' +
            '<thead><tr><th>值(key)</th><th>显示名</th><th>顺序</th><th>状态</th><th>被引用</th><th>操作</th></tr></thead>' +
            '<tbody>' + (rows || '<tr><td colspan="6" class="small muted">暂无选项</td></tr>') + '</tbody>' +
          '</table></div>' +
          newRow +
          '<ul class="small muted" style="margin:14px 0 0;padding-left:18px;line-height:1.8">' +
            '<li>改动<b>即时保存</b>到服务器，不需要另外点保存。</li>' +
            '<li>被引用的选项<b>禁止删除只能停用</b>；停用后新建单不再出现，历史数据照常显示中文名。</li>' +
            (editable ? '<li>注意：<b>停用后的选项暂时不会出现在本页列表</b>（接口只返回启用项），需要恢复请联系管理员。</li>' : '') +
            '<li><b>值(key)</b> 保存后不可改，历史数据靠它关联。</li>' +
            (dict.level === 'B' ? '<li>状态机类字典只能改名/排序，新增会让订单/商机流程走不通。</li>' : '') +
          '</ul>' +
        '</div>' +
        '<div class="form-actions">' +
          '<button type="button" class="btn modal-cancel">关闭</button>' +
        '</div>' +
      '</div>';

    bindBody();
  }

  function bindBody() {
    $('.modal-close', modal).addEventListener('click', close);
    $('.modal-cancel', modal).addEventListener('click', close);

    $$('[data-rename]', modal).forEach(function (inp) {
      inp.addEventListener('change', function () {
        var key = inp.getAttribute('data-rename');
        var label = (inp.value || '').trim();
        var current = (dict.items || []).filter(function (i) { return i.key === key; })[0];
        if (!label) {
          toast('显示名不能为空', true);
          inp.value = current ? current.label : '';
          return;
        }
        if (current && current.label === label) { return; }
        inp.disabled = true;
        putItem(key, { label: label }, '已改名');
      });
    });

    $$('[data-move]', modal).forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (btn.disabled || busy) { return; }
        var key = btn.getAttribute('data-key');
        var direction = btn.getAttribute('data-move');
        var ordered = itemsSorted();
        var index = ordered.map(function (it) { return it.key; }).indexOf(key);
        var target = direction === 'up' ? index - 1 : index + 1;
        if (index < 0 || target < 0 || target >= ordered.length) { return; }

        var moved = ordered[index];
        ordered[index] = ordered[target];
        ordered[target] = moved;
        var keys = ordered.map(function (it) { return it.key; });
        $$('[data-move]', modal).forEach(function (button) { button.disabled = true; });
        write(function () {
          return api(dictItemUrl(dict.code, 'order'), {
            method: 'PUT',
            body: { keys: keys }
          });
        }, '顺序已更新');
      });
    });

    $$('[data-toggle]', modal).forEach(function (chk) {
      chk.addEventListener('change', function () {
        var key = chk.getAttribute('data-toggle');
        chk.disabled = true;
        putItem(key, { enabled: chk.checked }, chk.checked ? '已启用' : '已停用');
      });
    });

    $$('[data-del]', modal).forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (btn.disabled) { return; }
        var key = btn.getAttribute('data-del');
        var current = (dict.items || []).filter(function (i) { return i.key === key; })[0];
        var tip = '删除选项「' + (current ? current.label : key) + '」？历史数据不引用它才能删。';
        if (!window.confirm(tip)) { return; }
        btn.disabled = true;
        write(function () {
          return api(dictItemUrl(dict.code, key), { method: 'DELETE' });
        }, '已删除');
      });
    });

    var addBtn = $('#btnAddItem', modal);
    if (addBtn) {
      addBtn.addEventListener('click', function () {
        var keyInput = $('#newKey', modal);
        var labelInput = $('#newLabel', modal);
        var key = (keyInput.value || '').trim();
        var label = (labelInput.value || '').trim();
        if (!key || !label) { toast('值和显示名都要填', true); return; }
        if ((dict.items || []).some(function (i) { return i.key === key; })) {
          toast('这个值已存在', true);
          return;
        }
        /* 排在末尾：取当前最大 sort + 1（后端 sort 默认 0 会顶到最前） */
        var maxSort = (dict.items || []).reduce(function (m, i) { return Math.max(m, i.sort || 0); }, 0);
        addBtn.disabled = true;
        write(function () {
          return api('/dicts/' + encodeURIComponent(dict.code) + '/items', {
            method: 'POST',
            body: { key: key, label: label, sort: maxSort + 1, enabled: true }
          });
        }, '已新增「' + label + '」').then(function () {
          var k = $('#newKey', modal);
          var l = $('#newLabel', modal);
          if (k) { k.value = ''; }
          if (l) { l.value = ''; }
        });
      });
    }
  }

  renderBody();
}
