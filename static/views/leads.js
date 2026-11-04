/* 线索列表页面逻辑 */
/* ---------------- 线索列表（表格，对齐 demo 定稿） ----------------
 * 定稿口径：表格列 = 名称 / 来源 / 地区 / 微信号 / 联系方式 / 标签 / 意向 / 上次跟进 / 创建时间 / 操作
 *           操作 = 编辑（弹层）/ 跟进（详情页）；转商机只在跟进页发起
 */
function viewLeads(root) {
    var st = state.filters;
    if (st.status === 'converted') { st.status = ''; }
    /* 版本一致性自检：app.js 与 views/*.js 版本不同步时（浏览器缓存一半），
       下面所有 dictOptions / openLeadFormModal 都会 ReferenceError，表现为「点了没反应」。
       这里直接给出可执行的提示，别让用户猜。 */
    if (typeof dictOptions !== 'function' || typeof ensureDicts !== 'function') {
        root.innerHTML = '<div class="card"><p class="err">页面脚本版本不一致（浏览器缓存了旧文件）。' +
            '请按 Ctrl+F5（手机：清缓存）强制刷新一次。</p></div>';
        return Promise.resolve();
    }
    /* 线索转商机后归入客户链路，不再在线索池提供「已转化」入口。 */
    var tabs = [['', '全部'], ['new', '新线索'], ['following', '跟进中'], ['invalid', '无效']];
    var tabHtml = tabs.map(function (t) {
        return '<button type="button" class="tab-btn' + ((st.status || '') === t[0] ? ' active' : '') +
            '" data-status="' + t[0] + '">' + t[1] + '</button>';
    }).join('');

    root.innerHTML =
        '<div class="card">' +
        '<div class="card-head lead-page-head"><div><h2>线索池</h2>' +
        '<p class="card-subtitle">集中管理待转化线索，出现跟进后自动进入「跟进中」。</p></div>' +
        '<div class="btn-row" style="display:flex;gap:8px;align-items:center">' +
        '<button type="button" class="btn btn-primary btn-sm" id="toggleNewLead">＋ 新增线索</button>' +
        '<button type="button" class="btn btn-sm" id="btnImportLead">⇪ 批量导入</button>' +
        '</div></div>' +
        '<div class="searchbar">' +
        '<input id="leadSearch" type="search" placeholder="搜名称 / 电话 / 微信 / 地区" autocomplete="off" value="' + esc(st.q) + '">' +
        '<button type="button" class="btn" id="leadSearchBtn">搜索</button>' +
        '</div>' +
        '<div class="tabs" id="leadTabs">' + tabHtml + '</div>' +
        '</div>' +
        '<div class="card"><div id="leadList"><p class="loading">加载中…</p></div><div id="leadPager"></div></div>';

    $('#toggleNewLead', root).addEventListener('click', function () { openLeadFormModal(root); });
    $('#btnImportLead', root).addEventListener('click', function () { openLeadImportModal(root); });

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

    $('#leadTabs', root).addEventListener('click', function (ev) {
        var btn = ev.target.closest('.tab-btn');
        if (!btn) { return; }
        st.status = btn.getAttribute('data-status') || '';
        $$('.tab-btn', root).forEach(function (b) { b.classList.toggle('active', b === btn); });
        st.page = 1;
        loadLeads(root);
    });

    return loadLeads(root);
}

function leadSourceText(l) {
    if (!l.source) { return '—'; }
    if (l.source === 'other' && l.source_other) { return l.source_other; }
    return dictLabel('customer_source', l.source, SOURCE_LABELS[l.source] || l.source);
}

function leadTypeText(l) {
    return dictLabel('customer_type', l.lead_type, l.lead_type || '—');
}

function leadIntentBadge(level) {
    if (!level) { return '—'; }
    var cls = level === 'high' ? 'danger' : (level === 'medium' ? 'warn' : 'muted');
    var label = INTENT_LABELS[level] || level;
    return '<span class="badge ' + cls + '">' + esc(label) + '</span>';
}

