/* 线索列表页面逻辑 */
/* ---------------- 线索列表（表格，对齐 demo 定稿） ----------------
 * 定稿口径：表格列 = 名称 / 来源 / 地区 / 微信号 / 联系方式 / 标签 / 意向 / 上次跟进 / 创建时间 / 操作
 *           操作 = 编辑（弹层）/ 跟进（详情页）/ 转商机（独立页面 #/deals/new?lead=）
 */
function viewLeads(root) {
    var st = state.filters;
    /* 版本一致性自检：app.js 与 views/*.js 版本不同步时（浏览器缓存一半），
       下面所有 dictOptions / openLeadFormModal 都会 ReferenceError，表现为「点了没反应」。
       这里直接给出可执行的提示，别让用户猜。 */
    if (typeof dictOptions !== 'function' || typeof ensureDicts !== 'function') {
        root.innerHTML = '<div class="card"><p class="err">页面脚本版本不一致（浏览器缓存了旧文件）。' +
            '请按 Ctrl+F5（手机：清缓存）强制刷新一次。</p></div>';
        return Promise.resolve();
    }
    var tabs = [['', '全部'], ['new', '新线索'], ['following', '跟进中'], ['converted', '已转化'], ['invalid', '已失效']];
    var tabHtml = tabs.map(function (t) {
        return '<button type="button" class="tab-btn' + ((st.status || '') === t[0] ? ' active' : '') +
            '" data-status="' + t[0] + '">' + t[1] + '</button>';
    }).join('');

    root.innerHTML =
        '<div class="card">' +
        '<div class="card-head"><h2>线索池</h2>' +
        '<div class="btn-row" style="display:flex;gap:8px;align-items:center">' +
        '<button type="button" class="btn btn-primary btn-sm" id="toggleNewLead">＋ 新增线索</button>' +
        '<button type="button" class="btn btn-sm" id="btnImportLead">⇪ 批量导入</button>' +
        '</div></div>' +
        '<div class="searchbar">' +
        '<input id="leadSearch" type="search" placeholder="搜姓名 / 电话 / 微信 / 地区" autocomplete="off" value="' + esc(st.q) + '">' +
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

function leadIntentBadge(level) {
    if (!level) { return '—'; }
    var cls = level === 'high' ? 'danger' : (level === 'medium' ? 'warn' : 'muted');
    var label = INTENT_LABELS[level] || level;
    return '<span class="badge ' + cls + '">' + esc(label) + '</span>';
}

function leadStatusBadge(status) {
    var map = {
        new: ['ok', '新线索'], following: ['warn', '跟进中'],
        converted: ['muted', '已转化'], invalid: ['danger', '已失效']
    };
    var v = map[status] || map.new;
    return '<span class="badge ' + v[0] + '">' + v[1] + '</span>';
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
                return '<a href="#/leads/' + l.id + '">' + esc(name) + '</a>' +
                    (l.company_name && l.lead_type === 'company' && l.company_name !== name
                        ? '<div class="small muted">' + esc(l.company_name) + '</div>' : '') +
                    ' ' + leadStatusBadge(l.status);
            } },
            { title: '来源', render: function (l) { return esc(leadSourceText(l)); }, nowrap: true },
            { title: '地区', render: function (l) { return esc(l.location || '—'); } },
            { title: '微信号', render: function (l) { return esc(l.wechat || '—'); }, nowrap: true },
            { title: '联系方式', render: function (l) { return esc(l.phone || '—'); }, nowrap: true },
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
                var ops = [{ op: 'edit', arg: l.id, label: '编辑' }, { op: 'follow', arg: l.id, label: '跟进' }];
                if (l.status === 'converted') {
                    ops.push({ op: 'toDeal', arg: l.id, label: '转商机', disabled: true, tip: '已转化，请到客户里转商机' });
                } else if (l.status === 'invalid') {
                    ops.push({ op: 'toDeal', arg: l.id, label: '转商机', disabled: true, tip: '已失效线索不能转商机' });
                } else {
                    ops.push({ op: 'toDeal', arg: l.id, label: '转商机' });
                }
                return opButtons(ops);
            } }
        ], items, st.q || st.status ? '没有匹配的线索，换个条件试试'
            : '还没有线索，点右上「新增线索」开始');

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
            toDeal: function (id) {
                api('/leads/' + id).then(function (l) { openLeadDealModal(l); })
                    .catch(function (err) { toast(err.message, true); });
            }
        });
    }).catch(function (err) {
        listEl.innerHTML = '<p class="err">' + esc(err.message) + '</p>';
    });
}

