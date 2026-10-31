/* 商机页面（2026-10-31 对齐 demo 定稿）
 *
 * 定稿口径（与 static/demo/views/deals.js 一致，差别只在数据源换成真实 API）：
 *   · 列表用表格；列：客户 / 产品 / 型号 / 手动电动 / 尺寸 / 金额 / 阶段 / 更新时间 / 操作(跟进)
 *   · 商机只能由线索或客户「转商机」产生 —— 页面上不再有「新增商机」表单卡片
 *   · 详情页 = 顶部信息卡 + 跟进履历（含系统自动履历）+ 操作（编辑 / 生成订单 / 判流失）
 *   · 产品类型、型号、阶段、流失原因全部取数据字典（dictOptions / dictLabel），不许硬编码
 */

/* 阶段徽标：成交绿、流失红、其余黄 */
function dealStageBadge(stage, label) {
    var cls = stage === 'won' ? 'ok' : (stage === 'lost' ? 'danger' : 'warn');
    return '<span class="badge ' + cls + '">' + esc(label || STAGE_LABEL[stage] || stage || '—') + '</span>';
}

/* 手动/电动徽标（后端下发 drive_type_label；数据字典里没有这张表） */
function driveBadge(deal) {
    if (!deal.drive_type) { return '<span class="muted small">—</span>'; }
    var label = deal.drive_type_label || (deal.drive_type === 'electric' ? '电动' : '手动');
    return '<span class="badge ' + (deal.drive_type === 'electric' ? 'ok' : 'muted') + '">' + esc(label) + '</span>';
}

function dealProductText(deal) {
    var parts = [deal.product_type, deal.model, deal.spec].filter(Boolean);
    return parts.length ? parts.join(' / ') : '未填产品';
}

/* ---------------- 商机列表（表格） ---------------- */
function viewDeals(root, route) {
    var stage = (route && route.query.get('stage')) || '';
    var path = '/deals' + (stage ? '?stage=' + encodeURIComponent(stage) : '');

    return Promise.all([api(path), ensureCustomerIndex()]).then(function (all) {
        var deals = (all[0] || []).slice().sort(function (a, b) {
            var ak = a.updated_at || a.created_at || '';
            var bk = b.updated_at || b.created_at || '';
            return ak < bk ? 1 : (ak > bk ? -1 : 0);
        });
        var index = all[1] || {};

        var tabs = [['', '全部']].concat(STAGES);
        var tabHtml = tabs.map(function (t) {
            return '<button type="button" class="tab-btn' + (stage === t[0] ? ' active' : '') +
                '" data-stage="' + t[0] + '">' + esc(t[1]) + '</button>';
        }).join('');

        var rowsHtml = deals.length ? deals.map(function (d) {
            var customerName = index[d.customer_id] || ('客户 #' + d.customer_id);
            return '<tr>' +
                '<td><a href="#/deals/' + d.id + '">' + esc(customerName) + '</a></td>' +
                '<td>' + esc(d.product_type || '—') + '</td>' +
                '<td>' + esc(d.model || '—') + '</td>' +
                '<td>' + driveBadge(d) + '</td>' +
                '<td>' + esc(d.spec || '—') + '</td>' +
                '<td style="text-align:right;white-space:nowrap">' + money(d.amount) + '</td>' +
                '<td>' + dealStageBadge(d.stage, d.stage_label) + '</td>' +
                '<td style="white-space:nowrap">' + fmtDateTime(d.updated_at || d.created_at).slice(0, 10) + '</td>' +
                '<td style="white-space:nowrap"><a class="btn btn-sm" href="#/deals/' + d.id + '">跟进</a></td>' +
                '</tr>';
        }).join('') : '<tr><td colspan="9" class="empty">还没有商机：请到线索或客户里点「转商机」</td></tr>';

        root.innerHTML =
            '<div class="card">' +
            '<div class="card-head"><h2>商机 <span class="badge muted">' + deals.length + '</span></h2>' +
            '<span class="small muted">由线索 / 客户转来，不在此新建</span></div>' +
            '<div class="tabs" id="dealTabs">' + tabHtml + '</div>' +
            '</div>' +
            '<div class="card"><div class="table-wrap"><table><thead><tr>' +
            '<th>客户</th><th>产品</th><th>型号</th><th>手动/电动</th><th>尺寸</th>' +
            '<th style="text-align:right">金额</th><th>阶段</th><th>更新时间</th><th>操作</th>' +
            '</tr></thead><tbody>' + rowsHtml + '</tbody></table></div></div>';

        $('#dealTabs', root).addEventListener('click', function (ev) {
            var btn = ev.target.closest('.tab-btn');
            if (!btn) { return; }
            var next = btn.getAttribute('data-stage') || '';
            navigate('#/deals' + (next ? '?stage=' + encodeURIComponent(next) : ''));
        });
    });
}

