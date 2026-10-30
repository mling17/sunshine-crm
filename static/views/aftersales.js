/* 售后页面 */
(function () {
  'use strict';

  function viewAftersales(root, route) {
    var status = route.query.get('status') || '';
    var orderId = route.query.get('order_id') || '';
    var customerId = route.query.get('customer_id') || '';

    var params = new URLSearchParams();
    params.set('page', '1');
    params.set('size', '20');
    if (status) params.set('status', status);
    if (orderId) params.set('order_id', orderId);
    if (customerId) params.set('customer_id', customerId);

    return api('/aftersales?' + params.toString()).then(function (res) {
      var aftersales = res.items || [];
      
      var listHtml = aftersales.length ? aftersales.map(function (a) {
        var statusLabel = a.status_label || a.status;
        var statusBadge = '<span class=\"badge muted\">' + statusLabel + '</span>';
        
        return '<div class=\"item\">' +
          '<div class=\"item-main\">' +
            '<div class=\"item-title\">' + esc(a.no) + statusBadge + '</div>' +
            '<div class=\"item-sub\">' + esc(a.type_label || a.type) + '</div>' +
            '<div class=\"item-sub small\">' + esc(a.description.substring(0, 50)) + '</div>' +
            '<div class=\"item-sub small\">订单：' + esc(a.order_no) + '</div>' +
          '</div>' +
          '<div class=\"item-side\"><a class=\"btn btn-sm\" href=\"#/aftersales/' + a.id + '\">详情</a></div>' +
        '</div>';
      }).join('') : '<p class=\"empty\">' + (status ? '这个状态下没有售后单' : '还没有售后单') + '</p>';

      root.innerHTML =
        '<div class=\"card\">' +
          '<div class=\"card-head\"><h2>售后单列表（' + res.total + '）</h2>' +
            '<select id=\"aftersaleStatusFilter\" aria-label=\"按状态筛选\" style=\"width:auto\">' +
              '<option value=\"\">全部状态</option>' +
              '<option value=\"pending\">待处理</option>' +
              '<option value=\"processing\">处理中</option>' +
              '<option value=\"done\">已完成</option>' +
              '<option value=\"rejected\">已拒绝</option>' +
            '</select>' +
            '<button type=\"button\" class=\"btn btn-primary btn-sm\" id=\"btnNewAftersale\">新建售后单</button>' +
          '</div>' +
          listHtml +
        '</div>' +
        '<div class=\"card\"><div id=\"aftersalePager\">' + pagerHtml(res) + '</div></div>';

      $('#aftersaleStatusFilter', root).addEventListener('change', function (ev) {
        var value = ev.target.value;
        navigate('#/aftersales' + (value ? '?status=' + encodeURIComponent(value) : ''));
      });

      $('#btnNewAftersale', root).addEventListener('click', function () {
        showNewAftersaleForm();
      });

      $('#aftersalePager', root).onclick = function (ev) {
        var btn = ev.target.closest('button[data-page]');
        if (!btn || btn.disabled) { return; }
        var pageNum = Number(btn.getAttribute('data-page')) || 1;
        navigate('#/aftersales?page=' + pageNum + (status ? '&status=' + encodeURIComponent(status) : ''));
      };
    });
  }

  function viewAftersaleDetail(root, aftersaleId) {
    return Promise.all([
      api('/aftersales/' + aftersaleId),
      api('/follow-ups?object_type=aftersale&object_id=' + aftersaleId)
    ]).then(function (all) {
      var aftersale = all[0];
      var followUps = all[1] || [];

      if (!aftersale) {
        root.innerHTML = '<div class=\"card\">售后单不存在</div>';
        return;
      }

      // 售后单信息
      var statusLabel = aftersale.status_label || aftersale.status;
      var statusBadge = '<span class=\"badge muted\">' + statusLabel + '</span>';
      
      root.innerHTML =
        '<div class=\"card\">' +
          '<div class=\"card-head\"><h2>售后单详情</h2></div>' +
          '<div class=\"item-sub\">' +
            '售后单号：' + esc(aftersale.no) + '<br>' +
            '关联订单：' + esc(aftersale.order_no) + '<br>' +
            '类型：' + esc(aftersale.type_label || aftersale.type) + '<br>' +
            '状态：' + statusBadge + '<br>' +
            '创建时间：' + fmtDateTime(aftersale.created_at) + '<br>' +
            '描述：' + esc(aftersale.description) + '<br>' +
          '</div>' +
        '</div>';

      // 如果是终态，不显示重开按钮
      if (aftersale.status !== 'done' && aftersale.status !== 'rejected') {
        root.innerHTML += '<div class=\"card\"><div class=\"card-head\"><h2>操作</h2></div>' +
          '<div class=\"form-actions\">' +
            '<button type=\"button\" class=\"btn btn-primary\" id=\"btnStartProcessing\">开始处理</button>' +
            '<button type=\"button\" class=\"btn btn-secondary\" id=\"btnReject\">拒绝</button>' +
            '<button type=\"button\" class=\"btn btn-sm\" id=\"btnNewAftersale\">新建售后单</button>' +
          '</div>' +
        '</div>';
      }

      // 跟进记录
      if (followUps.length) {
        root.innerHTML += '<div class=\"card\"><div class=\"card-head\"><h2>跟进记录（' + followUps.length + '）</h2></div>' +
          followUps.map(function (fu) {
            var photos = (fu.photos || []).map(function (p) {
              var url = '/crm' + p.url;
              return '<a href=\"' + esc(url) + '\" target=\"_blank\" rel=\"noopener noreferrer\">' +
                '<img src=\"' + esc(url) + '\" alt=\"照片\" loading=\"lazy\"></a>';
            }).join('');
            return '<div class=\"item\">' +
              '<div class=\"item-main\">' +
                '<div class=\"item-title\">' + esc(fu.content) + '</div>' +
                '<div class=\"item-sub small\">' + fmtDateTime(fu.created_at) + '</div>' +
                photos +
              '</div>' +
            '</div>';
          }).join('') +
        '</div>';
      }

      // 事件绑定
      if (aftersale.status !== 'done' && aftersale.status !== 'rejected') {
        $('#btnStartProcessing', root).addEventListener('click', function () {
          startProcessing(aftersale);
        });
        
        $('#btnReject', root).addEventListener('click', function () {
          rejectAftersale(aftersale);
        });
        
        $('#btnNewAftersale', root).addEventListener('click', function () {
          showNewAftersaleForm(aftersale.order_id);
        });
      }
    });
  }

  function showNewAftersaleForm(orderId) {
    var modal = createModal('新建售后单');
    modal.innerHTML = '<form id=\"newAftersaleForm\" class=\"form-modal\">' +
      '<div class=\"field\"><label>关联订单 *</label>' +
      '<input type=\"text\" id=\"aftersaleOrderId\" value=\"' + (orderId || '') + '\" required readonly></div>' +
      '<div class=\"field\"><label>售后类型 *</label>' +
      '<select id=\"aftersaleType\" required>' +
        '<option value=\"\">请选择</option>' +
        '<option value=\"return\">退货</option>' +
        '<option value=\"exchange\">换货</option>' +
        '<option value=\"repair\">维修</option>' +
        '<option value=\"complaint\">投诉</option>' +
        '<option value=\"other\">其他</option>' +
      '</select></div>' +
      '<div class=\"field\"><label>描述 *</label>' +
      '<textarea id=\"aftersaleDescription\" placeholder=\"请详细描述售后问题\" required></textarea></div>' +
      '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">提交</button></div>' +
    '</form>';
    
    var form = $('#newAftersaleForm', modal);
    var orderIdInput = $('#aftersaleOrderId', modal);
    var typeInput = $('#aftersaleType', modal);
    var descInput = $('#aftersaleDescription', modal);

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var orderId = orderIdInput.value;
      var type = typeInput.value;
      var desc = descInput.value;
      
      if (!orderId) {
        toast('请选择关联订单', true);
        return;
      }
      if (!type) {
        toast('请选择售后类型', true);
        return;
      }
      if (!desc) {
        toast('请填写售后描述', true);
        return;
      }
      
      var payload = {
        order_id: orderId,
        type: type,
        description: desc
      };
      
      api('/aftersales', { method: 'POST', body: payload })
        .then(function (res) {
          toast('售后单已创建');
          document.body.removeChild(modal);
          navigate('#/aftersales/' + res.id);
        })
        .catch(function (err) {
          toast(err.message, true);
        });
    });
    
    document.body.appendChild(modal);
  }

  function startProcessing(aftersale) {
    api('/aftersales/' + aftersale.id + '/start', { method: 'POST' })
      .then(function (res) {
        toast('售后单已开始处理');
        location.reload();
      })
      .catch(function (err) {
        toast(err.message, true);
      });
  }

  function rejectAftersale(aftersale) {
    var modal = createModal('拒绝售后单');
    modal.innerHTML = '<form id=\"rejectForm\" class=\"form-modal\">' +
      '<div class=\"field\"><label>拒绝原因 *</label>' +
      '<textarea id=\"rejectReason\" placeholder=\"请说明拒绝原因\" required></textarea></div>' +
      '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">提交</button></div>' +
    '</form>';
    
    var form = $('#rejectForm', modal);
    var reasonInput = $('#rejectReason', modal);

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var reason = reasonInput.value;
      
      if (!reason) {
        toast('请填写拒绝原因', true);
        return;
      }
      
      api('/aftersales/' + aftersale.id + '/reject', { 
        method: 'POST', 
        body: { reject_reason: reason } 
      })
        .then(function (res) {
          toast('售后单已拒绝');
          document.body.removeChild(modal);
          location.reload();
        })
        .catch(function (err) {
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
  window.viewAftersales = viewAftersales;
  window.viewAftersaleDetail = viewAftersaleDetail;
})();