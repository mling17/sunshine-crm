/* 客户列表页面逻辑 */
function viewCustomers(root) {
    var st = state.filters;
    return api('/tags').catch(function () { return []; }).then(function (tags) {
        root.innerHTML =
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>客户档案</h2>' +
            '<span class=\"small muted\">客户由线索转化，不在此新建</span></div>' +
            '<div class=\"searchbar\">' +
            '<input id=\"custSearch\" type=\"search\" placeholder=\"搜客户 / 公司 / 联系人 / 电话 / 微信 / 地区\" autocomplete=\"off\" value=\"' + esc(st.q) + '\">' +
            '<button type=\"button\" class=\"btn\" id=\"custSearchBtn\">搜索</button>' +
            '</div>' +
            '<div class=\"chips\" id=\"tagChips\">' + chipHtml(tags, st.tag) + '</div>' +
            '</div>' +
            '<div class=\"card\"><div id=\"custList\"><p class=\"loading\">加载中…</p></div><div id=\"custPager\"></div></div>';

        var searchEl = $('#custSearch', root);
        var timer = null;
        function applySearch() {
            st.q = String(searchEl.value || '').trim();
            st.page = 1;
            loadCustomers(root);
        }
        searchEl.addEventListener('input', function () {
            clearTimeout(timer);
            timer = setTimeout(applySearch, 300);
        });
        searchEl.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter') { ev.preventDefault(); clearTimeout(timer); applySearch(); }
        });
        $('#custSearchBtn', root).addEventListener('click', applySearch);

        $('#tagChips', root).addEventListener('click', function (ev) {
            var btn = ev.target.closest('button[data-tag]');
            if (!btn) { return; }
            st.tag = btn.getAttribute('data-tag') || '';
            st.page = 1;
            $$('#tagChips .chip', root).forEach(function (chip) {
                chip.classList.toggle('active', (chip.getAttribute('data-tag') || '') === st.tag);
            });
            loadCustomers(root);
        });

        return loadCustomers(root);
    });
}

