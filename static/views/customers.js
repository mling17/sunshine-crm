/* 客户列表页面逻辑 */
function customerPrimaryContact(c) {
    return String(c.primary_contact_name || '').trim();
}

function customerContactPhone(c) {
    return String(c.primary_contact_phone || c.phone || '').trim();
}

function customerNameCellHtml(c) {
    var contact = customerPrimaryContact(c);
    var phone = customerContactPhone(c);
    var secondary = [
        c.customer_type === 'company' ? contact : '',
        phone
    ].filter(Boolean).join(' · ');
    return '<div class="lead-name-cell customer-name-cell">' +
        '<div class="lead-name-main">' +
        '<a class="lead-name-link" href="#/customers/' + c.id + '" title="' + esc(c.name) + '">' +
        esc(c.name) + '</a>' +
        (secondary ? '<span class="lead-phone-text" title="' + esc(secondary) + '">' +
            esc(secondary) + '</span>' : '') +
        '</div>' +
        (c.is_repeat ? '<span class="badge ok customer-repeat-badge">老客</span>' : '') +
        '</div>';
}

function viewCustomers(root) {
    var st = state.filters;
    return api('/tags').catch(function () { return []; }).then(function (tags) {
        root.innerHTML =
            '<div class=\"card\">' +
            '<div class=\"card-head lead-page-head\"><div><h2>客户档案</h2>' +
            '<p class=\"card-subtitle\">客户由线索转化，不在此新建；跟进和商机都在客户档案中管理。</p></div></div>' +
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
                return customerNameCellHtml(c);
            } },
            { title: '类型', nowrap: true, render: function (c) {
                return dictLabel('customer_type', c.customer_type, c.customer_type || '—');
            } },
            { title: '地区', render: function (c) { return esc(c.location || '—'); } },
            { title: '微信号', nowrap: true, render: function (c) { return esc(c.wechat || '—'); } },
            { title: '标签', render: function (c) {
                return leadTagSummaryHtml(c.tags);
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
            : '还没有客户：客户由线索转化产生，请先到「线索」把线索转成客户',
        'customer-table', 'customer-table-wrap');

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
        var regionComboEl = form.querySelector('[data-searchable-select]');
        if (regionComboEl) { bindRegionCombo(regionComboEl); }
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
                '<select name="customer_type">' + dictOptions('customer_type', c.customer_type || 'personal') + '</select></div>' +
        '</div>' +
        '<div class=\"field\"><label>电话</label>' +
        '<input name=\"phone\" type=\"tel\" maxlength=\"32\" inputmode=\"tel\" value=\"' + esc(c.phone || '') + '\"></div>' +
        '<div class=\"field\"><label>微信</label>' +
        '<input name=\"wechat\" type=\"text\" maxlength=\"64\" value=\"' + esc(c.wechat || '') + '\"></div>' +
        '<div class=\"field\"><label>地区</label>' +
        regionComboHtml(c.location) + '</div>' +
        '<div class=\"field\"><label>联系人</label>' +
        '<input name=\"company_name\" type=\"text\" maxlength=\"100\" value=\"' + esc(c.company_name || '') + '\"></div>' +
        '<div class=\"field\"><label>来源</label>' +
                '<select name="source">' + dictOptions('customer_source', c.source, '请选择') + '</select></div>' +
        '<div class=\"field\"><label>意向</label>' +
                '<select name="intent_level">' + dictOptions('intent_level', c.intent_level || 'medium') + '</select></div>' +
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
function customer360Stage(c) {
    var deals = c.deals || [];
    var orders = c.orders || [];
    if (orders.some(function (o) { return o.status === 'completed'; })) {
        return ['已成交', 'is-done'];
    }
    if (orders.length) { return ['交付中', 'is-progress']; }
    if (deals.some(function (d) { return d.stage === 'won'; })) {
        return ['待下单', 'is-progress'];
    }
    if (deals.some(function (d) { return d.stage === 'confirm'; })) {
        return ['待客户确认', 'is-progress'];
    }
    if (deals.length) { return ['商机跟进', 'is-progress']; }
    return ['新客户', 'is-new'];
}

function customerActivityData(records) {
    var now = new Date();
    var buckets = [];
    var i;
    for (i = 5; i >= 0; i--) {
        var d = new Date(now.getFullYear(), now.getMonth() - i, 1);
        buckets.push({
            year: d.getFullYear(),
            month: d.getMonth(),
            label: (d.getMonth() + 1) + '月',
            follow: 0,
            system: 0
        });
    }
    (records || []).forEach(function (record) {
        var date = new Date(record.at);
        if (isNaN(date.getTime())) { return; }
        buckets.forEach(function (bucket) {
            if (date.getFullYear() === bucket.year && date.getMonth() === bucket.month) {
                if (record.type === 'follow') { bucket.follow += 1; }
                else { bucket.system += 1; }
            }
        });
    });
    return buckets;
}

function customer360OverviewHtml(c, records) {
    var deals = c.deals || [];
    var orders = c.orders || [];
    var aftersales = c.aftersales || [];
    var sortedRecords = sortedTimelineRecords(records || []);
    var latestFollow = sortedRecords.filter(function (r) { return r.type === 'follow'; })[0] || sortedRecords[0];
    var stage = customer360Stage(c);
    var orderTotal = orders.reduce(function (sum, order) {
        return sum + (Number(order.amount) || 0);
    }, 0);
    var activity = customerActivityData(sortedRecords);
    var maxActivity = 1;
    activity.forEach(function (month) {
        maxActivity = Math.max(maxActivity, month.follow + month.system);
    });
    var followTotal = sortedRecords.filter(function (r) { return r.type === 'follow'; }).length;
    var systemTotal = sortedRecords.length - followTotal;
    var contactName = c.primary_contact_name || c.name;
    var company = c.company_name || c.name;
    var contactLine = [contactName, c.primary_contact_phone || c.phone,
        (c.primary_contact_wechat || c.wechat) ? '微信 ' + (c.primary_contact_wechat || c.wechat) : '']
        .filter(Boolean).join(' · ');
    var monogram = String(c.name || '客').trim().slice(0, 1);
    var source = c.source ? (SOURCE_LABELS[c.source] || c.source) : '—';
    if (c.source === 'other' && c.source_other) { source = c.source_other; }
    var intent = c.intent_level ? (INTENT_LABELS[c.intent_level] || c.intent_level) : '—';
    var latestHtml = latestFollow
        ? '<div class="customer-360-latest-head"><strong>' +
          (latestFollow.type === 'follow' ? '最近一次跟进' : '最近业务动态') + '</strong><time>' +
          esc(fmtDateTime(latestFollow.at)) + '</time></div>' +
          '<p>' + esc(latestFollow.content || '—') + '</p>' +
          (latestFollow.next_date
            ? '<div class="customer-360-next' +
              (latestFollow.next_date < todayISO() ? ' is-overdue' : '') + '">下次跟进 ' +
              esc(latestFollow.next_date) +
              (latestFollow.next_date < todayISO() ? ' · 已到期' : '') + '</div>'
            : '')
        : '<div class="customer-360-latest-head"><strong>最近一次跟进</strong></div>' +
          '<p>还没有跟进记录，记下第一次沟通后会显示在这里。</p>';

    var chartHtml = activity.map(function (month) {
        var total = month.follow + month.system;
        var followHeight = total ? Math.max(3, Math.round(month.follow / maxActivity * 100)) : 0;
        var systemHeight = total ? Math.max(3, Math.round(month.system / maxActivity * 100)) : 0;
        return '<div class="customer-360-activity-column" title="' + esc(month.label) + '：' +
            total + ' 次动态（跟进 ' + month.follow + '，系统节点 ' + month.system + '）">' +
            '<span class="customer-360-activity-count">' + (total || '') + '</span>' +
            '<div class="customer-360-activity-plot" aria-hidden="true">' +
            (month.system ? '<i class="customer-360-activity-segment is-system" style="height:' +
                systemHeight + '%"></i>' : '') +
            (month.follow ? '<i class="customer-360-activity-segment is-follow" style="height:' +
                followHeight + '%"></i>' : '') +
            '</div><span class="customer-360-activity-month">' + esc(month.label) + '</span></div>';
    }).join('');

    var journey = [
        ['建档', 1],
        ['商机', deals.length],
        ['订单', orders.length],
        ['售后', aftersales.length],
        ['动态', sortedRecords.length]
    ].map(function (step) {
        return '<div class="customer-360-journey-step' + (step[1] ? ' has-data' : '') + '">' +
            esc(step[0]) + '<b>' + step[1] + '</b></div>';
    }).join('');

    return '<section class="customer-360-overview" aria-label="客户全景信息">' +
        '<div class="customer-360-contact">' +
        '<div class="customer-360-identity">' +
        '<span class="customer-360-mark" aria-hidden="true">' + esc(monogram) + '</span>' +
        '<div class="customer-360-identity-copy"><div class="customer-360-company">' + esc(company) + '</div>' +
        '<div class="customer-360-relationship">' + esc(contactLine || '暂无联系人信息') + '</div></div>' +
        '<span class="customer-360-state ' + stage[1] + '">' + esc(stage[0]) + '</span></div>' +
        '<dl class="customer-360-facts">' +
        '<div class="customer-360-fact"><dt>联系电话</dt><dd>' +
        esc(c.primary_contact_phone || c.phone || '—') + '</dd></div>' +
        '<div class="customer-360-fact"><dt>微信</dt><dd>' +
        esc(c.primary_contact_wechat || c.wechat || '—') + '</dd></div>' +
        '<div class="customer-360-fact"><dt>所在地区</dt><dd>' + esc(c.location || '—') + '</dd></div>' +
        '<div class="customer-360-fact"><dt>来源 / 意向</dt><dd>' +
        esc(source + ' · ' + intent) + '</dd></div>' +
        '<div class="customer-360-fact"><dt>负责人</dt><dd>' + esc(c.owner || '—') + '</dd></div>' +
        '<div class="customer-360-fact"><dt>联系人</dt><dd>' + esc(contactLine || '—') + '</dd></div>' +
        '</dl>' +
        (c.note ? '<div class="customer-360-note"><span>备注</span><span>' + esc(c.note) + '</span></div>' : '') +
        '<div class="customer-360-latest">' + latestHtml + '</div>' +
        '</div>' +
        '<div class="customer-360-insights">' +
        '<div class="customer-360-kpis">' +
        '<div class="customer-360-kpi"><div class="customer-360-kpi-label">累计订单额</div>' +
        '<div class="customer-360-kpi-value is-money">' + esc(money(orderTotal)) + '</div></div>' +
        '<div class="customer-360-kpi"><div class="customer-360-kpi-label">商机</div>' +
        '<div class="customer-360-kpi-value">' + deals.length + '</div></div>' +
        '<div class="customer-360-kpi"><div class="customer-360-kpi-label">订单</div>' +
        '<div class="customer-360-kpi-value">' + orders.length + '</div></div>' +
        '<div class="customer-360-kpi"><div class="customer-360-kpi-label">售后</div>' +
        '<div class="customer-360-kpi-value">' + aftersales.length + '</div></div></div>' +
        '<div class="customer-360-chart-head"><h3>近 6 个月业务动态</h3><span>共 ' +
        sortedRecords.length + ' 次</span></div>' +
        '<div class="customer-360-chart" role="img" aria-label="近 6 个月客户动态柱状图，人工跟进 ' +
        followTotal + ' 次，系统节点 ' + systemTotal + ' 次">' + chartHtml + '</div>' +
        '<div class="customer-360-legend"><span><i class="is-follow"></i>人工跟进 ' + followTotal +
        '</span><span><i class="is-system"></i>系统节点 ' + systemTotal + '</span></div>' +
        '<div class="customer-360-journey" aria-label="客户业务规模">' + journey + '</div>' +
        '<div class="customer-360-meta">建档 ' + esc(fmtDateTime(c.created_at)) +
        ' · 最近更新 ' + esc(fmtDateTime(c.updated_at)) + '</div>' +
        '</div></section>';
}

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
        var tagsHtml = (c.tags || []).length
            ? '<span class="detail-title-tag">' + c.tags.map(function (t) {
                return '<span class="tag">' + esc(t) + '</span>';
            }).join('') + '</span>'
            : '<span class="detail-title-empty">暂无标签</span>';

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

        var actions =
            '<button type=\"button\" class=\"btn btn-sm\" id=\"toggleEditCustomer\">编辑客户</button>' +
            '<button type=\"button\" class=\"btn btn-sm btn-primary\" id=\"custToDeal\">转商机</button>';

        renderEntityFollowPage(root, {
            backHash: '#/customers',
            backLabel: '客户',
            objectType: 'customer',
            title: c.name,
            titleHtml:
                '<div class="lead-detail-title-main">' +
                '<a class="crumb lead-detail-crumb" href="#/customers">‹ 客户</a>' +
                '<div class="lead-detail-title-line"><h2>' + esc(c.name) + '</h2>' +
                '<div class="detail-title-tags">' + tagsHtml + '</div></div></div>',
            badgesHtml: '<span class="badge muted">' +
                esc(dictLabel('customer_type', c.customer_type, c.customer_type || '—')) + '</span>',
            infoHtml: customer360OverviewHtml(c, records),
            actionsHtml: actions,
            placeholder: '这次沟通聊了什么？客户是什么态度？下一步做什么？',
            records: records,
            initialTimelineLimit: 6,
            timelineBatchSize: 6,
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
