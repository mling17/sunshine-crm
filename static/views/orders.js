/* 订单页面（2026-10-31 对齐 demo 定稿）
 *
 * 定稿口径：
 *   · 列表用表格 + 状态 Tab；订单由商机「生成订单」产生，页面不新建
 *   · 详情 = 信息卡（含关联商机，可点回）+ 状态进度条 + 收款 + 收货/配送 + 当前操作 + 售后单 + 状态历史
 *   · 状态推进统一走 POST /orders/{id}/transition；押金/尾款走 /pay-deposit /pay-balance（要传截图）
 */

var LOGISTICS_MODE_OPTIONS = [['free', '包邮'], ['agent', '代办'], ['self', '自提']];

/* 下一步动作：状态 → [目标状态, 按钮文案] */
var ORDER_NEXT_STEP = {
    pending_payment: ['deposit_paid', '收押金'],
    deposit_paid: ['producing', '开始生产'],
    producing: ['balance_paid', '收尾款'],
    balance_paid: ['ready_to_ship', '备货完成'],
    ready_to_ship: ['shipped', '发货'],
    shipped: ['completed', '确认收货']
};

function orderStatusBadge(status, label) {
    var cls = status === 'completed' ? 'ok' : (status === 'pending_payment' ? 'warn' : 'muted');
    return '<span class="badge ' + cls + '">' + esc(label || ORDER_STATUS_LABEL[status] || status) + '</span>';
}

/* ---------------- 订单列表 ---------------- */
function viewOrders(root, route) {
    var status = (route && route.query.get('status')) || '';
    var page = Number((route && route.query.get('page')) || 1);
    var customerId = (route && route.query.get('customer_id')) || '';

    var params = new URLSearchParams();
    params.set('page', String(page));
    params.set('size', String(PAGE_SIZE));
    if (status) { params.set('status', status); }
    if (customerId) { params.set('customer_id', customerId); }

    return Promise.all([api('/orders?' + params.toString()), ensureCustomerIndex()]).then(function (all) {
        var res = all[0];
        var index = all[1] || {};
        var orders = Array.isArray(res) ? res : ((res && res.items) || []);
        var total = Array.isArray(res) ? orders.length : ((res && res.total) || orders.length);

        var tabs = [['', '全部']].concat(ORDER_STATUS);
        var tabHtml = tabs.map(function (t) {
            return '<button type="button" class="tab-btn' + (status === t[0] ? ' active' : '') +
                '" data-status="' + t[0] + '">' + esc(t[1]) + '</button>';
        }).join('');

        var listHtml = dataTable([
            { title: '订单号', nowrap: true, render: function (o) {
                return '<a href="#/orders/' + o.id + '">' + esc(o.order_no) + '</a>';
            } },
            { title: '客户', render: function (o) {
                return esc(o.customer_name || index[o.customer_id] || ('客户 #' + o.customer_id));
            } },
            { title: '产品', nowrap: true, render: function (o) {
                return esc([o.product_name_snapshot, o.product_code_snapshot || o.model]
                    .filter(Boolean).join(' / ') || [o.product_type, o.model].filter(Boolean).join(' ') || '—');
            } },
            { title: '总额', align: 'right', nowrap: true, render: function (o) { return money(o.amount); } },
            { title: '已收', align: 'right', nowrap: true, render: function (o) {
                return money(o.paid_amount !== undefined && o.paid_amount !== null
                    ? o.paid_amount
                    : (Number(o.deposit_paid) || 0) + (Number(o.balance_paid) || 0));
            } },
            { title: '未收', align: 'right', nowrap: true, render: function (o) {
                var paid = o.paid_amount !== undefined && o.paid_amount !== null
                    ? Number(o.paid_amount) || 0
                    : (Number(o.deposit_paid) || 0) + (Number(o.balance_paid) || 0);
                return money(Math.max(0, Number(o.amount || 0) - paid));
            } },
            { title: '物流', nowrap: true, render: function (o) {
                var mode = o.logistics_mode_label || '';
                var fee = o.logistics_fee ? '<div class="small muted">运费 ' + money(o.logistics_fee) + '</div>' : '';
                return (mode ? esc(mode) : '<span class="muted small">—</span>') + fee;
            } },
            { title: '状态', nowrap: true, render: function (o) {
                return orderStatusBadge(o.status, o.status_label);
            } },
            { title: '创建时间', nowrap: true, render: function (o) {
                return fmtDateTime(o.created_at).slice(0, 10);
            } },
            { title: '操作', nowrap: true, render: function (o) {
                return opButtons([{ op: 'view', arg: o.id, label: '详情' }]);
            } }
        ], orders, status ? '这个状态下没有订单' : '还没有订单：商机里点「生成订单」才会产生');

        root.innerHTML =
            '<div class="card">' +
            '<div class="card-head"><h2>订单 <span class="badge muted">' + total + '</span></h2>' +
            '<span class="small muted">订单由商机「生成订单」产生</span></div>' +
            '<div class="tabs" id="orderTabs">' + tabHtml + '</div>' +
            '</div>' +
            '<div class="card">' + listHtml + '<div id="orderPager">' + pagerHtml(res) + '</div></div>';

        $('#orderTabs', root).addEventListener('click', function (ev) {
            var btn = ev.target.closest('.tab-btn');
            if (!btn) { return; }
            var next = btn.getAttribute('data-status') || '';
            navigate('#/orders' + (next ? '?status=' + encodeURIComponent(next) : ''));
        });

        $('#orderPager', root).onclick = function (ev) {
            var btn = ev.target.closest('button[data-page]');
            if (!btn || btn.disabled) { return; }
            navigate('#/orders?page=' + (Number(btn.getAttribute('data-page')) || 1) +
                (status ? '&status=' + encodeURIComponent(status) : ''));
        };

        bindOps(root, { view: function (id) { navigate('#/orders/' + id); } });
    });
}

