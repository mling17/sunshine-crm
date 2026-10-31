/* ============================================================================
 * 物流公司（Demo 版，覆盖正式版 views/logistics.js）
 * 用户 2026-10-31 定稿：增删改查 + **显示该物流公司被订单关联的次数**
 * ==========================================================================*/

function viewLogistics(root, route) {
  var activeOnly = route && route.query.get('active') === '1';
  var list = (window.DEMO.carriers || []).slice();
  if (activeOnly) { list = list.filter(function (c) { return c.is_active; }); }
  list.sort(function (a, b) { return (b.used || 0) - (a.used || 0); });

  var totalUsed = (window.DEMO.carriers || []).reduce(function (s, c) { return s + (c.used || 0); }, 0);

  root.innerHTML =
    '<div class="card">' +
      '<div class="card-head"><h2>物流公司 <span class="badge muted">' + list.length + '</span></h2>' +
        '<div class="btn-row">' +
          '<button type="button" class="btn btn-sm btn-primary" id="btnNewCarrier">＋ 新增物流公司</button>' +
          '<button type="button" class="btn btn-sm" id="btnToggleActive">' +
            (activeOnly ? '显示全部' : '只显示启用') + '</button>' +
        '</div>' +
      '</div>' +
      '<p class="small muted" style="margin-top:0">共被订单关联 <b>' + totalUsed + '</b> 次；' +
        '被关联过的公司<b>只能停用不能删除</b>（历史订单要显示原名）。</p>' +
    '</div>' +
    '<div class="card">' +
      dataTable([
        { title: '公司名称', render: function (c) {
            return esc(c.name) + (c.is_active ? '' : ' <span class="badge muted">已停用</span>');
          } },
        { title: '联系人', render: function (c) { return esc(c.contact || '—'); } },
        { title: '电话', render: function (c) { return esc(c.phone || '—'); }, nowrap: true },
        { title: '备注', render: function (c) { return esc(c.note || '—'); } },
        { title: '被订单关联', align: 'center', nowrap: true, render: function (c) {
            return (c.used || 0) > 0
              ? '<a href="#/orders"><span class="badge ok">' + c.used + ' 次</span></a>'
              : '<span class="muted">0 次</span>';
          } },
        { title: '操作', nowrap: true, render: function (c) {
            return opButtons([
              { op: 'edit', arg: c.id, label: '编辑' },
              { op: 'toggle', arg: c.id, label: c.is_active ? '停用' : '启用' },
              (c.used || 0) > 0
                ? { op: 'del', arg: c.id, label: '删除', disabled: true, tip: '被 ' + c.used + ' 个订单引用，只能停用' }
                : { op: 'del', arg: c.id, label: '删除', danger: true }
            ]);
          } }
      ], list, '还没有物流公司，点右上「新增物流公司」') +
    '</div>';

  $$('[data-op]', root).forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (btn.disabled) { return; }
      var op = btn.getAttribute('data-op');
      var id = Number(btn.getAttribute('data-arg'));
      var c = (window.DEMO.carriers || []).filter(function (x) { return x.id === id; })[0];
      if (!c) { return; }
      if (op === 'edit') { openCarrierForm(id); }
      else if (op === 'toggle') {
        c.is_active = !c.is_active;
        toast(c.is_active ? '已启用' : '已停用（历史订单仍显示原名）');
        render();
      } else if (op === 'del') {
        if (!window.confirm('删除物流公司「' + c.name + '」？')) { return; }
        window.DEMO.carriers = window.DEMO.carriers.filter(function (x) { return x.id !== id; });
        toast('已删除（演示）');
        render();
      }
    });
  });

  $('#btnNewCarrier', root).addEventListener('click', function () { openCarrierForm(null); });
  $('#btnToggleActive', root).addEventListener('click', function () {
    navigate('#/logistics' + (activeOnly ? '' : '?active=1'));
  });
}

function openCarrierForm(id) {
  var c = id ? (window.DEMO.carriers || []).filter(function (x) { return x.id === Number(id); })[0] : null;
  var isEdit = !!c;
  var d = c || { is_active: true };

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content">' +
      '<div class="modal-header"><h3>' + (isEdit ? '编辑物流公司' : '新增物流公司') + '</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="carrierFormEl" autocomplete="off">' +
        '<div class="field"><label>公司名称 *</label>' +
          '<input name="name" required maxlength="64" value="' + esc(d.name || '') + '"></div>' +
        '<div class="row-2">' +
          '<div class="field"><label>联系人</label><input name="contact" maxlength="32" value="' + esc(d.contact || '') + '"></div>' +
          '<div class="field"><label>电话</label><input name="phone" maxlength="32" value="' + esc(d.phone || '') + '"></div>' +
        '</div>' +
        '<div class="field"><label>备注</label><textarea name="note" rows="2" maxlength="200">' + esc(d.note || '') + '</textarea></div>' +
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

  $('#carrierFormEl', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var name = String(f.name.value || '').trim();
    if (!name) { toast('公司名称必填', true); return; }
    var payload = {
      name: name,
      contact: String(f.contact.value || '').trim() || null,
      phone: String(f.phone.value || '').trim() || null,
      note: String(f.note.value || '').trim() || null
    };
    if (isEdit) {
      Object.keys(payload).forEach(function (k) { c[k] = payload[k]; });
      toast('已保存（演示）');
    } else {
      payload.id = Math.max.apply(null, window.DEMO.carriers.map(function (x) { return x.id; })) + 1;
      payload.is_active = true;
      payload.used = 0;
      window.DEMO.carriers.push(payload);
      toast('已新增（演示）');
    }
    close();
    render();
  });
}