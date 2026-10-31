/* 物流公司页面（2026-10-31 对齐 demo 定稿）
 *
 * 定稿口径：增删改查 + 显示「被订单关联次数」；被关联过的公司只能停用不能删除；
 *          一个公司可维护多个联系人（业务 / 调度 / 结算）。
 *
 * 顺带修掉旧版三个真 bug（旧代码字段名和后端对不上，数据根本没存进去）：
 *   1. 旧 payload 传 contact / note → 后端是 contact_person / address / contacts[]
 *   2. 旧「删除」按钮按 is_active 判断 → 应按 order_count（被订单引用次数）
 *   3. 旧列表读 c.contact / c.note → 永远空
 */

function carrierContacts(c) {
    return (c && c.contacts) || [];
}

/* ---------------- 列表 ---------------- */
function viewLogistics(root, route) {
    var activeOnly = (route && route.query.get('active') === '1');
    var keyword = (route && route.query.get('q')) || '';

    return api('/carriers').then(function (all) {
        var carriers = (all || []).slice();
        var totalUsed = carriers.reduce(function (s, c) { return s + (c.order_count || 0); }, 0);

        var list = carriers;
        if (activeOnly) { list = list.filter(function (c) { return c.is_active; }); }
        if (keyword) {
            list = list.filter(function (c) {
                var hay = [c.name, c.code, c.contact_person, c.phone, c.address].join(' ');
                carrierContacts(c).forEach(function (p) { hay += ' ' + (p.name || '') + ' ' + (p.phone || ''); });
                return hay.indexOf(keyword) >= 0;
            });
        }
        list.sort(function (a, b) { return (b.order_count || 0) - (a.order_count || 0); });

        var rowsHtml = dataTable([
            { title: '公司名称', render: function (c) {
                return '<a href="javascript:void(0)" data-op="edit" data-arg="' + c.id + '">' + esc(c.name) + '</a>' +
                    (c.is_active ? '' : ' <span class="badge muted">已停用</span>') +
                    (c.code ? '<div class="small muted">编号 ' + esc(c.code) + '</div>' : '');
            } },
            { title: '联系人', render: function (c) {
                var cs = carrierContacts(c);
                if (!cs.length) {
                    return c.contact_person
                        ? esc(c.contact_person)
                        : '<span class="muted">—</span>';
                }
                var f0 = cs[0];
                var chips = (f0.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('');
                return esc(f0.name || '—') +
                    (chips ? '<div class="tag-row">' + chips + '</div>' : '') +
                    (cs.length > 1 ? ' <span class="badge muted">+' + (cs.length - 1) + '</span>' : '');
            } },
            { title: '电话', nowrap: true, render: function (c) {
                var cs = carrierContacts(c);
                var phone = cs.length ? cs[0].phone : c.phone;
                return phone ? esc(phone) : '<span class="muted">—</span>';
            } },
            { title: '地址', render: function (c) { return esc(c.address || '—'); } },
            { title: '被订单关联', align: 'center', nowrap: true, render: function (c) {
                return (c.order_count || 0) > 0
                    ? '<a href="#/orders"><span class="badge ok">' + c.order_count + ' 次</span></a>'
                    : '<span class="muted">0 次</span>';
            } },
            { title: '操作', nowrap: true, render: function (c) {
                return opButtons([
                    { op: 'edit', arg: c.id, label: '编辑' },
                    { op: 'toggle', arg: c.id, label: c.is_active ? '停用' : '启用' },
                    (c.order_count || 0) > 0
                        ? { op: 'del', arg: c.id, label: '删除', disabled: true,
                            tip: '被 ' + c.order_count + ' 张订单引用，只能停用' }
                        : { op: 'del', arg: c.id, label: '删除', danger: true }
                ]);
            } }
        ], list, keyword ? '没有匹配的物流公司' : '还没有物流公司，点右上「新增物流公司」');

        root.innerHTML =
            '<div class="card">' +
            '<div class="card-head"><h2>物流公司 <span class="badge muted">' + list.length + '</span></h2>' +
            '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">' +
            '<input id="carrierSearch" type="search" placeholder="搜公司 / 联系人 / 电话" ' +
            'value="' + esc(keyword) + '" autocomplete="off" style="width:180px">' +
            '<button type="button" class="btn btn-sm btn-primary" id="btnNewCarrier">＋ 新增物流公司</button>' +
            '<button type="button" class="btn btn-sm" id="btnToggleActive">' +
            (activeOnly ? '显示全部' : '只显示启用') + '</button>' +
            '</div></div>' +
            '<p class="small muted" style="margin-top:0">共被订单关联 <b>' + totalUsed + '</b> 次；' +
            '被关联过的公司<b>只能停用不能删除</b>。一个公司可维护多个联系人（业务 / 调度 / 结算）。</p>' +
            '</div>' +
            '<div class="card">' + rowsHtml + '</div>';

        bindOps(root, {
            edit: function (id) { return openCarrierForm(id, root); },
            toggle: function (id) { return toggleCarrier(id, root); },
            del: function (id) { return deleteCarrier(id, root); }
        });

        $('#btnNewCarrier', root).addEventListener('click', function () { openCarrierForm(null, root); });
        $('#btnToggleActive', root).addEventListener('click', function () {
            var q = [];
            if (!activeOnly) { q.push('active=1'); }
            if (keyword) { q.push('q=' + encodeURIComponent(keyword)); }
            navigate('#/logistics' + (q.length ? '?' + q.join('&') : ''));
        });
        var searchEl = $('#carrierSearch', root);
        searchEl.addEventListener('keydown', function (ev) {
            if (ev.key !== 'Enter') { return; }
            var q = [];
            if (activeOnly) { q.push('active=1'); }
            var v = String(searchEl.value || '').trim();
            if (v) { q.push('q=' + encodeURIComponent(v)); }
            navigate('#/logistics' + (q.length ? '?' + q.join('&') : ''));
        });
    });
}

/* ---------------- 新增 / 编辑（多联系人） ---------------- */
function openCarrierForm(id, root) {
    var loader = id ? api('/carriers/' + id) : Promise.resolve(null);
    return loader.then(function (c) {
        var isEdit = !!c;
        var d = c || { is_active: true, contacts: [] };
        var contacts = carrierContacts(d).map(function (x) {
            return { name: x.name || '', phone: x.phone || '', tags: (x.tags || []).slice() };
        });
        if (!contacts.length) { contacts = [{ name: '', phone: '', tags: [] }]; }

        var modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML =
            '<div class="modal-overlay"></div>' +
            '<div class="modal-content wide">' +
            '<div class="modal-header"><h3>' + (isEdit ? '编辑物流公司' : '新增物流公司') + '</h3>' +
            '<button type="button" class="btn btn-link modal-close">×</button></div>' +
            '<div class="modal-body">' +
            '<form id="carrierFormEl" class="form-grid" autocomplete="off">' +
            '<div class="row-2">' +
            '<div class="field"><label>公司名称 *</label>' +
            '<input name="name" required maxlength="64" value="' + esc(d.name || '') + '"></div>' +
            '<div class="field"><label>公司编号（可选）</label>' +
            '<input name="code" maxlength="32" value="' + esc(d.code || '') + '"></div>' +
            '</div>' +
            '<div class="field field-wide"><label>地址（可选）</label>' +
            '<input name="address" maxlength="200" value="' + esc(d.address || '') + '"></div>' +
            '<div class="field"><label>联系人（可多个：业务 / 调度 / 结算）</label>' +
            '<div id="contactRows"></div>' +
            '<button type="button" class="btn btn-sm" id="btnAddContact" style="margin-top:8px">＋ 添加联系人</button>' +
            '</div>' +
            '<div class="form-actions">' +
            '<button type="button" class="btn modal-cancel">取消</button>' +
            '<button type="submit" class="btn btn-primary">保存</button>' +
            '</div>' +
            '</form>' +
            '</div></div>';
        document.body.appendChild(modal);

        function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
        modal.querySelector('.modal-close').addEventListener('click', close);
        modal.querySelector('.modal-cancel').addEventListener('click', close);

        function renderRows() {
            modal.querySelector('#contactRows').innerHTML = contacts.map(function (p, i) {
                return '<div class="row-3 contact-row" data-idx="' + i + '">' +
                    '<div class="field"><label>姓名</label>' +
                    '<input data-f="name" value="' + esc(p.name) + '" maxlength="32" placeholder="李经理"></div>' +
                    '<div class="field"><label>电话</label>' +
                    '<input data-f="phone" value="' + esc(p.phone) + '" maxlength="32" placeholder="138…"></div>' +
                    '<div class="field"><label>标签（逗号分隔）</label>' +
                    '<div style="display:flex;gap:6px;align-items:center">' +
                    '<input data-f="tags" value="' + esc((p.tags || []).join('、')) + '" maxlength="40" placeholder="业务、调度、结算">' +
                    '<button type="button" class="btn-link danger" data-del-contact="' + i + '">删</button>' +
                    '</div></div>' +
                    '</div>';
            }).join('');

            $$('.contact-row input', modal).forEach(function (inp) {
                inp.addEventListener('input', function () {
                    var idx = Number(inp.closest('.contact-row').getAttribute('data-idx'));
                    var field = inp.getAttribute('data-f');
                    if (field === 'tags') {
                        contacts[idx].tags = inp.value.split(/[,，、\s]+/).filter(Boolean);
                    } else {
                        contacts[idx][field] = inp.value;
                    }
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

        modal.querySelector('#btnAddContact').addEventListener('click', function () {
            contacts.push({ name: '', phone: '', tags: [] });
            renderRows();
        });

        var form = modal.querySelector('#carrierFormEl');
        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var btn = form.querySelector('button[type="submit"]');
            var name = String(form.querySelector('[name="name"]').value || '').trim();
            if (!name) { toast('公司名称必填', true); return; }

            var cleaned = contacts.filter(function (p) { return p.name || p.phone; });
            var payload = {
                name: name,
                code: String(form.querySelector('[name="code"]').value || '').trim() || null,
                address: String(form.querySelector('[name="address"]').value || '').trim() || null,
                contacts: cleaned
            };
            /* 兼容老字段：列表/别处可能只读 contact_person/phone */
            if (cleaned.length) {
                payload.contact_person = cleaned[0].name || null;
                payload.phone = cleaned[0].phone || null;
            }

            btn.disabled = true;
            var req = isEdit
                ? api('/carriers/' + d.id, { method: 'PUT', body: payload })
                : api('/carriers', { method: 'POST', body: payload });
            req.then(function () {
                toast(isEdit ? '物流公司已保存' : '物流公司已创建');
                close();
                if (root) { viewLogistics(root, parseRoute()); }
            }).catch(function (err) {
                toast(err.message, true);
                btn.disabled = false;
            });
        });
    }).catch(function (err) { toast(err.message, true); });
}

/* ---------------- 启停 / 删除 ---------------- */
function toggleCarrier(id, root) {
    return api('/carriers/' + id).then(function (c) {
        return api('/carriers/' + id, { method: 'PUT', body: { is_active: !c.is_active } }).then(function () {
            toast(c.is_active ? '已停用（历史订单仍显示原名）' : '已启用');
            if (root) { viewLogistics(root, parseRoute()); }
        });
    }).catch(function (err) { toast(err.message, true); });
}

function deleteCarrier(id, root) {
    return api('/carriers/' + id).then(function (c) {
        if ((c.order_count || 0) > 0) {
            toast('有 ' + c.order_count + ' 张订单在用，只能停用不能删除', true);
            return null;
        }
        if (!window.confirm('删除物流公司「' + c.name + '」？')) { return null; }
        return api('/carriers/' + id, { method: 'DELETE' }).then(function () {
            toast('物流公司已删除');
            if (root) { viewLogistics(root, parseRoute()); }
        });
    }).catch(function (err) { toast(err.message, true); });
}