function loadCustomers(root) {
    var st = state.filters;
    var listEl = $('#custList', root);
    var pagerEl = $('#custPager', root);
    if (!listEl) { return Promise.resolve(); }
    listEl.innerHTML = '<p class=\"loading\">加载中…</p>';

    var params = new URLSearchParams();
    params.set('page', String(st.page));
    params.set('size', String(PAGE_SIZE));
    if (st.q) { params.set('search', st.q); }
    if (st.tag) { params.set('tag', st.tag); }

    return api('/customers?' + params.toString()).then(function (res) {
        var items = res.items || [];
        listEl.innerHTML = dataTable([
            { title: '名称', render: function (c) {
                return '<a href="#/customers/' + c.id + '">' + esc(c.name) + '</a>' +
                    (c.is_repeat ? ' <span class="badge ok">老客</span>' : '') +
                    (c.customer_type === 'company'
                        ? '<div class="small muted">联系人：' +
                            esc(c.primary_contact_name || '—') +
                            (c.primary_contact_phone ? ' · ' + esc(c.primary_contact_phone) : '') +
                            '</div>'
                        : '');
            } },
            { title: '类型', nowrap: true, render: function (c) {
                return dictLabel('customer_type', c.customer_type, c.customer_type || '—');
            } },
            { title: '地区', render: function (c) { return esc(c.location || '—'); } },
            { title: '微信号', nowrap: true, render: function (c) { return esc(c.wechat || '—'); } },
            { title: '联系方式', nowrap: true, render: function (c) { return esc(c.phone || '—'); } },
            { title: '标签', render: function (c) {
                return (c.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') || '—';
            } },
            { title: '意向', nowrap: true, render: function (c) { return leadIntentBadge(c.intent_level); } },
            { title: '商机', align: 'center', nowrap: true, render: function (c) { return (c.deals_total || 0) + ' 个'; } },
            { title: '累计成交', align: 'right', nowrap: true, render: function (c) { return money(c.total_closed_amount); } },
            { title: '创建时间', nowrap: true, render: function (c) { return fmtDateTime(c.created_at).slice(0, 10); } },
            { title: '操作', nowrap: true, render: function (c) {
                return opButtons([
                    { op: 'edit', arg: c.id, label: '编辑' },
                    { op: 'follow', arg: c.id, label: '跟进' }
                ]);
            } }
        ], items, st.q || st.tag ? '没有匹配的客户，换个条件试试'
            : '还没有客户：客户由线索转化产生，请先到「线索」把线索转成客户');

        pagerEl.innerHTML = pagerHtml(res);
        pagerEl.onclick = function (ev) {
            var btn = ev.target.closest('button[data-page]');
            if (!btn || btn.disabled) { return; }
            st.page = Number(btn.getAttribute('data-page')) || 1;
            loadCustomers(root);
        };

        bindOps(root, {
            edit: function (id) { return openCustomerEdit(id, root); },
            follow: function (id) { navigate('#/customers/' + id); }
        });
    }).catch(function (err) {
        listEl.innerHTML = '<p class="err">' + esc(err.message) + '</p>';
    });
}

/* 客户转商机复用线索页的通用弹层。 */
function openCustomerDealModal(customer) {
    return openDealConvertModal(customer, 'customer');
}

/* ---------------- 编辑客户（弹层；列表/详情共用） ---------------- */
function openCustomerEdit(id, root) {
    return api('/customers/' + id).then(function (c) {
        var modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML =
            '<div class="modal-overlay"></div>' +
            '<div class="modal-content wide">' +
            '<div class="modal-header"><h3>编辑客户 · ' + esc(c.name) + '</h3>' +
            '<button type="button" class="btn btn-link modal-close">×</button></div>' +
            '<div class="modal-body">' + customerFormHtml(c) + '</div>' +
            '</div>';
        document.body.appendChild(modal);

        function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
        modal.querySelector('.modal-close').addEventListener('click', close);
        modal.addEventListener('click', function (ev) {
            if (ev.target === modal || (ev.target.classList && ev.target.classList.contains('modal-overlay'))) { close(); }
        });

        var form = modal.querySelector('form');
        var actions = form.querySelector('.form-actions');
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'btn modal-cancel';
        cancelBtn.textContent = '取消';
        cancelBtn.addEventListener('click', close);
        if (actions) { actions.insertBefore(cancelBtn, actions.firstChild); }

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var btn = form.querySelector('button[type="submit"]');
            var payload = readCustomerForm(form);
            if (!payload.name) { toast('名称必填', true); return; }
            btn.disabled = true;
            api('/customers/' + c.id, { method: 'PUT', body: payload }).then(function () {
                invalidateCustomerIndex();
                toast('已保存');
                close();
                if (root) { loadCustomers(root); } else { render(); }
            }).catch(function (err) {
                toast(err.message, true);
                btn.disabled = false;
            });
        });
    }).catch(function (err) { toast(err.message, true); });
}

