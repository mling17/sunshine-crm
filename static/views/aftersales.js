/* 售后页面（2026-10-31 对齐 demo 定稿）
 *
 * 定稿口径：
 *   · 列表用表格 + 状态 Tab；**没有「新建售后单」**（售后单从「订单 → 已完成 → 添加售后」生成）
 *   · 列表操作只有「跟进」；已完成后跟进按钮置灰不可点，直接点「售后单号」看详情
 *   · 详情 = 信息卡 + 跟进履历 + 记一条；待处理记一条后后端自动转「处理中」；
 *     处理中可「标记完成」；已完成 / 已拒绝不再允许跟进（后端也会拦）
 */

/* ---------------- 售后列表 ---------------- */
function viewAftersales(root, route) {
    var status = (route && route.query.get('status')) || '';
    var orderId = (route && route.query.get('order_id')) || '';
    var customerId = (route && route.query.get('customer_id')) || '';
    var page = Number((route && route.query.get('page')) || 1);

    var params = new URLSearchParams();
    params.set('page', String(page));
    params.set('size', String(PAGE_SIZE));
    if (status) { params.set('status', status); }
    if (orderId) { params.set('order_id', orderId); }
    if (customerId) { params.set('customer_id', customerId); }

    return api('/aftersales?' + params.toString()).then(function (res) {
        var items = (res && res.items) || [];

        var tabs = [['', '全部'], ['pending', '待处理'], ['processing', '处理中'],
            ['done', '已完成'], ['rejected', '已拒绝']];
        var tabHtml = tabs.map(function (t) {
            return '<button type="button" class="tab-btn' + (status === t[0] ? ' active' : '') +
                '" data-status="' + t[0] + '">' + t[1] + '</button>';
        }).join('');

        var listHtml = dataTable([
            { title: '售后单号', nowrap: true, render: function (a) {
                return '<a href="#/aftersales/' + a.id + '">' + esc(a.no) + '</a>';
            } },
            { title: '类型', nowrap: true, render: function (a) {
                return esc(aftersaleTypeLabel(a.type, a.type_other));
            } },
            { title: '订单', nowrap: true, render: function (a) {
                return a.order_id
                    ? '<a href="#/orders/' + a.order_id + '">' + esc(a.order_no || ('#' + a.order_id)) + '</a>'
                    : esc(a.order_no || '—');
            } },
            { title: '客户', render: function (a) { return esc(a.customer_name || '—'); } },
            { title: '问题', render: function (a) {
                return esc(String(a.description || '').slice(0, 22));
            } },
            { title: '状态', nowrap: true, render: function (a) {
                return aftersaleStatusBadge(a.status, a.status_label);
            } },
            { title: '创建时间', nowrap: true, render: function (a) {
                return fmtDateTime(a.created_at).slice(0, 10);
            } },
            { title: '操作', nowrap: true, render: function (a) {
                /* 售后只给「跟进」；已结束（完成/拒绝）置灰 —— 看详情请点单号 */
                var finished = (a.status === 'done' || a.status === 'rejected');
                return opButtons([{
                    op: 'follow', arg: a.id, label: '跟进',
                    disabled: finished,
                    tip: a.status === 'done' ? '已完成，不能再跟进（点单号看详情）' : '已拒绝，不能再跟进（点单号看详情）'
                }]);
            } }
        ], items, status ? '这个状态下没有售后单' : '还没有售后单：到「已完成」订单里点「添加售后」');

        root.innerHTML =
            '<div class="card">' +
            '<div class="card-head"><h2>售后 <span class="badge muted">' + ((res && res.total) || items.length) + '</span></h2>' +
            '<span class="small muted">售后单从「订单 → 已完成 → 添加售后」生成</span></div>' +
            '<div class="tabs" id="asTabs">' + tabHtml + '</div>' +
            '</div>' +
            '<div class="card">' + listHtml + '<div id="asPager">' + pagerHtml(res) + '</div></div>';

        $('#asTabs', root).addEventListener('click', function (ev) {
            var btn = ev.target.closest('.tab-btn');
            if (!btn) { return; }
            var next = btn.getAttribute('data-status') || '';
            navigate('#/aftersales' + (next ? '?status=' + encodeURIComponent(next) : ''));
        });

        $('#asPager', root).onclick = function (ev) {
            var btn = ev.target.closest('button[data-page]');
            if (!btn || btn.disabled) { return; }
            var q = [];
            if (status) { q.push('status=' + encodeURIComponent(status)); }
            if (orderId) { q.push('order_id=' + encodeURIComponent(orderId)); }
            q.push('page=' + (Number(btn.getAttribute('data-page')) || 1));
            navigate('#/aftersales?' + q.join('&'));
        };

        bindOps(root, { follow: function (id) { navigate('#/aftersales/' + id); } });
    });
}

