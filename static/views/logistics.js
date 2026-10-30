/* 物流页面 */
(function () {
  'use strict';

  function viewLogistics(root, route) {
    var activeOnly = route.query.get('active_only') === 'true';
    
    return api('/carriers' + (activeOnly ? '?active_only=true' : '')).then(function (carriers) {
      var listHtml = carriers.length ? carriers.map(function (c) {
        var isActive = c.is_active;
        var statusBadge = '<span class=\"badge ' + (isActive ? 'ok' : 'warn') + '\">' + (isActive ? '启用' : '停用') + '</span>';
        
        return '<div class=\"item\">' +
          '<div class=\"item-main\">' +
            '<div class=\"item-title\">' + esc(c.name) + statusBadge + '</div>' +
            '<div class=\"item-sub\">' + (c.contact ? '联系人：' + esc(c.contact) : '') + '</div>' +
            '<div class=\"item-sub\">' + (c.phone ? '电话：' + esc(c.phone) : '') + '</div>' +
            '<div class=\"item-sub small\">' + (c.note ? esc(c.note) : '') + '</div>' +
          '</div>' +
          '<div class=\"item-side\">' +
            '<button type=\"button\" class=\"btn btn-sm\" data-edit-carrier=\"' + c.id + '\">编辑</button>' +
            '<button type=\"button\" class=\"btn btn-sm ' + (isActive ? '' : 'disabled') + '\" data-toggle-carrier=\"' + c.id + '\">' + (isActive ? '停用' : '启用') + '</button>' +
            '<button type=\"button\" class=\"btn btn-sm ' + (isActive ? 'btn-danger' : 'disabled') + '\" data-delete-carrier=\"' + c.id + '\">删除</button>' +
          '</div>' +
        '</div>';
      }).join('') : '<p class=\"empty\">还没有物流公司</p>';

      root.innerHTML =
        '<div class=\"card\">' +
          '<div class=\"card-head\"><h2>物流公司</h2>' +
            '<button type=\"button\" class=\"btn btn-primary btn-sm\" id=\"btnNewCarrier\">新增物流公司</button>' +
            '<button type=\"button\" class=\"btn btn-sm\" id=\"btnToggleActive\">' + (activeOnly ? '显示全部' : '只显示启用') + '</button>' +
          '</div>' +
          listHtml +
        '</div>';

      // 事件绑定
      $('#btnNewCarrier', root).addEventListener('click', function () {
        showNewCarrierForm();
      });
      
      $('#btnToggleActive', root).addEventListener('click', function () {
        var newActiveOnly = !activeOnly;
        navigate('#/logistics' + (newActiveOnly ? '?active_only=true' : ''));
      });
      
      $$('[data-edit-carrier]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
          var carrierId = btn.getAttribute('data-edit-carrier');
          editCarrier(carrierId);
        });
      });
      
      $$('[data-toggle-carrier]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
          var carrierId = btn.getAttribute('data-toggle-carrier');
          toggleCarrier(carrierId);
        });
      });
      
      $$('[data-delete-carrier]', root).forEach(function (btn) {
        btn.addEventListener('click', function () {
          var carrierId = btn.getAttribute('data-delete-carrier');
          deleteCarrier(carrierId);
        });
      });
    });
  }

  function showNewCarrierForm() {
    var modal = createModal('新增物流公司');
    modal.innerHTML = '<form id=\"newCarrierForm\" class=\"form-modal\">' +
      '<div class=\"field\"><label>公司名称 *</label>' +
      '<input type=\"text\" id=\"carrierName\" required></div>' +
      '<div class=\"field\"><label>联系人</label>' +
      '<input type=\"text\" id=\"carrierContact\"></div>' +
      '<div class=\"field\"><label>电话</label>' +
      '<input type=\"tel\" id=\"carrierPhone\"></div>' +
      '<div class=\"field\"><label>备注</label>' +
      '<textarea id=\"carrierNote\"></textarea></div>' +
      '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">提交</button></div>' +
    '</form>';
    
    var form = $('#newCarrierForm', modal);
    var nameInput = $('#carrierName', modal);

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var name = nameInput.value.trim();
      
      if (!name) {
        toast('请输入公司名称', true);
        return;
      }
      
      var payload = {
        name: name,
        contact: $('#carrierContact', modal).value.trim(),
        phone: $('#carrierPhone', modal).value.trim(),
        note: $('#carrierNote', modal).value.trim()
      };
      
      api('/carriers', { method: 'POST', body: payload })
        .then(function (res) {
          toast('物流公司已创建');
          document.body.removeChild(modal);
          location.reload();
        })
        .catch(function (err) {
          toast(err.message, true);
        });
    });
    
    document.body.appendChild(modal);
  }

  function editCarrier(carrierId) {
    api('/carriers/' + carrierId).then(function (carrier) {
      var modal = createModal('编辑物流公司');
      modal.innerHTML = '<form id=\"editCarrierForm\" class=\"form-modal\">' +
        '<div class=\"field\"><label>公司名称 *</label>' +
        '<input type=\"text\" id=\"carrierName\" value=\"' + esc(carrier.name) + '\" required></div>' +
        '<div class=\"field\"><label>联系人</label>' +
        '<input type=\"text\" id=\"carrierContact\" value=\"' + esc(carrier.contact || '') + '\"></div>' +
        '<div class=\"field\"><label>电话</label>' +
        '<input type=\"tel\" id=\"carrierPhone\" value=\"' + esc(carrier.phone || '') + '\"></div>' +
        '<div class=\"field\"><label>备注</label>' +
        '<textarea id=\"carrierNote\">' + esc(carrier.note || '') + '</textarea></div>' +
        '<div class=\"form-actions\"><button type=\"submit\" class=\"btn btn-primary\">保存</button></div>' +
      '</form>';
      
      var form = $('#editCarrierForm', modal);
      var nameInput = $('#carrierName', modal);

      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var name = nameInput.value.trim();
        
        if (!name) {
          toast('请输入公司名称', true);
          return;
        }
        
        var payload = {
          name: name,
          contact: $('#carrierContact', modal).value.trim(),
          phone: $('#carrierPhone', modal).value.trim(),
          note: $('#carrierNote', modal).value.trim()
        };
        
        api('/carriers/' + carrierId, { method: 'PUT', body: payload })
          .then(function (res) {
            toast('物流公司已保存');
            document.body.removeChild(modal);
            location.reload();
          })
          .catch(function (err) {
            toast(err.message, true);
          });
      });
      
      document.body.appendChild(modal);
    });
  }

  function toggleCarrier(carrierId) {
    api('/carriers/' + carrierId).then(function (carrier) {
      var newActive = !carrier.is_active;
      api('/carriers/' + carrierId, { 
        method: 'PUT', 
        body: { is_active: newActive } 
      })
        .then(function (res) {
          toast('物流公司已' + (newActive ? '启用' : '停用'));
          location.reload();
        })
        .catch(function (err) {
          toast(err.message, true);
        });
    });
  }

  function deleteCarrier(carrierId) {
    api('/carriers/' + carrierId).then(function (carrier) {
      if (!carrier.is_active) {
        // 如果已经停用，可以直接删除
        if (!window.confirm('确定要删除物流公司「' + carrier.name + '」？')) return;
        
        api('/carriers/' + carrierId, { method: 'DELETE' })
          .then(function (res) {
            toast('物流公司已删除');
            location.reload();
          })
          .catch(function (err) {
            toast(err.message, true);
          });
      } else {
        // 如果处于启用状态，提示用户只能停用
        toast('物流公司已被订单引用，只能停用', true);
      }
    });
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
  window.viewLogistics = viewLogistics;
})();