/* ---------------- 订单详情 ---------------- */
function viewOrderDetail(root, rawId) {
    var id = Number(rawId);
    if (!id || isNaN(id)) {
        root.innerHTML = '<div class="card">订单 id 不合法，<a href="#/orders">回订单列表</a></div>';
        return Promise.resolve();
    }

    return Promise.all([
        api('/orders/' + id),
        api('/aftersales?order_id=' + id).catch(function () { return []; }),
        ensureCustomerIndex()
    ]).then(function (all) {
        var order = all[0];
        var afRes = all[1];
        var index = all[2] || {};
        var aftersales = Array.isArray(afRes) ? afRes : ((afRes && afRes.items) || []);

        if (!order) {
            root.innerHTML = '<div class="card">订单不存在，<a href="#/orders">回订单列表</a></div>';
            return;
        }

        var totalAmount = Number(order.amount) || 0;
        var paidTotal = (order.paid_amount !== undefined && order.paid_amount !== null)
            ? Number(order.paid_amount) || 0
            : (Number(order.deposit_paid) || 0) + (Number(order.balance_paid) || 0);
        var unpaid = Math.max(0, totalAmount - paidTotal);
        var customerName = order.customer_name || index[order.customer_id] ||
            ('客户 #' + order.customer_id);

        /* 进度条：走字典顺序（ORDER_STATUS 已由字典回填） */
        var stepIdx = ORDER_STATUS.map(function (p) { return p[0]; }).indexOf(order.status);
        var progressHtml = '<div class="progress-bar">' + ORDER_STATUS.map(function (p, i) {
            var cls = 'step' + (i === stepIdx ? ' active' : (i < stepIdx ? ' done' : ''));
            return '<div class="' + cls + '"><div class="step-label">' + esc(p[1]) + '</div></div>';
        }).join('') + '</div>';

        /* 关联商机（能点回去） */
        var dealHtml = order.deal_id
            ? '<a href="#/deals/' + order.deal_id + '">商机 #' + order.deal_id + ' ›</a>'
            : '—';

        var infoHtml = infoGrid([
            ['客户', '<a href="#/customers/' + order.customer_id + '">' + esc(customerName) + '</a>', true],
            ['关联商机', dealHtml, true],
            ['关联产品', order.product_id
                ? '<a href="#/products/' + order.product_id + '">' +
                  esc(order.product_name_snapshot || ('产品 #' + order.product_id)) + '</a>'
                : '未关联产品', true],
            ['产品 / 型号', [order.product_code_snapshot, order.product_type, order.model, order.spec]
                .filter(Boolean).join(' ')],
            ['产品配置', order.product_config_snapshot || '—'],
            ['物流方式', order.logistics_mode_label],
            ['承运公司', (order.carrier && (order.carrier.name || order.carrier.company)) || '不指定'],
            ['运单号', order.tracking_number || order.tracking_no || '待补'],
            ['创建时间', fmtDateTime(order.created_at)],
            ['完成时间', order.completed_at ? fmtDateTime(order.completed_at) : '—']
        ]);

        /* 售后单 */
        var aftersalesHtml = aftersales.length ? '<div class="card">' +
            '<div class="card-head"><h2>售后单（' + aftersales.length + '）</h2></div>' +
            aftersales.map(function (a) {
                return '<div class="item"><div class="item-main">' +
                    '<div class="item-title"><a href="#/aftersales/' + a.id + '">' + esc(a.no) + '</a>' +
                    '<span class="badge ' + (a.status === 'done' ? 'ok' : (a.status === 'rejected' ? 'danger' : 'warn')) + '">' +
                    esc(a.status_label || AFTERSALE_STATUS_LABEL[a.status] || a.status) + '</span></div>' +
                    '<div class="item-sub small muted">' +
                    esc(a.type_label || AFTERSALE_TYPE_LABEL[a.type] || a.type) +
                    ' · ' + fmtDateTime(a.created_at).slice(0, 10) +
                    ' · ' + esc(String(a.description || '').slice(0, 30)) + '</div>' +
                    '</div><div class="item-side muted">›</div></div>';
            }).join('') + '</div>'
            : '<div class="card"><div class="card-head"><h2>售后单</h2></div><p class="empty">暂无售后单</p></div>';

        /* 状态历史 */
        var logs = order.status_log || [];
        var historyHtml = logs.length ? '<div class="card">' +
            '<div class="card-head"><h2>状态历史</h2></div>' +
            logs.map(function (log) {
                var shots = (log.screenshots || []).map(function (s) {
                    var url = '/crm' + s.url;
                    return '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' +
                        '<img src="' + esc(url) + '" alt="截图" loading="lazy"></a>';
                }).join('');
                return '<div class="item"><div class="item-main">' +
                    '<div class="item-title">' + esc(log.to_status_label || log.to_status) + '</div>' +
                    '<div class="item-sub small">' + fmtDateTime(log.created_at) + '</div>' +
                    (log.note ? '<div class="item-sub">' + esc(log.note) + '</div>' : '') +
                    (shots ? '<div class="photos">' + shots + '</div>' : '') +
                    '</div></div>';
            }).join('') + '</div>' : '';

        /* 下一步操作 */
        var next = ORDER_NEXT_STEP[order.status];
        var actionBtns = '';
        if (next) {
            actionBtns += '<button type="button" class="btn btn-primary" id="btnNextAction">' + next[1] + '</button>';
        }
        if (order.status === 'completed') {
            actionBtns += '<button type="button" class="btn" id="btnAddAftersale">＋ 添加售后</button>';
        } else {
            actionBtns += '<button type="button" class="btn" disabled title="订单完成后才能申请售后">添加售后</button>';
        }
        /* 收款只有两笔：押金（待支付 → 已付押金）、尾款（生产中 → 已付尾款）。
           入口就一个 —— 上面「下一步」按钮在对应状态就是「收押金 / 收尾款」，不再重复放快捷按钮。 */

        root.innerHTML =
            '<div class="card">' +
            '<div class="card-head"><h2><a href="#/orders">‹ 订单</a> / ' + esc(order.order_no) + '</h2>' +
            orderStatusBadge(order.status, order.status_label) + '</div>' +
            infoHtml +
            progressHtml +
            '<div class="form-actions" style="justify-content:flex-start;flex-wrap:wrap">' + actionBtns + '</div>' +
            '</div>' +

            (function () {
                var depositDue = Number(order.deposit_amount || 0);
                var balanceDue = Number(order.balance_amount || 0);
                var depositPaid = Number(order.deposit_paid || 0);
                var balancePaid = Number(order.balance_paid || 0);
                function paidBadge(paid, due) {
                    if (!due) { return '<span class="badge muted">无需收</span>'; }
                    return paid >= due
                        ? '<span class="badge ok">已收</span>'
                        : '<span class="badge warn">待收</span>';
                }
                return '<div class="card">' +
                    '<div class="card-head"><h2>收款</h2>' +
                    '<span class="small muted">只收两笔：押金 + 尾款，合计 ' + money(totalAmount) + '</span></div>' +
                    '<div class="grid-kpi">' +
                    '<div class="kpi"><div class="label">押金应收</div><div class="value">' + money(depositDue) + '</div>' +
                    '<div class="sub">' + paidBadge(depositPaid, depositDue) + '</div></div>' +
                    '<div class="kpi"><div class="label">押金已收</div><div class="value">' + money(depositPaid) + '</div>' +
                    '<div class="sub">第一笔</div></div>' +
                    '<div class="kpi"><div class="label">尾款应收</div><div class="value">' + money(balanceDue) + '</div>' +
                    '<div class="sub">' + paidBadge(balancePaid, balanceDue) + '</div></div>' +
                    '<div class="kpi"><div class="label">尾款已收</div><div class="value">' + money(balancePaid) + '</div>' +
                    '<div class="sub">第二笔</div></div>' +
                    '</div>' +
                    '<p class="small muted" style="margin:10px 0 0">已收合计 <b>' + money(paidTotal) + '</b>' +
                    ' · 未收 ' + money(unpaid) + '</p>' +
                    '</div>';
            })() +

            '<div class="card">' +
            '<div class="card-head"><h2>收货 / 配送</h2></div>' +
            infoGrid([
                ['收件人', order.receiver_name],
                ['电话', order.receiver_phone],
                ['收货地址', order.receiver_address],
                ['物流方式', order.logistics_mode_label],
                ['物流费用', order.logistics_fee ? money(order.logistics_fee) : '0'],
                ['运单号', order.tracking_number || order.tracking_no]
            ]) +
            '</div>' +

            aftersalesHtml + historyHtml;

        var nextBtn = $('#btnNextAction', root);
        if (nextBtn) {
            nextBtn.addEventListener('click', function () {
                var target = next[0];
                if (target === 'deposit_paid') { showDepositPayment(order); return; }
                if (target === 'balance_paid') { showBalancePayment(order); return; }
                if (target === 'shipped') { showShipModal(order); return; }
                transitionOrder(order, target, {}, next[1]);
            });
        }

        var addAsBtn = $('#btnAddAftersale', root);
        if (addAsBtn) { addAsBtn.addEventListener('click', function () { openAftersaleModal(order); }); }
    });
}

