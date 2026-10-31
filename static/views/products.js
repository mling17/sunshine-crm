/* 产品主档：由 123 份下单表归纳为可检索、可维护的产品/配置库。
 * 商机只引用 product_id，并保存名称、编码、配置快照，避免后续改主档污染历史凭证。
 */

var PRODUCT_CATEGORIES = ['天窗', '天幕', '开合屋面', '纱窗', '遮阳', '配件'];
var PRODUCT_SERIES = ['25型', '55型', '95型', '140型', '300/340型', '480型', '540型', '工程型', '通用'];
var PRODUCT_STRUCTURES = ['平放', '嵌入', '平起', '平移', 'L型平移', '折叠平移', '框扇一体平移', '排水板', '隐藏排水', '隐藏螺杆', '三角形', '天幕', '开合屋面', '标准'];
var PRODUCT_FRAMES = ['普通', '重型', '极窄', '断桥', '隐藏型材', '大料', '标准'];
var PRODUCT_LEAVES = ['新扇', '老扇', '高低扇', '大料', '标准'];

function productOption(values, current, emptyLabel) {
    var html = emptyLabel === null ? '' : '<option value="">' + esc(emptyLabel || '不指定') + '</option>';
    var known = false;
    html += values.map(function (value) {
        var selected = String(current || '') === value;
        known = known || selected;
        return '<option value="' + esc(value) + '"' + (selected ? ' selected' : '') + '>' + esc(value) + '</option>';
    }).join('');
    if (current && !known) {
        html += '<option value="' + esc(current) + '" selected>' + esc(current) + '（自定义）</option>';
    }
    return html;
}

function productDriveLabel(value) {
    if (value === 'manual') { return '手动'; }
    if (value === 'electric') { return '电动'; }
    return '未指定';
}

function productDriveBadge(product) {
    var cls = product.drive_type === 'electric' ? 'ok' : 'muted';
    return '<span class="badge ' + cls + '">' + esc(productDriveLabel(product.drive_type)) + '</span>';
}

function productRangeText(product) {
    function range(min, max) {
        if (min === null || min === undefined) {
            if (max === null || max === undefined) { return ''; }
            return '≤' + max;
        }
        if (max === null || max === undefined) { return '≥' + min; }
        return min + '–' + max;
    }
    var width = range(product.min_width, product.max_width);
    var height = range(product.min_height, product.max_height);
    if (width && height) { return width + ' × ' + height + ' mm'; }
    if (width) { return '宽 ' + width + ' mm'; }
    if (height) { return '高 ' + height + ' mm'; }
    return '按现场量尺';
}

function productFileLinks(product, compact) {
    if (!product.form_available) {
        return '<span class="badge danger">缺少 Excel</span>';
    }
    var label = compact ? 'Excel' : ('下载 Excel · ' + (product.form_file_name || '下单表'));
    return '<a class="btn-link" href="/crm/api/crm/products/' + product.id +
        '/form-file" target="_blank" rel="noopener noreferrer">' + esc(label) + '</a>';
}

function productFeatureBadges(product) {
    var a = product.attributes || {};
    var values = [
        product.series,
        product.structure,
        product.opening_mode,
        product.edge_type,
        a.screen,
        a.mesh,
        a.motor_cover ? ('电机罩 ' + a.motor_cover) : null,
        a.shade,
        a.handle
    ].filter(Boolean);
    if (!values.length) { return '<span class="small muted">无附加配置</span>'; }
    return '<div class="product-chips">' + values.slice(0, 7).map(function (value) {
        return '<span class="product-chip">' + esc(value) + '</span>';
    }).join('') + '</div>';
}

function filterProducts(products, filters) {
    var q = String(filters.q || '').trim().toLowerCase();
    return products.filter(function (p) {
        if (filters.category && p.category !== filters.category) { return false; }
        if (filters.series && p.series !== filters.series) { return false; }
        if (filters.drive && p.drive_type !== filters.drive) { return false; }
        if (filters.active === '1' && !p.is_active) { return false; }
        if (filters.active === '0' && p.is_active) { return false; }
        if (!q) { return true; }
        return [p.code, p.name, p.category, p.series, p.structure, p.opening_mode,
            p.frame_type, p.leaf_type, p.config_summary]
            .filter(Boolean).join(' ').toLowerCase().indexOf(q) >= 0;
    });
}

