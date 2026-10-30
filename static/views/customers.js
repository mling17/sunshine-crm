/* 客户列表页面逻辑 */
function viewCustomers(root) {
    var st = state.filters;
    return api('/tags').catch(function () { return []; }).then(function (tags) {
        root.innerHTML =
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>客户档案</h2>' +
            '<button type=\"button\" class=\"btn btn-primary btn-sm\" id=\"toggleNewCustomer\">+ 新增客户</button></div>' +
            '<div class=\"searchbar\">' +
            '<input id=\"custSearch\" type=\"search\" placeholder=\"搜姓名 / 电话 / 楼盘\" autocomplete=\"off\" value=\"' + esc(st.q) + '\">' +
            '<button type=\"button\" class=\"btn\" id=\"custSearchBtn\">搜索</button>' +
            '</div>' +
            '<div class=\"chips\" id=\"tagChips\">' + chipHtml(tags, st.tag) + '</div>' +
            '<div id=\"newCustomerWrap\" hidden>' + customerFormHtml(null) + '</div>' +
            '</div>' +
            '<div class=\"card\"><div id=\"custList\"><p class=\"loading\">加载中…</p></div><div id=\"custPager\"></div></div>';

        var wrap = $('#newCustomerWrap', root);
        $('#toggleNewCustomer', root).addEventListener('click', function () {
            wrap.hidden = !wrap.hidden;
            if (!wrap.hidden) { wrap.querySelector('[name=\"name\"]').focus(); }
        });

        wrap.querySelector('form').addEventListener('submit', function (ev) {
            ev.preventDefault();
            var form = ev.target;
            var btn = form.querySelector('button[type=\"submit\"]');
            var payload = readCustomerForm(form);
            if (!payload.name) { toast('姓名必填', true); return; }
            btn.disabled = true;
            api('/customers', { method: 'POST', body: payload }).then(function () {
                invalidateCustomerIndex();
                toast('已新增客户');
                form.reset();
                wrap.hidden = true;
                return api('/tags').catch(function () { return []; });
            }).then(function (newTags) {
                var chips = $('#tagChips', root);
                if (chips) { chips.innerHTML = chipHtml(newTags, st.tag); }
                st.page = 1;
                return loadCustomers(root);
            }).catch(function (err) {
                toast(err.message, true);
            }).then(function () { btn.disabled = false; });
        });

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
        if (!items.length) {
            listEl.innerHTML = '<p class=\"empty\">' +
                (st.q || st.tag ? '没有匹配的客户，换个条件试试' : '还没有客户，点右上「新增客户」开始') + '</p>';
        } else {
            listEl.innerHTML = items.map(customerItemHtml).join('');
        }
        pagerEl.innerHTML = pagerHtml(res);
        pagerEl.onclick = function (ev) {
            var btn = ev.target.closest('button[data-page]');
            if (!btn || btn.disabled) { return; }
            st.page = Number(btn.getAttribute('data-page')) || 1;
            loadCustomers(root);
        };
    }).catch(function (err) {
        listEl.innerHTML = '<p class=\"err\">' + esc(err.message) + '</p>';
    });
}

function customerItemHtml(c) {
    var tags = (c.tags || []).map(function (t) { return '<span class=\"tag\">' + esc(t) + '</span>'; }).join('');
    var repeat = c.is_repeat ? '<span class=\"badge ok\">老客</span>' : '';
    var lifecycleBadge = '';
    switch (c.lifecycle) {
        case 'potential':
            lifecycleBadge = '<span class=\"badge muted\">潜在</span>';
            break;
        case 'dealing':
            lifecycleBadge = '<span class=\"badge warn\">商机中</span>';
            break;
        case 'won':
            lifecycleBadge = '<span class=\"badge ok\">已成交</span>';
            break;
        case 'repeat':
            lifecycleBadge = '<span class=\"badge ok\">复购</span>';
            break;
    }
    
    return '<div class=\"item\">' +
        '<div class=\"item-main\">' +
        '<div class=\"item-title\"><a href=\"#/customers/' + c.id + '\">' + esc(c.name) + '</a>' + repeat + lifecycleBadge + '</div>' +
        '<div class=\"item-sub\">' + esc(c.phone || '无电话') + 
        (c.location ? ' · ' + esc(c.location) : '') + '</div>' +
        (tags ? '<div class=\"tags\">' + tags + '</div>' : '') +
        '</div>' +
        '<div class=\"item-side\"><div>' + (c.deals_total || 0) + ' 个商机</div>' +
        '<div class=\"muted small\">成交 ' + money(c.total_closed_amount) + '</div></div>' +
        '</div>';
}