function aftersaleStatusBadge(status, label) {
    var cls = status === 'done' ? 'ok' : (status === 'rejected' ? 'danger' : 'warn');
    return '<span class="badge ' + cls + '">' +
        esc(label || AFTERSALE_STATUS_LABEL[status] || status) + '</span>';
}

/* ---------------- 售后详情 ---------------- */
function viewAftersaleDetail(root, rawId) {
    var id = Number(rawId);
    if (!id || isNaN(id)) {
        root.innerHTML = '<div class="card">售后单 id 不合法，<a href="#/aftersales">回售后列表</a></div>';
        return Promise.resolve();
    }

    return Promise.all([
        api('/aftersales/' + id),
        api('/follow-ups?object_type=aftersale&object_id=' + id).catch(function () { return []; })
    ]).then(function (all) {
        var a = all[0];
        var followUps = all[1] || [];

        if (!a) {
            root.innerHTML = '<div class="card">售后单不存在，<a href="#/aftersales">回售后列表</a></div>';
            return;
        }

        var finished = (a.status === 'done' || a.status === 'rejected');
        var recordsHtml = followUps.length
            ? followUps.map(function (fu) {
                return followupItemHtml(fu, { withDelete: false, showCustomer: false });
            }).join('')
            : '<p class="empty">还没有跟进记录</p>';

        var actionsHtml;
        if (a.status === 'pending') {
            actionsHtml = '<span class="small muted">待处理：在下面写一条跟进，售后单会自动进入「处理中」</span>';
        } else if (a.status === 'processing') {
            actionsHtml = '<button type="button" class="btn btn-sm btn-primary" id="asFinish">标记完成</button>' +
                '<span class="small muted">处理完点这里收口，收口后不能再加跟进</span>';
        } else if (a.status === 'done') {
            actionsHtml = '<span class="small muted">已完成，不能再添加跟进记录</span>';
        } else {
            actionsHtml = '<span class="small muted">已拒绝，不能再添加跟进记录</span>';
        }

        var followForm = finished ? '' :
            '<form id="asFollowForm" class="card" autocomplete="off" style="margin-top:10px">' +
            '<div class="field"><label>跟进内容 *（≤2000 字）</label>' +
            '<textarea name="content" maxlength="2000" required ' +
            'placeholder="和客户沟通了什么？处理到哪一步了？"></textarea></div>' +
            '<div class="row-2">' +
            '<div class="field"><label>跟进方式</label>' +
            '<select name="method">' + dictOptions('follow_method', 'wechat') + '</select></div>' +
            '<div class="field"><label>下次跟进日期</label>' +
            '<input type="date" name="next_date"></div>' +
            '</div>' +
            '<div class="field"><label>照片 / 附件（可选，最多 ' + MAX_PHOTOS + ' 个）</label>' +
            '<input type="file" name="files" multiple></div>' +
            '<div class="form-actions"><button type="submit" class="btn btn-primary">保存跟进</button></div>' +
            '</form>';

        root.innerHTML =
            '<div class="card">' +
            '<div class="card-head"><h2><a href="#/aftersales">‹ 售后</a> / ' + esc(a.no) + '</h2>' +
            aftersaleStatusBadge(a.status, a.status_label) + '</div>' +
            infoGrid([
                ['关联订单', a.order_id
                    ? '<a href="#/orders/' + a.order_id + '">' + esc(a.order_no || ('订单 #' + a.order_id)) + ' ›</a>'
                    : '—', true],
                ['客户', a.customer_id
                    ? '<a href="#/customers/' + a.customer_id + '">' + esc(a.customer_name || ('客户 #' + a.customer_id)) + '</a>'
                    : esc(a.customer_name || '—'), true],
                ['类型', aftersaleTypeLabel(a.type, a.type_other)],
                ['状态', aftersaleStatusBadge(a.status, a.status_label), true],
                ['创建时间', fmtDateTime(a.created_at)],
                ['完成时间', a.closed_at ? fmtDateTime(a.closed_at) : '—'],
                ['问题描述', a.description],
                ['处理结果', a.result || (a.reject_reason ? '拒绝原因：' + a.reject_reason : '')]
            ]) +
            '<div class="form-actions" style="justify-content:flex-start;flex-wrap:wrap;margin-top:10px">' +
            actionsHtml + '</div>' +
            '</div>' +
            '<div class="card">' +
            '<div class="card-head"><h2>跟进履历（' + followUps.length + '）</h2></div>' +
            recordsHtml +
            followForm +
            '</div>';

        var finishBtn = $('#asFinish', root);
        if (finishBtn) {
            finishBtn.addEventListener('click', function () { openAftersaleFinish(a); });
        }

        var form = $('#asFollowForm', root);
        if (form) {
            form.addEventListener('submit', function (ev) {
                ev.preventDefault();
                var btn = form.querySelector('button[type="submit"]');
                var content = String(form.querySelector('[name="content"]').value || '').trim();
                if (!content) { toast('跟进内容不能为空', true); return; }
                var fd = new FormData();
                fd.append('object_type', 'aftersale');
                fd.append('object_id', String(a.id));
                fd.append('content', content);
                fd.append('method', form.querySelector('[name="method"]').value || 'wechat');
                var nextDate = form.querySelector('[name="next_date"]').value;
                if (nextDate) { fd.append('next_date', nextDate); }
                var files = form.querySelector('[name="files"]').files;
                for (var i = 0; i < files.length && i < MAX_PHOTOS; i++) { fd.append('files', files[i]); }
                btn.disabled = true;
                api('/follow-ups', { method: 'POST', body: fd }).then(function () {
                    toast('已记录跟进');
                    return render();
                }).catch(function (err) {
                    toast(err.message, true);
                    btn.disabled = false;
                });
            });
        }
    });
}

/* ---------------- 标记完成（后端要求必填「处理结果」） ---------------- */
function openAftersaleFinish(a) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content">' +
        '<div class="modal-header"><h3>标记完成 · ' + esc(a.no) + '</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<form id="asFinishForm" autocomplete="off">' +
        '<div class="field"><label>处理结果 *</label>' +
        '<textarea name="result" maxlength="1000" rows="3" required ' +
        'placeholder="换了什么件、怎么处理的、客户是否满意"></textarea></div>' +
        '<p class="small muted">完成后售后单不可再添加跟进记录。</p>' +
        '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">确认完成</button>' +
        '</div>' +
        '</form>' +
        '</div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);

    var form = modal.querySelector('form');
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var result = String(form.querySelector('[name="result"]').value || '').trim();
        if (!result) { toast('处理结果必填', true); return; }
        btn.disabled = true;
        api('/aftersales/' + a.id + '/finish', { method: 'POST', body: { result: result } }).then(function () {
            toast('售后单已完成');
            close();
            return render();
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}
