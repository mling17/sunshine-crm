/* 线索列表页面逻辑 */
function viewLeads(root) {
    var st = state.filters;
    return api('/leads?status=' + (st.status || '') + '&search=' + encodeURIComponent(st.q || '')).then(function (res) {
        var items = res.items || [];
        root.innerHTML =
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>线索列表</h2>' +
            '<button type=\"button\" class=\"btn btn-primary btn-sm\" id=\"toggleNewLead\">+ 新建线索</button></div>' +
            '<div class=\"searchbar\">' +
            '<input id=\"leadSearch\" type=\"search\" placeholder=\"搜姓名 / 电话 / 微信 / 地址\" autocomplete=\"off\" value=\"' + esc(st.q) + '\">' +
            '<button type=\"button\" class=\"btn\" id=\"leadSearchBtn\">搜索</button>' +
            '</div>' +
            '<div class=\"tabs\" id=\"leadTabs\">' +
            '<button type=\"button\" class=\"tab-btn active\" data-status=\"\">全部</button>' +
            '<button type=\"button\" class=\"tab-btn\" data-status=\"new\">新线索</button>' +
            '<button type=\"button\" class=\"tab-btn\" data-status=\"following\">跟进中</button>' +
            '<button type=\"button\" class=\"tab-btn\" data-status=\"converted\">已转化</button>' +
            '<button type=\"button\" class=\"tab-btn\" data-status=\"invalid\">已失效</button>' +
            '</div>' +
            '<div id=\"newLeadWrap\" hidden>' + leadFormHtml(null) + '</div>' +
            '</div>' +
            '<div class=\"card\"><div id=\"leadList\"><p class=\"loading\">加载中…</p></div><div id=\"leadPager\"></div></div>';

        var wrap = $('#newLeadWrap', root);
        $('#toggleNewLead', root).addEventListener('click', function () {
            wrap.hidden = !wrap.hidden;
            if (!wrap.hidden) { wrap.querySelector('[name=\"name\"]').focus(); }
        });

        wrap.querySelector('form').addEventListener('submit', function (ev) {
            ev.preventDefault();
            var form = ev.target;
            var btn = form.querySelector('button[type=\"submit\"]');
            var payload = readLeadForm(form);
            if (!payload.name && !payload.phone && !payload.wechat) { 
                toast('姓名、手机或微信至少填一项', true); 
                return; 
            }
            btn.disabled = true;
            api('/leads', { method: 'POST', body: payload }).then(function (lead) {
                // 处理去重提示
                if (lead.duplicate_hint) {
                    showDuplicateHintModal(lead.duplicate_hint);
                }
                toast('已新建线索');
                form.reset();
                wrap.hidden = true;
                return loadLeads(root);
            }).catch(function (err) {
                toast(err.message, true);
            }).then(function () { btn.disabled = false; });
        });

        var searchEl = $('#leadSearch', root);
        var timer = null;
        function applySearch() {
            st.q = String(searchEl.value || '').trim();
            st.page = 1;
            loadLeads(root);
        }
        searchEl.addEventListener('input', function () {
            clearTimeout(timer);
            timer = setTimeout(applySearch, 300);
        });
        searchEl.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter') { ev.preventDefault(); clearTimeout(timer); applySearch(); }
        });
        $('#leadSearchBtn', root).addEventListener('click', applySearch);

        // 状态标签切换
        $('#leadTabs', root).addEventListener('click', function (ev) {
            var btn = ev.target.closest('.tab-btn');
            if (!btn) { return; }
            st.status = btn.getAttribute('data-status') || '';
            $$('.tab-btn', root).forEach(function (b) {
                b.classList.toggle('active', b === btn);
            });
            st.page = 1;
            loadLeads(root);
        });

        return loadLeads(root);
    });
}