function productFiltersHtml() {
    return '<div class="product-filters">' +
        '<label class="product-search"><span class="sr-only">搜索产品</span>' +
        '<input id="productQ" type="search" placeholder="搜索编码、名称、结构或配置"></label>' +
        '<select id="productCategory">' + productOption(PRODUCT_CATEGORIES, '', '全部分类') + '</select>' +
        '<select id="productSeries">' + productOption(PRODUCT_SERIES, '', '全部系列') + '</select>' +
        '<select id="productDrive"><option value="">全部驱动</option><option value="manual">手动</option>' +
        '<option value="electric">电动</option></select>' +
        '<select id="productActive"><option value="">全部状态</option><option value="1">在售</option>' +
        '<option value="0">已停用</option></select>' +
        '</div>';
}

function bindProductFilters(root, onChange) {
    var filters = { q: '', category: '', series: '', drive: '', active: '' };
    var map = {
        productQ: 'q',
        productCategory: 'category',
        productSeries: 'series',
        productDrive: 'drive',
        productActive: 'active'
    };
    Object.keys(map).forEach(function (id) {
        var el = $('#' + id, root);
        if (!el) { return; }
        var key = map[id];
        var eventName = id === 'productQ' ? 'input' : 'change';
        el.addEventListener(eventName, function () {
            filters[key] = String(el.value || '').trim();
            onChange(filters);
        });
    });
    return filters;
}

function productRowsHtml(products) {
    return dataTable([
        { title: '产品', render: function (p) {
            return '<a href="#/products/' + p.id + '">' + esc(p.name) + '</a>' +
                '<div class="small muted">' + esc(p.code) + '</div>';
        } },
        { title: '分类 / 系列', nowrap: true, render: function (p) {
            return esc([p.category, p.series].filter(Boolean).join(' / ') || '—');
        } },
        { title: '结构 / 开启', nowrap: true, render: function (p) {
            return esc([p.structure, p.opening_mode].filter(Boolean).join(' / ') || '—');
        } },
        { title: '配置', render: function (p) { return productFeatureBadges(p); } },
        { title: '驱动', nowrap: true, render: function (p) { return productDriveBadge(p); } },
        { title: '规格范围', nowrap: true, render: function (p) { return esc(productRangeText(p)); } },
        { title: '引用', align: 'right', nowrap: true, render: function (p) {
            return '<span title="商机 / 订单">' + p.deal_count + ' / ' + p.order_count + '</span>';
        } },
        { title: '状态', nowrap: true, render: function (p) {
            return '<span class="badge ' + (p.is_active ? 'ok' : 'muted') + '">' +
                (p.is_active ? '在售' : '停用') + '</span>' +
                (p.form_available ? '' : ' <span class="badge danger">缺表</span>');
        } },
        { title: '操作', nowrap: true, render: function (p) {
            return '<div class="op-group">' + productFileLinks(p, true) +
                opButtons([{ op: 'edit', arg: p.id, label: '编辑' }, { op: 'view', arg: p.id, label: '详情' }]) + '</div>';
        } }
    ], products, '没有匹配的产品');
}

function viewProducts(root) {
    return api('/products').then(function (products) {
        var all = products || [];
        var activeCount = all.filter(function (p) { return p.is_active; }).length;
        root.innerHTML =
            '<div class="card product-hero">' +
                '<div class="card-head"><div><h2>产品 <span class="badge muted">' + all.length + '</span></h2>' +
                '<p class="card-subtitle">一份 Excel 对应一个产品；下单表是产品的必传凭证，商机关联后自动冻结产品快照。</p></div>' +
                '<button type="button" class="btn btn-primary" id="productNew">＋ 新增产品</button></div>' +
                '<div class="product-kpis"><span><b>' + activeCount + '</b> 在售</span>' +
                '<span><b>' + all.filter(function (p) { return p.category === '天窗'; }).length + '</b> 天窗</span>' +
                '<span><b>' + all.filter(function (p) { return p.drive_type === 'electric'; }).length + '</b> 电动款</span></div>' +
            '</div>' +
            '<div class="card">' + productFiltersHtml() +
                '<div id="productList">' + productRowsHtml(all) + '</div>' +
            '</div>';

        function paint(filters) {
            var hits = filterProducts(all, filters);
            var box = $('#productList', root);
            box.innerHTML = '<div class="small muted product-result">显示 ' + hits.length + ' / ' + all.length + ' 个产品</div>' +
                productRowsHtml(hits);
        }
        bindProductFilters(root, paint);

        $('#productNew', root).addEventListener('click', function () {
            openProductEdit(null, function () { return render(); });
        });
        bindOps(root, {
            edit: function (id) {
                var product = all.filter(function (p) { return p.id === id; })[0];
                if (product) { openProductEdit(product, function () { return render(); }); }
            },
            view: function (id) { navigate('#/products/' + id); }
        });
    });
}