function leadStatusBadge(status, compact) {
    var map = {
        new: ['ok', '新线索', '新'], following: ['warn', '跟进中', '跟'],
        converted: ['muted', '已转化', '转'], invalid: ['danger', '无效', '无']
    };
    var v = map[status] || map.new;
    if (!compact) {
        return '<span class="badge ' + v[0] + '">' + v[1] + '</span>';
    }
    return '<span class="badge ' + v[0] + ' lead-status-badge" title="' + v[1] +
        '" aria-label="' + v[1] + '">' + v[2] + '</span>';
}

function leadDetailTags(tags) {
    if (!tags || !tags.length) { return '<span class="detail-title-empty">暂无标签</span>'; }
    return '<span class="detail-title-tag">' + tags.map(function (tag) {
        return '<span class="tag">' + esc(tag) + '</span>';
    }).join('') + '</span>';
}

function invalidReasonLabel(reason, other) {
    if (reason === 'other') { return other || '其他'; }
    var map = {
        invalid_phone: '无效号码',
        blacklist: '黑名单',
        no_intent: '无意向',
        duplicate: '重复'
    };
    return map[reason] || reason || '—';
}

function loadLeads(root) {
    var st = state.filters;
    var listEl = $('#leadList', root);
    var pagerEl = $('#leadPager', root);
    if (!listEl) { return Promise.resolve(); }
    listEl.innerHTML = '<p class="loading">加载中…</p>';

    var params = new URLSearchParams();
    params.set('page', String(st.page || 1));
    params.set('size', String(PAGE_SIZE));
    if (st.q) { params.set('search', st.q); }
    if (st.status) { params.set('status', st.status); }

    return api('/leads?' + params.toString()).then(function (res) {
        var items = res.items || [];
        listEl.innerHTML = dataTable([
            { title: '名称', render: function (l) {
                var name = l.name || (l.lead_type === 'company' ? l.company_name : '') || '—';
                return '<div class="lead-name-cell"><div class="lead-name-main">' +
                    '<a class="lead-name-link" href="#/leads/' + l.id + '" title="' + esc(name) + '">' +
                    esc(name) + '</a>' +
                    (l.company_name && l.lead_type === 'company' && l.company_name !== name
                        ? '<div class="lead-company muted" title="' + esc(l.company_name) + '">' +
                            esc(l.company_name) + '</div>' : '') +
                    '</div>' + leadStatusBadge(l.status, true) + '</div>';
            } },
            { title: '类型', render: function (l) { return esc(leadTypeText(l)); }, nowrap: true },
            { title: '来源', render: function (l) { return esc(leadSourceText(l)); }, nowrap: true },
            { title: '地区', render: function (l) { return esc(l.location || '—'); } },
            { title: '微信号', render: function (l) {
                var wechat = l.wechat || '—';
                return '<span class="lead-cell-ellipsis" title="' + esc(wechat) + '">' + esc(wechat) + '</span>';
            }, nowrap: true },
            { title: '联系方式', render: function (l) {
                var phone = l.phone || '—';
                return '<span class="lead-cell-ellipsis" title="' + esc(phone) + '">' + esc(phone) + '</span>';
            }, nowrap: true },
            { title: '标签', render: function (l) {
                return (l.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') || '—';
            } },
            { title: '意向', render: function (l) { return leadIntentBadge(l.intent_level); }, nowrap: true },
            { title: '上次跟进', nowrap: true, render: function (l) {
                return l.last_follow_at ? fmtDateTime(l.last_follow_at).slice(5, 16) : '—';
            } },
            { title: '创建时间', nowrap: true, render: function (l) {
                return fmtDateTime(l.created_at).slice(0, 10);
            } },
            { title: '操作', nowrap: true, render: function (l) {
                var ops = [];
                if (l.status === 'invalid') {
                    ops.push({ op: 'follow', arg: l.id, label: '查看' });
                    ops.push({ op: 'delete', arg: l.id, label: '删除', danger: true });
                } else {
                    ops.push({ op: 'edit', arg: l.id, label: '编辑' });
                    ops.push({ op: 'follow', arg: l.id, label: '跟进' });
                }
                return opButtons(ops);
            } }
        ], items, st.q || st.status ? '没有匹配的线索，换个条件试试'
            : '还没有线索，点右上「新增线索」开始', 'lead-table');

        pagerEl.innerHTML = pagerHtml(res);
        pagerEl.onclick = function (ev) {
            var btn = ev.target.closest('button[data-page]');
            if (!btn || btn.disabled) { return; }
            st.page = Number(btn.getAttribute('data-page')) || 1;
            loadLeads(root);
        };

        bindOps(root, {
            edit: function (id) { return openLeadEdit(id, root); },
            follow: function (id) { navigate('#/leads/' + id + '/follow'); },
            delete: function (id) { return openLeadDeleteConfirm(id); }
        });
    }).catch(function (err) {
        listEl.innerHTML = '<p class="err">' + esc(err.message) + '</p>';
    });
}

function leadFormHtml(lead) {
    var l = lead || {};
    return '<form class=\"lead-form form-grid\" autocomplete=\"off\" novalidate>' +
        '<div class=\"notice danger-notice\" id=\"leadFormError\" role=\"alert\" aria-live=\"assertive\" hidden></div>' +
        '<div class=\"row-2\">' +
        '<div class=\"field\"><label>名称 *</label>' +
        '<input name=\"name\" type=\"text\" maxlength=\"64\" required value=\"' + esc(l.name || '') + '\"></div>' +
        '<div class=\"field\"><label>类型</label>' +
                '<select name="lead_type">' + dictOptions('customer_type', l.lead_type || 'company') + '</select></div>' +
        '</div>' +
        '<div class=\"row-2\">' +
        '<div class=\"field\"><label>电话 *</label>' +
        '<input name=\"phone\" type=\"tel\" maxlength=\"32\" inputmode=\"tel\" required value=\"' + esc(l.phone || '') + '\"></div>' +
        '<div class=\"field\"><label>微信</label>' +
        '<input name=\"wechat\" type=\"text\" maxlength=\"64\" value=\"' + esc(l.wechat || '') + '\"></div>' +
        '</div>' +
        '<div class=\"row-2\">' +
        '<div class=\"field\"><label>联系人</label>' +
        '<input name=\"company_name\" type=\"text\" maxlength=\"100\" value=\"' + esc(l.company_name || '') + '\"></div>' +
        '<div class=\"field\"><label>地区</label>' +
        '<input name=\"location\" type=\"text\" maxlength=\"200\" value=\"' + esc(l.location || '') + '\" placeholder=\"省份.城市\"></div>' +
        '</div>' +
        '<div class=\"row-2\">' +
        '<div class=\"field\"><label>来源</label>' +
        '<select name="source">' + dictOptions('customer_source', l.source || 'other', '') + '</select></div>' +
        '<div class=\"field\"><label>意向</label>' +
        '<select name="intent_level">' + dictOptions('intent_level', l.intent_level || 'low', '') + '</select></div>' +
        '</div>' +
        '<div class=\"field\"><label>标签</label>' +
        '<input name=\"tags\" type=\"text\" maxlength=\"400\" value=\"' + esc((l.tags || []).join('，')) + '" ' +
        'placeholder="多个标签可用中文或英文逗号分隔"></div>' +
        '<div class=\"field\"><label>备注</label>' +
        '<textarea name=\"note\" maxlength=\"500\">' + esc(l.note || '') + '</textarea></div>' +
        '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">保存</button></div>' +
        '</form>';
}

function parseLeadTags(raw) {
    var seen = {};
    return String(raw || '').split(/[，,、;；\s]+/).map(function (tag) {
        return tag.trim();
    }).filter(function (tag) {
        if (!tag || seen[tag]) { return false; }
        seen[tag] = true;
        return true;
    }).slice(0, MAX_TAGS);
}

function readLeadForm(form) {
    function val(name) {
        var el = form.querySelector('[name=\"' + name + '\"]');
        return el ? String(el.value || '').trim() : '';
    }
    var tags = parseLeadTags(val('tags'));
    return {
        name: val('name'),
        phone: val('phone') || null,
        wechat: val('wechat') || null,
        lead_type: val('lead_type') || 'personal',
        company_name: val('company_name') || null,
        source: val('source') || 'other',
        location: val('location') || null,
        note: val('note') || null,
        intent_level: val('intent_level') || 'low',
        tags: tags
    };
}

/* 新建线索：模态对话框（原内嵌表单搬到弹层，对齐 demo 定稿；手机上不再把列表顶出屏） */
function openLeadFormModal(root, lead) {
    var isEdit = !!(lead && lead.id);
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content wide">' +
        '<div class="modal-header"><h3>' + (isEdit ? '编辑线索' : '新建线索') + '</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' + leadFormHtml(lead || null) + '</div>' +
        '</div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }

    var form = modal.querySelector('form');
    var actions = form.querySelector('.form-actions');
    var errorEl = form.querySelector('#leadFormError');
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn modal-cancel';
    cancelBtn.textContent = '取消';
    cancelBtn.addEventListener('click', close);
    if (actions) { actions.insertBefore(cancelBtn, actions.firstChild); }
    var submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) { submitBtn.textContent = isEdit ? '保存' : '新增'; }

    function clearLeadFormError() {
        if (errorEl) {
            errorEl.textContent = '';
            errorEl.hidden = true;
        }
        $$('[aria-invalid="true"]', form).forEach(function (el) {
            el.removeAttribute('aria-invalid');
        });
    }

    function showLeadFormError(message, fieldName) {
        var text = message || '保存失败，请稍后重试';
        if (errorEl) {
            errorEl.textContent = text;
            errorEl.hidden = false;
        }
        var field = fieldName ? form.querySelector('[name="' + fieldName + '"]') : null;
        if (field) {
            field.setAttribute('aria-invalid', 'true');
            field.focus();
        }
        toast(text, true);
    }

    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.addEventListener('click', function (ev) {
        if (ev.target === modal || (ev.target.classList && ev.target.classList.contains('modal-overlay'))) { close(); }
    });

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        clearLeadFormError();
        var payload = readLeadForm(form);
        if (!payload.name) {
            showLeadFormError('名称不能为空', 'name');
            return;
        }
        if (!payload.phone) {
            showLeadFormError('电话不能为空', 'phone');
            return;
        }
        if (!payload.source) {
            showLeadFormError('请选择来源（可在「数据字典 → 客户来源」里维护）', 'source');
            return;
        }
        submitBtn.disabled = true;
        var req = isEdit
            ? api('/leads/' + lead.id, { method: 'PUT', body: payload })
            : api('/leads', { method: 'POST', body: payload });
        req.then(function (res) {
            if (!isEdit && res && res.duplicate_hint) { showDuplicateHintModal(res.duplicate_hint); }
            toast(isEdit ? '线索已保存' : '已新建线索');
            close();
            refreshAfterLeadChange(root);
        }).catch(function (err) {
            if (!isEdit && err.code === 'duplicate_contact' && err.data && err.data.duplicate_hint) {
                close();
                showDuplicateHintModal(err.data.duplicate_hint);
                return;
            }
            showLeadFormError(err.message);
        }).then(function () { submitBtn.disabled = false; });
    });
    form.addEventListener('input', clearLeadFormError);
    form.addEventListener('change', clearLeadFormError);
}