/* ---------------- 商机详情 = 跟进页 ---------------- */
function viewDealDetail(root, rawId) {
    var id = Number(rawId);
    if (!id || isNaN(id)) {
        root.innerHTML = '<div class="card">商机 id 不合法，<a href="#/deals">回商机列表</a></div>';
        return Promise.resolve();
    }

    return Promise.all([
        api('/deals/' + id),
        ensureCustomerIndex(),
        api('/follow-ups?object_type=deal&object_id=' + id + '&include_system=true')
            .catch(function () { return []; })
    ]).then(function (all) {
        var d = all[0];
        var index = all[1] || {};
        var records = all[2] || [];

        if (!d) {
            root.innerHTML = '<div class="card">商机不存在，<a href="#/deals">回商机列表</a></div>';
            return;
        }

        var customerName = index[d.customer_id] || ('客户 #' + d.customer_id);
        var recordsHtml = records.length
            ? records.map(function (it) {
                return followupItemHtml(it, { withDelete: false, showCustomer: false });
            }).join('')
            : '<p class="empty">还没有跟进记录，点右上「记跟进」写一条</p>';

        var orderLink = d.order_id
            ? '<a class="badge ok" href="#/orders/' + d.order_id + '">已生成订单 ›</a>' : '';
        var actionHtml;
        if (d.order_id) {
            actionHtml = '<button type="button" class="btn btn-sm" disabled title="已生成订单，商机不可修改">编辑商机</button>' +
                '<a class="btn btn-sm" href="#/orders/' + d.order_id + '">查看订单</a>' +
                '<span class="small muted">已生成订单，商机锁定</span>';
        } else if (d.stage === 'lost') {
            actionHtml = '<button type="button" class="btn btn-sm" disabled title="已判流失，不可修改">编辑商机</button>' +
                '<span class="small muted">已判流失' +
                (d.lost_reason_label ? '（' + esc(d.lost_reason_label) + '）' : '') + '</span>';
        } else {
            actionHtml = '<button type="button" class="btn btn-sm" id="dealEdit">编辑商机</button>' +
                (d.stage === 'won'
                    ? '<button type="button" class="btn btn-sm btn-primary" id="dealToOrder">生成订单</button>'
                    : '<button type="button" class="btn btn-sm" disabled title="先把阶段推进到「成交」">生成订单</button>') +
                '<button type="button" class="btn btn-sm" id="dealLose">判流失</button>' +
                '<span class="small muted">' +
                (d.stage === 'won' ? '已成交，可以生成订单' : '阶段推进到「成交」后才能生成订单') + '</span>';
        }

        root.innerHTML =
            '<div class="card">' +
            '<div class="card-head">' +
            '<h2><a href="#/deals">‹ 商机</a> ' + esc(customerName) + ' · ' + esc(dealProductText(d)) + '</h2>' +
            '<div>' + dealStageBadge(d.stage, d.stage_label) + ' ' + orderLink +
            ' <a class="btn btn-sm" href="#/followups?object=deal&id=' + d.id + '">+ 记跟进</a></div>' +
            '</div>' +
            '<div class="item-sub" style="line-height:1.9">' +
            '客户：<a href="#/customers/' + d.customer_id + '">' + esc(customerName) + '</a><br>' +
            '产品类型：' + esc(d.product_type || '—') + '　型号：' + esc(d.model || '—') + '<br>' +
            '手动/电动：' + driveBadge(d) + '　尺寸：' + esc(d.spec || '—') + '<br>' +
            '金额：' + money(d.amount) + '　定金：' + money(d.deposit) + '　尾款：' + money(d.balance) + '<br>' +
            '阶段：' + dealStageBadge(d.stage, d.stage_label) + '<br>' +
            (d.note ? '备注：' + esc(d.note) + '<br>' : '') +
            '<span class="muted small">创建 ' + fmtDateTime(d.created_at) +
            ' · 更新 ' + fmtDateTime(d.updated_at) +
            (d.closed_at ? ' · 成交 ' + fmtDateTime(d.closed_at) : '') + '</span>' +
            '</div>' +
            '<div class="form-actions" style="margin-top:10px">' + actionHtml + '</div>' +
            '</div>' +
            '<div class="card">' +
            '<div class="card-head"><h2>跟进履历（' + records.length + '）</h2>' +
            '<a class="btn btn-sm" href="#/followups?object=deal&id=' + d.id + '">+ 记一条</a></div>' +
            recordsHtml +
            '</div>';

        var editBtn = $('#dealEdit', root);
        if (editBtn) {
            editBtn.addEventListener('click', function () {
                openDealEdit(d, function () { return render(); });
            });
        }

        var orderBtn = $('#dealToOrder', root);
        if (orderBtn) {
            orderBtn.addEventListener('click', function () {
                openDealOrderModal(d, customerName);
            });
        }

        var loseBtn = $('#dealLose', root);
        if (loseBtn) {
            loseBtn.addEventListener('click', function () {
                openDealLose(d, function () { return render(); });
            });
        }
    });
}

