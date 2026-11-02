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
    var cls = stage === 'won' ? 'ok' : (stage === 'lost' ? 'muted' :
        (stage === 'confirm' ? 'warn' : 'quote'));
    return '<span class="badge ' + cls + '">' + esc(label || STAGE_LABEL[stage] || stage || '—') + '</span>';
}

/* 手动/电动徽标（后端下发 drive_type_label；数据字典里没有这张表） */
function driveBadge(deal) {
    if (!deal.drive_type) { return '<span class="muted small">—</span>'; }
    var label = deal.drive_type_label || (deal.drive_type === 'electric' ? '电动' : '手动');
    return '<span class="badge ' + (deal.drive_type === 'electric' ? 'ok' : 'muted') + '">' + esc(label) + '</span>';
}

function dealProductText(deal) {
    if (deal.confirmed_quote_no) {
        return '客户已确认报价单 ' + deal.confirmed_quote_no;
    }
    if (deal.quote_count > 0 && !deal.product_id) {
        return deal.quote_count + ' 张报价单';
    }
    if (!deal.product_id && !deal.product_type) {
        return '待创建报价单';
    }
    if (deal.items && deal.items.length > 1) {
        return (deal.product_name_snapshot || deal.product_type || '多产品') +
            ' 等 ' + deal.items.length + ' 项产品';
    }
    var parts = [deal.product_name_snapshot, deal.product_type, deal.model, deal.spec].filter(Boolean);
    parts = parts.filter(function (value, index) { return parts.indexOf(value) === index; });
    return parts.length ? parts.join(' / ') : '未填产品';
}

function dealItemName(item) {
    return [item.product_code_snapshot, item.product_name_snapshot].filter(Boolean).join(' · ') ||
        [item.product_type, item.model].filter(Boolean).join(' · ') || '未关联产品';
}

function dealItemsCardHtml(items, editable, total) {
    var rows = (items || []).map(function (item, index) {
        return '<tr>' +
            '<td>' + (index + 1) + '</td>' +
            '<td><b>' + esc(dealItemName(item)) + '</b>' +
                (item.product_config_snapshot ? '<div class="small muted">' +
                    esc(item.product_config_snapshot) + '</div>' : '') + '</td>' +
            '<td>' + esc(item.quantity || 1) + '</td>' +
            '<td>' + esc(item.spec || '—') + '</td>' +
            '<td>' + esc(item.production_spec || '—') + '</td>' +
            '<td style="text-align:right;white-space:nowrap">' + money(item.unit_price) + '</td>' +
            '<td style="text-align:right;white-space:nowrap"><b>' + money(item.amount) + '</b></td>' +
            (editable ? '<td style="white-space:nowrap">' +
                '<button type="button" class="btn btn-sm" data-edit-item="' + item.id + '">编辑</button> ' +
                '<button type="button" class="btn btn-sm btn-danger" data-delete-item="' + item.id + '">删除</button>' +
                '</td>' : '') +
            '</tr>';
    }).join('');
    var empty = '<tr><td colspan="' + (editable ? 8 : 7) +
        '" class="empty">还没有产品明细</td></tr>';
    return '<div class="card" id="dealItemsCard">' +
        '<div class="card-head"><h2>产品明细 <span class="badge muted">' +
        (items || []).length + '</span></h2>' +
        (editable ? '<button type="button" class="btn btn-sm btn-primary" id="btnAddDealItem">' +
            '＋ 添加产品</button>' :
            '<span class="small muted">商机已锁定，产品明细为快照</span>') +
        '</div><div class="table-wrap"><table><thead><tr>' +
        '<th>#</th><th>产品</th><th>数量</th><th>洞口尺寸</th><th>生产参数</th>' +
        '<th style="text-align:right">单价</th><th style="text-align:right">金额</th>' +
        (editable ? '<th>操作</th>' : '') +
        '</tr></thead><tbody>' + (rows || empty) + '</tbody></table></div>' +
        '<p class="small muted" style="margin:10px 0 0;text-align:right">' +
        '产品合计 <b>' + money(total) + '</b>；优惠和运费在生成订单时单独填写</p></div>';
}

function quoteStatusBadge(quote) {
    var cls = quote.status === 'confirmed' ? 'ok' : (quote.status === 'void' ? 'muted' :
        (quote.status === 'pending' ? 'warn' : 'quote'));
    return '<span class="badge ' + cls + '">' +
        esc(quote.status_label || quote.status) + '</span>';
}

function quoteFormPreviewHtml(item) {
    if (item.form_preview_url) {
        var previewUrl = '/crm' + item.form_preview_url;
        return '<div class="small muted" style="margin:8px 0 6px">下单表</div>' +
            '<button type="button" class="thumb quote-form-thumbnail" ' +
            'data-img="' + esc(previewUrl) + '" data-name="下单表数据区域">' +
            '<img src="' + esc(previewUrl) + '" alt="下单表缩略图" loading="lazy"></button>';
    }
    var content = item.form_content || {};
    var sheets = content.sheets || [];
    if (!sheets.length) {
        return '<p class="small muted">尚未上传下单表</p>';
    }
    return sheets.map(function (sheet, sheetIndex) {
        var rows = sheet.rows || [];
        return '<details class="quote-form-sheet"' + (sheetIndex === 0 ? ' open' : '') + '>' +
            '<summary>' + esc(sheet.name) + ' · ' + rows.length + ' 行' +
            (sheet.truncated ? '（仅展示前 160 行 / 48 列）' : '') + '</summary>' +
            '<div class="table-wrap quote-form-preview" style="max-height:360px;overflow:auto">' +
            '<table><tbody>' + rows.map(function (row) {
                return '<tr>' + row.map(function (cell) {
                    return '<td>' + esc(cell === null || cell === undefined ? '' : cell) + '</td>';
                }).join('') + '</tr>';
            }).join('') + '</tbody></table></div></details>';
    }).join('');
}

function quoteItemHtml(item, editable) {
    return '<div class="item" style="display:block">' +
        '<div class="item-main" style="width:100%">' +
        '<div class="item-title">' +
            esc([item.product_code_snapshot, item.product_name_snapshot].filter(Boolean).join(' · ')) +
            '<span class="badge muted">×' + esc(item.quantity || 1) + '</span>' +
            '<span style="margin-left:auto"><b>' + money(item.amount) + '</b></span></div>' +
        '<div class="item-sub small">' +
            '报价金额 ' + money(item.amount) + '</div>' +
        '<div class="quote-item-actions">' +
            (item.form_url
                ? '<a class="btn btn-sm quote-file-action" href="/crm' + esc(item.form_url) +
                  '" title="下载已上传下单表"><span aria-hidden="true">⇩</span> 下载下单表</a>'
                : '<span class="badge warn">待上传下单表</span>') +
            (editable
                ? '<span class="quote-action-divider" aria-hidden="true"></span>' +
                  '<button type="button" class="btn btn-sm quote-edit-action" data-quote-edit-item="' +
                  item.id + '">编辑产品</button>' +
                  '<button type="button" class="btn btn-sm btn-outline-danger quote-delete-action" data-quote-delete-item="' +
                  item.id + '">删除</button>'
                : '') +
        '</div>' +
        (item.note ? '<div class="item-sub small muted">' + esc(item.note) + '</div>' : '') +
        quoteFormPreviewHtml(item) +
        '</div></div>';
}