/* 线索改动后刷新：
 *   · 在跟进页（#/leads/{id}/follow）→ 整页重渲染，信息卡/履历立刻是最新的
 *   · 在列表页 → 只重载列表
 */
function refreshAfterLeadChange(root) {
    if (/^#\/leads\/\d+/.test(location.hash || '')) {
        return render();
    }
    if (root && $('#leadList', root)) {
        return loadLeads(root);
    }
    return render();
}

/* 编辑：先取详情再开弹层（列表行只有摘要字段） */
function openLeadEdit(id, root) {
    return api('/leads/' + id).then(function (l) {
        openLeadFormModal(root, l);
    }).catch(function (err) { toast(err.message, true); });
}

/* 线索详情页面逻辑 */
/* 线索详情 = 跟进页（完全对齐 demo #/leads/{id}/follow）
 *   · 顶部信息卡 + 操作（编辑线索 / 转商机 / **标记失效**——用户要求保留）
 *   · 跟进履历 = 时间线（跟进 / 创建 / 编辑 / 状态变更… 混排，带缩略图）
 *   · 记一条跟进走模态框（含下次跟进开关 + 多附件）
 *   · 底部资料卡汇总所有附件
 */
function viewLeadDetail(root, rawId) {
    var id = Number(rawId);
    if (!id || isNaN(id)) {
        root.innerHTML = '<div class="card">线索 id 不合法，<a href="#/leads">回线索池</a></div>';
        return Promise.resolve();
    }

    return Promise.all([
        api('/leads/' + id),
        api('/follow-ups?object_type=lead&object_id=' + id + '&include_system=true')
            .catch(function () { return []; })
    ]).then(function (all) {
        var l = all[0];
        var raw = all[1] || [];
        if (!l) {
            root.innerHTML = '<div class="card">线索不存在，<a href="#/leads">回线索池</a></div>';
            return;
        }

        var records = followupRecordsFromApi(raw);

        var name = l.name || (l.lead_type === 'company' ? l.company_name : '') || ('线索 #' + l.id);
        var converted = l.status === 'converted';
        var invalid = l.status === 'invalid';

        var actions = '';
        if (converted) {
            if (l.converted_customer_id) {
                actions += '<a class="btn btn-sm" href="#/customers/' + l.converted_customer_id + '">看客户档案 ›</a>';
            }
        } else if (invalid) {
            actions += '<button type="button" class="btn btn-sm btn-danger" id="deleteLeadBtn">删除线索</button>';
        } else {
            actions += '<button type="button" class="btn btn-sm" id="leadEditBtn">编辑线索</button>' +
                '<button type="button" class="btn btn-sm btn-primary" id="leadToDealBtn">转商机</button>' +
                '<button type="button" class="btn btn-sm" id="invalidateBtn">标记失效</button>';
        }

        renderEntityFollowPage(root, {
            backHash: '#/leads',
            backLabel: '线索池',
            objectType: 'lead',
            title: name,
            titleHtml:
                '<div class="lead-detail-title-main">' +
                '<a class="crumb lead-detail-crumb" href="#/leads">‹ 线索池</a>' +
                '<div class="lead-detail-title-line"><h2>' + esc(name) + '</h2>' +
                '<div class="detail-title-tags">' + leadDetailTags(l.tags) + '</div></div></div>',
            badgesHtml: leadStatusBadge(l.status) + ' ' + leadIntentBadge(l.intent_level),
            infoHtml: infoGrid([
                ['类型', leadTypeText(l)],
                ['来源', leadSourceText(l), true],
                ['地区', l.location],
                ['微信号', l.wechat],
                ['联系方式', l.phone],
                ['联系人', l.company_name],
                ['建档时间', fmtDateTime(l.created_at)],
                ['最近更新', fmtDateTime(l.updated_at)],
                ['备注', l.note],
                ['失效原因', invalid ? invalidReasonLabel(l.invalid_reason, l.invalid_reason_other) : '—']
            ]),
            actionsHtml: actions,
            placeholder: '这次沟通聊了什么？对方什么态度？下一步做什么？',
            canFollow: !invalid && !converted,
            lockedText: converted ? '线索已转商机，请到客户档案中继续跟进' : '无效的线索不能再添加跟进',
            records: records,
            extraHtml: filesCardHtml(collectFiles(records), '这个线索还没有上传图纸 / 报价单 / 现场照片'),
            onSubmit: function (p) {
                var fd = new FormData();
                fd.append('object_type', 'lead');
                fd.append('object_id', String(l.id));
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

        var editBtn = $('#leadEditBtn', root);
        if (editBtn) { editBtn.addEventListener('click', function () { openLeadFormModal(root, l); }); }
        var toDealBtn = $('#leadToDealBtn', root);
        if (toDealBtn) { toDealBtn.addEventListener('click', function () { openLeadDealModal(l); }); }
        var invBtn = $('#invalidateBtn', root);
        if (invBtn) { invBtn.addEventListener('click', function () { invalidateLead(l.id); }); }
        var deleteBtn = $('#deleteLeadBtn', root);
        if (deleteBtn) { deleteBtn.addEventListener('click', function () { openLeadDeleteConfirm(l.id); }); }
    });
}

/* 转商机：同样使用 shared.js 的通用弹层。 */
function openLeadDealModal(lead) {
    return openDealConvertModal(lead, 'lead');
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
        '<form id=\"invalidateForm\" class=\"invalidate-form form-grid\">' +
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
                state.filters.q = '';
                state.filters.status = 'invalid';
                state.filters.page = 1;
                location.hash = '#/leads';
                render();
            })
            .catch(function (err) {
                toast(err.message, true);
            });
    });
}