/* ---------------- 编辑商机（弹层；产品类型/型号/阶段取字典） ---------------- */
function openDealEdit(deal, done) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content wide">' +
        '<div class="modal-header"><h3>编辑商机</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<form id="dealEditForm" autocomplete="off">' +
        '<div class="row-2">' +
        '<div class="field"><label>产品类型</label>' +
        '<select name="product_type">' + dictOptions('product_type', deal.product_type, '不指定') + '</select></div>' +
        '<div class="field"><label>型号</label>' + modelComboHtml(deal.model || '') + '</div>' +
        '</div>' +
        '<div class="row-2">' +
        '<div class="field"><label>手动 / 电动</label>' +
        '<select name="drive_type">' +
        '<option value=""' + (deal.drive_type ? '' : ' selected') + '>不指定</option>' +
        '<option value="manual"' + (deal.drive_type === 'manual' ? ' selected' : '') + '>手动</option>' +
        '<option value="electric"' + (deal.drive_type === 'electric' ? ' selected' : '') + '>电动</option>' +
        '</select></div>' +
        '<div class="field"><label>尺寸 / 洞口</label>' +
        '<input name="spec" maxlength="200" placeholder="如 1200×2400" value="' + esc(deal.spec || '') + '"></div>' +
        '</div>' +
        '<div class="row-3">' +
        '<div class="field"><label>报价金额 *</label>' +
        '<input name="amount" type="number" min="0" step="0.01" inputmode="decimal" required value="' + (deal.amount || 0) + '"></div>' +
        '<div class="field"><label>定金</label>' +
        '<input name="deposit" type="number" min="0" step="0.01" inputmode="decimal" value="' + (deal.deposit || 0) + '"></div>' +
        '<div class="field"><label>尾款</label>' +
        '<input name="balance" type="number" min="0" step="0.01" inputmode="decimal" value="' + (deal.balance || 0) + '"></div>' +
        '</div>' +
        '<div class="field"><label>阶段</label>' +
        '<select name="stage">' + stageOptions(deal.stage) + '</select></div>' +
        '<div class="field"><label>备注</label>' +
        '<textarea name="note" maxlength="500">' + esc(deal.note || '') + '</textarea></div>' +
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

    var form = modal.querySelector('form');

    /* 型号可搜索；只带产品类型 / 手动电动，尺寸保留手填 */
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
        if (amount === null || amount < 0) { toast('报价金额必填且 ≥0', true); return; }

        function val(name) {
            var el = form.querySelector('[name="' + name + '"]');
            return el ? String(el.value || '').trim() : '';
        }
        var payload = {
            product_type: val('product_type') || null,
            model: val('model') || null,
            drive_type: val('drive_type') || null,
            spec: val('spec') || null,
            amount: amount,
            deposit: numOrNull(form.querySelector('[name="deposit"]').value) || 0,
            balance: numOrNull(form.querySelector('[name="balance"]').value) || 0,
            stage: val('stage'),
            note: val('note') || null
        };
        btn.disabled = true;
        api('/deals/' + deal.id, { method: 'PUT', body: payload }).then(function () {
            toast('商机已保存');
            close();
            if (done) { done(); }
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}

/* ---------------- 判流失（原因取字典 lost_reason） ---------------- */
function openDealLose(deal, done) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content">' +
        '<div class="modal-header"><h3>判流失</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<form id="dealLoseForm" autocomplete="off">' +
        '<div class="field"><label>流失原因 *</label>' +
        '<select name="lost_reason" required>' + dictOptions('lost_reason', '', '请选择') + '</select></div>' +
        '<div class="field"><label>补充说明（选「其他」时填）</label>' +
        '<input name="lost_reason_other" maxlength="200"></div>' +
        '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">确认流失</button>' +
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
        var reason = String(form.querySelector('[name="lost_reason"]').value || '');
        if (!reason) { toast('请选择流失原因', true); return; }
        var payload = { lost_reason: reason };
        var other = String(form.querySelector('[name="lost_reason_other"]').value || '').trim();
        if (reason === 'other' && other) { payload.lost_reason_other = other; }
        btn.disabled = true;
        api('/deals/' + deal.id + '/lose', { method: 'POST', body: payload }).then(function () {
            toast('商机已判流失');
            close();
            if (done) { done(); }
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}

/* ---------------- 转商机独立页面（#/deals/new?lead=ID | ?customer=ID） ----------------
 * 与 demo 定稿一致：商机不从商机页新建，而是从线索或客户点「转商机」进这一页。
 * 线索来源走 POST /leads/{id}/convert（一次搞定「线索转客户 + 建商机」）；
 * 客户来源走 POST /deals。
 */
function viewDealNew(root, route) {
    var leadId = Number((route && route.query.get('lead')) || 0);
    var custId = Number((route && route.query.get('customer')) || 0);

    if (!leadId && !custId) {
        root.innerHTML = '<div class="card">缺少来源：请从「线索」或「客户」里点「转商机」，' +
            '<a href="#/leads">回线索池</a> · <a href="#/customers">回客户档案</a></div>';
        return Promise.resolve();
    }

    var load = leadId ? api('/leads/' + leadId) : api('/customers/' + custId);
    return load.then(function (src) {
        var fromName = leadId
            ? ((src.name || src.company_name || '线索 #' + leadId) + '（线索）')
            : ((src.name || '客户 #' + custId) + '（客户）');
        var backHash = leadId ? '#/leads' : '#/customers';
        var backLabel = leadId ? '线索池' : '客户档案';

        root.innerHTML =
            '<div class="card">' +
            '<div class="card-head"><h2><a href="' + backHash + '">‹ ' + backLabel + '</a> / 转商机</h2>' +
            '<span class="badge muted">来源：' + esc(fromName) + '</span></div>' +
            '<form id="dealNewForm" autocomplete="off">' +
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
            '<input name="spec" maxlength="32" required placeholder="1200×2400"></div>' +
            '</div>' +
            '<div class="row-2">' +
            '<div class="field"><label>金额（报价）*</label>' +
            '<input name="amount" type="number" min="0" step="0.01" inputmode="decimal" required placeholder="12000"></div>' +
            '<div class="field"><label>阶段</label>' +
            '<input value="报价" disabled title="新建商机固定为报价"></div>' +
            '</div>' +
            '<div class="field"><label>备注</label>' +
            '<textarea name="note" maxlength="300" placeholder="客户需求、现场情况、特殊要求…"></textarea></div>' +
            '<p class="small muted">新建商机固定从「报价」开始；定金 / 尾款在生成订单时才填。' +
            (leadId ? '线索转化会同时新建客户档案。' : '') + '</p>' +
            '<div class="form-actions">' +
            '<button type="button" class="btn" id="dealNewCancel">取消</button>' +
            '<button type="submit" class="btn btn-primary">创建商机</button>' +
            '</div>' +
            '</form>' +
            '</div>';

        var form = $('#dealNewForm', root);

        /* 型号可搜索；只带产品类型 / 手动电动，尺寸手填 */
        bindModelCombo(form.querySelector('[data-model-combo]'), dictItems('product_model'), function (hit) {
            if (hit && hit.meta) {
                if (hit.meta.drive) { form.querySelector('[name="drive_type"]').value = hit.meta.drive; }
                if (hit.meta.product) { form.querySelector('[name="product_type"]').value = hit.meta.product; }
            }
        });

        $('#dealNewCancel', root).addEventListener('click', function () { navigate(backHash); });

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var btn = form.querySelector('button[type="submit"]');
            var amount = numOrNull(form.querySelector('[name="amount"]').value);
            var model = String(form.querySelector('[name="model"]').value || '');
            var spec = String(form.querySelector('[name="spec"]').value || '').trim();
            if (!model) { toast('请选择产品型号', true); return; }
            if (!spec) { toast('尺寸必填', true); return; }
            if (amount === null || !(amount > 0)) { toast('金额必须大于 0', true); return; }

            function val(name) {
                var el = form.querySelector('[name="' + name + '"]');
                return el ? String(el.value || '').trim() : '';
            }
            var deal = {
                title: [val('product_type'), model].filter(Boolean).join(' ').slice(0, 100) || null,
                product_type: val('product_type') || null,
                model: model,
                spec: spec,
                amount: amount,
                drive_type: val('drive_type') || null,
                note: val('note') || null
            };

            btn.disabled = true;
            var req = leadId
                ? api('/leads/' + leadId + '/convert', { method: 'POST', body: { mode: 'new', deal: deal } })
                : api('/deals', {
                    method: 'POST',
                    body: {
                        customer_id: custId,
                        product_type: deal.product_type,
                        model: deal.model,
                        spec: deal.spec,
                        amount: deal.amount,
                        drive_type: deal.drive_type,
                        stage: 'quote',
                        note: deal.note
                    }
                });
            req.then(function (res) {
                var created = leadId ? (res && res.deal) : res;
                toast('商机已创建');
                invalidateCustomerIndex();
                if (created && created.id) {
                    navigate('#/deals/' + created.id);
                } else {
                    navigate('#/deals');
                }
            }).catch(function (err) {
                toast(err.message, true);
                btn.disabled = false;
            });
        });
    }).catch(function (err) {
        root.innerHTML = '<div class="card"><p class="err">加载来源失败：' + esc(err.message) + '</p></div>';
    });
}

