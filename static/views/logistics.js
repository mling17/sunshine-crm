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

/* ---------------- 列表（Ticket #15）：服务端分页/排序/筛选 ----------------
 * 与线索/客户/商机/产品页同一套共享外壳口径（Ticket #9/#10/#13/#14）：
 * page/size/sort/order 与筛选条件（active 仅看启用、q 关键词）一起写入
 * #/logistics hash URL（history.replaceState，刷新或分享后状态保持）；
 * 改排序、每页条数或任一筛选条件都自动回第 1 页；筛选与排序全部在服务端执行。
 * 默认排序（issue #8）：被订单关联次数倒序，由后端维护，不是可排序列。
 */
var CARRIER_SORT_KEYS = ['name', 'address'];

function readCarrierListQuery(query) {
    var page = parseInt(query.get('page'), 10);
    var size = parseInt(query.get('size'), 10);
    var sort = query.get('sort') || '';
    var order = query.get('order') || '';
    if (!(page >= 1)) { page = 1; }
    if (LIST_PAGE_SIZES.indexOf(size) < 0) { size = 20; }
    if (CARRIER_SORT_KEYS.indexOf(sort) < 0) { sort = ''; }
    if (order !== 'asc' && order !== 'desc') { order = 'desc'; }
    return {
        page: page, size: size, sort: sort, order: order,
        active: query.get('active') || '',
        q: (query.get('q') || '').trim()
    };
}

function carrierListHash(list) {
    var p = new URLSearchParams();
    if (list.active) { p.set('active', list.active); }
    if (list.q) { p.set('q', list.q); }
    p.set('page', String(list.page));
    p.set('size', String(list.size));
    if (list.sort) {
        p.set('sort', list.sort);
        p.set('order', list.order);
    }
    return '#/logistics?' + p.toString();
}

/* 状态变更统一入口：合并 patch 写 hash；除翻页外任何变更（条数/排序/任一筛选）都回第 1 页 */
function updateCarrierListState(root, patch) {
    var cur = readCarrierListQuery(parseRoute().query);
    var next = {
        page: cur.page, size: cur.size, sort: cur.sort, order: cur.order,
        active: cur.active, q: cur.q
    };
    Object.keys(patch).forEach(function (k) { next[k] = patch[k]; });
    if (patch.page === undefined) { next.page = 1; }
    if (!next.sort) { next.order = 'desc'; }
    history.replaceState(null, '', carrierListHash(next));
    return next;
}

function viewLogistics(root) {
    var list = readCarrierListQuery(parseRoute().query);
    root.innerHTML =
        '<div class="card">' +
        '<div class="card-head"><h2>物流公司 <span class="badge muted" id="carrierTotal"></span></h2>' +
        '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">' +
        '<input id="carrierSearch" type="search" placeholder="搜公司 / 联系人 / 电话" ' +
        'value="' + esc(list.q) + '" autocomplete="off" style="width:180px">' +
        '<button type="button" class="btn btn-sm btn-primary" id="btnNewCarrier">＋ 新增物流公司</button>' +
        '<button type="button" class="btn btn-sm" id="btnToggleActive">' +
        (list.active === '1' ? '显示全部' : '只显示启用') + '</button>' +
        '</div></div>' +
        '<p class="small muted" style="margin-top:0">被关联过的公司<b>只能停用不能删除</b>；' +
        '一个公司可维护多个联系人（业务 / 调度 / 结算）；默认按被订单关联次数倒序。</p>' +
        '</div>' +
        '<div class="card">' +
        '<div id="carrierShell"><div id="carrierList"><p class="loading">加载中…</p></div>' +
        '<div id="carrierPager"></div></div>' +
        '</div>';

    bindListShell($('#carrierShell', root), {
        onPage: function (p) { updateCarrierListState(root, { page: p }); loadCarriers(root); },
        onSize: function (s) { updateCarrierListState(root, { size: s }); loadCarriers(root); },
        onSort: function (key, order) {
            var nextOrder = cycleSortOrder(order);
            if (nextOrder) { updateCarrierListState(root, { sort: key, order: nextOrder }); }
            else { updateCarrierListState(root, { sort: '' }); }
            loadCarriers(root);
        }
    });

    bindOps(root, {
        edit: function (id) { return openCarrierForm(id, root); },
        toggle: function (id) { return toggleCarrier(id, root); },
        del: function (id) { return deleteCarrier(id, root); }
    });

    $('#btnNewCarrier', root).addEventListener('click', function () { openCarrierForm(null, root); });
    $('#btnToggleActive', root).addEventListener('click', function () {
        updateCarrierListState(root, { active: list.active === '1' ? '' : '1' });
        loadCarriers(root);
    });
    var searchEl = $('#carrierSearch', root);
    var timer = null;
    function applyCarrierSearch() {
        updateCarrierListState(root, { q: String(searchEl.value || '').trim() });
        loadCarriers(root);
    }
    searchEl.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(applyCarrierSearch, 300);
    });
    searchEl.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Enter') { return; }
        clearTimeout(timer);
        applyCarrierSearch();
    });

    return loadCarriers(root);
}

function loadCarriers(root) {
    var listEl = $('#carrierList', root);
    var pagerEl = $('#carrierPager', root);
    if (!listEl) { return Promise.resolve(); }
    listEl.innerHTML = '<p class="loading">加载中…</p>';

    var list = readCarrierListQuery(parseRoute().query);
    var params = new URLSearchParams();
    if (list.q) { params.set('q', list.q); }
    if (list.active) { params.set('active', list.active); }
    params.set('page', String(list.page));
    params.set('size', String(list.size));
    if (list.sort) { params.set('sort', list.sort); params.set('order', list.order); }

    return api('/carriers?' + params.toString()).then(function (res) {
        var totalEl = $('#carrierTotal', root);
        if (totalEl) { totalEl.textContent = (res && res.total) || 0; }
        listEl.innerHTML = dataTable([
            { title: '公司名称', sortKey: 'name', render: function (c) {
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
            { title: '地址', sortKey: 'address', render: function (c) { return esc(c.address || '—'); } },
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
        ], (res && res.items) || [], list.q ? '没有匹配的物流公司' : '还没有物流公司，点右上「新增物流公司」', '', '',
        { key: list.sort, order: list.order });

        pagerEl.innerHTML = listPagerHtml(res);
    }).catch(function (err) {
        listEl.innerHTML = '<p class="err">' + esc(err.message) + '</p>';
    });
}

/* ---------------- 新增 / 编辑（多联系人） ---------------- */
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
