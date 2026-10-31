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
        '被关联过公司<b>只能停用不能删除</b>。一个公司可维护多个联系人（业务 / 调度 / 结算）。</p>' +
    '</div>' +
    '<div class="card">' +
      dataTable([
        { title: '公司名称', render: function (c) {
            return esc(c.name) + (c.is_active ? '' : ' <span class="badge muted">已停用</span>');
          } },
        { title: '联系人', render: function (c) {
            var cs = c.contacts || [];
            if (!cs.length) { return '<span class="muted">—</span>'; }
            var f0 = cs[0];
            return esc(f0.name) + (f0.role ? '<div class="small muted">' + esc(f0.role) + '</div>' : '') +
              (cs.length > 1 ? ' <span class="badge muted">+' + (cs.length - 1) + '</span>' : '');
          } },
        { title: '电话', nowrap: true, render: function (c) {
            var cs = c.contacts || [];
            return cs.length ? esc(cs[0].phone) : '<span class="muted">—</span>';
          } },
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

  bindOps(root, {
    edit: function (id) { openCarrierForm(id); },
    toggle: function (id) {
      var c = (window.DEMO.carriers || []).filter(function (x) { return x.id === id; })[0];
      if (!c) { return; }
      c.is_active = !c.is_active;
      toast(c.is_active ? '已启用' : '已停用（历史订单仍显示原名）');
      render();
    },
    del: function (id) {
      var c = (window.DEMO.carriers || []).filter(function (x) { return x.id === id; })[0];
      if (!c) { return; }
      if (!window.confirm('删除物流公司「' + c.name + '」？')) { return; }
      window.DEMO.carriers = window.DEMO.carriers.filter(function (x) { return x.id !== id; });
      toast('已删除（演示）');
      render();
    }
  });

  $('#btnNewCarrier', root).addEventListener('click', function () { openCarrierForm(null); });
  $('#btnToggleActive', root).addEventListener('click', function () {
    navigate('#/logistics' + (activeOnly ? '' : '?active=1'));
  });
}

function openCarrierForm(id) {
  var c = id ? (window.DEMO.carriers || []).filter(function (x) { return x.id === Number(id); })[0] : null;
  var isEdit = !!c;
  var d = c || { is_active: true, contacts: [] };
  var contacts = (d.contacts || []).map(function (x) {
    return { name: x.name || '', phone: x.phone || '', role: x.role || '' };
  });
  if (!contacts.length) { contacts = [{ name: '', phone: '', role: '' }]; }

  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML =
    '<div class="modal-content">' +
      '<div class="modal-header"><h3>' + (isEdit ? '编辑物流公司' : '新增物流公司') + '</h3>' +
        '<button type="button" class="btn-link modal-close">×</button></div>' +
      '<form id="carrierFormEl" autocomplete="off">' +
        '<div class="field"><label>公司名称 *</label>' +
          '<input name="name" required maxlength="64" value="' + esc(d.name || '') + '"></div>' +
        '<div class="field">' +
          '<label>联系人（可多个：业务 / 调度 / 结算）</label>' +
          '<div id="contactRows"></div>' +
          '<button type="button" class="btn btn-sm" id="btnAddContact" style="margin-top:8px">＋ 添加联系人</button>' +
        '</div>' +
        '<div class="field"><label>备注</label><input name="note" maxlength="200" value="' + esc(d.note || '') + '"></div>' +
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

  /* 联系人行（可增删） */
  function renderRows() {
    $('#contactRows', modal).innerHTML = contacts.map(function (p, i) {
      return '<div class="row-3 contact-row" data-idx="' + i + '">' +
        '<div class="field"><label>姓名</label>' +
          '<input data-f="name" value="' + esc(p.name) + '" maxlength="32" placeholder="李经理"></div>' +
        '<div class="field"><label>电话</label>' +
          '<input data-f="phone" value="' + esc(p.phone) + '" maxlength="32" placeholder="138…"></div>' +
        '<div class="field"><label>职务</label>' +
          '<div style="display:flex;gap:6px;align-items:center">' +
            '<input data-f="role" value="' + esc(p.role) + '" maxlength="24" placeholder="业务/调度">' +
            '<button type="button" class="btn-link danger" data-del-contact="' + i + '">删</button>' +
          '</div></div>' +
      '</div>';
    }).join('');

    $$('.contact-row input', modal).forEach(function (inp) {
      inp.addEventListener('input', function () {
        var idx = Number(inp.closest('.contact-row').getAttribute('data-idx'));
        contacts[idx][inp.getAttribute('data-f')] = inp.value;
      });
    });
    $$('[data-del-contact]', modal).forEach(function (b) {
      b.addEventListener('click', function () {
        if (contacts.length === 1) { toast('至少留一个联系人', true); return; }
        contacts.splice(Number(b.getAttribute('data-del-contact')), 1);
        renderRows();
      });
    });
  }
  renderRows();

  $('#btnAddContact', modal).addEventListener('click', function () {
    contacts.push({ name: '', phone: '', role: '' });
    renderRows();
  });

  $('#carrierFormEl', modal).addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var name = String(f.name.value || '').trim();
    if (!name) { toast('公司名称必填', true); return; }
    var payload = {
      name: name,
      note: String(f.note.value || '').trim() || null,
      contacts: contacts.filter(function (p) { return p.name || p.phone; })
    };
    if (isEdit) {
      Object.keys(payload).forEach(function (k) { c[k] = payload[k]; });
      toast('已保存（演示）');
    } else {
      payload.id = Math.max.apply(null, (window.DEMO.carriers || []).map(function (x) { return x.id; }).concat([0])) + 1;
      payload.is_active = true;
      payload.used = 0;
      window.DEMO.carriers.push(payload);
      toast('已新增（演示）');
    }
    close();
    render();
  });
}