function customerFormHtml(customer) {
    var c = customer || {};
    return '<form class=\"customer-form form-grid\" autocomplete=\"off\">' +
        '<div class=\"row-2\">' +
        '<div class=\"field\"><label>名称 *</label>' +
        '<input name=\"name\" type=\"text\" maxlength=\"64\" required value=\"' + esc(c.name || '') + '\"></div>' +
        '<div class=\"field\"><label>类型</label>' +
                '<select name="customer_type">' + dictOptions('customer_type', c.customer_type || 'personal', '') + '</select></div>' +
        '</div>' +
        '<div class=\"field\"><label>电话</label>' +
        '<input name=\"phone\" type=\"tel\" maxlength=\"32\" inputmode=\"tel\" value=\"' + esc(c.phone || '') + '\"></div>' +
        '<div class=\"field\"><label>微信</label>' +
        '<input name=\"wechat\" type=\"text\" maxlength=\"64\" value=\"' + esc(c.wechat || '') + '\"></div>' +
        '<div class=\"field\"><label>地区</label>' +
        '<input name=\"location\" type=\"text\" maxlength=\"200\" value=\"' + esc(c.location || '') + '\"></div>' +
        '<div class=\"field\"><label>联系人</label>' +
        '<input name=\"company_name\" type=\"text\" maxlength=\"100\" value=\"' + esc(c.company_name || '') + '\"></div>' +
        '<div class=\"field\"><label>来源</label>' +
                '<select name="source">' + dictOptions('customer_source', c.source, '请选择') + '</select></div>' +
        '<div class=\"field\"><label>来源补充（选“其他”填）</label>' +
        '<input name=\"source_other\" type=\"text\" maxlength=\"100\" value=\"' + esc(c.source_other || '') + '\"></div>' +
        '<div class=\"field\"><label>意向</label>' +
                '<select name="intent_level">' + dictOptions('intent_level', c.intent_level || 'medium', '') + '</select></div>' +
        '<div class=\"field\"><label>标签（逗号分隔，如：重点、转介绍）</label>' +
        '<input name=\"tags\" type=\"text\" maxlength=\"400\" value=\"' + esc((c.tags || []).join('、')) + '\"></div>' +
        '<div class=\"field\"><label>备注</label>' +
        '<textarea name=\"note\" maxlength=\"500\">' + esc(c.note || '') + '</textarea></div>' +
        '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">保存</button></div>' +
        '</form>';
}

function readCustomerForm(form) {
    function val(name) {
        var el = form.querySelector('[name=\"' + name + '\"]');
        return el ? String(el.value || '').trim() : '';
    }
    var tags = val('tags').split(/[,，、;；\\s]+/).filter(Boolean).slice(0, MAX_TAGS);
    return {
        name: val('name'),
        phone: val('phone') || null,
        wechat: val('wechat') || null,
        location: val('location') || null,
        customer_type: val('customer_type') || 'personal',
        company_name: val('company_name') || null,
        source: val('source') || null,
        source_other: val('source_other') || null,
        intent_level: val('intent_level') || null,
        note: val('note') || null,
        tags: tags
    };
}

function chipHtml(tags, active) {
    var html = '<button type=\"button\" class=\"chip' + (active ? '' : ' active') + '\" data-tag=\"\">全部</button>';
    return html + (tags || []).map(function (tag) {
        return '<button type=\"button\" class=\"chip' + (active === tag ? ' active' : '') +
            '\" data-tag=\"' + esc(tag) + '\">' + esc(tag) + '</button>';
    }).join('');
}

function pagerHtml(res) {
    var pages = Math.max(1, Math.ceil((res.total || 0) / (res.size || PAGE_SIZE)));
    if (!res.total) { return ''; }
    return '<div class=\"form-actions\" style=\"justify-content:space-between;align-items:center\">' +
        '<button type=\"button\" class=\"btn btn-sm\" data-page=\"' + (res.page - 1) + '\"' +
        (res.page <= 1 ? ' disabled' : '') + '>上一页</button>' +
        '<span class=\"small muted\">第 ' + res.page + ' / ' + pages + ' 页 · 共 ' + res.total + ' 位</span>' +
        '<button type=\"button\" class=\"btn btn-sm\" data-page=\"' + (res.page + 1) + '\"' +
        (res.page >= pages ? ' disabled' : '') + '>下一页</button>' +
    '</div>';
}