function loadLeads(root) {
    var st = state.filters;
    var listEl = $('#leadList', root);
    var pagerEl = $('#leadPager', root);
    if (!listEl) { return Promise.resolve(); }
    listEl.innerHTML = '<p class=\"loading\">加载中…</p>';

    var params = new URLSearchParams();
    params.set('page', String(st.page));
    params.set('size', String(PAGE_SIZE));
    if (st.q) { params.set('search', st.q); }
    if (st.status) { params.set('status', st.status); }

    return api('/leads?' + params.toString()).then(function (res) {
        var items = res.items || [];
        if (!items.length) {
            listEl.innerHTML = '<p class=\"empty\">' +
                (st.q || st.status ? '没有匹配的线索，换个条件试试' : '还没有线索，点右上「新建线索」开始') + '</p>';
        } else {
            listEl.innerHTML = items.map(leadItemHtml).join('');
        }
        pagerEl.innerHTML = pagerHtml(res);
        pagerEl.onclick = function (ev) {
            var btn = ev.target.closest('button[data-page]');
            if (!btn || btn.disabled) { return; }
            st.page = Number(btn.getAttribute('data-page')) || 1;
            loadLeads(root);
        };
    }).catch(function (err) {
        listEl.innerHTML = '<p class=\"err\">' + esc(err.message) + '</p>';
    });
}

function leadItemHtml(l) {
    var statusBadge = '';
    switch (l.status) {
        case 'new':
            statusBadge = '<span class=\"badge muted\">新线索</span>';
            break;
        case 'following':
            statusBadge = '<span class=\"badge warn\">跟进中</span>';
            break;
        case 'converted':
            statusBadge = '<span class=\"badge ok\">已转化</span>';
            break;
        case 'invalid':
            statusBadge = '<span class=\"badge danger\">已失效</span>';
            break;
    }

    var sourceBadge = '';
    if (l.source) {
        var srcText = (l.source === 'other' && l.source_other) ? l.source_other : (SOURCE_LABELS[l.source] || l.source);
        sourceBadge = '<span class=\"badge muted\">' + esc(srcText) + '</span>';
    }

    var intentBadge = '';
    if (l.intent_level) {
        switch (l.intent_level) {
            case 'high':
                intentBadge = '<span class=\"badge ok\">高</span>';
                break;
            case 'medium':
                intentBadge = '<span class=\"badge warn\">中</span>';
                break;
            case 'low':
                intentBadge = '<span class=\"badge muted\">低</span>';
                break;
            case 'none':
                intentBadge = '<span class=\"badge danger\">无意向</span>';
                break;
        }
    }

    var overdueClass = '';
    if (l.next_date && l.days_overdue > 0) {
        overdueClass = ' overdue';
    }

    var convertedLink = '';
    if (l.converted_customer_id) {
        convertedLink = '<a href=\"#/customers/' + l.converted_customer_id + '\" class=\"btn btn-sm\">已转化 → 客户</a>';
    }

    return '<div class=\"item' + overdueClass + '\">' +
        '<div class=\"item-main\">' +
        '<div class=\"item-title\">' + esc(l.name || (l.lead_type === 'company' ? l.company_name : '')) + 
        (l.lead_type === 'company' ? ' <span class=\"badge muted\">公司</span>' : '') + 
        statusBadge + sourceBadge + intentBadge + '</div>' +
        '<div class=\"item-sub\">' + 
        (l.phone ? '<span class=\"phone\">' + esc(l.phone) + '</span>' : '') +
        (l.wechat ? '<span class=\"wechat\">' + esc(l.wechat) + '</span>' : '') +
        '</div>' +
        '<div class=\"item-sub\">' + 
        (l.location ? esc(l.location) : '') + 
        '</div>' +
        '</div>' +
        '<div class=\"item-side\">' + 
        (l.next_date ? '<div class=\"small\">下次 ' + esc(l.next_date) + '</div>' : '') +
        (l.days_overdue > 0 ? '<div class=\"small danger\">逾期 ' + l.days_overdue + ' 天</div>' : '') +
        convertedLink +
        '</div>' +
        '</div>';
}

