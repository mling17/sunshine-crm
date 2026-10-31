/* 跟进记录页面（跨客户/商机，V1 视图迁移到 V2 拆分结构）*/

function followupItemHtml(item, opts) {
  opts = opts || {};
  var photos = (item.photos || []).map(function (p) {
    var url = '/crm' + p.url;
    return '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' +
      '<img src="' + esc(url) + '" alt="' + esc(p.file_name || '照片') + '" loading="lazy"></a>';
  }).join('');
  var deleteBtn = opts.withDelete
    ? '<button type="button" class="btn-link" data-del-followup="' + item.id + '">删除</button>' : '';
  return '<div class="item">' +
    '<div class="item-main">' +
      '<div class="item-title">' +
        (opts.showCustomer && item.customer_name
          ? '<a href="#/customers/' + item.customer_id + '">' + esc(item.customer_name) + '</a>'
          : '<span class="muted small">' + fmtDateTime(item.created_at) + '</span>') +
        (item.deal_stage && STAGE_LABEL[item.deal_stage]
          ? '<span class="tag">' + esc(STAGE_LABEL[item.deal_stage]) + '</span>' : '') +
      '</div>' +
      '<div class="item-sub">' + esc(item.content) + '</div>' +
      '<div class="item-sub small">' +
        fmtDateTime(item.created_at) +
        (item.next_date ? ' · 下次 ' + esc(item.next_date) : '') +
        (item.photo_count ? ' · 📷 ' + item.photo_count : '') +
      '</div>' +
      (photos ? '<div class="photos">' + photos + '</div>' : '') +
    '</div>' +
    '<div class="item-side">' + deleteBtn + '</div>' +
  '</div>';
}

function followupFormHtml(index, preCustomer, preDeal) {
  var hasCustomers = Object.keys(index).length > 0;
  return '<form id="fuForm" autocomplete="off">' +
    '<div class="row-2">' +
      '<div class="field"><label>客户 *</label>' +
        (hasCustomers
          ? '<select id="fuCustomer" name="customer_id">' + customerOptions(index, preCustomer) + '</select>'
          : '<p class="small muted">还没有客户，先 <a href="#/customers">建一个</a></p>') +
      '</div>' +
      '<div class="field"><label>关联商机</label>' +
        '<select id="fuDeal" name="deal_id"><option value="">不关联</option></select></div>' +
    '</div>' +
    '<div class="field"><label>跟进内容 *（≤2000 字）</label>' +
      '<textarea name="content" maxlength="2000" required placeholder="聊了什么、客户什么态度、下一步做什么"></textarea></div>' +
    '<div class="row-2">' +
      '<div class="field"><label>下次跟进日期</label>' +
        '<input type="date" name="next_date" value="' + todayISO() + '"></div>' +
      '<div class="field"><label>顺手改阶段（选了商机才生效）</label>' +
        '<select id="fuStage" name="stage" disabled><option value="">不改阶段</option>' +
          STAGES.map(function (p) { return '<option value="' + p[0] + '">' + p[1] + '</option>'; }).join('') +
        '</select></div>' +
    '</div>' +
    '<div class="field"><label>照片（最多 ' + MAX_PHOTOS + ' 张，单张 ≤' + MAX_PHOTO_MB + 'MB）</label>' +
      '<input type="file" id="fuPhotos" name="photos" accept="image/*" capture="environment" multiple></div>' +
    '<div class="form-actions"><button type="submit" class="btn btn-primary">保存跟进</button></div>' +
  '</form>';
}

