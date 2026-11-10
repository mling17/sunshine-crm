/* 订单页面（2026-10-31 对齐 demo 定稿）
 *
 * 定稿口径：
 *   · 列表用表格 + 状态 Tab；订单由商机「生成订单」产生，页面不新建
 *   · 详情 = 订单摘要 + 跟进履历 + 报价单 + 金额收款 + 物流 + 售后单 + 资料
 *   · 状态推进统一走 POST /orders/{id}/transition；定金/尾款走 /pay-deposit /pay-balance（要传截图）
 */

var LOGISTICS_MODE_OPTIONS = [['free', '包邮'], ['agent', '代办'], ['self', '自提']];

/* 下一步动作：状态 → [目标状态, 按钮文案] */
var ORDER_NEXT_STEP = {
    pending_confirmation: ['deposit_paid', '收定金'],
    pending_payment: ['deposit_paid', '收定金'],
    deposit_paid: ['producing', '开始生产'],
    producing: ['balance_paid', '收尾款'],
    balance_paid: ['ready_to_ship', '备货完成'],
    ready_to_ship: ['completed', '确认发货']
};

function canEditOrder(order) {
    return !!(order && order.id);
}

/* 物流公司 + 联络人联动；编辑订单、发货弹层共用。 */
function populateCarrierContactSelects(carrierEl, contactEl, carriers, selectedCarrierId, selectedContactId) {
    var selectedId = String(selectedCarrierId || '');
    var list = (carriers || []).filter(function (carrier) {
        return carrier.is_active || String(carrier.id) === selectedId;
    });
    carrierEl.innerHTML = '<option value="">请选择</option>' + list.map(function (carrier) {
        return '<option value="' + carrier.id + '">' + esc(carrier.name) +
            (carrier.is_active === false ? '（已停用）' : '') + '</option>';
    }).join('');
    carrierEl.value = selectedId;

    function refreshContacts(contactId) {
        var carrier = list.filter(function (item) {
            return String(item.id) === String(carrierEl.value || '');
        })[0];
        var contacts = (carrier && carrier.contacts) || [];
        contactEl.innerHTML = contacts.length
            ? '<option value="">请选择联络人</option>' + contacts.map(function (contact) {
                return '<option value="' + contact.id + '">' + esc(contact.name) +
                    (contact.phone ? ' · ' + esc(contact.phone) : '') + '</option>';
            }).join('')
            : '<option value="">' +
              esc(carrier ? '该物流公司尚未设置联络人' : '请先选择物流公司') +
              '</option>';
        contactEl.value = contactId ? String(contactId) : '';
        contactEl.disabled = !carrier || !contacts.length;
    }

    refreshContacts(selectedContactId);
    carrierEl.onchange = function () { refreshContacts(''); };
}

function orderStatusBadge(status, label) {
    var cls = status === 'completed' ? 'ok' :
        ((status === 'pending_confirmation' || status === 'pending_payment') ? 'warn' : 'muted');
    var text = status === 'pending_confirmation'
        ? '待支付'
        : (label || ORDER_STATUS_LABEL[status] || status);
    return '<span class="badge ' + cls + '">' + esc(text) + '</span>';
}

function orderVisibleStatuses() {
    return ORDER_STATUS.filter(function (item) {
        return item[0] !== 'pending_confirmation';
    });
}