function quoteCardsHtml(deal, quotes) {
    var cards = (quotes || []).map(function (quote) {
        var editable = !deal.order_id && quote.status === 'draft';
        var itemHtml = quote.items && quote.items.length
            ? quote.items.map(function (item) { return quoteItemHtml(item, editable); }).join('')
            : '<p class="empty" style="padding:16px">还没有关联产品，请先添加产品并上传对应下单表。</p>';
        var actions = '';
        if (editable) {
            var canConfirm = quote.items && quote.items.length &&
                quote.items.every(function (item) { return item.form_available; });
            actions += '<button type="button" class="btn btn-sm btn-primary" data-quote-add-item="' +
                quote.id + '">＋ 添加产品</button> ';
            actions += '<button type="button" class="btn btn-sm btn-warning" data-quote-send="' +
                quote.id + '"' + (canConfirm ? '' : ' disabled title="每个产品都必须上传对应下单表"') +
                '>发客户确认</button> ';
        }
        if (quote.status === 'pending') {
            actions += '<button type="button" class="btn btn-sm btn-success" data-quote-confirm="' +
                quote.id + '">客户已确认</button> ';
            actions += '<button type="button" class="btn btn-sm" data-quote-requote="' +
                quote.id + '">重新报价</button> ';
        }
        if (quote.order_id) {
            actions += '<a class="btn btn-sm btn-primary" href="#/orders/' + quote.order_id + '">查看订单</a> ';
        }
        if (!quote.order_id && !deal.order_id &&
            (quote.status === 'draft' || quote.status === 'pending')) {
            actions += '<button type="button" class="btn btn-sm btn-outline-danger" data-quote-void="' +
                quote.id + '">作废</button> ';
        }
        var canDeleteQuote = !quote.order_id && !deal.order_id &&
            (quote.status === 'draft' || quote.status === 'void');
        var quoteTitle = quote.title || quote.quote_no;
        var deleteCardAction = canDeleteQuote
            ? '<button type="button" class="deal-quote-card-delete" ' +
              'data-quote-delete="' + quote.id + '" title="删除报价单" ' +
              'aria-label="删除报价单 ' + esc(quoteTitle) + '">' +
              '<span aria-hidden="true">×</span></button>'
            : '';
        var itemCount = (quote.items || []).length;
        return '<details class="deal-quote-card">' +
            '<summary class="deal-quote-card-head">' +
                '<span class="deal-quote-card-title">' + esc(quoteTitle) + '</span>' +
                '<span class="deal-quote-card-side">' + quoteStatusBadge(quote) +
                    '<b>' + money(quote.amount) + '</b></span>' +
                '<span class="deal-quote-card-meta">' + esc(quote.quote_no) +
                    ' · ' + itemCount + ' 项产品</span>' +
                deleteCardAction +
            '</summary>' +
            '<div class="deal-quote-card-body">' +
                '<div class="small muted">创建 ' + fmtDateTime(quote.created_at) +
                    (quote.confirmed_at ? ' · 确认 ' + fmtDateTime(quote.confirmed_at) : '') + '</div>' +
                (quote.note ? '<div class="item-sub">' + esc(quote.note) + '</div>' : '') +
                (quote.confirmation_note
                    ? '<div class="item-sub small">确认说明：' + esc(quote.confirmation_note) + '</div>'
                    : '') +
                ((quote.confirmation_files || []).length
                    ? '<div class="photos">' + quote.confirmation_files.map(function (file) {
                        var url = '/crm' + file.url;
                        return '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' +
                            '<img src="' + esc(url) + '" alt="客户确认截图" loading="lazy"></a>';
                    }).join('') + '</div>'
                    : '') +
                '<div class="deal-quote-items">' + itemHtml + '</div>' +
                (actions ? '<div class="deal-quote-actions">' + actions + '</div>' : '') +
            '</div>' +
        '</details>';
    }).join('');
    return '<div class="deal-quote-list">' +
        (cards || '<div class="deal-quote-empty"><b>无报价单</b>' +
            '<span>添加报价单后在这里比较不同方案</span></div>') +
        '</div>';
}

function dealTagsHtml(deal, quotes) {
    var tags = deal.tags || [];
    return '<div class="deal-tags" aria-label="商机标签">' +
        '<span class="deal-tag deal-tag-system" title="系统标签，自动统计">报价单 ' +
          (quotes || []).length + '</span>' +
        tags.map(function (tag) {
            return '<span class="deal-tag ' +
                (tag.source === 'auto' ? 'deal-tag-auto' : 'deal-tag-manual') +
                '" title="' + (tag.deletable ? '手动标签' : '系统自动标签，不能删除') + '">' +
                esc(tag.name) +
                (tag.deletable
                    ? '<button type="button" class="deal-tag-remove" data-deal-tag-remove="' +
                      tag.id + '" title="删除标签" aria-label="删除标签 ' + esc(tag.name) + '">×</button>'
                    : '') +
            '</span>';
        }).join('') +
        '<button type="button" class="deal-tag-add" data-deal-tag-add="' + deal.id +
          '" title="添加标签" aria-label="添加标签">＋</button>' +
    '</div>';
}

function dealOverviewHtml(deal, customerName, quotes) {
    var confirmedQuote = (quotes || []).filter(function (quote) {
        return quote.status === 'confirmed';
    })[0];
    var hasPendingOrConfirmedQuote = (quotes || []).some(function (quote) {
        return quote.status === 'pending' || quote.status === 'confirmed';
    });
    var canAddQuote = !deal.order_id && deal.stage !== 'lost' && !hasPendingOrConfirmedQuote;
    var canLose = !deal.order_id && deal.stage !== 'lost' && !confirmedQuote;
    var orderAction;
    if (deal.order_id) {
        orderAction = '<a class="btn btn-sm btn-primary" href="#/orders/' + deal.order_id +
            '">查看订单</a>';
    } else if (confirmedQuote) {
        orderAction = '<button type="button" class="btn btn-sm btn-primary" id="dealCreateOrder" ' +
            'data-quote-order="' + confirmedQuote.id + '">生成订单</button>';
    } else {
        orderAction = '<button type="button" class="btn btn-sm btn-primary" disabled ' +
            'title="客户确认报价单后才能生成订单">生成订单</button>';
    }
    var addQuoteAction = canAddQuote
        ? '<button type="button" class="btn btn-sm btn-primary" id="headerCreateQuote">' +
          '＋ 添加报价单</button>'
        : '<button type="button" class="btn btn-sm btn-primary" disabled ' +
          'title="已有待客户确认或客户已确认的报价单，或商机已关闭">＋ 添加报价单</button>';
    var loseAction = canLose
        ? '<button type="button" class="btn btn-sm btn-danger" id="dealLose">标记流失</button>'
        : '<button type="button" class="btn btn-sm btn-danger" disabled ' +
          'title="已确认报价或商机已关闭">标记流失</button>';
    return '<section class="deal-overview" id="dealQuotesCard">' +
        '<div class="deal-overview-head">' +
            '<div class="deal-overview-identity">' +
                '<span class="deal-overview-crumb"><a href="#/deals">‹ 商机</a> /</span>' +
                '<a class="deal-overview-name" href="#/customers/' + deal.customer_id + '">' +
                    esc(customerName) + '</a>' +
                dealTagsHtml(deal, quotes) +
            '</div>' +
            '<div class="deal-overview-status"><span>商机状态</span>' +
                dealStageBadge(deal.stage, deal.stage_label) + '</div>' +
        '</div>' +
        quoteCardsHtml(deal, quotes) +
        '<div class="deal-overview-actions">' + addQuoteAction +
            orderAction + loseAction + '</div>' +
    '</section>';
}