function viewProductDetail(root, rawId) {
    var id = Number(rawId);
    if (!id || isNaN(id)) {
        root.innerHTML = '<div class="card">产品 id 不合法，<a href="#/products">回产品列表</a></div>';
        return Promise.resolve();
    }
    return api('/products/' + id).then(function (p) {
        if (!p) {
            root.innerHTML = '<div class="card">产品不存在，<a href="#/products">回产品列表</a></div>';
            return;
        }
        var deals = p.deals || [];
        var dealTable = dataTable([
            { title: '商机', nowrap: true, render: function (d) {
                return '<a href="#/deals/' + d.id + '">#' + d.id + '</a>';
            } },
            { title: '客户', render: function (d) { return esc(d.customer_name || '—'); } },
            { title: '尺寸', nowrap: true, render: function (d) { return esc(d.spec || '—'); } },
            { title: '金额', align: 'right', nowrap: true, render: function (d) { return money(d.amount); } },
            { title: '阶段', nowrap: true, render: function (d) {
                return dealStageBadge(d.stage, STAGE_LABEL[d.stage]);
            } },
            { title: '订单', nowrap: true, render: function (d) {
                return d.order_id ? '<a href="#/orders/' + d.order_id + '">查看订单</a>' : '—';
            } }
        ], deals, '还没有商机关联这个产品');

        root.innerHTML =
            '<div class="card">' +
                '<div class="card-head"><h2><a href="#/products">‹ 产品</a> / ' +
                    esc(p.name) + '</h2><div>' +
                    '<span class="badge ' + (p.is_active ? 'ok' : 'muted') + '">' +
                    (p.is_active ? '在售' : '已停用') + '</span> ' +
                    (p.form_available ? '' : '<span class="badge danger">缺少 Excel</span> ') +
                    '<button type="button" class="btn btn-sm" id="productEdit">编辑产品</button></div></div>' +
                '<div class="product-detail-head"><span class="product-code">' + esc(p.code) + '</span>' +
                    '<span class="badge muted">' + esc(p.category) + '</span> ' + productDriveBadge(p) + '</div>' +
                '<p class="product-config-line">' + esc(p.config_summary || '按订单参数配置') + '</p>' +
                '<div class="product-form-file">' +
                    (p.form_available
                        ? '<div><b>对应下单表</b><div class="small muted">' + esc(p.form_file_name || '') +
                          ' · ' + Math.max(1, Math.round(Number(p.form_file_size || 0) / 1024)) + ' KB</div></div>' +
                          productFileLinks(p, false)
                        : '<div><b>对应下单表</b><div class="small muted">该产品缺少 Excel 下单表，需要补齐后才能启用。</div></div>') +
                '</div>' +
                infoGrid([
                    ['系列', p.series || '通用'],
                    ['结构方式', p.structure || '—'],
                    ['开启方式', p.opening_mode || '—'],
                    ['型材 / 边框', p.frame_type || '—'],
                    ['扇型', p.leaf_type || '—'],
                    ['边型', p.edge_type || '—'],
                    ['扇数', p.leaf_count ? p.leaf_count + ' 扇' : '按图'],
                    ['规格范围', productRangeText(p)],
                    ['关联商机', p.deal_count + ' 个'],
                    ['已生成订单', p.order_count + ' 个'],
                    ['来源模板', p.source_template || '手工新增'],
                    ['下单表', p.form_available ? '已归档' : '缺失'],
                    ['维护说明', p.description || '—']
                ]) +
            '</div>' +
            '<div class="card"><div class="card-head"><h2>关联商机 <span class="badge muted">' +
                deals.length + '</span></h2><span class="small muted">产品修改不会改写这些历史快照</span></div>' +
                dealTable + '</div>';

        $('#productEdit', root).addEventListener('click', function () {
            openProductEdit(p, function () { return render(); });
        });
    });
}