function leadFormHtml(lead) {
    var l = lead || {};
    return '<form class=\"lead-form\" autocomplete=\"off\">' +
        '<div class=\"row-2\">' +
        '<div class=\"field\"><label>姓名 *</label>' +
        '<input name=\"name\" type=\"text\" maxlength=\"64\" required value=\"' + esc(l.name || '') + '\"></div>' +
        '<div class=\"field\"><label>类型</label>' +
                '<select name="lead_type">' + dictOptions('customer_type', l.lead_type || 'company') + '</select></div>' +
        '</div>' +
        '<div class=\"field\"><label>电话</label>' +
        '<input name=\"phone\" type=\"tel\" maxlength=\"32\" inputmode=\"tel\" value=\"' + esc(l.phone || '') + '\"></div>' +
        '<div class=\"field\"><label>微信</label>' +
        '<input name=\"wechat\" type=\"text\" maxlength=\"64\" value=\"' + esc(l.wechat || '') + '\"></div>' +
        '<div class=\"field\"><label>公司名</label>' +
        '<input name=\"company_name\" type=\"text\" maxlength=\"100\" value=\"' + esc(l.company_name || '') + '\"></div>' +
        '<div class=\"field\"><label>地区</label>' +
        '<input name=\"location\" type=\"text\" maxlength=\"200\" value=\"' + esc(l.location || '') + '\"></div>' +
        '<div class=\"field\"><label>来源</label>' +
        '<select name="source">' + dictOptions('customer_source', l.source, '请选择') + '</select></div>' +
        '<div class=\"field\"><label>意向</label>' +
        '<select name="intent_level">' + dictOptions('intent_level', l.intent_level || 'medium', '') + '</select></div>' +
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
        location: val('location') || null,
        note: val('note') || null,
        intent_level: val('intent_level') || null,
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
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn modal-cancel';
    cancelBtn.textContent = '取消';
    cancelBtn.addEventListener('click', close);
    if (actions) { actions.insertBefore(cancelBtn, actions.firstChild); }
    var submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) { submitBtn.textContent = isEdit ? '保存' : '新增'; }

    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.addEventListener('click', function (ev) {
        if (ev.target === modal || (ev.target.classList && ev.target.classList.contains('modal-overlay'))) { close(); }
    });

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var payload = readLeadForm(form);
        if (!payload.name && !payload.phone && !payload.wechat) {
            toast('姓名、手机或微信至少填一项', true);
            return;
        }
        /* 来源是后端必填（数据字典 customer_source），别让它以 400 的形式回来 */
        if (!payload.source) {
            toast('请选择来源（可在「数据字典 → 客户来源」里维护）', true);
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
            toast(err.message, true);
        }).then(function () { submitBtn.disabled = false; });
    });
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

        /* 后端记录 → 时间线记录（kind → RECORD_META 的 type） */
        var TYPE_MAP = {
            follow: 'follow', create: 'create', change: 'change', update: 'change',
            stage: 'stage', order: 'order', aftersale: 'aftersale', pay: 'pay', ship: 'ship'
        };
        var records = raw.map(function (r) {
            var photos = (r.photos || []).map(function (ph) {
                var url = '/crm' + ph.url;
                return { name: ph.file_name || '照片', url: url, isImage: /\.(jpg|jpeg|png|gif|webp|bmp|heic)$/i.test(ph.file_name || '') };
            });
            return {
                at: r.created_at,
                type: TYPE_MAP[r.kind] || 'follow',
                content: r.content || '',
                next_date: r.next_date,
                method: r.method,
                files: photos
            };
        });

        var name = l.name || (l.lead_type === 'company' ? l.company_name : '') || ('线索 #' + l.id);
        var converted = l.status === 'converted';
        var invalid = l.status === 'invalid';

        var actions = '<button type="button" class="btn btn-sm" id="leadEditBtn">编辑线索</button>';
        if (converted) {
            actions += '<button type="button" class="btn btn-sm" disabled title="已转化，请到客户里转商机">转商机</button>';
            if (l.converted_customer_id) {
                actions += '<a class="btn btn-sm" href="#/customers/' + l.converted_customer_id + '">看客户档案 ›</a>';
            }
        } else if (invalid) {
            actions += '<button type="button" class="btn btn-sm" disabled title="已失效线索不能转商机">转商机</button>';
        } else {
            actions += '<button type="button" class="btn btn-sm btn-primary" id="leadToDealBtn">转商机</button>' +
                '<button type="button" class="btn btn-sm" id="invalidateBtn">标记失效</button>';
        }

        renderEntityFollowPage(root, {
            backHash: '#/leads',
            backLabel: '线索池',
            title: name,
            badgesHtml: leadStatusBadge(l.status) + ' ' + leadIntentBadge(l.intent_level),
            infoHtml: infoGrid([
                ['类型', l.lead_type === 'company' ? '公司' : '个人'],
                ['来源', leadSourceText(l), true],
                ['地区', l.location],
                ['微信号', l.wechat],
                ['联系方式', l.phone],
                ['公司名', l.company_name],
                ['标签', (l.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') || '—', true],
                ['建档时间', fmtDateTime(l.created_at)],
                ['最近更新', fmtDateTime(l.updated_at)],
                ['备注', l.note],
                ['失效原因', invalid ? (l.invalid_reason_other || l.invalid_reason) : '—']
            ]),
            actionsHtml: actions,
            placeholder: '这次沟通聊了什么？对方什么态度？下一步做什么？',
            canFollow: !invalid,
            lockedText: '已失效的线索不能再添加跟进',
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

        $('#leadEditBtn', root).addEventListener('click', function () { openLeadFormModal(root, l); });
        var toDealBtn = $('#leadToDealBtn', root);
        if (toDealBtn) { toDealBtn.addEventListener('click', function () { openLeadDealModal(l); }); }
        var invBtn = $('#invalidateBtn', root);
        if (invBtn) { invBtn.addEventListener('click', function () { invalidateLead(l.id); }); }
    });
}

/* 转商机（模态；字段对齐 demo #/deals/new?lead=1） */
function openLeadDealModal(lead) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content wide">' +
        '<div class="modal-header"><h3>转商机</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<form id="leadDealForm" autocomplete="off">' +
        '<p class="small muted" style="margin-top:0">来源：' +
        esc(lead.name || lead.company_name || ('线索 #' + lead.id)) + '（线索）　转化会同时建立客户档案。</p>' +
        '<div class="row-2">' +
        '<div class="field"><label>产品类型</label>' +
        '<select name="product_type">' + dictOptions('product_type', '天窗', '请选择') + '</select></div>' +
        '<div class="field"><label>手动 / 电动 *</label>' +
        '<select name="drive_type">' +
        '<option value="manual">手动</option>' +
        '<option value="electric">电动</option>' +
        '</select></div>' +
        '</div>' +
        '<div class="row-2">' +
        '<div class="field"><label>产品型号 *</label>' + modelComboHtml('') + '</div>' +
        '<div class="field"><label>尺寸（宽×高 mm）*</label>' +
        '<input name="spec" maxlength="32" required placeholder="按现场量尺填，如 1480×2350"></div>' +
        '</div>' +
        '<div class="row-2">' +
        '<div class="field"><label>金额（报价）*</label>' +
        '<input name="amount" type="number" min="0" step="0.01" inputmode="decimal" required placeholder="12000"></div>' +
        '<div class="field"><label>阶段</label>' +
        '<input value="报价" disabled title="新建商机固定为报价"></div>' +
        '</div>' +
        '<div class="field"><label>备注</label>' +
        '<textarea name="note" maxlength="300" placeholder="客户需求、现场情况、特殊要求…"></textarea></div>' +
        '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">创建商机</button>' +
        '</div>' +
        '</form>' +
        '</div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);

    var form = modal.querySelector('form');

    /* 型号可搜索；只带出产品类型 / 手动电动，**尺寸不自动填**（定制天窗尺寸不固定） */
    bindModelCombo(form.querySelector('[data-model-combo]'), dictItems('product_model'), function (hit) {
        if (hit && hit.meta) {
            if (hit.meta.drive) { form.querySelector('[name="drive_type"]').value = hit.meta.drive; }
            if (hit.meta.product) { form.querySelector('[name="product_type"]').value = hit.meta.product; }
        }
    });

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var amount = numOrNull(form.querySelector('[name="amount"]').value);
        var model = String(form.querySelector('[name="model"]').value || '');
        var spec = String(form.querySelector('[name="spec"]').value || '').trim();
        if (!model) { toast('请选择产品型号', true); return; }
        if (!spec) { toast('尺寸必填', true); return; }
        if (amount === null || !(amount > 0)) { toast('金额必须大于 0', true); return; }

        function val(n) {
            var el = form.querySelector('[name="' + n + '"]');
            return el ? String(el.value || '').trim() : '';
        }
        var body = {
            mode: 'new',
            deal: {
                title: [val('product_type'), model].filter(Boolean).join(' ').slice(0, 100) || null,
                product_type: val('product_type') || null,
                model: model,
                spec: spec,
                amount: amount,
                drive_type: val('drive_type') || null,
                note: val('note') || null
            }
        };
        btn.disabled = true;
        api('/leads/' + lead.id + '/convert', { method: 'POST', body: body }).then(function (res) {
            toast('已转商机');
            close();
            invalidateCustomerIndex();
            var deal = res && res.deal;
            if (deal && deal.id) { navigate('#/deals/' + deal.id); }
            else { navigate('#/deals'); }
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
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
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content">' +
        '<div class="modal-header"><h3>线索重复提醒</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<p>线索池里已有同手机号 / 同微信的记录：</p>' +
        '<p><b>' + esc(hint.name || '') + '</b>' +
        (hint.phone ? ' · ' + esc(hint.phone) : '') + '</p>' +
        '<p class="small muted">这次的新线索已经保存。重复记录请在列表里合并信息，或把多余的那条「标记失效」。</p>' +
        '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">知道了</button>' +
        (hint.object_id ? '<a class="btn btn-primary" href="#/leads/' + hint.object_id + '">查看已有线索</a>' : '') +
        '</div>' +
        '</div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);
}

/* ---------------- 批量导入 / 导入模板（对齐 demo PAGES-V2 §7.3 顶部按钮） ----------------
 * demo 里那两颗按钮是假导入；这里是真链路：
 *   上传 CSV → POST /import/preview（表头 + 前 5 行 + 建议列映射，文件被后端缓存成 file_ref）
 *   → 核对/手改列映射 → POST /import/commit（file_ref + column_mapping）→ 写 customers 表。
 * 模板表头必须能命中后端 csvimport.HEADER_ALIASES 才会自动映射（姓名/电话/微信/地区/备注）。
 */
var IMPORT_FIELDS_FALLBACK = [
    { key: 'name', label: '姓名', required: true },
    { key: 'phone', label: '电话', required: false },
    { key: 'wechat', label: '微信', required: false },
    { key: 'location', label: '地区', required: false },
    { key: 'note', label: '备注', required: false }
];

/* 生成并下载 CSV 模板（纯前端 Blob，不请求后端）
 * 2026-10-31 用户要求：
 *   1) 模板里加「来源」列（值可填数据字典里的名称，如 微信 / 抖音 / 转介绍）
 *   2) **所有单元格都是文本**：每个值都写成 ="内容"，Excel 打开后手机号不会被当数字
 *      变成 1.38E+10，日期也不会被自动改写。后端 csvimport 解析时会剥掉 ="..." 外壳。
 */
function leadTemplateCell(v) {
    return '="' + String(v === null || v === undefined ? '' : v).replace(/"/g, '""') + '"';
}

function downloadLeadTemplate() {
    var header = ['姓名', '电话', '微信', '地区', '来源', '备注'];
    var rows = [
        ['张三', '13800000000', 'zhangsan', '济南·历下区', '微信', '示例行，填真数据前删掉'],
        ['某某装饰公司', '0531-88888888', 'abc888', '青岛·崂山区', '转介绍', '来源填数据字典里的名称，如 抖音 / 小红书']
    ];
    var csv = '\ufeff' + [header].concat(rows).map(function (r) {
        return r.map(leadTemplateCell).join(',');
    }).join('\r\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '客户导入模板.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    toast('模板已下载（全文本格式，手机号不会变成科学计数）');
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
            return '<option value="' + esc(f.key) + '"' + (f.key === current ? ' selected' : '') + '>' +
                esc(f.label) + (f.required ? ' *' : '') + '</option>';
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

function openLeadImportModal() {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content">' +
        '<div class="modal-header"><h3>批量导入线索</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<ol class="small muted" style="padding-left:18px;line-height:1.9;margin-top:0">' +
        '<li>下载模板 → 按列填好（<b>姓名必填</b>，电话和微信至少一个；来源可填字典里的名称）</li>' +
        '<li>模板已做成「全文本」格式（不会把手机号变成 1.38E+10）；填完另存为 CSV（逗号分隔）再上传</li>' +
        '<li>上传 → 核对列映射和前 5 行 → 确认导入（写进「线索池」）</li>' +
        '</ol>' +
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

    /* 「姓名」必须映射；同一字段不能被两列同时占用（后端以字段为 key 建索引，会互相覆盖） */
    function refreshGoState() {
        var mapping = readMapping();
        var used = Object.keys(mapping).map(function (k) { return mapping[k]; });
        var dup = used.filter(function (v, i) { return used.indexOf(v) !== i; });
        var msg = '';
        if (used.indexOf('name') < 0) { msg = '必须把某一列映射到「姓名 *」'; }
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
            previewEl.innerHTML =
                '<div class="notice">成功导入线索 <b>' + res.imported + '</b> 行' +
                (res.skipped ? '，跳过 <b>' + res.skipped + '</b> 行（姓名为空）' : '') +
                '；文件共 ' + res.total_rows + ' 行。' +
                (res.mapping_reused ? '（复用了上次的列映射）' : '') +
                '<br><a href="#/leads" id="impGoLeads">去看线索池 →</a></div>';
            var link = previewEl.querySelector('#impGoLeads');
            if (link) {
                link.addEventListener('click', function (ev) {
                    ev.preventDefault();
                    close();
                    /* 当前已经在 #/leads 时 navigate 不触发 hashchange，必须主动重渲染 */
                    if (location.hash === '#/leads') { render(); }
                    else { navigate('#/leads'); }
                });
            }
            toast('导入完成：' + res.imported + ' 行');
            goBtn.textContent = '确认导入';
            goBtn.disabled = true;
        }).catch(function (err) {
            toast(err.message, true);
            goBtn.textContent = '确认导入';
            goBtn.disabled = false;
        });
    });
}