function bindQuoteActions(root, deal, customerName, quotes, products) {
    $$('[data-quote-add-item]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            var quote = quotes.filter(function (q) {
                return String(q.id) === btn.getAttribute('data-quote-add-item');
            })[0];
            if (quote) { openQuoteItemModal(deal, quote, null, products, function () { return render(); }); }
        });
    });
    $$('[data-quote-edit-item]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            var itemId = btn.getAttribute('data-quote-edit-item');
            var hit = null;
            (quotes || []).forEach(function (q) {
                (q.items || []).forEach(function (item) {
                    if (String(item.id) === itemId) { hit = { quote: q, item: item }; }
                });
            });
            if (hit) {
                openQuoteItemModal(deal, hit.quote, hit.item, products, function () { return render(); });
            }
        });
    });
    $$('[data-quote-delete-item]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            if (!window.confirm('确认删除这条报价产品及下单表？')) { return; }
            btn.disabled = true;
            api('/quotes/items/' + btn.getAttribute('data-quote-delete-item'), { method: 'DELETE' })
                .then(function () { toast('报价产品已删除'); return render(); })
                .catch(function (err) { toast(err.message, true); btn.disabled = false; });
        });
    });
    $$('[data-quote-confirm]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            var quote = quotes.filter(function (q) {
                return String(q.id) === btn.getAttribute('data-quote-confirm');
            })[0];
            if (quote) { openQuoteConfirmModal(quote, function () { return render(); }); }
        });
    });
    $$('[data-quote-send]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            btn.disabled = true;
            api('/quotes/' + btn.getAttribute('data-quote-send') + '/send', { method: 'POST' })
                .then(function () { toast('报价单已发客户确认'); return render(); })
                .catch(function (err) { toast(err.message, true); btn.disabled = false; });
        });
    });
    $$('[data-quote-requote]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            if (!window.confirm('确认将报价单退回「报价」状态并重新修改？')) { return; }
            btn.disabled = true;
            api('/quotes/' + btn.getAttribute('data-quote-requote') + '/requote', { method: 'POST' })
                .then(function () { toast('报价单已恢复为报价状态，可继续修改'); return render(); })
                .catch(function (err) { toast(err.message, true); btn.disabled = false; });
        });
    });
    $$('[data-quote-void]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            if (!window.confirm('确认作废这张报价单？')) { return; }
            btn.disabled = true;
            api('/quotes/' + btn.getAttribute('data-quote-void') + '/void', { method: 'POST' })
                .then(function () { toast('报价单已作废'); return render(); })
                .catch(function (err) { toast(err.message, true); btn.disabled = false; });
        });
    });
    $$('[data-quote-delete]', root).forEach(function (btn) {
        btn.addEventListener('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            if (!window.confirm('确认删除整张报价单卡片及其所有产品明细？')) { return; }
            btn.disabled = true;
            api('/quotes/' + btn.getAttribute('data-quote-delete'), { method: 'DELETE' })
                .then(function () { toast('报价单已删除'); return render(); })
                .catch(function (err) { toast(err.message, true); btn.disabled = false; });
        });
    });
    $$('[data-quote-order]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            var quote = quotes.filter(function (q) {
                return String(q.id) === btn.getAttribute('data-quote-order');
            })[0];
            if (quote) { openDealOrderModal(deal, customerName, quote.items || [], quote); }
        });
    });
}

function bindDealTagActions(root, deal) {
    $$('[data-deal-tag-add]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            openDealTagModal(deal, function () { return render(); });
        });
    });
    $$('[data-deal-tag-remove]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
            btn.disabled = true;
            api('/deals/' + deal.id + '/tags/' + btn.getAttribute('data-deal-tag-remove'), {
                method: 'DELETE'
            }).then(function () {
                toast('标签已删除');
                return render();
            }).catch(function (err) {
                toast(err.message, true);
                btn.disabled = false;
            });
        });
    });
}