function viewFollowups(root, route) {
  var preCustomer = route.query.get('customer') || '';
  var preDeal = route.query.get('deal') || '';

  return Promise.all([api('/follow-ups'), ensureCustomerIndex()]).then(function (all) {
    var list = all[0] || [];
    var index = all[1];

    var listHtml = list.length ? list.map(function (f) {
      return followupItemHtml(f, { withDelete: true, showCustomer: true });
    }).join('') : '<p class="empty">还没有跟进记录</p>';

    root.innerHTML =
      '<div class="card">' + '<div class="card-head"><h2>记一条跟进</h2></div>' +
        followupFormHtml(index, preCustomer, preDeal) +
      '</div>' +
      '<div class="card"><div class="card-head"><h2>全部跟进（' + list.length + '）</h2></div>' +
        listHtml + '</div>';

    var customerSel = $('#fuCustomer', root);
    var dealSel = $('#fuDeal', root);
    var stageSel = $('#fuStage', root);
    var photosInput = $('#fuPhotos', root);
    var form = $('#fuForm', root);
    if (!form || !customerSel) { return; }

    function loadDealsForCustomer(customerId) {
      dealSel.innerHTML = '<option value="">不关联</option>';
      stageSel.disabled = true;
      stageSel.value = '';
      if (!customerId) { return Promise.resolve(); }
      return api('/deals?customer_id=' + encodeURIComponent(customerId)).then(function (deals) {
        dealSel.innerHTML = '<option value="">不关联</option>' + (deals || []).map(function (d) {
          var label = [d.product_type, d.model].filter(Boolean).join(' ') || ('商机 #' + d.id);
          return '<option value="' + d.id + '">' + esc(label) + ' · ' +
            esc(d.stage_label || STAGE_LABEL[d.stage] || d.stage) + ' · ' + money(d.amount) + '</option>';
        }).join('');
        if (preDeal && deals && deals.some(function (d) { return String(d.id) === String(preDeal); })) {
          dealSel.value = String(preDeal);
          stageSel.disabled = false;
        }
        return null;
      });
    }

    customerSel.addEventListener('change', function () {
      loadDealsForCustomer(customerSel.value);
    });
    dealSel.addEventListener('change', function () {
      stageSel.disabled = !dealSel.value;
      if (!dealSel.value) { stageSel.value = ''; }
    });
    photosInput.addEventListener('change', function () {
      if (photosInput.files.length > MAX_PHOTOS) {
        toast('一条跟进最多 ' + MAX_PHOTOS + ' 张照片，已清空选择', true);
        photosInput.value = '';
      }
    });

    loadDealsForCustomer(customerSel.value).catch(function (err) { toast(err.message, true); });

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var btn = form.querySelector('button[type="submit"]');
      var content = String(form.querySelector('[name="content"]').value || '').trim();
      var customerId = customerSel.value;
      if (!customerId) { toast('先选客户', true); return; }
      if (!content) { toast('跟进内容不能为空', true); return; }
      if (photosInput.files.length > MAX_PHOTOS) { toast('照片最多 ' + MAX_PHOTOS + ' 张', true); return; }

      var tooBig = Array.prototype.some.call(photosInput.files, function (f) {
        return f.size > MAX_PHOTO_MB * 1024 * 1024;
      });
      if (tooBig) { toast('有照片超过 ' + MAX_PHOTO_MB + 'MB', true); return; }

      var fd = new FormData();
      fd.append('customer_id', customerId);
      fd.append('content', content);
      var nextDate = form.querySelector('[name="next_date"]').value;
      if (nextDate) { fd.append('next_date', nextDate); }
      if (dealSel.value) {
        fd.append('deal_id', dealSel.value);
        if (stageSel.value) { fd.append('stage', stageSel.value); }
      }
      Array.prototype.forEach.call(photosInput.files, function (file) { fd.append('photos', file); });

      btn.disabled = true;
      btn.textContent = '保存中…';
      api('/follow-ups', { method: 'POST', body: fd }).then(function (item) {
        toast('已记录跟进' + (item && item.photo_count ? '（' + item.photo_count + ' 张照片）' : ''));
        // 提交后清掉 URL 里的预填参数，避免表单又被填上一次
        navigate('#/followups');
      }).catch(function (err) {
        toast(err.message, true);
        btn.disabled = false;
        btn.textContent = '保存跟进';
      });
    });

    $$('button[data-del-followup]', root).forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (!window.confirm('删除这条跟进？')) { return; }
        api('/follow-ups/' + btn.getAttribute('data-del-followup'), { method: 'DELETE' })
          .then(function () { toast('已删除'); return render(); })
          .catch(function (err) { toast(err.message, true); });
      });
    });
  });
}

/* ================= 统计 ================= */