function leadFormHtml(lead) {
    var l = lead || {};
    return '<form class=\"lead-form\" autocomplete=\"off\">' +
        '<div class=\"row-2\">' +
        '<div class=\"field\"><label>姓名 *</label>' +
        '<input name=\"name\" type=\"text\" maxlength=\"64\" required value=\"' + esc(l.name || '') + '\"></div>' +
        '<div class=\"field\"><label>类型</label>' +
        '<select name=\"lead_type\">' +
        '<option value=\"personal\"' + (l.lead_type === 'personal' ? ' selected' : '') + '>个人</option>' +
        '<option value=\"company\"' + (l.lead_type === 'company' ? ' selected' : '') + '>公司</option>' +
        '</select></div>' +
        '</div>' +
        '<div class=\"field\"><label>电话</label>' +
        '<input name=\"phone\" type=\"tel\" maxlength=\"32\" inputmode=\"tel\" value=\"' + esc(l.phone || '') + '\"></div>' +
        '<div class=\"field\"><label>微信</label>' +
        '<input name=\"wechat\" type=\"text\" maxlength=\"64\" value=\"' + esc(l.wechat || '') + '\"></div>' +
        '<div class=\"field\"><label>公司名</label>' +
        '<input name=\"company_name\" type=\"text\" maxlength=\"100\" value=\"' + esc(l.company_name || '') + '\"></div>' +
        '<div class=\"field\"><label>地区 / 安装地址</label>' +
        '<input name=\"location\" type=\"text\" maxlength=\"200\" value=\"' + esc(l.location || '') + '\"></div>' +
        '<div class=\"field\"><label>来源</label>' +
        '<select name=\"source\">' +
        '<option value=\"wechat\"' + (l.source === 'wechat' ? ' selected' : '') + '>微信</option>' +
        '<option value=\"phone\"' + (l.source === 'phone' ? ' selected' : '') + '>电话</option>' +
        '<option value=\"referral\"' + (l.source === 'referral' ? ' selected' : '') + '>转介绍</option>' +
        '<option value=\"existing\"' + (l.source === 'existing' ? ' selected' : '') + '>老客户</option>' +
        '<option value=\"other\"' + (l.source === 'other' ? ' selected' : '') + '>其他</option>' +
        '</select></div>' +
        '<div class=\"field\"><label>来源其他</label>' +
        '<input name=\"source_other\" type=\"text\" maxlength=\"100\" value=\"' + esc(l.source_other || '') + '\"></div>' +
        '<div class=\"field\"><label>意向等级</label>' +
        '<select name=\"intent_level\">' +
        '<option value=\"high\"' + (l.intent_level === 'high' ? ' selected' : '') + '>高</option>' +
        '<option value=\"medium\"' + (l.intent_level === 'medium' ? ' selected' : '') + '>中</option>' +
        '<option value=\"low\"' + (l.intent_level === 'low' ? ' selected' : '') + '>低</option>' +
        '<option value=\"none\"' + (l.intent_level === 'none' ? ' selected' : '') + '>无意向</option>' +
        '</select></div>' +
        '<div class=\"field\"><label>标签（逗号分隔）</label>' +
        '<input name=\"tags\" type=\"text\" maxlength=\"400\" value=\"' + esc((l.tags || []).join('、')) + '\"></div>' +
        '<div class=\"field\"><label>备注</label>' +
        '<textarea name=\"note\" maxlength=\"500\">' + esc(l.note || '') + '</textarea></div>' +
        '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">保存</button></div>' +
        '</form>';
}

function readLeadForm(form) {
    function val(name) {
        var el = form.querySelector('[name=\"' + name + '\"]');
        return el ? String(el.value || '').trim() : '';
    }
    var tags = val('tags').split(/[,，、;；\\s]+/).filter(Boolean).slice(0, MAX_TAGS);
    return {
        name: val('name'),
        phone: val('phone') || null,
        wechat: val('wechat') || null,
        lead_type: val('lead_type') || 'personal',
        company_name: val('company_name') || null,
        source: val('source') || null,
        source_other: val('source_other') || null,
        location: val('location') || null,
        note: val('note') || null,
        intent_level: val('intent_level') || null,
        tags: tags
    };
}