function openDealTagModal(deal, done) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = '<div class="modal-overlay"></div><div class="modal-content">' +
        '<div class="modal-header"><h3>添加商机标签</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body"><form class="form-grid deal-tag-form">' +
        '<div class="field"><label>标签名称 *</label>' +
        '<input name="name" maxlength="32" required autofocus placeholder="例如：重点跟进、别墅项目"></div>' +
        '<p class="small muted">手动添加的标签可删除；系统自动生成的标签不可删除。</p>' +
        '<div class="form-actions"><button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">添加标签</button></div></form></div></div>';
    document.body.appendChild(modal);
    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);
    var form = modal.querySelector('form');
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var name = String(form.querySelector('[name="name"]').value || '').trim();
        if (!name) { toast('请输入标签名称', true); return; }
        var btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        api('/deals/' + deal.id + '/tags', {
            method: 'POST',
            body: { name: name }
        }).then(function () {
            toast('标签已添加');
            close();
            if (done) { done(); }
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}

function openCreateQuoteModal(deal, done) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = '<div class="modal-overlay"></div><div class="modal-content">' +
        '<div class="modal-header"><h3>创建报价单</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body"><form id="quoteCreateForm" class="form-grid">' +
        '<div class="field"><label>报价单名称 *</label><input name="title" maxlength="120" required ' +
        'placeholder="例如：客厅天窗方案 A"></div>' +
        '<div class="field"><label>报价备注</label><textarea name="note" maxlength="1000"></textarea></div>' +
        '<p class="small muted">创建后逐项添加产品和对应下单表。同一商机只能有一张客户确认的报价单。</p>' +
        '<div class="form-actions"><button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">创建报价单</button></div></form></div></div>';
    document.body.appendChild(modal);
    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);
    var form = modal.querySelector('form');
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var title = String(form.querySelector('[name="title"]').value || '').trim();
        if (!title) { toast('请填写报价单名称', true); return; }
        btn.disabled = true;
        api('/deals/' + deal.id + '/quotes', {
            method: 'POST',
            body: {
                title: title,
                note: String(form.querySelector('[name="note"]').value || '').trim() || null
            }
        }).then(function () {
            toast('报价单已创建');
            close();
            if (done) { done(); }
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}

function openQuoteItemModal(deal, quote, item, products, done) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = '<div class="modal-overlay"></div><div class="modal-content wide">' +
        '<div class="modal-header"><h3>' + (item ? '编辑报价产品' : '添加报价产品') + '</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body"><form id="quoteItemForm" class="form-grid">' +
        '<div class="field field-wide"><label>关联产品 *</label>' +
        productPickerHtml(products || [], item && item.product_id, '搜索并选择产品') +
        '<div class="small" style="margin-top:8px" id="quoteTemplateHint">选择产品后上传对应的 Excel 下单表。</div></div>' +
        '<div class="field"><label>对应下单表 * ' + (item && item.form_file_name
            ? '（当前：' + esc(item.form_file_name) + '，不选则保留）' : '') + '</label>' +
        '<input type="file" name="form_file" accept=".xlsx" ' + (item ? '' : 'required') + '></div>' +
        '<div class="field"><label>报价金额 *</label>' +
        '<input name="amount" type="number" min="0.01" step="0.01" inputmode="decimal" ' +
        'placeholder="上传下单表后自动识别，可修改" value="' +
        (item && item.amount ? Number(item.amount).toFixed(2) : '') + '"></div>' +
        '<div class="field"><label>备注</label><textarea name="note" maxlength="500" ' +
        'placeholder="记录这版报价的沟通要点">' + esc(item && item.note || '') + '</textarea></div>' +
        '<div class="card" id="quoteFormPreview" style="margin:0;display:none">' +
        '<div class="card-head"><h3>下单表识别结果</h3>' +
        '<span class="small muted" id="quoteFormPreviewStatus"></span></div>' +
        '<div id="quoteFormPreviewBody"></div></div>' +
        '<p class="small muted">只读取 Sheet1。保存前会用 A1 校验下单表是否属于当前产品，' +
        '自动识别合计金额，并把数据区域生成图片保存。单个文件不超过 20MB。</p>' +
        '<div class="form-actions"><button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary"' + (item ? '' : ' disabled') +
        '>保存产品</button></div></form></div></div>';
    document.body.appendChild(modal);
    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);
    var form = modal.querySelector('form');
    var submitBtn = form.querySelector('button[type="submit"]');
    var fileInput = form.querySelector('[name="form_file"]');
    var amountInput = form.querySelector('[name="amount"]');
    var previewBox = form.querySelector('#quoteFormPreview');
    var previewBody = form.querySelector('#quoteFormPreviewBody');
    var previewStatus = form.querySelector('#quoteFormPreviewStatus');
    var previewState = item && item.form_preview_url ? {
        preview_token: item.form_sha256,
        image_url: item.form_preview_url,
        recognized_total: item.recognized_total,
        a1_value: item.a1_value
    } : null;

    function resetPreview() {
        previewState = null;
        previewBox.style.display = 'none';
        previewBody.innerHTML = '';
        if (!item) { amountInput.value = ''; }
        submitBtn.disabled = true;
    }

    function renderPreview(data) {
        previewState = data;
        amountInput.value = Number(data.recognized_total || 0).toFixed(2);
        previewStatus.textContent = 'A1 校验通过 · ' + (data.a1_value || '');
        previewBody.innerHTML = '<div class="small muted" style="margin-bottom:8px">' +
            'A1：' + esc(data.a1_value || '—') + ' · 合计金额已填入上方，可手动修改</div>' +
            '<div style="overflow:auto;padding:8px;background:#fff">' +
            '<img src="/crm' + esc(data.image_url) + '" alt="下单表数据区域" ' +
            'style="max-width:none;width:auto;min-width:min(100%,720px);display:block"></div>';
        previewBox.style.display = '';
        submitBtn.disabled = false;
    }

    if (previewState) { renderPreview(previewState); }

    var picker = bindProductPicker(form.querySelector('[data-product-picker]'), products || [], {
        onChange: function (product) {
            var hint = form.querySelector('#quoteTemplateHint');
            if (!product) {
                hint.textContent = '选择产品后上传对应的 Excel 下单表。';
                resetPreview();
                return;
            }
            hint.innerHTML = '产品：' +
                esc([product.code, product.name].filter(Boolean).join(' · '));
            if (!item || String(product.id) !== String(item.product_id)) {
                resetPreview();
            }
        }
    });

    fileInput.addEventListener('change', function () {
        var file = fileInput.files[0];
        if (!file) { resetPreview(); return; }
        var productId = picker.getValue();
        if (!productId) { toast('请先选择关联产品', true); fileInput.value = ''; return; }
        var fd = new FormData();
        fd.append('product_id', productId);
        fd.append('form_file', file);
        submitBtn.disabled = true;
        previewBox.style.display = '';
        previewStatus.textContent = '正在识别 Sheet1…';
        previewBody.innerHTML = '<p class="empty">正在校验 A1、识别合计金额并生成图片…</p>';
        api('/quotes/form-preview', { method: 'POST', body: fd }).then(function (data) {
            renderPreview(data);
        }).catch(function (err) {
            resetPreview();
            previewBox.style.display = '';
            previewStatus.textContent = '识别失败';
            previewBody.innerHTML = '<p class="err">' + esc(err.message || '下单表识别失败') + '</p>';
            toast(err.message || '下单表识别失败', true);
        });
    });

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        if (!picker.getValue()) { toast('请选择关联产品', true); return; }
        var file = fileInput.files[0];
        if (!item && !file) { toast('请上传与产品对应的下单表', true); return; }
        if (file && !previewState) { toast('请等待下单表识别完成', true); return; }
        var quotedAmount = numOrNull(amountInput.value);
        if (quotedAmount === null || quotedAmount <= 0) {
            toast('报价金额必须大于 0', true);
            return;
        }
        var fd = new FormData();
        fd.append('product_id', picker.getValue());
        fd.append('amount', String(quotedAmount));
        fd.append('note', String(form.querySelector('[name="note"]').value || '').trim());
        if (file) {
            fd.append('form_file', file);
            fd.append('preview_token', previewState.preview_token);
        }
        submitBtn.disabled = true;
        api(item ? '/quotes/items/' + item.id : '/quotes/' + quote.id + '/items', {
            method: item ? 'PUT' : 'POST',
            body: fd
        }).then(function () {
            toast(item ? '报价产品已更新' : '产品与下单表已添加');
            close();
            if (done) { done(); }
        }).catch(function (err) {
            toast(err.message, true);
            submitBtn.disabled = false;
        });
    });
}