/* ---------------- 添加售后（订单已完成才允许；售后单只能这么创建） ---------------- */
function openAftersaleModal(order) {
    var modal = createOrderModal('添加售后');
    modal.querySelector('.modal-body').innerHTML =
        '<form id="asNewForm" class="form-modal form-grid" autocomplete="off">' +
        '<p class="small muted">订单 ' + esc(order.order_no) + ' · 客户 ' +
        esc(order.customer_name || ('#' + order.customer_id)) + '</p>' +
        '<div class="field"><label>售后类型 *</label>' +
        '<select name="type" required>' + dictOptions('aftersale_type', '', '请选择') + '</select></div>' +
        '<div class="field"><label>问题描述 *</label>' +
        '<textarea name="description" maxlength="1000" rows="3" required ' +
        'placeholder="客户反馈的问题、现象、期望怎么处理"></textarea></div>' +
        '<div class="form-actions"><button type="submit" class="btn btn-primary">创建售后单</button></div>' +
        '</form>';

    var form = modal.querySelector('#asNewForm');
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var type = String(form.querySelector('[name="type"]').value || '');
        var desc = String(form.querySelector('[name="description"]').value || '').trim();
        if (!type) { toast('请选择售后类型', true); return; }
        if (!desc) { toast('请填写问题描述', true); return; }
        btn.disabled = true;
        api('/aftersales', {
            method: 'POST',
            body: { order_id: order.id, type: type, description: desc }
        }).then(function (res) {
            toast('售后单已创建');
            if (modal.parentNode) { document.body.removeChild(modal); }
            navigate('#/aftersales/' + (res && res.id ? res.id : ''));
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}

/* ---------------- 通用状态推进 ---------------- */
function transitionOrder(order, toStatus, extra, confirmText) {
    if (confirmText && !window.confirm('确定执行「' + confirmText + '」？订单号 ' + order.order_no)) { return; }
    var payload = Object.assign({ to_status: toStatus }, extra || {});
    api('/orders/' + order.id + '/transition', { method: 'POST', body: payload }).then(function () {
        toast('已' + (confirmText || '更新状态'));
        return render();
    }).catch(function (err) { toast(err.message, true); });
}

/* 发货：填物流方式 / 承运 / 运单号 */
function showShipModal(order) {
    var modal = createOrderModal('发货');
    modal.querySelector('.modal-body').innerHTML = '<form id="shipForm" class="form-modal form-grid">' +
        '<div class="row-2">' +
        '<div class="field"><label>物流方式</label>' +
        '<select name="logistics_mode">' +
        LOGISTICS_MODE_OPTIONS.map(function (p) {
            return '<option value="' + p[0] + '"' +
                (order.logistics_mode === p[0] ? ' selected' : '') + '>' + p[1] + '</option>';
        }).join('') + '</select></div>' +
        '<div class="field"><label>物流费用</label>' +
        '<input name="logistics_fee" type="number" min="0" step="0.01" value="' + (order.logistics_fee || 0) + '"></div>' +
        '</div>' +
        '<div class="row-2">' +
        '<div class="field"><label>承运公司 ID（可空）</label>' +
        '<input name="carrier_id" type="number" min="1" placeholder="物流公司 id"></div>' +
        '<div class="field"><label>运单号</label>' +
        '<input name="tracking_number" maxlength="64" value="' + esc(order.tracking_number || '') + '"></div>' +
        '</div>' +
        '<div class="field"><label>备注</label><textarea name="note" maxlength="500"></textarea></div>' +
        '<div class="form-actions"><button type="submit" class="btn btn-primary">确认发货</button></div>' +
        '</form>';

    var form = $('#shipForm', modal);
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var extra = {
            logistics_mode: form.querySelector('[name="logistics_mode"]').value,
            logistics_fee: numOrNull(form.querySelector('[name="logistics_fee"]').value) || 0,
            tracking_number: String(form.querySelector('[name="tracking_number"]').value || '').trim() || null,
            note: String(form.querySelector('[name="note"]').value || '').trim() || null
        };
        var carrierId = numOrNull(form.querySelector('[name="carrier_id"]').value);
        if (carrierId) { extra.carrier_id = carrierId; }
        document.body.removeChild(modal);
        transitionOrder(order, 'shipped', extra, '发货');
    });
    document.body.appendChild(modal);
}

