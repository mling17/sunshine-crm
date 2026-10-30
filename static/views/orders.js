/* 订单页面 */
(function () {
  'use strict';

  function viewOrders(root, route) {
    var page = Number(route.query.get('page') || 1);
    var status = route.query.get('status') || '';
    var customerId = route.query.get('customer_id') || '';

    var params = new URLSearchParams();
    params.set('page', String(page));
    params.set('size', '20');
    if (status) params.set('status', status);
    if (customerId) params.set('customer_id', customerId);

    return api('/orders?' + params.toString()).then(function (res) {
      var orders = res.items || [];
      
      var listHtml = orders.length ? orders.map(function (o) {
        var statusLabel = o.status_label || o.status;
        var statusBadge = '<span class=\"badge muted\">' + statusLabel + '</span>';
        
        // 订单金额信息
        var amounts = '总额 ' + money(o.amount);
        if (o.deposit_paid) { amounts += ' · 押金 ' + money(o.deposit_paid); }
        if (o.balance_paid) { amounts += ' · 尾款 ' + money(o.balance_paid); }
        
        return '<div class=\"item\">' +
          '<div class=\"item-main\">' +
            '<div class=\"item-title\">' + esc(o.order_no) + 
            statusBadge + '</div>' +
            '<div class=\"item-sub\">' + esc(o.product_type + ' ' + o.model + ' ' + o.spec) + '</div>' +
            '<div class=\"item-sub small\">' + amounts + '</div>' +
            '<div class=\"item-sub small\">' + 
              (o.customer_name ? '客户：' + esc(o.customer_name) : '') +
              (o.shipped_at ? ' · 已发货' : '') +
              (o.completed_at ? ' · 已完成' : '') +
            '</div>' +
          '</div>' +
          '<div class=\"item-side\"><a class=\"btn btn-sm\" href=\"#/orders/' + o.id + '\">详情</a></div>' +
        '</div>';
      }).join('') : '<p class=\"empty\">' + (status ? '这个状态下没有订单' : '还没有订单') + '</p>';

      root.innerHTML =
        '<div class=\"card\">' +
          '<div class=\"card-head\"><h2>订单列表（' + res.total + '）</h2>' +
            '<select id=\"orderStatusFilter\" aria-label=\"按状态筛选\" style=\"width:auto\">' +
              '<option value=\"\">全部状态</option>' +
              '<option value=\"pending_payment\">待支付</option>' +
              '<option value=\"deposit_paid\">已支付押金</option>' +
              '<option value=\"producing\">生产中</option>' +
              '<option value=\"balance_paid\">已支付尾款</option>' +
              '<option value=\"ready_to_ship\">待发货</option>' +
              '<option value=\"shipped\">已发货</option>' +
              '<option value=\"completed\">已完成</option>' +
            '</select>' +
          '</div>' +
          listHtml +
        '</div>' +
        '<div class=\"card\"><div id=\"orderPager\">' + pagerHtml(res) + '</div></div>';

      $('#orderStatusFilter', root).addEventListener('change', function (ev) {
        var value = ev.target.value;
        navigate('#/orders' + (value ? '?status=' + encodeURIComponent(value) : ''));
      });

      $('#orderPager', root).onclick = function (ev) {
        var btn = ev.target.closest('button[data-page]');
        if (!btn || btn.disabled) { return; }
        var pageNum = Number(btn.getAttribute('data-page')) || 1;
        navigate('#/orders?page=' + pageNum + (status ? '&status=' + encodeURIComponent(status) : ''));
      };
    });
  }

  function viewOrderDetail(root, orderId) {
    return Promise.all([
      api('/orders/' + orderId),
      api('/aftersales?order_id=' + orderId)
    ]).then(function (all) {
      var order = all[0];
      var aftersales = all[1] || [];

      if (!order) {
        root.innerHTML = '<div class=\"card\">订单不存在</div>';
        return;
      }

      // 计算金额信息
      var totalAmount = order.amount || 0;
      var depositPaid = order.deposit_paid || 0;
      var balancePaid = order.balance_paid || 0;
      var unpaid = totalAmount - depositPaid - balancePaid;

      // 状态进度条
      var statusProgress = '';
      var statusSteps = [
        { key: 'pending_payment', label: '待支付' },
        { key: 'deposit_paid', label: '已支付押金' },
        { key: 'producing', label: '生产中' },
        { key: 'balance_paid', label: '已支付尾款' },
        { key: 'ready_to_ship', label: '待发货' },
        { key: 'shipped', label: '已发货' },
        { key: 'completed', label: '已完成' }
      ];

      statusProgress = '<div class=\"progress-bar\">' + statusSteps.map(function (step, i) {
        var isActive = order.status === step.key;
        var isDone = ['pending_payment', 'deposit_paid', 'producing', 'balance_paid', 'ready_to_ship', 'shipped', 'completed'].indexOf(order.status) >= i;
        var className = 'step' + (isActive ? ' active' : isDone ? ' done' : '');
        return '<div class=\"' + className + '\"><div class=\"step-label\">' + step.label + '</div></div>';
      }).join('') + '</div>';

      // 售后单列表
      var aftersalesHtml = '';
      if (aftersales.length) {
        aftersalesHtml = '<div class=\"card\"><div class=\"card-head\"><h2>售后单（' + aftersales.length + '）</h2></div>' +
          aftersales.map(function (a) {
            var statusLabel = a.status_label || a.status;
            var statusBadge = '<span class=\"badge muted\">' + statusLabel + '</span>';
            return '<div class=\"item\">' +
              '<div class=\"item-main\">' +
                '<div class=\"item-title\">' + esc(a.no) + statusBadge + '</div>' +
                '<div class=\"item-sub\">' + esc(a.type_label || a.type) + '</div>' +
                '<div class=\"item-sub small\">' + esc(a.description.substring(0, 50)) + '</div>' +
              '</div>' +
              '<div class=\"item-side\"><a class=\"btn btn-sm\" href=\"#/aftersales/' + a.id + '\">详情</a></div>' +
            '</div>';
          }).join('') +
          '</div>';
      } else {
        aftersalesHtml = '<div class=\"card\"><div class=\"card-head\"><h2>售后单</h2></div><p class=\"empty\">暂无售后单</p></div>';
      }

      // 当前状态操作区
      var actionArea = '';
      if (order.next_status) {
        actionArea = '<div class=\"card\"><div class=\"card-head\"><h2>当前操作</h2></div>' +
          '<div class=\"form-actions\"><button type=\"button\" class=\"btn btn-primary\" id=\"btnNextAction\">' + getNextActionLabel(order.next_status) + '</button></div>' +
        '</div>';
      }

      // 历史记录
      var historyHtml = '';
      if (order.status_log && order.status_log.length) {
        historyHtml = '<div class=\"card\"><div class=\"card-head\"><h2>状态历史</h2></div>' +
          order.status_log.map(function (log) {
            var date = fmtDateTime(log.created_at);
            var screenshotsHtml = '';
            if (log.screenshots && log.screenshots.length) {
              screenshotsHtml = '<div class=\"photos\">' + log.screenshots.map(function (s) {
                var url = '/crm' + s.url;
                return '<a href=\"' + esc(url) + '\" target=\"_blank\" rel=\"noopener noreferrer\">' +
                  '<img src=\"' + esc(url) + '\" alt=\"截图\" loading=\"lazy\"></a>';
              }).join('') + '</div>';
            }
            return '<div class=\"item\">' +
              '<div class=\"item-main\">' +
                '<div class=\"item-title\">' + esc(log.to_status_label || log.to_status) + '</div>' +
                '<div class=\"item-sub small\">' + date + '</div>' +
                '<div class=\"item-sub\">' + (log.note || '') + '</div>' +
                screenshotsHtml +
              '</div>' +
            '</div>';
          }).join('') +
        '</div>';
      }

      root.innerHTML =
        '<div class=\"card\">' +
          '<div class=\"card-head\"><h2>订单详情</h2></div>' +
          '<div class=\"item-sub\">' +
            '订单号：' + esc(order.order_no) + '<br>' +
            '客户：' + esc(order.customer_name || '—') + '<br>' +
            '产品：' + esc(order.product_type + ' ' + order.model + ' ' + order.spec) + '<br>' +
            '状态：' + esc(order.status_label || order.status) + '<br>' +
            '创建时间：' + fmtDateTime(order.created_at) + '<br>' +
          '</div>' +
        '</div>' +
        '<div class=\"card\">' +
          '<div class=\"card-head\"><h2>金额信息</h2></div>' +
          '<div class=\"grid-3col\">' +
            '<div class=\"kpi\"><div class=\"label\">总额</div><div class=\"value\">' + money(totalAmount) + '</div></div>' +
            '<div class=\"kpi\"><div class=\"label\">已收</div><div class=\"value\">' + money(depositPaid + balancePaid) + '</div></div>' +
            '<div class=\"kpi\"><div class=\"label\">未收</div><div class=\"value\">' + money(unpaid) + '</div></div>' +
          '</div>' +
          '<div class=\"form-actions\"><button type=\"button\" class=\"btn btn-sm\" id=\"btnPayDeposit\">支付押金</button></div>' +
        '</div>' +
        statusProgress +
        actionArea +
        aftersalesHtml +
        historyHtml;

      // 事件绑定
      $('#btnNextAction', root).addEventListener('click', function () {
        performNextAction(order);
      });
      
      $('#btnPayDeposit', root).addEventListener('click', function () {
        showDepositPayment(order);
      });
    });
  }

  function getNextActionLabel(status) {
    switch (status) {
      case 'deposit_paid': return '支付押金';
      case 'producing': return '开始生产';
      case 'balance_paid': return '支付尾款';
      case 'ready_to_ship': return '准备发货';
      case 'shipped': return '发货';
      case 'completed': return '确认收货';
      default: return '下一步';
    }
  }

  function performNextAction(order) {
    // 根据当前状态执行下一步操作
    switch (order.next_status) {
      case 'deposit_paid':
        showDepositPayment(order);
        break;
      case 'producing':
        showProductionStart(order);
        break;
      case 'balance_paid':
        showBalancePayment(order);
        break;
      case 'ready_to_ship':
        showReadyToShip(order);
        break;
      case 'shipped':
        showShip(order);
        break;
      case 'completed':
        showComplete(order);
        break;
      default:
        toast('暂不支持此操作', true);
    }
  }

  function showDepositPayment(order) {
    var modal = createModal('支付押金');
    modal.innerHTML = '<form id=\"depositForm\" class=\"form-modal\">' +
      '<div class=\"field\"><label>押金金额 *</label>' +
      '<input type=\"number\" id=\"depositAmount\" min=\"0\" step=\"0.01\" required></div>' +
      '<div class=\"field\"><label>备注</label>' +
      '<textarea id=\"depositNote\"></textarea></div>' +
      '<div class=\"field\"><label>支付截图（最多 3 张）</label>' +
      '<input type=\"file\" id=\"depositScreenshots\" accept=\"image/*\" multiple></div>' +
      '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">提交</button></div>' +
    '</form>';
    
    var form = $('#depositForm', modal);
    var amountInput = $('#depositAmount', modal);
    var noteInput = $('#depositNote', modal);
    var screenshotsInput = $('#depositScreenshots', modal);

    // 设置押金金额为总额的提示
    amountInput.placeholder = '请输入押金金额（总额 ' + money(order.amount) + '）';
    
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var amount = parseFloat(amountInput.value);
      var note = noteInput.value;
      
      if (isNaN(amount) || amount <= 0) {
        toast('请输入有效的押金金额', true);
        return;
      }
      
      // 验证金额是否不超过总额
      if (amount > order.amount) {
        toast('押金金额不能超过总额', true);
        return;
      }
      
      var formData = new FormData();
      formData.append('amount', amount);
      if (note) formData.append('note', note);
      
      // 添加截图
      if (screenshotsInput.files.length > 0) {
        for (var i = 0; i < screenshotsInput.files.length; i++) {
          formData.append('screenshots', screenshotsInput.files[i]);
        }
      }
      
      api('/orders/' + order.id + '/pay-deposit', {
        method: 'POST',
        body: formData
      }).then(function (res) {
        toast('押金支付成功');
        location.reload();
      }).catch(function (err) {
        toast(err.message, true);
      });
    });
    
    document.body.appendChild(modal);
  }

  function showBalancePayment(order) {
    var modal = createModal('支付尾款');
    modal.innerHTML = '<form id=\"balanceForm\" class=\"form-modal\">' +
      '<div class=\"field\"><label>尾款金额 *</label>' +
      '<input type=\"number\" id=\"balanceAmount\" min=\"0\" step=\"0.01\" required></div>' +
      '<div class=\"field\"><label>备注</label>' +
      '<textarea id=\"balanceNote\"></textarea></div>' +
      '<div class=\"field\"><label>支付截图（最多 3 张）</label>' +
      '<input type=\"file\" id=\"balanceScreenshots\" accept=\"image/*\" multiple></div>' +
      '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">提交</button></div>' +
    '</form>';
    
    var form = $('#balanceForm', modal);
    var amountInput = $('#balanceAmount', modal);
    var noteInput = $('#balanceNote', modal);
    var screenshotsInput = $('#balanceScreenshots', modal);

    // 设置尾款金额提示
    var remaining = order.amount - (order.deposit_paid || 0);
    amountInput.placeholder = '应付尾款 ¥' + money(remaining);
    
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var amount = parseFloat(amountInput.value);
      var note = noteInput.value;
      
      if (isNaN(amount) || amount <= 0) {
        toast('请输入有效的尾款金额', true);
        return;
      }
      
      // 验证金额是否不超过剩余金额
      if (amount > remaining) {
        toast('尾款金额不能超过剩余金额', true);
        return;
      }
      
      var formData = new FormData();
      formData.append('amount', amount);
      if (note) formData.append('note', note);
      
      // 添加截图
      if (screenshotsInput.files.length > 0) {
        for (var i = 0; i < screenshotsInput.files.length; i++) {
          formData.append('screenshots', screenshotsInput.files[i]);
        }
      }
      
      api('/orders/' + order.id + '/pay-balance', {
        method: 'POST',
        body: formData
      }).then(function (res) {
        toast('尾款支付成功');
        location.reload();
      }).catch(function (err) {
        toast(err.message, true);
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
  window.viewOrders = viewOrders;
  window.viewOrderDetail = viewOrderDetail;
})();