function openQuoteConfirmModal(quote, done) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = '<div class="modal-overlay"></div><div class="modal-content">' +
        '<div class="modal-header"><h3>客户确认报价单</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body"><form id="quoteConfirmForm" class="form-grid">' +
        '<p class="small muted">' + esc(quote.quote_no) + ' · ' + money(quote.amount) +
        '<br>确认后该报价单锁定，并成为本商机唯一可用于生成订单的报价单。</p>' +
        '<div class="field"><label>确认说明</label><textarea name="note" maxlength="500" rows="3"></textarea></div>' +
        '<div class="field"><label>微信确认截图（最多 3 张）</label>' +
        '<input type="file" name="screenshots" accept="image/*" multiple></div>' +
        '<div class="form-actions"><button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">客户已确认</button></div></form></div></div>';
    document.body.appendChild(modal);
    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);
    var form = modal.querySelector('form');
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        if (!window.confirm('确认客户已经同意这张报价单？确认后本商机不能再创建新的确认报价单。')) {
            return;
        }
        var fd = new FormData();
        fd.append('note', String(form.querySelector('[name="note"]').value || '').trim());
        var files = form.querySelector('[name="screenshots"]').files;
        for (var i = 0; i < files.length && i < 3; i++) { fd.append('screenshots', files[i]); }
        var btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        api('/quotes/' + quote.id + '/confirm', { method: 'POST', body: fd }).then(function () {
            toast('客户已确认报价单');
            close();
            if (done) { done(); }
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
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
                '<td>' + esc(d.product_name_snapshot || d.product_type ||
                    (d.quote_count ? d.quote_count + ' 张报价单' : '—')) + '</td>' +
                '<td>' + esc(d.product_code_snapshot || d.model || '—') + '</td>' +
                '<td>' + driveBadge(d) + '</td>' +
                '<td>' + esc(d.spec || '—') + '</td>' +
                '<td style="text-align:right;white-space:nowrap">' +
                (Number(d.amount || 0) > 0 ? money(d.amount) : '—') + '</td>' +
                '<td>' + dealStageBadge(d.stage, d.stage_label) + '</td>' +
                '<td style="white-space:nowrap">' + fmtDateTime(d.updated_at || d.created_at).slice(0, 10) + '</td>' +
                '<td style="white-space:nowrap"><a class="btn btn-sm" href="#/deals/' + d.id + '">跟进</a></td>' +
                '</tr>';
        }).join('') : '<tr><td colspan="9" class="empty">还没有商机：请进入线索或客户跟进页转商机</td></tr>';

        root.innerHTML =
            '<div class="card">' +
            '<div class="card-head"><h2>商机 <span class="badge muted">' + deals.length + '</span></h2>' +
            '<span class="small muted">由线索 / 客户转来，不在此新建</span></div>' +
            '<div class="tabs" id="dealTabs">' + tabHtml + '</div>' +
            '</div>' +
            '<div class="card"><div class="table-wrap"><table><thead><tr>' +
            '<th>客户</th><th>产品</th><th>型号</th><th>手动/电动</th><th>尺寸</th>' +
            '<th style="text-align:right">成交报价</th><th>阶段</th><th>更新时间</th><th>操作</th>' +
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
        loadProductCatalog(),
        api('/deals/' + id + '/quotes'),
        api('/follow-ups?object_type=deal&object_id=' + id + '&include_system=true')
            .catch(function () { return []; })
    ]).then(function (all) {
        var d = all[0];
        var index = all[1] || {};
        var products = all[2] || [];
        var quotes = all[3] || [];
        var records = all[4] || [];
        d.quote_count = quotes.length;
        d.confirmed_quote_no = (quotes.filter(function (q) {
            return q.status === 'confirmed';
        })[0] || {}).quote_no || null;

        if (!d) {
            root.innerHTML = '<div class="card">商机不存在，<a href="#/deals">回商机列表</a></div>';
            return;
        }

        var customerName = index[d.customer_id] || ('客户 #' + d.customer_id);
        var timelineRecords = followupRecordsFromApi(records);
        var canFollow = !d.order_id && d.stage !== 'lost';
        var canEditItems = !d.order_id && d.stage !== 'lost';
        var items = d.items || [];

        renderEntityFollowPage(root, {
            backHash: '#/deals',
            backLabel: '商机',
            title: customerName,
            hideEntityCard: true,
            placeholder: '这次沟通聊了什么？客户对报价和参数是什么态度？下一步做什么？',
            canFollow: canFollow,
            lockedText: d.order_id
                ? '商机已生成订单，请到订单中继续处理'
                : (d.stage === 'lost' ? '已作废的商机不能再添加跟进' : '已转订单的商机请到订单中继续跟进'),
            records: timelineRecords,
            followExtraHtml:
                '<div class="field"><label>关联报价单</label><select name="quote_id"' +
                (quotes.length ? '' : ' disabled') + '>' +
                (quotes.length ? '<option value="">不关联报价单</option>' :
                    '<option value="">暂无报价单</option>') +
                quotes.map(function (quote) {
                    return '<option value="' + quote.id + '">' + esc(quote.quote_no) +
                        ' · ' + esc(quote.status_label || quote.status) + '</option>';
                }).join('') + '</select></div>',
            beforeTimelineHtml: dealOverviewHtml(d, customerName, quotes) +
                ((!quotes.length && items.length)
                    ? dealItemsCardHtml(items, false, d.amount) : ''),
            extraHtml:
                filesCardHtml(collectFiles(timelineRecords), '这个商机还没有上传图纸 / 报价单 / 现场照片'),
            onSubmit: function (p) {
                var fd = new FormData();
                fd.append('object_type', 'deal');
                fd.append('object_id', String(d.id));
                fd.append('content', p.content);
                fd.append('method', p.method || 'wechat');
                if (p.next_date) { fd.append('next_date', p.next_date); }
                if (p.quote_id) { fd.append('quote_id', String(p.quote_id)); }
                (p.files || []).forEach(function (f) { if (f.file) { fd.append('files', f.file); } });
                api('/follow-ups', { method: 'POST', body: fd }).then(function () {
                    toast('已记录跟进');
                    return render();
                }).catch(function (err) { toast(err.message, true); });
            }
        });

        var headerCreateQuote = $('#headerCreateQuote', root);
        if (headerCreateQuote) {
            headerCreateQuote.addEventListener('click', function () {
                openCreateQuoteModal(d, function () { return render(); });
            });
        }

        bindQuoteActions(root, d, customerName, quotes, products);
        bindDealTagActions(root, d);

        var addItemBtn = $('#btnAddDealItem', root);
        if (addItemBtn) {
            addItemBtn.addEventListener('click', function () {
                openDealItemModal(d, null, products, function () { return render(); });
            });
        }
        $$('[data-edit-item]', root).forEach(function (btn) {
            btn.addEventListener('click', function () {
                var itemId = Number(btn.getAttribute('data-edit-item'));
                var item = items.filter(function (row) { return Number(row.id) === itemId; })[0];
                if (item) {
                    openDealItemModal(d, item, products, function () { return render(); });
                }
            });
        });
        $$('[data-delete-item]', root).forEach(function (btn) {
            btn.addEventListener('click', function () {
                var itemId = Number(btn.getAttribute('data-delete-item'));
                if (!window.confirm('确认删除这条产品明细？')) { return; }
                btn.disabled = true;
                api('/deals/' + d.id + '/items/' + itemId, { method: 'DELETE' }).then(function () {
                    toast('产品明细已删除');
                    return render();
                }).catch(function (err) {
                    toast(err.message, true);
                    btn.disabled = false;
                });
            });
        });

        var loseBtn = $('#dealLose', root);
        if (loseBtn) {
            loseBtn.addEventListener('click', function () {
                openDealLose(d, function () { return render(); });
            });
        }
    });
}