function openProductEdit(product, done) {
    var p = product || {};
    var attrs = p.attributes || {};
    var other = Array.isArray(attrs.other) ? attrs.other.join('、') : (attrs.other || '');
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-overlay"></div>' +
        '<div class="modal-content wide">' +
        '<div class="modal-header"><h3>' + (product ? '编辑产品' : '新增产品') + '</h3>' +
        '<button type="button" class="btn btn-link modal-close">×</button></div>' +
        '<div class="modal-body"><form id="productForm" class="form-grid" autocomplete="off">' +
            '<div class="row-2">' +
                '<div class="field"><label>产品编码 *</label><input name="code" maxlength="64" required value="' +
                    esc(p.code || '') + '" placeholder="如 TS-124"></div>' +
                '<div class="field"><label>产品名称 *</label><input name="name" maxlength="120" required value="' +
                    esc(p.name || '') + '" placeholder="客户能看懂的产品名称"></div>' +
            '</div>' +
            '<div class="row-3">' +
                '<div class="field"><label>产品分类 *</label><select name="category">' +
                    productOption(PRODUCT_CATEGORIES, p.category || '天窗', null) + '</select></div>' +
                '<div class="field"><label>产品系列</label><select name="series">' +
                    productOption(PRODUCT_SERIES, p.series || '', '通用') + '</select></div>' +
                '<div class="field"><label>驱动方式</label><select name="drive_type">' +
                    '<option value="">不指定</option><option value="manual"' + (p.drive_type === 'manual' ? ' selected' : '') +
                    '>手动</option><option value="electric"' + (p.drive_type === 'electric' ? ' selected' : '') +
                    '>电动</option></select></div>' +
            '</div>' +
            '<div class="row-3">' +
                '<div class="field"><label>结构方式</label><select name="structure">' +
                    productOption(PRODUCT_STRUCTURES, p.structure || '', '不指定') + '</select></div>' +
                '<div class="field"><label>开启方式</label><input name="opening_mode" maxlength="32" value="' +
                    esc(p.opening_mode || '') + '" placeholder="单扇开启 / 联排 / 对开"></div>' +
                '<div class="field"><label>扇数</label><input name="leaf_count" type="number" min="1" max="30" value="' +
                    esc(p.leaf_count || '') + '"></div>' +
            '</div>' +
            '<div class="row-3">' +
                '<div class="field"><label>型材 / 边框</label><select name="frame_type">' +
                    productOption(PRODUCT_FRAMES, p.frame_type || '', '不指定') + '</select></div>' +
                '<div class="field"><label>扇型</label><select name="leaf_type">' +
                    productOption(PRODUCT_LEAVES, p.leaf_type || '', '不指定') + '</select></div>' +
                '<div class="field"><label>边型</label><select name="edge_type">' +
                    '<option value="">不指定</option><option value="带边"' + (p.edge_type === '带边' ? ' selected' : '') +
                    '>带边</option><option value="不带边"' + (p.edge_type === '不带边' ? ' selected' : '') +
                    '>不带边</option></select></div>' +
            '</div>' +
            '<div class="row-3">' +
                '<div class="field"><label>常用配置：纱窗</label><select name="screen">' +
                    productOption(['手动纱窗', '电动纱窗'], attrs.screen || '', '无') + '</select></div>' +
                '<div class="field"><label>常用配置：网</label><select name="mesh">' +
                    productOption(['金刚网'], attrs.mesh || '', '无') + '</select></div>' +
                '<div class="field"><label>常用配置：电机罩</label><select name="motor_cover">' +
                    productOption(['标准', 'L型'], attrs.motor_cover || '', '无') + '</select></div>' +
            '</div>' +
            '<div class="row-2">' +
                '<div class="field"><label>常用配置：遮阳</label><select name="shade">' +
                    productOption(['手动遮阳', '电动遮阳'], attrs.shade || '', '无') + '</select></div>' +
                '<div class="field"><label>常用配置：把手</label><select name="handle">' +
                    productOption(['普通把手', '隔热把手', '内置无钥匙隔热把手', '外置带钥匙隔热把手'],
                        attrs.handle || '', '无') + '</select></div>' +
            '</div>' +
            '<div class="row-2">' +
                '<div class="field"><label>其他配置</label><input name="other" maxlength="200" value="' +
                    esc(other) + '" placeholder="多个配置用顿号或逗号分隔"></div>' +
                '<div class="field"><label>来源模板</label><input name="source_template" maxlength="300" value="' +
                    esc(p.source_template || '') + '" placeholder="如：55型2扇联排+电机罩"></div>' +
            '</div>' +
            '<div class="field"><label>对应 Excel 下单表 ' + (product ? '（可选替换）' : '*') + '</label>' +
                '<input name="form_file" type="file" accept=".xlsx,.xls"' + (product ? '' : ' required') + '>' +
                '<div class="small muted">' + (product && p.form_available
                    ? '当前：' + esc(p.form_file_name || '已归档下单表') + '。不选择新文件则保留当前表。'
                    : '每个产品必须有一份对应的 Excel；支持 .xlsx / .xls，最大 20MB。') + '</div></div>' +
            '<div class="row-2">' +
                '<div class="field"><label>宽度范围（mm）</label><div class="dimension-pair">' +
                    '<input name="min_width" type="number" min="0" step="1" value="' + esc(p.min_width || '') + '" placeholder="最小">' +
                    '<span>—</span><input name="max_width" type="number" min="0" step="1" value="' + esc(p.max_width || '') + '" placeholder="最大">' +
                '</div></div>' +
                '<div class="field"><label>高度范围（mm）</label><div class="dimension-pair">' +
                    '<input name="min_height" type="number" min="0" step="1" value="' + esc(p.min_height || '') + '" placeholder="最小">' +
                    '<span>—</span><input name="max_height" type="number" min="0" step="1" value="' + esc(p.max_height || '') + '" placeholder="最大">' +
                '</div></div>' +
            '</div>' +
            '<div class="field"><label>维护说明</label><textarea name="description" maxlength="1000" ' +
                'placeholder="适用场景、报价口径、不可选项或工厂备注">' + esc(p.description || '') + '</textarea></div>' +
            '<label class="switch"><input name="is_active" type="checkbox"' + (p.is_active === false ? '' : ' checked') +
                '><span>在售，可被新商机关联</span></label>' +
            '<div class="form-actions"><button type="button" class="btn modal-cancel">取消</button>' +
                '<button type="submit" class="btn btn-primary">保存产品</button></div>' +
        '</form></div></div>';
    document.body.appendChild(modal);

    function close() { if (modal.parentNode) { document.body.removeChild(modal); } }
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('.modal-cancel').addEventListener('click', close);
    var form = modal.querySelector('form');
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        function val(name) {
            var el = form.querySelector('[name="' + name + '"]');
            return el ? String(el.value || '').trim() : '';
        }
        function dim(name) {
            var raw = val(name);
            return raw === '' ? null : Number(raw);
        }
        var payload = {
            code: val('code'),
            name: val('name'),
            category: val('category'),
            series: val('series') || null,
            structure: val('structure') || null,
            opening_mode: val('opening_mode') || null,
            drive_type: val('drive_type') || null,
            frame_type: val('frame_type') || null,
            leaf_type: val('leaf_type') || null,
            edge_type: val('edge_type') || null,
            leaf_count: numOrNull(val('leaf_count')),
            min_width: dim('min_width'),
            max_width: dim('max_width'),
            min_height: dim('min_height'),
            max_height: dim('max_height'),
            attributes: {
                screen: val('screen') || null,
                mesh: val('mesh') || null,
                motor_cover: val('motor_cover') || null,
                shade: val('shade') || null,
                handle: val('handle') || null,
                other: val('other').split(/[、,，]/).map(function (x) { return x.trim(); }).filter(Boolean)
            },
            source_template: val('source_template') || null,
            description: val('description') || null,
            is_active: form.querySelector('[name="is_active"]').checked
        };
        if (!payload.code || !payload.name) { toast('产品编码和名称必填', true); return; }
        var fileInput = form.querySelector('[name="form_file"]');
        var formFile = fileInput && fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
        if (!product && !formFile) { toast('请上传该产品对应的 Excel 下单表', true); return; }
        if (formFile) {
            if (!/\.(xlsx|xls)$/i.test(formFile.name)) {
                toast('下单表必须是 .xlsx 或 .xls 文件', true);
                return;
            }
            if (formFile.size > 20 * 1024 * 1024) {
                toast('下单表不能超过 20MB', true);
                return;
            }
        }
        var btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        var req;
        if (product) {
            req = api('/products/' + product.id, { method: 'PUT', body: payload }).then(function (saved) {
                if (!formFile) { return saved; }
                var replaceData = new FormData();
                replaceData.append('form_file', formFile);
                return api('/products/' + product.id + '/form-file', {
                    method: 'PUT',
                    body: replaceData
                });
            });
        } else {
            var createData = new FormData();
            createData.append('payload', JSON.stringify(payload));
            createData.append('form_file', formFile);
            req = api('/products', { method: 'POST', body: createData });
        }
        req.then(function () {
            toast(product ? '产品已更新' : '产品已新增');
            PRODUCT_CATALOG_CACHE = null;
            close();
            if (done) { done(); }
        }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
        });
    });
}