/* ---------------- 押金 / 尾款（要传截图） ---------------- */
function showDepositPayment(order) {
    var modal = createOrderModal('支付押金');
    modal.querySelector('.modal-body').innerHTML = '<form id="depositForm" class="form-modal form-grid">' +
        '<div class="field"><label>押金金额 *</label>' +
        '<input type="number" id="depositAmount" name="amount" min="0" step="0.01" required ' +
        'placeholder="应收押金 ' + money(order.deposit_amount || order.amount) + '"></div>' +
        '<div class="field"><label>备注</label><textarea name="note"></textarea></div>' +
        '<div class="field"><label>支付截图（最多 3 张）</label>' +
        '<input type="file" name="screenshots" accept="image/*" multiple></div>' +
        '<div class="form-actions"><button type="submit" class="btn btn-primary">提交</button></div>' +
        '</form>';

    var form = $('#depositForm', modal);
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var amount = parseFloat(form.querySelector('[name="amount"]').value);
        if (isNaN(amount) || amount <= 0) { toast('请输入有效的押金金额', true); return; }
        if (amount > Number(order.amount)) { toast('押金金额不能超过总额', true); return; }
        var fd = new FormData();
        fd.append('amount', String(amount));
        var note = String(form.querySelector('[name="note"]').value || '').trim();
        if (note) { fd.append('note', note); }
        var files = form.querySelector('[name="screenshots"]').files;
        for (var i = 0; i < files.length && i < 3; i++) { fd.append('screenshots', files[i]); }
        api('/orders/' + order.id + '/pay-deposit', { method: 'POST', body: fd }).then(function () {
            toast('押金已记录');
            document.body.removeChild(modal);
            return render();
        }).catch(function (err) { toast(err.message, true); });
    });
    document.body.appendChild(modal);
}