/* ---------------- 产品明细：一张商机可包含多个产品，同产品不同参数拆行 ---------------- */
function openDealItemModal(deal, item, products, done) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content wide">' +
        '<div class="modal-header"><h3>' + (item ? '编辑产品明细' : '添加产品') + '</h3>' +
        '<button type="button" class="btn btn-link modal-close" aria-label="关闭">×</button></div>' +
        '<div class="modal-body"><form id="dealItemForm" class="form-grid" autocomplete="off">' +
        '<div class="field field-wide"><label>产品 *</label>' +
        productPickerHtml(products || [], item && item.product_id, '搜索并选择产品') +
        '<div class="small muted" data-product-hint>' +
        esc(item && item.product_config_snapshot || '选择产品后带出编码、类型和生产配置') +
        '</div></div>' +
        '<div class="row-3">' +
        '<div class="field"><label>数量 *</label><input name="quantity" type="number" ' +
        'min="1" max="999" step="1" inputmode="numeric" required value="' +
        Number(item && item.quantity || 1) + '"></div>' +
        '<div class="field"><label>单价 *</label><input name="unit_price" type="number" ' +
        'min="0" step="0.01" inputmode="decimal" required value="' +
        Number(item && item.unit_price || 0) + '"></div>' +
        '<div class="field"><label>明细金额</label><input name="amount" disabled value="0.00"></div>' +
        '</div>' +
        '<div class="row-2">' +
        '<div class="field"><label>洞口尺寸</label><input name="spec" maxlength="200" ' +
        'placeholder="如 1200*2400" value="' + esc(item && item.spec || '') + '"></div>' +
        '<div class="field"><label>生产参数</label><input name="production_spec" maxlength="1000" ' +
        'placeholder="框/扇/玻璃制作尺寸或公式结果" value="' +
        esc(item && item.production_spec || '') + '"></div>' +
        '</div>' +
        '<div class="field"><label>明细备注</label><textarea name="note" maxlength="500">' +
        esc(item && item.note || '') + '</textarea></div>' +
        '<p class="small muted" style="margin-top:0">同一产品且尺寸、配置相同请改数量；' +
        '尺寸或生产参数不同请另加一条明细。</p>' +
        '<div class="form-actions"><button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">保存明细</button></div>' +
        '</form></div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);

    var form = modal.querySelector('form');
    var picker = bindProductPicker(form.querySelector('[data-product-picker]'), products || [], {
        onChange: function (product) {
            var hint = form.querySelector('[data-product-hint]');
            if (hint) {
                hint.textContent = product
                    ? [product.code, product.name, product.config_summary].filter(Boolean).join(' · ')
                    : '搜索并选择产品';
            }
        }
    });
    var qtyEl = form.querySelector('[name="quantity"]');
    var priceEl = form.querySelector('[name="unit_price"]');
    var amountEl = form.querySelector('[name="amount"]');

    function refreshAmount() {
        var qty = Number(qtyEl.value) || 0;
        var price = Number(priceEl.value) || 0;
        amountEl.value = (Math.round(qty * price * 100) / 100).toFixed(2);
    }
    qtyEl.addEventListener('input', refreshAmount);
    priceEl.addEventListener('input', refreshAmount);
    refreshAmount();

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        if (!picker.getValue()) { toast('请选择产品', true); return; }
        var quantity = Number(qtyEl.value);
        var unitPrice = Number(priceEl.value);
        if (!Number.isInteger(quantity) || quantity < 1) {
            toast('数量必须是大于 0 的整数', true);
            return;
        }
        if (isNaN(unitPrice) || unitPrice < 0) {
            toast('单价不能为负', true);
            return;
        }
        var payload = {
            product_id: Number(picker.getValue()),
            quantity: quantity,
            unit_price: unitPrice,
            spec: String(form.querySelector('[name="spec"]').value || '').trim() || null,
            production_spec: String(form.querySelector('[name="production_spec"]').value || '').trim() || null,
            note: String(form.querySelector('[name="note"]').value || '').trim() || null
        };
        var btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        var path = '/deals/' + deal.id + '/items' + (item ? '/' + item.id : '');
        api(path, { method: item ? 'PUT' : 'POST', body: payload }).then(function () {
            toast(item ? '产品明细已保存' : '产品已添加');
            close();
            if (done) { done(); }
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}

/* ---------------- 旧版单产品编辑（仅保留兼容，不再从商机详情入口打开） ---------------- */
function openDealEdit(deal, products, done) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content wide deal-edit-modal">' +
        '<div class="modal-header deal-convert-modal-head">' +
        '<div><span class="deal-convert-kicker">商机跟进 · 参数调整</span>' +
        '<h3>编辑商机</h3><p>客户需求变化时，可直接搜索并更换关联产品</p></div>' +
        '<button type="button" class="btn btn-link modal-close" aria-label="关闭">×</button></div>' +
        '<div class="modal-body">' +
        '<form id="dealEditForm" class="form-grid" autocomplete="off">' +
        '<div class="field field-wide"><label>关联产品 <span class="deal-inline-badge">可更换</span></label>' +
        '<div class="deal-product-switch-note">' +
        '<b>产品可随沟通阶段调整</b>' +
        '<span>直接搜索新的产品；保存后会记录变更，并将后续商机与订单切换到新产品快照。</span></div>' +
        productPickerHtml(products || [], deal.product_id, '不关联产品（旧商机）') +
        '<div class="small muted" data-product-hint>' +
        esc(deal.product_config_snapshot || '选择产品后会自动带出类型、型号和驱动方式') + '</div></div>' +
        '<div class="row-2">' +
        '<div class="field"><label>产品类型 <span class="deal-inline-badge">自动</span></label>' +
        '<select name="product_type">' + dictOptions('product_type', deal.product_type, '不指定') + '</select></div>' +
        '<div class="field"><label>型号 <span class="deal-inline-badge">自动</span></label>' +
        modelComboHtml(deal.model || '') + '</div>' +
        '</div>' +
        '<div class="row-2">' +
        '<div class="field deal-product-sync-field"><label>手动 / 电动 ' +
        '<span class="deal-inline-badge">随产品</span></label>' +
        '<select name="drive_type">' +
        '<option value=""' + (deal.drive_type ? '' : ' selected') + '>不指定</option>' +
        '<option value="manual"' + (deal.drive_type === 'manual' ? ' selected' : '') + '>手动</option>' +
        '<option value="electric"' + (deal.drive_type === 'electric' ? ' selected' : '') + '>电动</option>' +
        '</select>' +
        '<div class="small muted deal-field-tip" data-drive-hint>' +
        '关联产品后，驱动方式会与产品参数保持一致</div></div>' +
        '<div class="field"><label>尺寸/洞口尺寸</label>' +
        '<input name="spec" maxlength="200" placeholder="如 1200*2400" value="' + esc(deal.spec || '') + '"></div>' +
        '</div>' +
        '<div class="row-2">' +
        '<div class="field"><label>报价金额 *</label>' +
        '<input name="amount" type="number" min="0" step="0.01" inputmode="decimal" required value="' + (deal.amount || 0) + '"></div>' +
        '<div class="field"><label>阶段</label>' +
        '<select name="stage">' + stageOptions(deal.stage) + '</select></div>' +
        '</div>' +
        '<div class="form-actions">' +
        '<button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">保存修改</button>' +
        '</div>' +
        '</form>' +
        '</div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);

    var form = modal.querySelector('form');
    var productTypeSelect = form.querySelector('[name="product_type"]');
    var modelInput = form.querySelector('[data-model-combo] .combo-input');
    var driveSelect = form.querySelector('[name="drive_type"]');
    var driveHint = form.querySelector('[data-drive-hint]');

    var modelCombo = bindModelCombo(form.querySelector('[data-model-combo]'), dictItems('product_model'), function (hit) {
        if (hit && hit.meta) {
            if (hit.meta.drive) { form.querySelector('[name="drive_type"]').value = hit.meta.drive; }
            if (hit.meta.product) { form.querySelector('[name="product_type"]').value = hit.meta.product; }
        }
    });

    function syncProductFields(product) {
        var linked = !!product;
        productTypeSelect.disabled = linked;
        if (modelInput) { modelInput.disabled = linked; modelInput.title = linked ? '型号随关联产品自动同步' : ''; }
        syncProductDriveField(product, driveSelect, driveHint);
    }

    var productPicker = bindProductPicker(form.querySelector('[data-product-picker]'), products, {
        onChange: function (product) {
            var hint = form.querySelector('[data-product-hint]');
            syncProductFields(product);
            if (!product) {
                if (hint) { hint.textContent = '已取消主档关联，保留当前产品字段；可继续手工编辑。'; }
                return;
            }
            productTypeSelect.value = product.category || '';
            modelCombo.set(product.code);
            if (hint) {
                hint.textContent = product.config_summary ||
                    [product.series, product.structure].filter(Boolean).join(' · ');
            }
        }
    });
    syncProductFields(productPicker.getProduct());

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var amount = numOrNull(form.querySelector('[name="amount"]').value);
        if (amount === null || !(amount > 0)) { toast('报价金额必须大于 0', true); return; }

        function val(name) {
            var el = form.querySelector('[name="' + name + '"]');
            return el ? String(el.value || '').trim() : '';
        }
        var payload = {
            product_type: val('product_type') || null,
            model: val('model') || null,
            drive_type: (productPicker.getProduct() && productPicker.getProduct().drive_type) ||
                val('drive_type') || null,
            spec: val('spec') || null,
            amount: amount,
            stage: val('stage'),
        };
        if (String(deal.product_id || '') !== String(productPicker.getValue() || '')) {
            payload.product_id = productPicker.getValue() ? Number(productPicker.getValue()) : null;
        }
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
        '<form id="dealLoseForm" class="form-grid" autocomplete="off">' +
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
        root.innerHTML = '<div class="card">缺少来源：请进入「线索」或「客户」跟进页转商机，' +
            '<a href="#/leads">回线索池</a> · <a href="#/customers">回客户档案</a></div>';
        return Promise.resolve();
    }

    var load = leadId ? api('/leads/' + leadId) : api('/customers/' + custId);
    return load.then(function (src) {
        var fromName = leadId
            ? (src.name || src.company_name || '线索 #' + leadId)
            : (src.name || '客户 #' + custId);
        var backHash = leadId ? '#/leads' : '#/customers';
        var backLabel = leadId ? '线索池' : '客户档案';

        root.innerHTML =
            '<div class="card deal-convert-page">' +
            '<div class="deal-convert-page-head">' +
              '<div><a class="crumb" href="' + backHash + '">‹ ' + backLabel + '</a>' +
              '<span class="deal-convert-kicker">销售流程 · 新建商机</span>' +
              '<h2>转商机</h2><p>确认后创建商机，产品与报价在商机内维护</p></div>' +
            '</div>' +
            '<div class="deal-convert-page-body">' +
              dealConvertFormHtml('dealNewForm', [], fromName,
                leadId ? 'lead' : 'customer') +
            '</div>' +
            '</div>';

        var form = $('#dealNewForm', root);
        form.querySelector('.modal-cancel').addEventListener('click', function () {
            navigate(backHash);
        });
        bindDealConvertForm(form, [], function (deal) {
            var req = leadId
                ? api('/leads/' + leadId + '/convert', { method: 'POST', body: { mode: 'new', deal: deal } })
                : api('/deals', {
                    method: 'POST',
                    body: {
                        customer_id: custId,
                        note: null
                    }
                });
            return req.then(function (res) {
                var created = leadId ? (res && res.deal) : res;
                toast('商机已创建');
                invalidateCustomerIndex();
                if (created && created.id) {
                    navigate('#/deals/' + created.id);
                } else {
                    navigate('#/deals');
                }
                return res;
            });
        });
    }).catch(function (err) {
        root.innerHTML = '<div class="card"><p class="err">加载来源失败：' + esc(err.message) + '</p></div>';
    });
}