function openLeadDeleteConfirm(leadId) {
    api('/leads/' + leadId).then(function (lead) {
        var name = lead.name || lead.company_name || ('线索 #' + lead.id);
        var modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML =
            '<div class="modal-overlay"></div>' +
            '<div class="modal-content">' +
            '<div class="modal-header"><h3>删除线索</h3>' +
            '<button type="button" class="btn btn-link modal-close">×</button></div>' +
            '<div class="modal-body">' +
            '<div class="notice danger-notice">即将删除无效线索「' + esc(name) +
            '」。数据会标记为已删除，不再出现在线索池，但可由管理员从数据库追溯。</div>' +
            '<div class="form-actions">' +
            '<button type="button" class="btn modal-cancel">取消</button>' +
            '<button type="button" class="btn btn-danger" id="confirmLeadDelete">确认删除</button>' +
            '</div></div></div>';
        document.body.appendChild(modal);

        function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
        modal.querySelector('.modal-close').addEventListener('click', close);
        modal.querySelector('.modal-cancel').addEventListener('click', close);
        modal.querySelector('#confirmLeadDelete').addEventListener('click', function () {
            var btn = modal.querySelector('#confirmLeadDelete');
            btn.disabled = true;
            api('/leads/' + lead.id, { method: 'DELETE' }).then(function () {
                close();
                toast('线索已删除');
                state.filters.q = '';
                state.filters.status = 'invalid';
                state.filters.page = 1;
                if (location.hash === '#/leads') { render(); }
                else { navigate('#/leads'); }
            }).catch(function (err) {
                btn.disabled = false;
                toast(err.message, true);
            });
        });
    }).catch(function (err) {
        toast(err.message, true);
    });
}