function showBalancePayment(order) {
    var modal = createOrderModal('支付尾款');
    var remaining = Math.max(0, Number(order.balance_amount || 0) - (Number(order.balance_paid) || 0));
    modal.querySelector('.modal-body').innerHTML = '<form id="balanceForm" class="form-modal form-grid">' +
        '<div class="field"><label>尾款金额 *</label>' +
        '<input type="number" name="amount" min="0" step="0.01" required ' +
        'placeholder="应付尾款 ' + money(remaining) + '"></div>' +
        '<div class="field"><label>备注</label><textarea name="note"></textarea></div>' +
        '<div class="field"><label>支付截图（最多 3 张）</label>' +
        '<input type="file" name="screenshots" accept="image/*" multiple></div>' +
        '<div class="form-actions"><button type="submit" class="btn btn-primary">提交</button></div>' +
        '</form>';

    var form = $('#balanceForm', modal);
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var amount = parseFloat(form.querySelector('[name="amount"]').value);
        if (isNaN(amount) || amount <= 0) { toast('请输入有效的尾款金额', true); return; }
        if (amount > remaining) { toast('尾款金额不能超过剩余金额', true); return; }
        var fd = new FormData();
        fd.append('amount', String(amount));
        var note = String(form.querySelector('[name="note"]').value || '').trim();
        if (note) { fd.append('note', note); }
        var files = form.querySelector('[name="screenshots"]').files;
        for (var i = 0; i < files.length && i < 3; i++) { fd.append('screenshots', files[i]); }
        api('/orders/' + order.id + '/pay-balance', { method: 'POST', body: fd }).then(function () {
            toast('尾款已记录');
            document.body.removeChild(modal);
            return render();
        }).catch(function (err) { toast(err.message, true); });
    });
    document.body.appendChild(modal);
}

function createOrderModal(title) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = '<div class="modal-overlay"></div>' +
        '<div class="modal-content"><div class="modal-header"><h3>' + esc(title) + '</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body"></div></div>';
    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.addEventListener('click', function (ev) {
        if (ev.target === modal || (ev.target.classList && ev.target.classList.contains('modal-overlay'))) { close(); }
    });
    document.body.appendChild(modal);
    return modal;
}