function orderUiStatusCode(status) {
    return status === 'pending_confirmation' ? 'pending_payment' : status;
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

        var tabs = [['', '全部']].concat(orderVisibleStatuses());
        var tabHtml = tabs.map(function (t) {
            return '<button type="button" class="tab-btn' + (status === t[0] ? ' active' : '') +
                '" data-status="' + t[0] + '">' + esc(t[1]) + '</button>';
        }).join('');

        var listHtml = dataTable([
            { title: '订单名称', nowrap: true, render: function (o) {
                return '<a href="#/orders/' + o.id + '">' +
                    esc(o.order_name || o.order_no) + '</a>' +
                    '<div class="small muted">' + esc(o.order_no) + '</div>';
            } },
            { title: '客户', render: function (o) {
                return esc(o.customer_name || index[o.customer_id] || ('客户 #' + o.customer_id));
            } },
            { title: '产品', nowrap: true, render: function (o) {
                var text = [o.product_name_snapshot, o.product_code_snapshot || o.model]
                    .filter(Boolean).join(' / ') || [o.product_type, o.model].filter(Boolean).join(' ') || '—';
                return esc(text) + (Number(o.item_count || 0) > 1
                    ? '<div class="small muted">共 ' + Number(o.item_count) + ' 项产品</div>' : '');
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
function orderFileUrl(url) {
    if (!url) { return ''; }
    return String(url).charAt(0) === '/' && String(url).indexOf('/crm/') !== 0 ? '/crm' + url : url;
}

var ORDER_CHANGE_LABELS = {
    logistics_mode: '物流方式',
    carrier_id: '物流公司',
    carrier_contact_id: '物流联络人',
    carrier_contact_name: '物流联络人',
    carrier_contact_phone: '联络电话',
    logistics_fee: '物流费用',
    receiver_name: '收件人',
    receiver_phone: '收货电话',
    receiver_address: '收货地址',
    amount: '订单金额',
    balance_amount: '尾款应收',
    tracking_no: '运单号'
};

function orderTimelineContent(record) {
    if (record.type !== 'change' && record.type !== 'address') {
        return record.content;
    }
    var detail = record.detail || {};
    var lines = Object.keys(detail).map(function (key) {
        var change = detail[key] || {};
        if (!change || typeof change !== 'object') { return ''; }
        var label = change.label || ORDER_CHANGE_LABELS[key] || key;
        var before = change.from_label !== undefined ? change.from_label : change.from;
        var after = change.to_label !== undefined ? change.to_label : change.to;
        before = before === null || before === undefined || before === '' ? '未填写' : before;
        after = after === null || after === undefined || after === '' ? '未填写' : after;
        return label + '：' + before + ' → ' + after;
    }).filter(Boolean);
    return lines.length ? lines.join('；') : record.content;
}

function orderTimelineRecords(order) {
    return (order.timeline || []).map(function (record) {
        return Object.assign({}, record, {
            content: orderTimelineContent(record),
            files: (record.files || []).map(function (file) {
                return Object.assign({}, file, { url: orderFileUrl(file.url) });
            })
        });
    });
}

function orderDocumentFiles(order, timelineRecords) {
    var seen = {};
    var files = [];
    function add(file, at) {
        if (!file) { return; }
        var url = orderFileUrl(file.url);
        var key = url || file.name;
        if (!key || seen[key]) { return; }
        seen[key] = true;
        files.push({
            name: file.name || file.file_name || '附件',
            url: url,
            isImage: /\.(jpg|jpeg|png|gif|webp|bmp|heic)$/i.test(file.name || file.file_name || ''),
            at: at || file.created_at || order.created_at
        });
    }
    (timelineRecords || []).forEach(function (record) {
        (record.files || []).forEach(function (file) { add(file, record.at); });
    });
    (order.confirmation_files || []).forEach(function (file) {
        add(file, order.customer_confirmed_at);
    });
    (order.attachments || []).forEach(function (file) {
        add(file, file.created_at || order.updated_at);
    });
    return files;
}

function orderTagsHtml(deal, locked) {
    var tags = (deal && deal.tags) || [];
    if (!deal) {
        return '<span class="small muted">订单没有关联商机标签</span>';
    }
    return '<div class="order-tags" aria-label="订单标签">' + tags.map(function (tag) {
        return '<span class="order-tag' + (tag.source === 'auto' ? ' is-auto' : '') + '">' +
            esc(tag.name) +
            (tag.deletable && !locked
                ? '<button type="button" class="order-tag-remove" data-deal-tag-remove="' +
                  tag.id + '" title="删除标签" aria-label="删除标签 ' + esc(tag.name) + '">×</button>'
                : '') +
            '</span>';
    }).join('') +
        (!locked
            ? '<button type="button" class="order-tag-add" data-deal-tag-add="' + deal.id +
              '" title="添加标签" aria-label="添加标签">＋</button>'
            : '') +
        '</div>';
}

function orderFollowModal(order) {
    openFollowModal({
        title: '记一条订单跟进 · ' + order.order_no,
        placeholder: '这次和客户沟通了什么？生产、收款、发货或安装有什么新进展？',
        objectType: 'order',
        onSubmit: function (payload) {
            var fd = new FormData();
            fd.append('object_type', 'order');
            fd.append('object_id', String(order.id));
            fd.append('content', payload.content);
            fd.append('method', payload.method || 'wechat');
            if (payload.next_date) { fd.append('next_date', payload.next_date); }
            (payload.files || []).forEach(function (file) {
                if (file.file) { fd.append('files', file.file); }
            });
            api('/follow-ups', { method: 'POST', body: fd }).then(function () {
                toast('已记录订单跟进');
                return render();
            }).catch(function (err) {
                toast(err.message, true);
            });
        }
    });
}

function viewOrderDetail(root, rawId) {
    var id = Number(rawId);
    if (!id || isNaN(id)) {
        root.innerHTML = '<div class="card">订单 id 不合法，<a href="#/orders">回订单列表</a></div>';
        return Promise.resolve();
    }

    var supporting = Promise.all([
        api('/aftersales?order_id=' + id).catch(function () { return []; }),
        ensureCustomerIndex()
    ]);

    return api('/orders/' + id).then(function (order) {
        if (!order) {
            root.innerHTML = '<div class="card">订单不存在，<a href="#/orders">回订单列表</a></div>';
            return;
        }
        return supporting.then(function (base) {
            var afRes = base[0];
            var index = base[1] || {};
            return Promise.all([
                order.deal_id
                    ? api('/deals/' + order.deal_id).catch(function () { return order.deal; })
                    : Promise.resolve(order.deal),
                order.quote_id
                    ? api('/quotes/' + order.quote_id).catch(function () { return order.quote; })
                    : Promise.resolve(order.quote)
            ]).then(function (extra) {
                var deal = extra[0] || order.deal;
                var quote = extra[1] || order.quote;
                var aftersales = Array.isArray(afRes) ? afRes : ((afRes && afRes.items) || order.aftersales || []);
                renderOrderDetail(root, order, deal, quote, aftersales, index);
            });
        });
    });
}

function renderOrderDetail(root, order, deal, quote, aftersales, index) {
    var totalAmount = Number(order.amount) || 0;
    var paidTotal = (order.paid_amount !== undefined && order.paid_amount !== null)
        ? Number(order.paid_amount) || 0
        : (Number(order.deposit_paid) || 0) + (Number(order.balance_paid) || 0);
    var unpaid = Math.max(0, totalAmount - paidTotal);
    var customerName = order.customer_name || index[order.customer_id] ||
        ('客户 #' + order.customer_id);
    var timelineRecords = orderTimelineRecords(order);
    var files = orderDocumentFiles(order, timelineRecords);
    var shippedRecord = timelineRecords.filter(function (record) {
        return record.type === 'ship';
    })[0];
    var shippedAt = shippedRecord ? shippedRecord.at : null;
    var afterSaleCount = aftersales.length;
    var isSelfPickup = order.logistics_mode === 'self';
    var carrierName = (order.carrier && (order.carrier.name || order.carrier.company)) ||
        (deal && deal.carrier_name) || '未指定';

    /* 进度条：前端不再展示待客户确认，历史记录统一按待支付展示。 */
    var visibleStatuses = orderVisibleStatuses();
    var stepIdx = visibleStatuses.map(function (p) { return p[0]; }).indexOf(orderUiStatusCode(order.status));
    var progressHtml = '<div class="progress-bar">' + visibleStatuses.map(function (p, i) {
        var cls = 'step' + (i === stepIdx ? ' active' : (i < stepIdx ? ' done' : ''));
        return '<div class="' + cls + '"><div class="step-label">' +
            esc(p[1]) + '</div></div>';
    }).join('') + '</div>';

    /* 关联商机（能点回去） */
    var dealHtml = order.deal_id
        ? '<a href="#/deals/' + order.deal_id + '">商机 #' + order.deal_id + ' ›</a>'
        : '—';
    var opportunityStatus = deal
        ? dealStageBadge(deal.stage, deal.stage_label, deal.order_id)
        : '<span class="badge muted">未关联</span>';
    var productNames = (order.items || []).map(function (item) {
        return item.product_name_snapshot || item.product_code_snapshot;
    }).filter(Boolean);
    var productSummary = productNames.length
        ? productNames.slice(0, 2).map(esc).join(' / ') +
          (productNames.length > 2 ? ' 等 ' + productNames.length + ' 项' : '')
        : ([order.product_code_snapshot, order.product_name_snapshot, order.model]
            .filter(Boolean).join(' · ') || '未关联产品');
    var logisticsContact;
    if (isSelfPickup) {
        logisticsContact =
            '<div class="order-logistics-main"><span class="order-logistics-icon">自</span>' +
            '<div><b>客户自提</b><p>无需物流公司联络人</p></div></div>';
    } else {
        logisticsContact =
            '<div class="order-logistics-main"><span class="order-logistics-icon">运</span>' +
            '<div><b>' + esc(carrierName) + '</b><p>' +
            esc(order.carrier_contact_name || '未指定联络人') +
            (order.carrier_contact_phone ? ' · ' + esc(order.carrier_contact_phone) : '') +
            '</p></div></div>';
    }

    var topOverview = '<section class="card order-command-card">' +
        '<div class="order-command-head">' +
            '<div class="order-command-identity">' +
                '<a class="crumb" href="#/orders">‹ 订单</a>' +
                '<span class="order-command-no">' + esc(order.order_name || order.order_no) + '</span>' +
                '<small class="order-command-code">' + esc(order.order_no) + '</small>' +
                (afterSaleCount
                    ? '<span class="badge warn">售后数量 ' + afterSaleCount + '</span>' : '') +
                '<div class="order-tags-row">' +
                    orderTagsHtml(deal, order.status === 'completed') + '</div>' +
            '</div>' +
            '<div class="order-command-state"><span>订单状态</span>' +
                orderStatusBadge(order.status, order.status_label) + '</div>' +
        '</div>' +
        '<div class="order-metrics">' +
            '<div class="order-metric order-metric-money">' +
                '<span>订单金额</span><strong>' + money(totalAmount) + '</strong>' +
                '<small>已收 ' + money(paidTotal) + ' · 未收 ' + money(unpaid) + '</small></div>' +
            '<div class="order-metric"><span>物流方式</span><strong>' +
                esc(order.logistics_mode_label || (isSelfPickup ? '自提' : '待确认')) +
                '</strong><small>运费 ' + money(order.logistics_fee || 0) + '</small></div>' +
            '<div class="order-metric"><span>商机状态</span>' + opportunityStatus +
                '<small>跟随报价单最高优先级</small></div>' +
            '<div class="order-metric"><span>收付款</span><strong>' +
                (unpaid ? '待收 ' + money(unpaid) : '已收清') +
                '</strong><small>已收 ' + money(paidTotal) + '</small></div>' +
            '<div class="order-metric order-metric-date"><span>创建时间</span><strong>' +
                fmtDateTime(order.created_at).slice(0, 10) + '</strong><small>' +
                esc(order.owner || '订单记录') + '</small></div>' +
        '</div>' +
        '<div class="order-context-grid">' +
            '<a class="order-context" href="#/customers/' + order.customer_id + '">' +
                '<span>客户</span><b>' + esc(customerName) + '</b><small>查看客户档案 ›</small></a>' +
            '<a class="order-context" href="#/deals/' + order.deal_id + '">' +
                '<span>关联商机</span><b>' + esc(dealHtml.replace(/<[^>]+>/g, '')) +
                '</b><small>' + esc(deal && (deal.product_name_snapshot || deal.model) || '查看商机详情') +
                '</small></a>' +
            '<a class="order-context" href="#/deals/' + order.deal_id + '">' +
                '<span>报价单</span><b>' + esc(quote ? quote.quote_no : '来源报价单') +
                '</b><small>' + esc(quote ? (quote.title || '查看报价明细') : '查看商机详情') +
                '</small></a>' +
            '<div class="order-context">' +
                '<span>关联产品</span><b>' + esc(productSummary) + '</b><small>' +
                (order.items || []).length + ' 项产品明细</small></div>' +
            '<div class="order-context">' +
                '<span>物流公司 / 联络人</span><b>' +
                esc(isSelfPickup ? '客户自提' : carrierName) + '</b><small>' +
                esc(isSelfPickup ? '无需物流公司联络人' :
                    ((order.carrier_contact_name || '未指定联络人') +
                    (order.carrier_contact_phone ? ' · ' + order.carrier_contact_phone : ''))) +
                '</small></div>' +
        '</div>' +
        '<div class="order-logistics-strip">' +
            '<div class="order-logistics-fact"><span>收件人</span><b>' +
                esc(order.receiver_name || '—') + '</b></div>' +
            '<div class="order-logistics-fact"><span>联系电话</span><b>' +
                esc(order.receiver_phone || '—') + '</b></div>' +
            '<div class="order-logistics-fact"><span>收货地址</span><b>' +
                esc(order.receiver_address || '—') + '</b></div>' +
            '<div class="order-logistics-fact"><span>发货日期</span><b>' +
                (shippedAt ? fmtDateTime(shippedAt).slice(0, 10) : '待发货') + '</b></div>' +
            '<div class="order-logistics-fact"><span>运单号</span><b>' +
                esc(isSelfPickup ? '自提' : (order.tracking_number || order.tracking_no || '待补')) +
                '</b></div>' +
        '</div>' +
        progressHtml +
        '<div class="order-primary-actions" id="orderPrimaryActions"></div>' +
    '</section>';

    var detailItems = (quote && quote.items && quote.items.length) ? quote.items : (order.items || []);
    var quoteItemsHtml = detailItems.length
        ? '<div class="order-quote-items">' + detailItems.map(function (item) {
            return quoteItemHtml(item, false);
        }).join('') + '</div>'
        : '<p class="empty">报价单还没有产品明细</p>';
    var quoteHtml = '<section class="card order-section" id="orderQuoteSection">' +
        '<div class="card-head"><div><h2>报价单明细</h2>' +
            '<p class="order-section-copy">客户确认的报价与下单表快照</p></div>' +
            (quote ? '<span class="badge quote">' + esc(quote.status_label || quote.status) + '</span>' : '') +
        '</div>' +
        (quote
            ? '<div class="order-quote-heading"><div><b>' + esc(quote.quote_no) + '</b>' +
              '<span>' + esc(quote.title || '') + '</span></div><strong>' +
              money(quote.amount) + '</strong></div>' +
              (quote.note ? '<p class="small muted order-quote-note">' + esc(quote.note) + '</p>' : '')
            : '<p class="small muted">这是历史订单，没有可回查的来源报价单。</p>') +
        quoteItemsHtml +
    '</section>';

    var productTotal = Number(order.product_total || order.amount || 0);
    var discountAmount = Number(order.discount_amount || 0);
    var productPayable = Number(order.product_payable || (productTotal - discountAmount));
    var freightAmount = Number(order.logistics_fee || order.freight_amount || 0);
    var depositDue = Number(order.deposit_amount || 0);
    var balanceDue = Number(order.balance_amount || 0);
    var depositPaid = Number(order.deposit_paid || 0);
    var balancePaid = Number(order.balance_paid || 0);
    function paidBadge(paid, due) {
        if (!due) { return '<span class="badge muted">无需收</span>'; }
        return paid >= due ? '<span class="badge ok">已收</span>' : '<span class="badge warn">待收</span>';
    }
    var moneyHtml = '<section class="card order-section">' +
        '<div class="card-head"><div><h2>订单金额及收付款</h2>' +
            '<p class="order-section-copy">优惠只作用于产品合计，运费独立核算</p></div>' +
            '<span class="badge ' + (unpaid ? 'warn' : 'ok') + '">' +
                (unpaid ? '待收 ' + money(unpaid) : '已收清') + '</span></div>' +
        '<div class="order-money-summary">' +
            '<div><span>产品合计</span><b>' + money(productTotal) + '</b></div>' +
            '<div><span>整单优惠</span><b>' + (discountAmount ? '-' + money(discountAmount) : money(0)) + '</b></div>' +
            '<div><span>运费</span><b>' + money(freightAmount) + '</b></div>' +
            '<div class="is-total"><span>订单应收</span><b>' + money(totalAmount) + '</b></div>' +
        '</div>' +
        (order.discount_reason
            ? '<p class="small muted order-discount-note">优惠说明：' + esc(order.discount_reason) + '</p>' : '') +
        '<div class="order-payment-grid">' +
            '<div class="order-payment"><span>定金应收</span><b>' + money(depositDue) + '</b>' +
                paidBadge(depositPaid, depositDue) + '<small>已收 ' + money(depositPaid) + '</small></div>' +
            '<div class="order-payment"><span>尾款应收</span><b>' + money(balanceDue) + '</b>' +
                paidBadge(balancePaid, balanceDue) + '<small>已收 ' + money(balancePaid) + '</small></div>' +
            '<div class="order-payment is-paid"><span>已收合计</span><b>' + money(paidTotal) + '</b>' +
                '<small>订单实收</small></div>' +
            '<div class="order-payment' + (unpaid ? ' is-due' : ' is-paid') + '"><span>未收金额</span><b>' +
                money(unpaid) + '</b><small>' + (unpaid ? '仍需跟进' : '应收账款已清零') + '</small></div>' +
        '</div>' +
    '</section>';

    var logisticsHtml = '<section class="card order-section">' +
        '<div class="card-head"><div><h2>物流信息</h2>' +
            '<p class="order-section-copy">物流公司、联络人和收货信息</p></div></div>' +
        '<div class="order-logistics-detail">' +
            '<div class="order-logistics-detail-main">' + logisticsContact +
                '<span class="badge muted">' + esc(order.logistics_mode_label || '待确认') + '</span></div>' +
            infoGrid([
                ['收件人', order.receiver_name || '—'],
                ['联系电话', order.receiver_phone || '—'],
                ['收货地址', order.receiver_address || '—'],
                ['发货日期', shippedAt ? fmtDateTime(shippedAt).slice(0, 10) : '—'],
                ['运单号', isSelfPickup ? '自提' : (order.tracking_number || order.tracking_no || '—')],
                ['物流费用', money(order.logistics_fee || 0)]
            ]) +
        '</div>' +
    '</section>';

    var aftersalesHtml = afterSaleCount ? '<section class="card order-section">' +
        '<div class="card-head"><div><h2>售后单 <span class="badge muted">' +
            afterSaleCount + '</span></h2><p class="order-section-copy">订单完成后产生的售后记录</p></div>' +
            '<button type="button" class="btn btn-sm" id="btnAddAftersale">＋ 添加售后</button></div>' +
        aftersales.map(function (a) {
            return '<a class="order-aftersale" href="#/aftersales/' + a.id + '">' +
                '<div><b>' + esc(a.no) + '</b><span>' +
                esc(a.type_label || aftersaleTypeLabel(a.type, a.type_other)) + ' · ' +
                esc(String(a.description || '').slice(0, 48)) + '</span></div>' +
                '<span class="badge ' + (a.status === 'done' ? 'ok' :
                    (a.status === 'rejected' ? 'danger' : 'warn')) + '">' +
                esc(a.status_label || aftersaleStatusLabel(a.status)) + '</span></a>';
        }).join('') +
    '</section>' : '';

    var historyHtml = '<section class="card order-section" id="orderTimelineSection">' +
        '<div class="card-head"><div><h2>跟进履历 <span class="badge muted">' +
            timelineRecords.length + '</span></h2><p class="order-section-copy">' +
            '人工跟进、状态变更、收付款、物流和售后记录统一展示</p></div>' +
            (order.status === 'completed'
                ? '<span class="small muted">订单已完成，后续跟进请创建售后单</span>'
                : '<button type="button" class="btn btn-sm btn-primary" id="btnOrderFollow">＋ 记一条跟进</button>') +
            '</div>' +
        timelineHtml(timelineRecords) +
    '</section>';

    var documentsHtml = filesCardHtml(files, '这个订单还没有上传确认截图、付款凭证或其它资料');

    root.innerHTML = '<div class="order-page">' + topOverview +
        quoteHtml + moneyHtml + logisticsHtml + aftersalesHtml + historyHtml + documentsHtml + '</div>';

    /* 操作区位于摘要卡内，按钮逻辑仍复用订单原有流转入口。 */
    var actionHost = $('#orderPrimaryActions', root);
    var next = ORDER_NEXT_STEP[order.status];
    var actionBtns = '';
    if (next) {
        actionBtns += '<button type="button" class="btn btn-primary" id="btnNextAction">' + next[1] + '</button>';
    }
    if (order.status !== 'completed') {
        actionBtns += '<button type="button" class="btn" id="btnOrderSummaryFollow">＋ 跟进</button>';
    }
    if (order.status !== 'completed') {
        actionBtns += '<button type="button" class="btn" id="btnEditOrder">修改订单</button>';
    }
    if (order.status === 'completed') {
        actionBtns += '<button type="button" class="btn" id="btnAddAftersaleTop">＋ 添加售后</button>';
    }
    actionHost.innerHTML = actionBtns;

    var nextBtn = $('#btnNextAction', root);
    if (nextBtn) {
        nextBtn.addEventListener('click', function () {
            var target = next[0];
            if (target === 'deposit_paid') { showDepositPayment(order); return; }
            if (target === 'balance_paid') { showBalancePayment(order); return; }
            if (target === 'completed') { showShipModal(order); return; }
            transitionOrder(order, target, {}, next[1]);
        });
    }

    ['#btnOrderFollow', '#btnOrderSummaryFollow'].forEach(function (selector) {
        var button = $(selector, root);
        if (button) { button.addEventListener('click', function () { orderFollowModal(order); }); }
    });

    ['#btnAddAftersale', '#btnAddAftersaleTop'].forEach(function (selector) {
        var button = $(selector, root);
        if (button) {
            button.addEventListener('click', function () {
                openAftersaleModal(order, aftersales);
            });
        }
    });

    var editOrderBtn = $('#btnEditOrder', root);
    if (editOrderBtn) {
        editOrderBtn.addEventListener('click', function () { openOrderEditModal(order); });
    }
    if (deal) { bindDealTagActions(root, deal); }
}

/* ---------------- 修改订单：商品/价格继承字段只读，其余订单信息可改 ---------------- */
function openOrderEditModal(order) {
    var modal = createOrderModal('修改订单');

    modal.querySelector('.modal-body').innerHTML =
        '<form id="orderEditForm" class="form-modal form-grid" autocomplete="off">' +
        '<div class="field"><label>订单名称 *</label>' +
        '<input name="order_name" maxlength="120" required value="' +
        esc(order.order_name || order.order_no) + '"></div>' +
        '<div class="field"><label>订单编号（不可修改）</label>' +
        '<input name="order_no" value="' + esc(order.order_no) + '" readonly tabindex="-1"></div>' +
        '<p class="small muted field-wide">产品明细、报价金额、优惠和商机来源保持只读；订单名称、物流、收货、费用和备注可修改。</p>' +
        '<div class="field"><label>物流方式</label><select name="logistics_mode">' +
        LOGISTICS_MODE_OPTIONS.map(function (option) {
            return '<option value="' + option[0] + '"' +
                (order.logistics_mode === option[0] ? ' selected' : '') + '>' +
                option[1] + '</option>';
        }).join('') + '</select></div>' +
        '<div class="field" data-ship><label>物流公司</label>' +
        '<select name="carrier_id"><option value="">请选择</option></select></div>' +
        '<div class="field" data-ship><label>物流公司联络人 *</label>' +
        '<select name="carrier_contact_id"><option value="">请选择</option></select></div>' +
        '<div class="field" data-ship><label>物流费用</label>' +
        '<input name="logistics_fee" type="number" min="0" step="0.01" value="' +
        (Number(order.logistics_fee) || 0) + '"></div>' +
        '<div class="field" data-ship><label>运单号</label>' +
        '<input name="tracking_number" maxlength="64" placeholder="可后补" value="' +
        esc(order.tracking_number || order.tracking_no || '') + '"></div>' +
        '<div class="field field-wide" data-ship><label>历史收件人及地址</label>' +
        '<select name="address_id"><option value="">手动填写 / 新地址</option></select></div>' +
        '<div class="field" data-ship><label>收件人 *</label>' +
        '<input name="receiver_name" maxlength="32" value="' +
        esc(order.receiver_name || '') + '"></div>' +
        '<div class="field" data-ship><label>收货电话 *</label>' +
        '<input name="receiver_phone" maxlength="32" inputmode="tel" value="' +
        esc(order.receiver_phone || '') + '"></div>' +
        '<div class="field field-wide" data-ship><label>收货地址 *</label>' +
        '<input name="receiver_address" maxlength="200" value="' +
        esc(order.receiver_address || '') + '"></div>' +
        '<div class="field field-wide"><label>订单备注</label>' +
        '<textarea name="note" maxlength="500" rows="3" placeholder="交付、安装或客户特别要求">' +
        esc(order.note || '') + '</textarea></div>' +
        '<div class="form-actions field-wide"><button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">保存修改</button></div>' +
        '</form>';

    var form = $('#orderEditForm', modal);
    var modeEl = form.querySelector('[name="logistics_mode"]');
    var carrierEl = form.querySelector('[name="carrier_id"]');
    var contactEl = form.querySelector('[name="carrier_contact_id"]');
    var feeEl = form.querySelector('[name="logistics_fee"]');
    var trackingEl = form.querySelector('[name="tracking_number"]');
    var addressEl = form.querySelector('[name="address_id"]');
    var receiverNameEl = form.querySelector('[name="receiver_name"]');
    var receiverPhoneEl = form.querySelector('[name="receiver_phone"]');
    var receiverAddressEl = form.querySelector('[name="receiver_address"]');
    var shipFields = $$('[data-ship]', modal);

    function refreshMode() {
        var needsShipping = modeEl.value !== 'self';
        shipFields.forEach(function (field) { field.hidden = !needsShipping; });
    }
    modeEl.addEventListener('change', refreshMode);
    refreshMode();

    api('/carriers').then(function (carriers) {
        populateCarrierContactSelects(
            carrierEl, contactEl, carriers, order.carrier_id, order.carrier_contact_id
        );
    }).catch(function () {
        toast('物流公司加载失败，请稍后重试', true);
    });

    var addressList = [];
    function applyAddress() {
        var address = addressList.filter(function (item) {
            return String(item.id) === String(addressEl.value || '');
        })[0];
        if (!address) { return; }
        receiverNameEl.value = address.receiver_name || '';
        receiverPhoneEl.value = address.phone || '';
        receiverAddressEl.value = address.address || '';
    }
    addressEl.addEventListener('change', applyAddress);
    [receiverNameEl, receiverPhoneEl, receiverAddressEl].forEach(function (input) {
        input.addEventListener('input', function () { addressEl.value = ''; });
    });
    api('/customers/' + order.customer_id + '/addresses').then(function (list) {
        addressList = list || [];
        addressEl.innerHTML = '<option value="">手动填写 / 新地址</option>' +
            addressList.map(function (address) {
                var label = [
                    address.label,
                    address.receiver_name,
                    address.phone,
                    address.address
                ].filter(Boolean).join(' · ');
                return '<option value="' + address.id + '">' + esc(label) + '</option>';
            }).join('');
        var current = addressList.filter(function (address) {
            return address.receiver_name === (order.receiver_name || '') &&
                address.phone === (order.receiver_phone || '') &&
                address.address === (order.receiver_address || '');
        })[0];
        if (current) { addressEl.value = String(current.id); }
    }).catch(function () { /* 历史地址加载失败时仍可手动填写 */ });

    modal.querySelector('.modal-cancel').addEventListener('click', function () {
        if (modal.parentNode) { document.body.removeChild(modal); }
    });
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var mode = modeEl.value;
        var payload = {
            order_name: String(form.querySelector('[name="order_name"]').value || '').trim(),
            logistics_mode: mode,
            carrier_id: null,
            carrier_contact_id: null,
            logistics_fee: 0,
            tracking_number: null,
            receiver_name: null,
            receiver_phone: null,
            receiver_address: null,
            note: String(form.querySelector('[name="note"]').value || '').trim() || null
        };
        if (mode !== 'self') {
            if (!carrierEl.value) {
                toast('请选择物流公司', true);
                return;
            }
            if (!contactEl.value) {
                toast('请选择物流公司的联络人；没有联络人请先到物流页维护', true);
                return;
            }
            payload.receiver_name = String(receiverNameEl.value || '').trim();
            payload.receiver_phone = String(receiverPhoneEl.value || '').trim();
            payload.receiver_address = String(receiverAddressEl.value || '').trim();
            if (!payload.receiver_name || !payload.receiver_phone || !payload.receiver_address) {
                toast('请填全收件人、收货电话和收货地址', true);
                return;
            }
            payload.carrier_id = Number(carrierEl.value);
            payload.carrier_contact_id = Number(contactEl.value);
            payload.logistics_fee = Number(feeEl.value) || 0;
            payload.tracking_number = String(trackingEl.value || '').trim() || null;
        }
        if (!payload.order_name) { toast('请填写订单名称', true); return; }
        var btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        api('/orders/' + order.id, { method: 'PUT', body: payload }).then(function () {
            toast('订单已修改');
            if (modal.parentNode) { document.body.removeChild(modal); }
            return render();
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}

/* ---------------- 添加售后（订单已完成才允许；售后单只能这么创建） ---------------- */
function openAftersaleModal(order, aftersales) {
    var completedHistory = (aftersales || []).filter(function (a) {
        return a.status === 'done';
    });
    var historyOptions = completedHistory.map(function (a) {
        var summary = [a.no, a.type_label || aftersaleTypeLabel(a.type, a.type_other),
            a.status_label || aftersaleStatusLabel(a.status)].filter(Boolean).join(' · ');
        return '<option value="' + a.id + '">' + esc(summary) + '</option>';
    }).join('');
    var historyField = historyOptions
        ? '<div class="field field-wide"><label>关联历史售后（可选）</label>' +
          '<select name="related_aftersale_id"><option value="">不关联</option>' +
          historyOptions + '</select>' +
          '<p class="small muted">只能关联当前订单下已完成的历史售后单，便于追溯同类问题。</p></div>'
        : '';
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
        historyField +
        '<div class="form-actions"><button type="submit" class="btn btn-primary">创建售后单</button></div>' +
        '</form>';

    var form = modal.querySelector('#asNewForm');
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var type = String(form.querySelector('[name="type"]').value || '');
        var desc = String(form.querySelector('[name="description"]').value || '').trim();
        var relatedEl = form.querySelector('[name="related_aftersale_id"]');
        var relatedId = relatedEl && relatedEl.value ? Number(relatedEl.value) : null;
        if (!type) { toast('请选择售后类型', true); return; }
        if (!desc) { toast('请填写问题描述', true); return; }
        btn.disabled = true;
        api('/aftersales', {
            method: 'POST',
            body: {
                order_id: order.id,
                type: type,
                description: desc,
                related_aftersale_id: relatedId
            }
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

/* 发货：确认物流方式、承运公司、联络人和运单号 */
function showShipModal(order) {
    var modal = createOrderModal('确认发货');
    modal.querySelector('.modal-body').innerHTML = '<form id="shipForm" class="form-modal form-grid">' +
        '<p class="small muted field-wide">确认发货后订单将直接进入“已完成”状态。</p>' +
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
        '<div class="field"><label>承运公司</label>' +
        '<select name="carrier_id"><option value="">请选择</option></select></div>' +
        '<div class="field"><label>物流公司联络人 *</label>' +
        '<select name="carrier_contact_id"><option value="">请选择</option></select></div>' +
        '</div>' +
        '<div class="row-2">' +
        '<div class="field"><label>运单号</label>' +
        '<input name="tracking_number" maxlength="64" value="' + esc(order.tracking_number || '') + '"></div>' +
        '<div class="field"><label>备注</label><textarea name="note" maxlength="500">' +
        esc(order.note || '') + '</textarea></div>' +
        '</div>' +
        '<div class="form-actions"><button type="submit" class="btn btn-primary">确认发货</button></div>' +
        '</form>';

    var form = $('#shipForm', modal);
    var modeEl = form.querySelector('[name="logistics_mode"]');
    var carrierEl = form.querySelector('[name="carrier_id"]');
    var contactEl = form.querySelector('[name="carrier_contact_id"]');

    api('/carriers').then(function (carriers) {
        populateCarrierContactSelects(
            carrierEl, contactEl, carriers, order.carrier_id, order.carrier_contact_id
        );
    }).catch(function () {
        toast('物流公司加载失败，请稍后重试', true);
    });

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var mode = modeEl.value;
        if (mode !== 'self') {
            if (!carrierEl.value) { toast('请选择物流公司', true); return; }
            if (!contactEl.value) { toast('请选择物流公司的联络人', true); return; }
            if (!String(form.querySelector('[name="tracking_number"]').value || '').trim()) {
                toast('使用物流公司时必须填写运单号', true);
                return;
            }
        }
        var extra = {
            logistics_mode: mode,
            carrier_id: mode === 'self' ? null : Number(carrierEl.value),
            carrier_contact_id: mode === 'self' ? null : Number(contactEl.value),
            logistics_fee: numOrNull(form.querySelector('[name="logistics_fee"]').value) || 0,
            tracking_number: String(form.querySelector('[name="tracking_number"]').value || '').trim() || null,
            note: String(form.querySelector('[name="note"]').value || '').trim() || null
        };
        document.body.removeChild(modal);
        transitionOrder(order, 'completed', extra, '确认发货');
    });
    document.body.appendChild(modal);
}

/* ---------------- 定金 / 尾款（要传截图） ---------------- */
function showDepositPayment(order) {
    var modal = createOrderModal('支付定金');
    modal.querySelector('.modal-body').innerHTML = '<form id="depositForm" class="form-modal form-grid">' +
        '<div class="field"><label>定金金额 *</label>' +
        '<input type="number" id="depositAmount" name="amount" min="0" step="0.01" required ' +
        'placeholder="应收定金 ' + money(order.deposit_amount || order.amount) + '"></div>' +
        '<div class="field"><label>备注</label><textarea name="note"></textarea></div>' +
        '<div class="field"><label>支付截图（最多 3 张）</label>' +
        '<input type="file" name="screenshots" accept="image/*" multiple></div>' +
        '<div class="form-actions"><button type="submit" class="btn btn-primary">提交</button></div>' +
        '</form>';

    var form = $('#depositForm', modal);
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var amount = parseFloat(form.querySelector('[name="amount"]').value);
        if (isNaN(amount) || amount <= 0) { toast('请输入有效的定金金额', true); return; }
        if (amount > Number(order.amount)) { toast('定金金额不能超过总额', true); return; }
        var fd = new FormData();
        fd.append('amount', String(amount));
        var note = String(form.querySelector('[name="note"]').value || '').trim();
        if (note) { fd.append('note', note); }
        var files = form.querySelector('[name="screenshots"]').files;
        for (var i = 0; i < files.length && i < 3; i++) { fd.append('screenshots', files[i]); }
        var ready = order.status === 'pending_confirmation'
            ? api('/orders/' + order.id + '/confirm', { method: 'POST', body: new FormData() })
            : Promise.resolve();
        ready.then(function () {
            return api('/orders/' + order.id + '/pay-deposit', { method: 'POST', body: fd });
        }).then(function () {
            toast('定金已记录');
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