// 显示去重提示弹层
function showDuplicateHintModal(hint) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content">' +
        '<div class="modal-header"><h3>线索重复提醒</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<p>线索池或客户档案里已有相同联系方式的记录：</p>' +
        '<p><b>' + esc(hint.name || '') + '</b>' +
        (hint.phone ? ' · ' + esc(hint.phone) : '') +
        (hint.wechat ? ' · ' + esc(hint.wechat) : '') + '</p>' +
        '<p class="small muted">本次没有创建新线索。请直接编辑已有档案，或到客户详情继续跟进。</p>' +
        '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">知道了</button>' +
        (hint.object_id
            ? '<a class="btn btn-primary" href="#/' +
                (hint.object_type === 'customer' ? 'customers/' : 'leads/') + hint.object_id + '">' +
                (hint.object_type === 'customer' ? '查看已有客户' : '查看已有线索') + '</a>'
            : '') +
        '</div>' +
        '</div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);
    var existingLink = modal.querySelector('a.btn');
    if (existingLink) { existingLink.addEventListener('click', close); }
}

/* ---------------- 批量导入 / 导入模板（对齐 demo PAGES-V2 §7.3 顶部按钮） ----------------
 * demo 里那两颗按钮是假导入；这里是真链路：
 *   上传 CSV → POST /import/preview（表头 + 前 5 行 + 建议列映射，文件被后端缓存成 file_ref）
 *   → 核对/手改列映射 → POST /import/commit（file_ref + column_mapping）→ 写 customers 表。
 * 模板表头必须能命中后端 csvimport.HEADER_ALIASES 才会自动映射（名称/电话/微信/地区/备注）。
 */