/* 客户详情页面逻辑 */
function viewCustomerDetail(root, rawId) {
    var id = Number(rawId);
    if (!id || isNaN(id)) {
        root.innerHTML = '<div class=\"card\">客户 id 不合法，<a href=\"#/customers\">回客户列表</a></div>';
        return Promise.resolve();
    }

    return Promise.all([
        api('/customers/' + id),
        api('/follow-ups?customer_id=' + id + '&include_system=true')
    ]).then(function (all) {
        var c = all[0];
        if (!c) {
            root.innerHTML = '<div class="card">客户不存在，<a href="#/customers">回客户列表</a></div>';
            return;
        }
        var records = followupRecordsFromApi(all[1] || []);
        var deals = c.deals || [];

        var dealHtml = deals.length
            ? '<div id=\"dealList\">' + deals.map(function (d) {
                var item = dealItemHtml(d);
                return item.replace('<div class=\"item-side\">',
                    '<div class=\"item-side\"><a class=\"btn btn-sm\" href=\"#/deals/' + d.id +
                    '\">查看商机</a>');
            }).join('') + '</div>'
            : '<p class=\"empty\">还没有商机</p>';

        var dealsCard =
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>商机（' + deals.length + '）</h2>' +
            '<span class=\"small muted\">商机从客户跟进页创建</span></div>' +
            dealHtml +
            '</div>';

        var contactParts = [c.company_name, c.primary_contact_name, c.primary_contact_phone,
            c.primary_contact_wechat ? '微信 ' + c.primary_contact_wechat : ''].filter(Boolean);
        var actions =
            '<button type=\"button\" class=\"btn btn-sm\" id=\"toggleEditCustomer\">编辑客户</button>' +
            '<button type=\"button\" class=\"btn btn-sm btn-primary\" id=\"custToDeal\">转商机</button>';

        renderEntityFollowPage(root, {
            backHash: '#/customers',
            backLabel: '客户',
            objectType: 'customer',
            title: c.name,
            titleHtml:
                '<div class=\"entity-title-main\"><h2><a class=\"crumb\" href=\"#/customers\">‹ 客户</a> / ' +
                esc(c.name) + '</h2><div class=\"detail-title-tags\">' +
                (c.tags || []).map(function (t) { return '<span class=\"tag\">' + esc(t) + '</span>'; }).join('') +
                '</div></div>',
            badgesHtml: '<span class=\"badge muted\">' +
                esc(dictLabel('customer_type', c.customer_type, c.customer_type || '—')) + '</span>',
            infoHtml: infoGrid([
                ['电话', c.phone || '—'],
                ['微信', c.wechat || '—'],
                ['地区', c.location || '—'],
                ['联系人', contactParts.join(' · ') || '—'],
                ['来源', c.source ? (SOURCE_LABELS[c.source] || c.source) : '—'],
                ['意向', c.intent_level ? (INTENT_LABELS[c.intent_level] || c.intent_level) : '—'],
                ['备注', c.note || '—'],
                ['时间', '建档 ' + fmtDateTime(c.created_at) + ' · 最近更新 ' + fmtDateTime(c.updated_at)]
            ]),
            actionsHtml: actions,
            placeholder: '这次沟通聊了什么？客户是什么态度？下一步做什么？',
            records: records,
            extraHtml: filesCardHtml(collectFiles(records), '这个客户还没有上传图纸 / 报价单 / 现场照片') + dealsCard,
            onSubmit: function (p) {
                var fd = new FormData();
                fd.append('object_type', 'customer');
                fd.append('object_id', String(c.id));
                fd.append('content', p.content);
                fd.append('method', p.method || 'wechat');
                if (p.next_date) { fd.append('next_date', p.next_date); }
                (p.files || []).forEach(function (f) { if (f.file) { fd.append('files', f.file); } });
                api('/follow-ups', { method: 'POST', body: fd }).then(function () {
                    toast('已记录跟进');
                    return render();
                }).catch(function (err) { toast(err.message, true); });
            }
        });

        /* 编辑客户 → 弹层（与列表页同一套逻辑） */
        $('#toggleEditCustomer', root).addEventListener('click', function () {
            openCustomerEdit(c.id, null);
        });
        /* 转商机 → 与线索页共用同一弹层 */
        $('#custToDeal', root).addEventListener('click', function () {
            openCustomerDealModal(c);
        });

        bindDealStageSelects(root);
    });
}