function customerFormHtml(customer) {
    var c = customer || {};
    return '<form class=\"customer-form\" autocomplete=\"off\">' +
        '<div class=\"row-2\">' +
        '<div class=\"field\"><label>姓名 *</label>' +
        '<input name=\"name\" type=\"text\" maxlength=\"64\" required value=\"' + esc(c.name || '') + '\"></div>' +
        '<div class=\"field\"><label>类型</label>' +
        '<select name=\"customer_type\">' +
        '<option value=\"personal\"' + (c.customer_type === 'personal' ? ' selected' : '') + '>个人</option>' +
        '<option value=\"company\"' + (c.customer_type === 'company' ? ' selected' : '') + '>公司</option>' +
        '</select></div>' +
        '</div>' +
        '<div class=\"field\"><label>电话</label>' +
        '<input name=\"phone\" type=\"tel\" maxlength=\"32\" inputmode=\"tel\" value=\"' + esc(c.phone || '') + '\"></div>' +
        '<div class=\"field\"><label>微信</label>' +
        '<input name=\"wechat\" type=\"text\" maxlength=\"64\" value=\"' + esc(c.wechat || '') + '\"></div>' +
        '<div class=\"field\"><label>楼盘 / 安装地址</label>' +
        '<input name=\"location\" type=\"text\" maxlength=\"200\" value=\"' + esc(c.location || '') + '\"></div>' +
        '<div class=\"field\"><label>公司名</label>' +
        '<input name=\"company_name\" type=\"text\" maxlength=\"100\" value=\"' + esc(c.company_name || '') + '\"></div>' +
        '<div class=\"field\"><label>来源</label>' +
        '<select name=\"source\">' +
        '<option value=\"wechat\"' + (c.source === 'wechat' ? ' selected' : '') + '>微信</option>' +
        '<option value=\"phone\"' + (c.source === 'phone' ? ' selected' : '') + '>电话</option>' +
        '<option value=\"referral\"' + (c.source === 'referral' ? ' selected' : '') + '>转介绍</option>' +
        '<option value=\"existing\"' + (c.source === 'existing' ? ' selected' : '') + '>老客户</option>' +
        '<option value=\"other\"' + (c.source === 'other' ? ' selected' : '') + '>其他</option>' +
        '</select></div>' +
        '<div class=\"field\"><label>来源其他</label>' +
        '<input name=\"source_other\" type=\"text\" maxlength=\"100\" value=\"' + esc(c.source_other || '') + '\"></div>' +
        '<div class=\"field\"><label>意向等级</label>' +
        '<select name=\"intent_level\">' +
        '<option value=\"high\"' + (c.intent_level === 'high' ? ' selected' : '') + '>高</option>' +
        '<option value=\"medium\"' + (c.intent_level === 'medium' ? ' selected' : '') + '>中</option>' +
        '<option value=\"low\"' + (c.intent_level === 'low' ? ' selected' : '') + '>低</option>' +
        '<option value=\"none\"' + (c.intent_level === 'none' ? ' selected' : '') + '>无意向</option>' +
        '</select></div>' +
        '<div class=\"field\"><label>备注</label>' +
        '<textarea name=\"note\" maxlength=\"500\">' + esc(c.note || '') + '</textarea></div>' +
        '<div class=\"field\"><label>标签（逗号分隔，如：重点、转介绍）</label>' +
        '<input name=\"tags\" type=\"text\" maxlength=\"400\" value=\"' + esc((c.tags || []).join('、')) + '\"></div>' +
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
        api('/follow-ups?customer_id=' + id)
    ]).then(function (all) {
        var c = all[0];
        var followups = all[1] || [];
        var deals = c.deals || [];

        var dealHtml = deals.length
            ? '<div id=\"dealList\">' + deals.map(function (d) {
                var item = dealItemHtml(d);
                // 详情页的商机卡片里额外给一个“记跟进”入口（带 deal_id）
                return item.replace('<div class=\"item-side\">',
                    '<div class=\"item-side\"><a class=\"btn btn-sm\" href=\"#/followups?customer=' + c.id +
                    '&deal=' + d.id + '\">记跟进</a>');
            }).join('') + '</div>'
            : '<p class=\"empty\">还没有商机</p>';

        var fuHtml = followups.length
            ? followups.map(function (f) { return followupItemHtml(f, { withDelete: true }); }).join('')
            : '<p class=\"empty\">还没有跟进记录</p>';

        root.innerHTML =
            '<div class=\"card\">' +
            '<div class=\"card-head\">' +
            '<h2><a href=\"#/customers\">‹ 客户</a> ' + esc(c.name) + '</h2>' +
            '<div>' +
            '<a class=\"btn btn-sm\" href=\"#/followups?customer=' + c.id + '\">记跟进</a> ' +
            '<button type=\"button\" class=\"btn btn-sm\" id=\"toggleEditCustomer\">编辑</button> ' +
            '<button type=\"button\" class=\"btn btn-sm btn-danger\" id=\"deleteCustomer\">删除</button>' +
            '</div>' +
            '</div>' +
            '<div class=\"tags\">' + (c.tags || []).map(function (t) { return '<span class=\"tag\">' + esc(t) + '</span>'; }).join('') + '</div>' +
            '<div class=\"item-sub\" style=\"margin-top:8px\">' +
            '类型：' + (c.customer_type === 'company' ? '公司' : '个人') + '<br>' +
            '电话：' + esc(c.phone || '—') + '<br>' +
            '微信：' + esc(c.wechat || '—') + '<br>' +
            '楼盘：' + esc(c.location || '—') + '<br>' +
            '公司名：' + esc(c.company_name || '—') + '<br>' +
            '来源：' + (c.source ? esc(SOURCE_LABELS[c.source] || c.source) : '—') + '<br>' +
            '意向：' + (c.intent_level ? esc(INTENT_LABELS[c.intent_level] || c.intent_level) : '—') + '<br>' +
            '备注：' + esc(c.note || '—') + '<br>' +
            '<span class=\"muted small\">建档 ' + fmtDateTime(c.created_at) + ' · 最近更新 ' + fmtDateTime(c.updated_at) + '</span>' +
            '</div>' +
            '<div id=\"editCustomerWrap\" hidden style=\"margin-top:12px\">' + customerFormHtml(c) + '</div>' +
            '</div>' +
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>商机（' + deals.length + '）</h2>' +
            '<button type=\"button\" class=\"btn btn-sm\" id=\"toggleNewDeal\">+ 新增商机</button></div>' +
            '<div id=\"newDealWrap\" hidden>' + dealFormHtml() + '</div>' +
            dealHtml +
            '</div>' +
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>跟进记录（' + followups.length + '）</h2>' +
            '<a class=\"btn btn-sm\" href=\"#/followups?customer=' + c.id + '\">+ 记一条</a></div>' +
            fuHtml +
            '</div>';

        /* 编辑客户 */
        var editWrap = $('#editCustomerWrap', root);
        $('#toggleEditCustomer', root).addEventListener('click', function () {
            editWrap.hidden = !editWrap.hidden;
            if (!editWrap.hidden) { editWrap.querySelector('[name=\"name\"]').focus(); }
        });
        editWrap.querySelector('form').addEventListener('submit', function (ev) {
            ev.preventDefault();
            var form = ev.target;
            var btn = form.querySelector('button[type=\"submit\"]');
            var payload = readCustomerForm(form);
            if (!payload.name) { toast('姓名必填', true); return; }
            btn.disabled = true;
            api('/customers/' + c.id, { method: 'PUT', body: payload }).then(function () {
                invalidateCustomerIndex();
                toast('已保存');
                return render();
            }).catch(function (err) {
                toast(err.message, true);
                btn.disabled = false;
            });
        });

        /* 删除客户（级联删商机/跟进/标签） */
        $('#deleteCustomer', root).addEventListener('click', function () {
            if (!window.confirm('删除客户「' + c.name + '」？其商机、跟进记录会一起删掉，不可恢复。')) { return; }
            api('/customers/' + c.id, { method: 'DELETE' }).then(function () {
                invalidateCustomerIndex();
                toast('已删除客户');
                navigate('#/customers');
            }).catch(function (err) { toast(err.message, true); });
        });

        /* 新增商机 */
        var newDealWrap = $('#newDealWrap', root);
        $('#toggleNewDeal', root).addEventListener('click', function () {
            newDealWrap.hidden = !newDealWrap.hidden;
        });
        $('#newDealForm', root).addEventListener('submit', function (ev) {
            ev.preventDefault();
            var form = ev.target;
            var btn = form.querySelector('button[type=\"submit\"]');
            var amount = numOrNull(form.querySelector('[name=\"amount\"]').value);
            if (amount === null || amount < 0) { toast('报价金额必填且 ≥0', true); return; }
            var payload = {
                customer_id: c.id,
                product_type: form.querySelector('[name=\"product_type\"]').value.trim() || null,
                model: form.querySelector('[name=\"model\"]').value.trim() || null,
                spec: form.querySelector('[name=\"spec\"]').value.trim() || null,
                amount: amount,
                deposit: numOrNull(form.querySelector('[name=\"deposit\"]').value) || 0,
                balance: numOrNull(form.querySelector('[name=\"balance\"]').value) || 0,
                stage: form.querySelector('[name=\"stage\"]').value
            };
            btn.disabled = true;
            api('/deals', { method: 'POST', body: payload }).then(function () {
                toast('已新增商机');
                return render();
            }).catch(function (err) {
                toast(err.message, true);
                btn.disabled = false;
            });
        });

        bindDealStageSelects(root);

        $$('button[data-del-followup]', root).forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (!window.confirm('删除这条跟进？照片也会一并无法查看（文件留存于备份）。')) { return; }
                api('/follow-ups/' + btn.getAttribute('data-del-followup'), { method: 'DELETE' })
                    .then(function () { toast('已删除'); return render(); })
                    .catch(function (err) { toast(err.message, true); });
            });
        });
    });
}