/* 线索详情页面逻辑 */
function viewLeadDetail(root, rawId) {
    var id = Number(rawId);
    if (!id || isNaN(id)) {
        root.innerHTML = '<div class=\"card\">线索 id 不合法，<a href=\"#/leads\">回线索列表</a></div>';
        return Promise.resolve();
    }

    return Promise.all([
        api('/leads/' + id),
        api('/follow-ups?object_type=lead&object_id=' + id)
    ]).then(function (all) {
        var l = all[0];
        var followups = all[1] || [];
        
        var fuHtml = followups.length
            ? followups.map(function (f) { return followupItemHtml(f, { withDelete: true, showCustomer: false }); }).join('')
            : '<p class=\"empty\">还没有跟进记录</p>';

        root.innerHTML =
            '<div class=\"card\">' +
            '<div class=\"card-head\">' +
            '<h2><a href=\"#/leads\">‹ 线索</a> ' + esc(l.name || (l.lead_type === 'company' ? l.company_name : '')) + '</h2>' +
            '<div>' +
            '<a class=\"btn btn-sm\" href=\"#/followups?object=lead&id=' + l.id + '\">记跟进</a> ' +
            '</div>' +
            '</div>' +
            '<div class=\"tags\">' + (l.tags || []).map(function (t) { return '<span class=\"tag\">' + esc(t) + '</span>'; }).join('') + '</div>' +
            '<div class=\"item-sub\" style=\"margin-top:8px\">' +
            '类型：' + (l.lead_type === 'company' ? '公司' : '个人') + '<br>' +
            '电话：' + esc(l.phone || '—') + '<br>' +
            '微信：' + esc(l.wechat || '—') + '<br>' +
            '地区：' + esc(l.location || '—') + '<br>' +
            '来源：' + (l.source ? esc(SOURCE_LABELS[l.source] || l.source) : '—') + '<br>' +
            '意向：' + (l.intent_level ? esc(INTENT_LABELS[l.intent_level] || l.intent_level) : '—') + '<br>' +
            '备注：' + esc(l.note || '—') + '<br>' +
            '<span class=\"muted small\">建档 ' + fmtDateTime(l.created_at) + ' · 最近更新 ' + fmtDateTime(l.updated_at) + '</span>' +
            '</div>' +
            '</div>' +
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>跟进记录（' + followups.length + '）</h2>' +
            '<a class=\"btn btn-sm\" href=\"#/followups?object=lead&id=' + l.id + '\">+ 记一条</a></div>' +
            fuHtml +
            '</div>' +
            '<div class=\"card\">' +
            '<div class=\"card-head\"><h2>操作</h2></div>' +
            '<div class=\"form-actions\">' +
            '<button type=\"button\" class=\"btn btn-primary\" id=\"convertBtn\">建商机并转化</button> ' +
            '<button type=\"button\" class=\"btn btn-danger\" id=\"invalidateBtn\">标记失效</button>' +
            '</div>' +
            '</div>';

        // 转化按钮事件
        $('#convertBtn', root).addEventListener('click', function () {
            convertLead(l.id);
        });

        // 标记失效按钮事件
        $('#invalidateBtn', root).addEventListener('click', function () {
            invalidateLead(l.id);
        });
    });
}

function convertLead(leadId) {
    // 先检查是否有重复
    api('/leads/convert-check?phone=&wechat=').then(function (checkRes) {
        // 显示转化弹层
        showConvertModal(leadId);
    }).catch(function (err) {
        // 直接转化
        showConvertModal(leadId);
    });
}

function showConvertModal(leadId) {
    // 创建转化弹层
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = 
        '<div class=\"modal-overlay\"></div>' +
        '<div class=\"modal-content\">' +
        '<div class=\"modal-header\">' +
        '<h3>转化线索</h3>' +
        '<button type=\"button\" class=\"btn btn-link modal-close\">×</button>' +
        '</div>' +
        '<div class=\"modal-body\">' +
        '<form id=\"convertForm\" class=\"convert-form\">' +
        '<div class=\"field\"><label>商机名称 *</label>' +
        '<input name=\"title\" type=\"text\" maxlength=\"64\" required></div>' +
        '<div class=\"row-3\">' +
        '<div class=\"field\"><label>产品类型</label>' +
        '<input name=\"product_type\" type=\"text\" maxlength=\"32\" placeholder=\"天窗 / 天幕\"></div>' +
        '<div class=\"field\"><label>型号</label>' +
        '<input name=\"model\" type=\"text\" maxlength=\"64\"></div>' +
        '<div class=\"field\"><label>规格</label>' +
        '<input name=\"spec\" type=\"text\" maxlength=\"200\"></div>' +
        '</div>' +
        '<div class=\"field\"><label>金额 *</label>' +
        '<input name=\"amount\" type=\"number\" min=\"0\" step=\"0.01\" inputmode=\"decimal\" required></div>' +
        '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">确定</button></div>' +
        '</form>' +
        '</div>' +
        '</div>';

    document.body.appendChild(modal);
    
    // 关闭事件
    modal.querySelector('.modal-close').addEventListener('click', function () {
        document.body.removeChild(modal);
    });
    
    // 提交事件
    modal.querySelector('#convertForm').addEventListener('submit', function (ev) {
        ev.preventDefault();
        var form = ev.target;
        var amount = numOrNull(form.querySelector('[name=\"amount\"]').value);
        if (amount === null || amount < 0) { 
            toast('报价金额必填且 ≥0', true); 
            return; 
        }
        
        var payload = {
            mode: 'new',
            deal: {
                title: form.querySelector('[name=\"title\"]').value.trim(),
                product_type: form.querySelector('[name=\"product_type\"]').value.trim() || null,
                model: form.querySelector('[name=\"model\"]').value.trim() || null,
                spec: form.querySelector('[name=\"spec\"]').value.trim() || null,
                amount: amount
            }
        };
        
        api('/leads/' + leadId + '/convert', { method: 'POST', body: payload })
            .then(function (res) {
                toast('转化成功');
                document.body.removeChild(modal);
                location.hash = '#/customers/' + res.customer.id;
            })
            .catch(function (err) {
                toast(err.message, true);
            });
    });
}