/* ---------------- 生成订单（成交 → 建订单；收款就是定金 + 尾款两笔） ----------------
 * 定稿口径：订单总额固定取商机报价；定金由业务填，尾款 = 报价金额 - 定金；
 *          自提不需要收货信息，包邮/代办必须选物流公司 + 填全收货人。
 * 走 POST /deals/{id}/orders（正路），不再用 /win（那是定金=全额的兼容端点）。
 */
function openDealOrderModal(deal, customerName, items, quote) {
    var productTotal = (items || []).reduce(function (sum, item) {
        return sum + (Number(item.amount) || 0);
    }, 0);
    var quoteTitle = quote && (quote.title || quote.quote_no) || '客户已确认报价单';
    var quotePreviewHtml = (items || []).map(function (item) {
        var productName = dealItemName(item);
        var previewUrl = item.form_preview_url ? '/crm' + item.form_preview_url : '';
        return '<article class="order-quote-card">' +
            (previewUrl
                ? '<button type="button" class="order-quote-preview" ' +
                  'data-img="' + esc(previewUrl) + '" ' +
                  'data-name="' + esc(productName + ' · 报价单下单表') + '" ' +
                  'title="点击查看报价单大图">' +
                  '<img src="' + esc(previewUrl) + '" alt="' +
                  esc(productName + ' 报价单缩略图') + '" loading="lazy">' +
                  '<span class="order-quote-zoom">查看大图</span></button>'
                : '<div class="order-quote-preview is-empty">' +
                  '<span>报价单缩略图暂不可用</span></div>') +
            '<div class="order-quote-card-copy">' +
                '<div class="order-quote-card-title">' + esc(productName) + '</div>' +
                '<div class="order-quote-card-meta"><span>数量 ' +
                    esc(item.quantity || 1) + '</span><strong>' + money(item.amount) +
                    '</strong></div>' +
            '</div>' +
        '</article>';
    }).join('');

    var modal = document.createElement('div');
    modal.className = 'modal deal-order-modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content deal-order-content wide">' +
        '<div class="modal-header deal-order-header">' +
        '<div class="order-modal-heading"><span class="order-modal-kicker">报价单转订单</span>' +
        '<h3>生成订单</h3><p>' + esc(customerName) + ' · ' + esc(quoteTitle) + '</p></div>' +
        '<button type="button" class="btn btn-link modal-close" aria-label="关闭生成订单弹层">×</button></div>' +
        '<div class="modal-body">' +
        '<form id="dealOrderForm" class="order-form" autocomplete="off">' +
        '<section class="order-quote-summary">' +
        '<div class="order-quote-summary-head">' +
            '<div><span class="order-section-eyebrow">客户已确认报价单</span>' +
            '<h4>' + esc(quoteTitle) + '</h4>' +
            '<p>' + esc(quote && quote.quote_no || '') + ' · 共 ' +
                (items || []).length + ' 项产品</p></div>' +
            '<span class="order-confirmed-badge"><span aria-hidden="true">✓</span> 已确认</span>' +
        '</div>' +
        '<div class="order-quote-gallery">' +
            (quotePreviewHtml || '<p class="order-quote-empty">报价单没有可展示的下单表</p>') +
        '</div>' +
        '<div class="order-quote-total"><span>报价产品合计</span>' +
            '<strong>' + money(productTotal) + '</strong></div>' +
        '</section>' +
        '<section class="order-form-section">' +
        '<div class="order-section-heading"><span>01</span><div>' +
            '<h4>金额与定金</h4><p>优惠只作用于产品金额，运费单独计入订单应收。</p></div></div>' +
        '<div class="order-money-grid">' +
        '<div class="field"><label>产品合计</label>' +
        '<div class="order-money-control"><span>¥</span>' +
        '<input class="order-money-input" name="product_total" type="number" ' +
        'value="' + productTotal + '" readonly tabindex="-1"></div></div>' +
        '<div class="field"><label>整单优惠</label>' +
        '<div class="order-money-control"><span>¥</span>' +
        '<input class="order-money-input is-editable" name="discount_amount" type="number" ' +
        'min="0" step="0.01" inputmode="decimal" value="0"></div></div>' +
        '<div class="field"><label>优惠后产品应收</label>' +
        '<div class="order-money-control"><span>¥</span>' +
        '<input class="order-money-input" name="product_payable" type="number" ' +
        'readonly tabindex="-1"></div></div>' +
        '<div class="field"><label>运费（我方收取）</label>' +
        '<div class="order-money-control"><span>¥</span>' +
        '<input class="order-money-input is-editable" name="logistics_fee" type="number" ' +
        'min="0" step="0.01" inputmode="decimal" value="0"></div></div>' +
        '<div class="field order-receivable-field"><label>订单应收</label>' +
        '<div class="order-money-control is-total"><span>¥</span>' +
        '<input class="order-money-input" name="amount" type="number" readonly tabindex="-1"></div></div>' +
        '</div>' +
        '<div class="order-payment-grid">' +
        '<div class="field"><label>定金（第一笔）*</label>' +
        '<div class="order-money-control"><span>¥</span>' +
        '<input class="order-money-input is-editable" name="deposit" type="number" ' +
        'min="0" step="0.01" inputmode="decimal" required placeholder="按协商填定金"></div></div>' +
        '<div class="field"><label>尾款（自动计算）</label>' +
        '<div class="order-money-control"><span>¥</span>' +
        '<input class="order-money-input" name="balance" type="number" disabled></div></div>' +
        '</div>' +
        '<div class="field order-field-wide"><label>优惠说明（优惠大于 0 时填写）</label>' +
        '<input name="discount_reason" maxlength="200" placeholder="微信协商的优惠原因"></div>' +
        '</section>' +
        '<section class="order-form-section">' +
        '<div class="order-section-heading"><span>02</span><div>' +
            '<h4>物流与收货</h4><p>包邮或代办需要选择物流公司并填写完整收货信息。</p></div></div>' +
        '<div class="order-shipping-grid">' +
        '<div class="field"><label>物流方式</label>' +
        '<select name="logistics_mode">' +
        '<option value="self">自提（不填收货信息）</option>' +
        '<option value="free">包邮</option>' +
        '<option value="agent">代办</option>' +
        '</select></div>' +
        '<div class="field" data-ship hidden><label>物流公司 *</label>' +
        '<select name="carrier_id"><option value="">请选择</option></select></div>' +
        '<div class="field order-field-wide" data-ship hidden><label>物流公司联络人 *</label>' +
        '<select name="carrier_contact_id"><option value="">请先选择物流公司</option></select></div>' +
        '</div>' +
        '<div class="order-address-grid" data-ship hidden>' +
        '<div class="field"><label>收货人 *</label><input name="receiver_name" maxlength="32"></div>' +
        '<div class="field"><label>收货电话 *</label><input name="receiver_phone" maxlength="32" inputmode="tel"></div>' +
        '<div class="field order-field-wide"><label>收货地址 *</label><input name="receiver_address" maxlength="200"></div>' +
        '</div>' +
        '</section>' +
        '<section class="order-form-section order-note-section">' +
        '<div class="order-section-heading"><span>03</span><div>' +
            '<h4>订单备注</h4><p>可补充交付、安装或客户特别要求。</p></div></div>' +
        '<div class="field order-field-wide"><label>备注</label>' +
        '<textarea name="note" maxlength="500" placeholder="填写订单补充说明（选填）"></textarea></div>' +
        '</section>' +
        '<p class="order-source-note">优惠只减产品合计，运费单独计入订单应收，不混入产品金额。' +
        '产品、价格和下单表均来自客户已确认的报价单；生成后直接进入待支付。</p>' +
        '<div class="form-actions order-form-actions">' +
        '<button type="button" class="btn modal-cancel">取消</button>' +
        '<button type="submit" class="btn btn-primary">确认生成订单</button>' +
        '</div>' +
        '</form>' +
        '</div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);

    var form = modal.querySelector('form');
    var discountEl = form.querySelector('[name="discount_amount"]');
    var feeEl = form.querySelector('[name="logistics_fee"]');
    var productPayableEl = form.querySelector('[name="product_payable"]');
    var amountEl = form.querySelector('[name="amount"]');
    var depositEl = form.querySelector('[name="deposit"]');
    var balanceEl = form.querySelector('[name="balance"]');
    var modeEl = form.querySelector('[name="logistics_mode"]');
    var carrierEl = form.querySelector('[name="carrier_id"]');
    var carrierContactEl = form.querySelector('[name="carrier_contact_id"]');
    var shipFields = $$('[data-ship]', modal);

    $$('.order-money-input.is-editable', modal).forEach(function (input) {
        input.addEventListener('wheel', function (ev) {
            ev.preventDefault();
            input.blur();
        }, { passive: false });
        input.addEventListener('keydown', function (ev) {
            if (ev.key === 'ArrowUp' || ev.key === 'ArrowDown') {
                ev.preventDefault();
            }
        });
    });

    function refreshMoney() {
        var discount = Number(discountEl.value) || 0;
        var fee = modeEl.value === 'self' ? 0 : (Number(feeEl.value) || 0);
        var payable = Math.max(0, productTotal - discount);
        var receivable = payable + fee;
        productPayableEl.value = (Math.round(payable * 100) / 100).toFixed(2);
        amountEl.value = (Math.round(receivable * 100) / 100).toFixed(2);
        var dep = Number(depositEl.value) || 0;
        balanceEl.value = (Math.round((receivable - dep) * 100) / 100).toFixed(2);
    }

    function refreshShip() {
        var need = modeEl.value !== 'self';
        shipFields.forEach(function (el) { el.hidden = !need; });
        feeEl.disabled = !need;
        if (!need) { feeEl.value = '0'; }
        refreshMoney();
    }
    modeEl.addEventListener('change', refreshShip);
    discountEl.addEventListener('input', refreshMoney);
    feeEl.addEventListener('input', refreshMoney);
    depositEl.addEventListener('input', refreshMoney);
    refreshShip();
    refreshMoney();

    /* 物流公司：只列启用的；联络人随物流公司联动 */
    var carrierList = [];
    function refreshCarrierContacts() {
        var carrier = carrierList.filter(function (item) {
            return String(item.id) === String(carrierEl.value || '');
        })[0];
        var contacts = (carrier && carrier.contacts) || [];
        carrierContactEl.innerHTML = contacts.length
            ? '<option value="">请选择联络人</option>' + contacts.map(function (contact) {
                return '<option value="' + contact.id + '">' + esc(contact.name) +
                    (contact.phone ? ' · ' + esc(contact.phone) : '') + '</option>';
            }).join('')
            : '<option value="">' +
              esc(carrier ? '该物流公司尚未设置联络人，请先到物流页维护' : '请先选择物流公司') +
              '</option>';
        carrierContactEl.disabled = !carrier;
    }
    carrierEl.addEventListener('change', refreshCarrierContacts);
    api('/carriers').then(function (list) {
        carrierList = (list || []).filter(function (c) { return c.is_active; });
        var active = carrierList;
        carrierEl.innerHTML = '<option value="">请选择</option>' + active.map(function (c) {
            return '<option value="' + c.id + '">' + esc(c.name) + '</option>';
        }).join('');
        refreshCarrierContacts();
    }).catch(function () { /* 拉不到就留空，用户可先自提 */ });

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var amount = Number(amountEl.value) || 0;
        var deposit = numOrNull(depositEl.value);
        var discount = numOrNull(discountEl.value) || 0;
        var mode = modeEl.value;
        if (!(productTotal > 0)) { toast('产品明细合计必须大于 0', true); return; }
        if (discount < 0 || discount > productTotal) {
            toast('优惠必须在 0 到产品合计之间', true);
            return;
        }
        if (deposit === null || deposit < 0 || deposit > amount) {
            toast('定金必须在 0 到订单应收之间', true);
            return;
        }
        var payload = {
            discount_amount: discount,
            discount_reason: String(form.querySelector('[name="discount_reason"]').value || '').trim() || null,
            deposit: deposit,
            logistics_mode: mode,
            logistics_fee: numOrNull(feeEl.value) || 0,
            note: String(form.querySelector('[name="note"]').value || '').trim() || null
        };
        if (mode !== 'self') {
            if (!carrierEl.value) { toast('包邮 / 代办要选物流公司', true); return; }
            payload.carrier_id = Number(carrierEl.value);
            if (!carrierContactEl.value) {
                toast('请选择物流公司的联络人；没有联络人请先到物流页维护', true);
                return;
            }
            payload.carrier_contact_id = Number(carrierContactEl.value);
            var rn = String(form.querySelector('[name="receiver_name"]').value || '').trim();
            var rp = String(form.querySelector('[name="receiver_phone"]').value || '').trim();
            var ra = String(form.querySelector('[name="receiver_address"]').value || '').trim();
            if (!rn || !rp || !ra) { toast('请填全收货人 / 电话 / 地址', true); return; }
            payload.receiver_name = rn;
            payload.receiver_phone = rp;
            payload.receiver_address = ra;
        }
        btn.disabled = true;
        var path = quote ? '/quotes/' + quote.id + '/orders' : '/deals/' + deal.id + '/orders';
        api(path, { method: 'POST', body: payload }).then(function (res) {
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
