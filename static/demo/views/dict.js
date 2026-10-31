/* ============================================================================
 * 数据字典（Demo 版）
 * 规格依据：/opt/data/crm/docs/PAGES-V2.md §2（Q7 分级 / Q8 产品类型下拉 / Q9 不做修改日志）
 *
 * 分级口径：A=可增删改（业务标签） B=只能改名/排序（状态机） C=只能改名（绑逻辑） D=只读
 * ==========================================================================*/
var DICT_LEVEL = {
  A: { name: '可自由维护', cls: 'ok', tip: '可以新增、改名、排序、停用' },
  B: { name: '状态机·仅改名', cls: 'warn', tip: '可以改名和调顺序，不能新增/删除（系统靠它推进流程）' },
  C: { name: '仅改名', cls: 'warn', tip: '可以改名，不能增删（背后绑定必填规则）' },
  D: { name: '系统只读', cls: 'muted', tip: '系统定义，只展示' }
};

function viewDict(root, route) {
  var code = route && route.parts[1] ? route.parts[1] : '';
  return api('/dicts').then(function (dicts) {
    if (code) {
      var target = (dicts || []).filter(function (d) { return d.code === code; })[0];
      if (!target) {
        root.innerHTML = '<div class="card">字典不存在，<a href="#/dict">回字典总览</a></div>';
        return;
      }
      renderDictEditor(root, target);
      return;
    }
    renderDictOverview(root, dicts || []);
  });
}