var IMPORT_FIELDS_FALLBACK = [
    { key: 'name', label: '名称', required: true },
    { key: 'phone', label: '电话', required: false },
    { key: 'wechat', label: '微信', required: false },
    { key: 'location', label: '地区', required: false },
    { key: 'source', label: '来源', required: true },
    { key: 'note', label: '备注', required: false }
];

/* 模板必须由后端在每次点击时实时读取数据字典并生成，避免页面缓存造成来源过期。 */
function downloadLeadTemplate() {
    toast('正在按最新数据字典生成模板…');
    fetch(API_BASE + '/import/leads-template', {
        credentials: 'include',
        cache: 'no-store'
    }).then(function (res) {
        if (!res.ok) {
            return res.json().catch(function () { return {}; }).then(function (data) {
                throw new Error((data && data.detail) || '模板生成失败');
            });
        }
        return res.blob();
    }).then(function (blob) {
        var a = document.createElement('a');
        var url = URL.createObjectURL(blob);
        a.href = url;
        a.download = '客户导入模板.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        toast('模板已按当前数据字典生成');
    }).catch(function (err) {
        toast(err.message || '模板生成失败', true);
    });
}

/* 列映射 + 前 5 行预览（字段列表用后端返回的 system_fields，缺省回退硬编码） */
function leadImportPreviewHtml(pv) {
    var fields = (pv.system_fields && pv.system_fields.length) ? pv.system_fields : IMPORT_FIELDS_FALLBACK;
    var suggested = pv.suggested_mapping || {};
    var last = pv.last_mapping || {};
    var initial = Object.keys(suggested).length ? suggested : last;
    var headers = pv.headers || [];

    var mappingRows = headers.map(function (header) {
        var current = initial[header] || '';
        var options = '<option value="">不导入</option>' + fields.map(function (f) {
            var optionLabel = f.label + ((f.required || f.key === 'source') ? ' *' : '');
            return '<option value="' + esc(f.key) + '"' + (f.key === current ? ' selected' : '') + '>' +
                esc(optionLabel) + '</option>';
        }).join('');
        return '<div class="field"><label>CSV 列：' + esc(header) + '</label>' +
            '<select data-imp-header="' + esc(header) + '">' + options + '</select></div>';
    }).join('');

    var headHtml = headers.map(function (h) { return '<th>' + esc(h) + '</th>'; }).join('');
    var bodyHtml = (pv.preview || []).map(function (row) {
        return '<tr>' + headers.map(function (h) {
            var v = row[h];
            return '<td>' + esc(v === undefined || v === null ? '' : v) + '</td>';
        }).join('') + '</tr>';
    }).join('');

    return '<p class="small muted">文件：' + esc(pv.file_name) +
        ' · 共 ' + (pv.total_rows || 0) + ' 行数据 · 编码 ' + esc(pv.encoding || '?') +
        ' · 分隔符 ' + esc(pv.delimiter || ',') +
        (Object.keys(suggested).length ? ' · 列名已自动匹配，可手改' : ' · 请手动指定每列对应字段') +
        '</p>' +
        mappingRows +
        '<p class="small muted">前 ' + (pv.preview || []).length + ' 行预览：</p>' +
        '<div class="table-wrap"><table><thead><tr>' + headHtml + '</tr></thead><tbody>' +
        (bodyHtml || '<tr><td>（没有数据行，只有表头）</td></tr>') + '</tbody></table></div>' +
        '<div class="notice small" id="impErr" hidden></div>';
}