function invalidateLead(leadId) {
    // 显示失效弹层
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = 
        '<div class=\"modal-overlay\"></div>' +
        '<div class=\"modal-content\">' +
        '<div class=\"modal-header\">' +
        '<h3>标记失效</h3>' +
        '<button type=\"button\" class=\"btn btn-link modal-close\">×</button>' +
        '</div>' +
        '<div class=\"modal-body\">' +
        '<form id=\"invalidateForm\" class=\"invalidate-form\">' +
        '<div class=\"field\"><label>失效原因 *</label>' +
        '<select name=\"invalid_reason\" required>' +
        '<option value=\"\">请选择失效原因</option>' +
        '<option value=\"invalid_phone\">无效号码</option>' +
        '<option value=\"blacklist\">黑名单</option>' +
        '<option value=\"no_intent\">无意向</option>' +
        '<option value=\"duplicate\">重复</option>' +
        '<option value=\"other\">其他</option>' +
        '</select></div>' +
        '<div class=\"field\"><label>其他说明</label>' +
        '<input name=\"invalid_reason_other\" type=\"text\" maxlength=\"100\"></div>' +
        '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-danger\">确定</button></div>' +
        '</form>' +
        '</div>' +
        '</div>';

    document.body.appendChild(modal);
    
    // 关闭事件
    modal.querySelector('.modal-close').addEventListener('click', function () {
        document.body.removeChild(modal);
    });
    
    // 提交事件
    modal.querySelector('#invalidateForm').addEventListener('submit', function (ev) {
        ev.preventDefault();
        var form = ev.target;
        var reason = form.querySelector('[name=\"invalid_reason\"]').value;
        if (!reason) { 
            toast('请选择失效原因', true); 
            return; 
        }
        
        var payload = {
            invalid_reason: reason
        };
        if (reason === 'other') {
            payload.invalid_reason_other = form.querySelector('[name=\"invalid_reason_other\"]').value.trim();
        }
        
        api('/leads/' + leadId + '/invalidate', { method: 'POST', body: payload })
            .then(function (res) {
                toast('标记失效成功');
                document.body.removeChild(modal);
                location.hash = '#/leads';
            })
            .catch(function (err) {
                toast(err.message, true);
            });
    });
}

// 显示去重提示弹层
function showDuplicateHintModal(hint) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = 
        '<div class=\"modal-overlay\"></div>' +
        '<div class=\"modal-content\">' +
        '<div class=\"modal-header\">' +
        '<h3>提示</h3>' +
        '<button type=\"button\" class=\"btn btn-link modal-close\">×</button>' +
        '</div>' +
        '<div class=\"modal-body\">' +
        '<p>该线索已存在：</p>' +
        '<p><strong>' + esc(hint.name) + '</strong> (' + esc(hint.type) + ')</p>' +
        '<p>是否要关联到该客户？</p>' +
        '<div class=\"form-actions\">' +
        '<button type=\"button\" class=\"btn\" id=\"linkBtn\">关联到该客户</button> ' +
        '<button type=\"button\" class=\"btn btn-primary\" id=\"newBtn\">仍要新建客户</button>' +
        '</div>' +
        '</div>' +
        '</div>';

    document.body.appendChild(modal);
    
    // 关闭事件
    modal.querySelector('.modal-close').addEventListener('click', function () {
        document.body.removeChild(modal);
    });
    
    // 关联按钮事件
    modal.querySelector('#linkBtn').addEventListener('click', function () {
        document.body.removeChild(modal);
        // 这里应该处理关联逻辑，实际应用中需要在提交时处理
    });
    
    // 新建按钮事件
    modal.querySelector('#newBtn').addEventListener('click', function () {
        // 继续保存，不阻塞
        document.body.removeChild(modal);
    });
}