/* ---------------- 总览 ---------------- */
function renderDictOverview(root, dicts) {
  var rows = dicts.map(function (d) {
    var lv = DICT_LEVEL[d.level] || DICT_LEVEL.D;
    var used = d.items.reduce(function (s, i) { return s + (i.used || 0); }, 0);
    return '<a class="dict-row" href="#/dict/' + d.code + '">' +
      '<div class="dict-row-main">' +
        '<div class="dict-row-name">' + esc(d.name) +
          ' <span class="badge ' + lv.cls + '">' + d.level + ' · ' + lv.name + '</span></div>' +
        '<div class="dict-row-sub small muted">' + esc(d.desc || '') + ' · ' + d.items.length + ' 个选项</div>' +
      '</div>' +
      '<div class="dict-row-side small muted">被引用 ' + used + ' 次 ›</div>' +
    '</a>';
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
    '<div class="card"><div class="dict-list">' + rows + '</div></div>';
}

/* ---------------- 单张字典编辑 ---------------- */
function renderDictEditor(root, dict) {
  var lv = DICT_LEVEL[dict.level] || DICT_LEVEL.D;
  var editable = dict.level === 'A';
  var canRename = dict.level === 'A' || dict.level === 'B' || dict.level === 'C';

  var items = dict.items.slice().sort(function (a, b) { return a.sort - b.sort; });

  var rows = items.map(function (it, idx) {
    var delDisabled = !editable || it.used > 0;
    var delTip = it.used > 0 ? ('有 ' + it.used + ' 条数据在用，只能停用') : (editable ? '删除' : '该字典不允许删除');
    return '<tr>' +
      '<td><code class="dict-key">' + esc(it.key) + '</code></td>' +
      '<td>' + (canRename
        ? '<input class="dict-input" data-rename="' + esc(it.key) + '" value="' + esc(it.label) + '" maxlength="20">'
        : esc(it.label)) + '</td>' +
      '<td>' + (editable
        ? '<input class="dict-sort" type="number" data-sort="' + esc(it.key) + '" value="' + it.sort + '" min="1" max="99">'
        : it.sort) + '</td>' +
      '<td>' + (editable
        ? '<label class="switch"><input type="checkbox" data-toggle="' + esc(it.key) + '"' + (it.enabled ? ' checked' : '') + '><span>' + (it.enabled ? '启用' : '停用') + '</span></label>'
        : (it.enabled ? '启用' : '停用')) + '</td>' +
      '<td class="' + (it.used ? '' : 'muted') + '">' + it.used + ' 条</td>' +
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
        '<button type="button" class="btn btn-sm" id="btnAddItem">+ 新增选项</button>' +
      '</div>'
    : '<p class="small muted">该字典为「' + lv.name + '」，' + esc(lv.tip) + '。</p>';

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head">' +
        '<h2><a href="#/dict" class="crumb">‹ 数据字典</a> / ' + esc(dict.name) + '</h2>' +
        '<span class="badge ' + lv.cls + '">' + dict.level + ' · ' + lv.name + '</span>' +
      '</div>' +
      '<p class="small muted" style="margin-top:0">' + esc(dict.desc || '') + '</p>' +
      '<div class="table-wrap"><table class="dict-table">' +
        '<thead><tr><th>值(key)</th><th>显示名</th><th>排序</th><th>状态</th><th>被引用</th><th>操作</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
      '</table></div>' +
      newRow +
      (canRename || editable
        ? '<div class="form-actions"><button type="button" class="btn btn-primary" id="btnSaveDict">保存修改</button>' +
          '<span class="small muted">改显示名后，历史数据里显示的文字会跟着变（数据里存的是 key）</span></div>'
        : '') +
    '</div>' +
    '<div class="card"><div class="card-head"><h2>规则</h2></div>' +
      '<ul class="small muted" style="margin:0;padding-left:18px;line-height:1.9">' +
        '<li><b>被引用的选项禁止删除</b>，只能停用（沿用「被引用的物流公司禁止删除」的口径）。</li>' +
        '<li><b>停用</b>后新建/编辑的下拉里不再出现，但历史数据照常显示中文名。</li>' +
        '<li><b>值(key)</b> 保存后不可修改，历史数据靠它关联。</li>' +
        '<li>状态机类字典（B）只能改名，新增会让订单/商机流程走不通。</li>' +
      '</ul></div>';

  /* 交互：全部先写内存，点保存才提示（演示） */
  $$('[data-rename]', root).forEach(function (inp) {
    inp.addEventListener('change', function () {
      var key = inp.getAttribute('data-rename');
      dict.items.forEach(function (i) { if (i.key === key) { i.label = inp.value.trim() || i.label; } });
    });
  });
  $$('[data-sort]', root).forEach(function (inp) {
    inp.addEventListener('change', function () {
      var key = inp.getAttribute('data-sort');
      dict.items.forEach(function (i) { if (i.key === key) { i.sort = Number(inp.value) || 99; } });
    });
  });
  $$('[data-toggle]', root).forEach(function (chk) {
    chk.addEventListener('change', function () {
      var key = chk.getAttribute('data-toggle');
      dict.items.forEach(function (i) { if (i.key === key) { i.enabled = chk.checked; } });
      chk.parentNode.querySelector('span').textContent = chk.checked ? '启用' : '停用';
    });
  });
  $$('[data-del]', root).forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (btn.disabled) { return; }
      var key = btn.getAttribute('data-del');
      dict.items = dict.items.filter(function (i) { return i.key !== key; });
      toast('已删除（演示：点保存后才生效）');
      render();
    });
  });

  var addBtn = $('#btnAddItem', root);
  if (addBtn) {
    addBtn.addEventListener('click', function () {
      var k = ($('#newKey').value || '').trim();
      var l = ($('#newLabel').value || '').trim();
      if (!k || !l) { toast('值和显示名都要填', true); return; }
      if (dict.items.some(function (i) { return i.key === k; })) { toast('这个值已存在', true); return; }
      dict.items.push({ key: k, label: l, sort: dict.items.length + 1, enabled: true, used: 0 });
      toast('已新增「' + l + '」（演示：仅本次会话有效）');
      render();
    });
  }

  var saveBtn = $('#btnSaveDict', root);
  if (saveBtn) {
    saveBtn.addEventListener('click', function () {
      toast('已保存（演示环境不落盘）');
    });
  }
}