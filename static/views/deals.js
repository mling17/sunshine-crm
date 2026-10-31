/* 商机页面 */
(function () {
  'use strict';

  function viewDeals(root, route) {
    var stage = route.query.get('stage') || '';
    var path = '/deals' + (stage ? '?stage=' + encodeURIComponent(stage) : '');

    return Promise.all([api(path), ensureCustomerIndex()]).then(function (all) {
      var deals = all[0] || [];
      var index = all[1];

      var listHtml = deals.length ? deals.map(function (d) {
        var name = index[d.customer_id] || ('客户 #' + d.customer_id);
        var parts = [d.product_type, d.model, d.spec].filter(Boolean).join(' / ') || '未填产品';
        var amounts = '报价 ' + money(d.amount);
        if (d.deposit) { amounts += ' · 定金 ' + money(d.deposit); }
        if (d.balance) { amounts += ' · 尾款 ' + money(d.balance); }
        
        var stageLabel = d.stage_label || STAGE_LABEL[d.stage] || d.stage;
        var stageBadge = '<span class=\"badge muted\">' + stageLabel + '</span>';
        
        return '<div class=\"item\">' +
          '<div class=\"item-main\">' +
            '<div class=\"item-title\"><a href=\"#/customers/' + d.customer_id + '\">' + esc(name) + '</a>' + 
            stageBadge + '</div>' +
            '<div class=\"item-sub\">' + esc(parts) + '</div>' +
            '<div class=\"item-sub small\">' + esc(amounts) + 
              (d.closed_at ? ' · 成交 ' + fmtDateTime(d.closed_at) : '') + '</div>' +
          '</div>' +
          '<div class=\"item-side\"><a class=\"btn btn-sm\" href=\"#/deals/' + d.id + '\">详情</a></div>' +
        '</div>';
      }).join('') : '<p class=\"empty\">' + (stage ? '这个阶段还没有商机' : '还没有商机') + '</p>';

      var customerIds = Object.keys(index).map(Number);
      var newDealCard = customerIds.length
        ? '<div class=\"card\"><div class=\"card-head\"><h2>新增商机</h2></div>' +
            '<div class=\"field\"><label>客户 *</label><select id=\"dealCustomer\">' +
              customerOptions(index, '') + '</select></div>' +
            dealFormHtml() + '</div>'
        : '<div class=\"card\"><p class=\"empty\">还没有客户，先 <a href=\"#/customers\">建客户</a></p></div>';

      root.innerHTML =
        '<div class=\"card\">' +
          '<div class=\"card-head\"><h2>商机管道（' + deals.length + '）</h2>' +
            '<select id=\"dealStageFilter\" aria-label=\"按阶段筛选\" style=\"width:auto\">' +
              '<option value=\"\">全部阶段</option>' +
              STAGES.map(function (pair) {
                return '<option value=\"' + pair[0] + '\"' + (pair[0] === stage ? ' selected' : '') + '>' +
                  pair[1] + '</option>';
              }).join('') +
            '</select>' +
          '</div>' +
          listHtml +
        '</div>' + newDealCard;

      $('#dealStageFilter', root).addEventListener('change', function (ev) {
        var value = ev.target.value;
        navigate('#/deals' + (value ? '?stage=' + encodeURIComponent(value) : ''));
      });

      bindDealStageSelects(root);

      var form = $('#newDealForm', root);
      if (form) {
        form.addEventListener('submit', function (ev) {
          ev.preventDefault();
          var btn = form.querySelector('button[type=\"submit\"]');
          var customerId = Number($('#dealCustomer', root).value);
          var amount = numOrNull(form.querySelector('[name=\"amount\"]').value);
          if (!customerId) { toast('先选客户', true); return; }
          if (amount === null || amount < 0) { toast('报价金额必填且 ≥0', true); return; }
          var payload = {
            customer_id: customerId,
            product_type: form.querySelector('[name=\"product_type\"]').value.trim() || null,
            model: form.querySelector('[name=\"model\"]').value.trim() || null,
            spec: form.querySelector('[name=\"spec\"]').value.trim() || null,
            amount: amount,
            deposit: numOrNull(form.querySelector('[name=\"deposit\"]').value) || 0,
            balance: numOrNull(form.querySelector('[name=\"balance\"]').value) || 0,
            stage: form.querySelector('[name=\"stage\"]').value
          };
          btn.disabled = true;
          api('/deals', { method: 'POST', body: payload }).then(function () {
            toast('已新增商机');
            return render();
          }).catch(function (err) {
            toast(err.message, true);
            btn.disabled = false;
          });
        });
      }
    });
  }

  function viewDealDetail(root, dealId) {
    return Promise.all([
      api('/deals/' + dealId),
      ensureCustomerIndex()
    ]).then(function (all) {
      var deal = all[0];
      var index = all[1];

      if (!deal) {
        root.innerHTML = '<div class=\"card\">商机不存在</div>';
        return;
      }

      var customerName = index[deal.customer_id] || ('客户 #' + deal.customer_id);
      var stageLabel = deal.stage_label || STAGE_LABEL[deal.stage] || deal.stage;
      
      var amounts = '报价 ' + money(deal.amount);
      if (deal.deposit) { amounts += ' · 定金 ' + money(deal.deposit); }
      if (deal.balance) { amounts += ' · 尾款 ' + money(deal.balance); }

      root.innerHTML =
        '<div class=\"card\">' +
          '<div class=\"card-head\"><h2>商机详情</h2></div>' +
          '<div class=\"item-sub\">' +
            '商机：' + esc(deal.title || ([deal.product_type, deal.model, deal.spec].filter(Boolean).join(' ') || ('#' + deal.id))) + '<br>' +
            '客户：' + esc(customerName) + '<br>' +
            '产品：' + esc(deal.product_type + ' ' + deal.model + ' ' + deal.spec) + '<br>' +
            '阶段：' + esc(stageLabel) + '<br>' +
            '金额：' + amounts + '<br>' +
            '创建时间：' + fmtDateTime(deal.created_at) + '<br>' +
            (deal.closed_at ? '成交时间：' + fmtDateTime(deal.closed_at) : '') +
          '</div>' +
        '</div>' +
        '<div class=\"card\"><div class=\"card-head\"><h2>操作</h2></div>' +
          '<div class=\"form-actions\">' +
            '<button type=\"button\" class=\"btn btn-primary\" id=\"btnWin\">赢单</button>' +
            '<button type=\"button\" class=\"btn btn-secondary\" id=\"btnLose\">流失</button>' +
            '<button type=\"button\" class=\"btn btn-sm\" id=\"btnEdit\">编辑</button>' +
          '</div>' +
        '</div>';

      // 事件绑定
      $('#btnWin', root).addEventListener('click', function () {
        winDeal(deal);
      });
      
      $('#btnLose', root).addEventListener('click', function () {
        loseDeal(deal);
      });
      
      $('#btnEdit', root).addEventListener('click', function () {
        editDeal(deal);
      });
    });
  }

  function winDeal(deal) {
    if (!window.confirm('确定要将商机「' + (deal.title || '未命名') + '」设为赢单？')) return;
    
    api('/deals/' + deal.id + '/win', { method: 'POST' })
      .then(function (res) {
        toast('商机已赢单，订单已生成');
        navigate('#/orders/' + res.order.id);
      })
      .catch(function (err) {
        toast(err.message, true);
      });
  }

  function loseDeal(deal) {
    var modal = createModal('流失商机');
    modal.innerHTML = '<form id=\"loseForm\" class=\"form-modal\">' +
      '<div class=\"field\"><label>流失原因 *</label>' +
      '<select id=\"loseReason\" required>' +
        '<option value=\"\">请选择</option>' +
        '<option value=\"price\">价格</option>' +
        '<option value=\"competitor\">竞品</option>' +
        '<option value=\"give_up\">客户放弃</option>' +
        '<option value=\"budget\">预算不足</option>' +
        '<option value=\"other\">其他</option>' +
      '</select></div>' +
      '<div class=\"field\"><label>详细说明</label>' +
      '<textarea id=\"loseReasonOther\" placeholder=\"请输入具体原因\"></textarea></div>' +
      '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">提交</button></div>' +
    '</form>';
    
    var form = $('#loseForm', modal);
    var reasonInput = $('#loseReason', modal);
    var otherInput = $('#loseReasonOther', modal);

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var reason = reasonInput.value;
      var other = otherInput.value;
      
      if (!reason) {
        toast('请选择流失原因', true);
        return;
      }
      
      var payload = { lost_reason: reason };
      if (reason === 'other' && other) {
        payload.lost_reason_other = other;
      }
      
      api('/deals/' + deal.id + '/lose', { method: 'POST', body: payload })
        .then(function (res) {
          toast('商机已设为流失');
          location.reload();
        })
        .catch(function (err) {
          toast(err.message, true);
        });
    });
    
    document.body.appendChild(modal);
  }

  function editDeal(deal) {
    var modal = createModal('编辑商机');
    modal.innerHTML = '<form id=\"editDealForm\" class=\"form-modal\">' +
      '<div class=\"row-2\">' +
        '<div class=\"field\"><label>产品类型</label>' +
        '<input name=\"product_type\" type=\"text\" maxlength=\"32\" placeholder=\"天窗 / 天幕\" value=\"' + esc(deal.product_type || '') + '\"></div>' +
        '<div class=\"field\"><label>型号</label>' +
        '<input name=\"model\" type=\"text\" maxlength=\"64\" placeholder=\"如 XW-120\" value=\"' + esc(deal.model || '') + '\"></div>' +
      '</div>' +
      '<div class=\"field\"><label>尺寸 / 洞口</label>' +
      '<input name=\"spec\" type=\"text\" maxlength=\"200\" placeholder=\"如 1200×2400\" value=\"' + esc(deal.spec || '') + '\"></div>' +
      '<div class=\"row-3\">' +
        '<div class=\"field\"><label>报价金额 *</label>' +
        '<input name=\"amount\" type=\"number\" min=\"0\" step=\"0.01\" inputmode=\"decimal\" required value=\"' + (deal.amount || '') + '\"></div>' +
        '<div class=\"field\"><label>定金</label>' +
        '<input name=\"deposit\" type=\"number\" min=\"0\" step=\"0.01\" inputmode=\"decimal\" value=\"' + (deal.deposit || '') + '\"></div>' +
        '<div class=\"field\"><label>尾款</label>' +
        '<input name=\"balance\" type=\"number\" min=\"0\" step=\"0.01\" inputmode=\"decimal\" value=\"' + (deal.balance || '') + '\"></div>' +
      '</div>' +
      '<div class=\"field\"><label>阶段</label>' +
      '<select name=\"stage\">' + stageOptions(deal.stage) + '</select></div>' +
      '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">保存</button></div>' +
    '</form>';
    
    var form = $('#editDealForm', modal);
    var stageSelect = form.querySelector('[name=\"stage\"]');

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var btn = form.querySelector('button[type=\"submit\"]');
      var amount = numOrNull(form.querySelector('[name=\"amount\"]').value);
      if (amount === null || amount < 0) { 
        toast('报价金额必填且 ≥0', true); 
        return; 
      }
      
      var payload = {
        product_type: form.querySelector('[name=\"product_type\"]').value.trim() || null,
        model: form.querySelector('[name=\"model\"]').value.trim() || null,
        spec: form.querySelector('[name=\"spec\"]').value.trim() || null,
        amount: amount,
        deposit: numOrNull(form.querySelector('[name=\"deposit\"]').value) || 0,
        balance: numOrNull(form.querySelector('[name=\"balance\"]').value) || 0,
        stage: stageSelect.value
      };
      
      btn.disabled = true;
      api('/deals/' + deal.id, { method: 'PUT', body: payload })
        .then(function (res) {
          toast('商机已保存');
          document.body.removeChild(modal);
          location.reload();
        })
        .catch(function (err) {
          toast(err.message, true);
          btn.disabled = false;
        });
    });
    
    document.body.appendChild(modal);
  }

  function createModal(title) {
    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = '<div class=\"modal-content\"><div class=\"modal-header\"><h3>' + title + '</h3><button type=\"button\" class=\"btn-link modal-close\">×</button></div></div>';
    
    var closeBtn = $('.modal-close', modal);
    closeBtn.addEventListener('click', function () {
      document.body.removeChild(modal);
    });
    
    return modal;
  }

  // 导出函数供全局访问
  window.viewDeals = viewDeals;
  window.viewDealDetail = viewDealDetail;
})();