/* ---------------- 生成订单（成交 → 建订单；收款就是押金 + 尾款两笔） ----------------
 * 定稿口径：押金由业务填，**尾款 = 订单金额 - 押金**（前端只展示，服务端强制再算一遍）；
 *          自提不需要收货信息，包邮/代办必须选物流公司 + 填全收货人。
 * 走 POST /deals/{id}/orders（正路），不再用 /win（那是押金=全额的兼容端点）。
 */
function openDealOrderModal(deal, customerName) {
    var amount0 = Number(deal.amount) || 0;

    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content wide">' +
        '<div class="modal-header"><h3>生成订单</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body">' +
        '<form id="dealOrderForm" autocomplete="off">' +
        '<p class="small muted" style="margin-top:0">' +
        esc(customerName) + ' · ' + esc(dealProductText(deal)) + '　成交后商机会锁定。</p>' +
        '<div class="row-3">' +
        '<div class="field"><label>订单金额 *</label>' +
        '<input name="amount" type="number" min="0" step="0.01" inputmode="decimal" required value="' + amount0 + '"></div>' +
        '<div class="field"><label>押金（第一笔）*</label>' +
        '<input name="deposit" type="number" min="0" step="0.01" inputmode="decimal" required ' +
        'placeholder="按合同填押金"></div>' +
        '<div class="field"><label>尾款（自动算）</label>' +
        '<input name="balance" value="" disabled></div>' +
        '</div>' +
        '<div class="row-2">' +
        '<div class="field"><label>物流方式</label>' +
        '<select name="logistics_mode">' +
        '<option value="self">自提（不填收货信息）</option>' +
        '<option value="free">包邮</option>' +
        '<option value="agent">代办</option>' +
        '</select></div>' +
        '<div class="field" data-ship hidden><label>物流公司 *</label>' +
        '<select name="carrier_id"><option value="">请选择</option></select></div>' +
        '</div>' +
        '<div class="field" data-ship hidden><label>物流费用</label>' +
        '<input name="logistics_fee" type="number" min="0" step="0.01" inputmode="decimal" value="0"></div>' +
        '<div class="row-3" data-ship hidden>' +
        '<div class="field"><label>收货人 *</label><input name="receiver_name" maxlength="32"></div>' +
        '<div class="field"><label>收货电话 *</label><input name="receiver_phone" maxlength="32" inputmode="tel"></div>' +
        '<div class="field"><label>收货地址 *</label><input name="receiver_address" maxlength="200"></div>' +
        '</div>' +
        '<p class="small muted">收款只走两笔：先「收押金」，生产阶段再「收尾款」。押金 + 尾款 = 订单金额。</p>' +
        '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">生成订单</button>' +
        '</div>' +
        '</form>' +
        '</div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);

    var form = modal.querySelector('form');
    var amountEl = form.querySelector('[name="amount"]');
    var depositEl = form.querySelector('[name="deposit"]');
    var balanceEl = form.querySelector('[name="balance"]');
    var modeEl = form.querySelector('[name="logistics_mode"]');
    var carrierEl = form.querySelector('[name="carrier_id"]');
    var shipFields = $$('[data-ship]', modal);

    function refreshBalance() {
        var a = Number(amountEl.value) || 0;
        var dep = Number(depositEl.value) || 0;
        balanceEl.value = (Math.round((a - dep) * 100) / 100).toFixed(2);
    }
    amountEl.addEventListener('input', refreshBalance);
    depositEl.addEventListener('input', refreshBalance);
    refreshBalance();

    function refreshShip() {
        var need = modeEl.value !== 'self';
        shipFields.forEach(function (el) { el.hidden = !need; });
    }
    modeEl.addEventListener('change', refreshShip);
    refreshShip();

    /* 物流公司：只列启用的 */
    api('/carriers').then(function (list) {
        var active = (list || []).filter(function (c) { return c.is_active; });
        carrierEl.innerHTML = '<option value="">请选择</option>' + active.map(function (c) {
            return '<option value="' + c.id + '">' + esc(c.name) + '</option>';
        }).join('');
    }).catch(function () { /* 拉不到就留空，用户可先自提 */ });

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var amount = numOrNull(amountEl.value);
        var deposit = numOrNull(depositEl.value);
        var mode = modeEl.value;
        if (amount === null || !(amount > 0)) { toast('订单金额必须大于 0', true); return; }
        if (deposit === null || deposit < 0 || deposit > amount) {
            toast('押金必须在 0 到订单金额之间', true);
            return;
        }
        var payload = {
            amount: amount,
            deposit: deposit,
            logistics_mode: mode,
            logistics_fee: numOrNull(form.querySelector('[name="logistics_fee"]').value) || 0
        };
        if (mode !== 'self') {
            if (!carrierEl.value) { toast('包邮 / 代办要选物流公司', true); return; }
            payload.carrier_id = Number(carrierEl.value);
            var rn = String(form.querySelector('[name="receiver_name"]').value || '').trim();
            var rp = String(form.querySelector('[name="receiver_phone"]').value || '').trim();
            var ra = String(form.querySelector('[name="receiver_address"]').value || '').trim();
            if (!rn || !rp || !ra) { toast('请填全收货人 / 电话 / 地址', true); return; }
            payload.receiver_name = rn;
            payload.receiver_phone = rp;
            payload.receiver_address = ra;
        }
        btn.disabled = true;
        api('/deals/' + deal.id + '/orders', { method: 'POST', body: payload }).then(function (res) {
            toast('订单已生成');
            close();
            invalidateCustomerIndex();
            navigate('#/orders/' + res.order.id);
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}