function openLeadImportModal(root) {
    var sourceLabels = dictItems('customer_source').map(function (item) {
        return String(item.label || item.key || '').trim();
    }).filter(Boolean);
    var sourceText = sourceLabels.join('、') || '请先到数据字典添加客户来源';
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content">' +
        '<div class="modal-header"><h3>批量导入线索</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<ol class="small muted" style="padding-left:18px;line-height:1.9;margin-top:0">' +
        '<li>下载模板 → 按列填好（<b>名称必填</b>，电话和微信至少一个，来源必填）</li>' +
        '<li>模板已做成「全文本」格式（不会把手机号变成 1.38E+10）；填完另存为 CSV（逗号分隔）再上传</li>' +
        '<li>上传 → 核对列映射和前 5 行 → 确认导入（写进「线索池」）</li>' +
        '</ol>' +
        '<div class="notice source-guide"><b>来源只能填写：</b>' + esc(sourceText) +
        '<br><span class="small muted">电话是唯一字段；文件内或数据库中电话重复时整批导入失败。来源不一致也会失败。</span></div>' +
        '<div class="field"><label>选择 CSV 文件</label>' +
        '<input type="file" id="impFileEl" accept=".csv,text/csv"></div>' +
        '<div id="impPreview"></div>' +
        '<div class="form-actions">' +
        '<button type="button" class="btn" id="impTpl2">⬇ 下载模板</button>' +
        '<button type="button" class="btn btn-primary" id="impGo" disabled>导入到线索池</button>' +
        '</div>' +
        '</div></div>';
    document.body.appendChild(modal);

    var fileEl = $('#impFileEl', modal);
    var previewEl = $('#impPreview', modal);
    var goBtn = $('#impGo', modal);
    var pv = null;

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }

    function readMapping() {
        var mapping = {};
        $$('select[data-imp-header]', modal).forEach(function (sel) {
            if (sel.value) { mapping[sel.getAttribute('data-imp-header')] = sel.value; }
        });
        return mapping;
    }

    /* 「名称」必须映射；同一字段不能被两列同时占用（后端以字段为 key 建索引，会互相覆盖） */
    function refreshGoState() {
        var mapping = readMapping();
        var used = Object.keys(mapping).map(function (k) { return mapping[k]; });
        var dup = used.filter(function (v, i) { return used.indexOf(v) !== i; });
        var msg = '';
        if (used.indexOf('name') < 0) { msg = '必须把某一列映射到「名称 *」'; }
        else if (used.indexOf('source') < 0) { msg = '必须把某一列映射到「来源 *」'; }
        else if (dup.length) { msg = '同一字段被多列占用：' + dup.join('、'); }
        else if (pv && pv.file_ref && !pv.total_rows) { msg = '文件里只有表头，没有数据行'; }
        var errEl = modal.querySelector('#impErr');
        if (errEl) { errEl.hidden = !msg; errEl.textContent = msg; }
        goBtn.disabled = !!msg || !pv || !pv.file_ref;
        return !msg;
    }

    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('#impTpl2').addEventListener('click', downloadLeadTemplate);

    fileEl.addEventListener('change', function (ev) {
        var file = ev.target.files && ev.target.files[0];
        if (!file) { return; }
        var fd = new FormData();
        fd.append('file', file);
        pv = null;
        goBtn.disabled = true;
        previewEl.innerHTML = '<p class="loading">解析中…</p>';
        api('/import/preview', { method: 'POST', body: fd }).then(function (res) {
            if (res.kind === 'xlsx_unsupported') {
                previewEl.innerHTML = '<div class="notice">' + esc(res.message || '请先另存为 CSV') + '</div>';
                toast('Excel 需要先另存为 CSV', true);
                return;
            }
            pv = res;
            previewEl.innerHTML = leadImportPreviewHtml(res);
            refreshGoState();
            toast('解析成功，共 ' + (res.total_rows || 0) + ' 行');
        }).catch(function (err) {
            previewEl.innerHTML = '';
            toast(err.message, true);
        });
    });

    previewEl.addEventListener('change', function (ev) {
        if (ev.target && ev.target.getAttribute && ev.target.getAttribute('data-imp-header') !== null) {
            refreshGoState();
        }
    });

    goBtn.addEventListener('click', function () {
        if (!pv || !pv.file_ref) { toast('先上传一个 CSV 文件', true); return; }
        if (!refreshGoState()) { return; }
        goBtn.disabled = true;
        goBtn.textContent = '导入中…';
        api('/import/commit', {
            method: 'POST',
            body: { file_ref: pv.file_ref, column_mapping: readMapping(), source_name: pv.file_name, target: 'leads' }
        }).then(function (res) {
            pv = null;
            fileEl.value = '';
            invalidateCustomerIndex();
            close();
            state.filters.q = '';
            state.filters.status = '';
            state.filters.page = 1;
            var summary = '导入完成：成功 ' + res.imported + ' 行';
            if (res.skipped) { summary += '，空名称跳过 ' + res.skipped + ' 行'; }
            toast(summary);
            if (location.hash === '#/leads') { render(); }
            else { navigate('#/leads'); }
        }).catch(function (err) {
            var message = err.message || '导入失败';
            previewEl.innerHTML = '<div class="notice danger-notice">' + esc(message) + '</div>';
            toast('导入失败，请按校验信息修正文件', true);
            goBtn.textContent = '导入到线索池';
            goBtn.disabled = false;
        });
    });
}
