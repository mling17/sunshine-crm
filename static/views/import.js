/* CSV 导入页面（V1 视图迁移到 V2 拆分结构）*/

function importMappingHtml(pv) {
  var fields = pv.system_fields || [];
  var suggested = pv.suggested_mapping || {};
  var last = pv.last_mapping || {};
  var initial = Object.keys(suggested).length ? suggested : last;
  var usedLast = !Object.keys(suggested).length && Object.keys(last).length;

  var rows = (pv.headers || []).map(function (header) {
    var current = initial[header] || '';
    var options = '<option value="">不导入</option>' + fields.map(function (f) {
      return '<option value="' + esc(f.key) + '"' + (f.key === current ? ' selected' : '') + '>' +
        esc(f.label) + (f.required ? ' *' : '') + '</option>';
    }).join('');
    return '<div class="row-2"><div class="field"><label>CSV 列：' + esc(header) + '</label>' +
      '<select data-imp-header="' + esc(header) + '">' + options + '</select></div></div>';
  }).join('');

  var previewHead = (pv.headers || []).map(function (h) { return '<th>' + esc(h) + '</th>'; }).join('');
  var previewRows = (pv.preview || []).map(function (row) {
    return '<tr>' + (pv.headers || []).map(function (h) {
      return '<td>' + esc(row[h] === undefined ? '' : row[h]) + '</td>';
    }).join('') + '</tr>';
  }).join('');

  return '<div class="card">' +
    '<div class="card-head"><h2>列映射</h2>' +
      (usedLast && pv.last_mapping
        ? '<button type="button" class="btn btn-sm" id="useLastMapping">用上次映射</button>' : '') +
    '</div>' +
    '<p class="small muted">文件：' + esc(pv.file_name) + ' · 共 ' + (pv.total_rows || 0) + ' 行数据 · ' +
      '编码 ' + esc(pv.encoding || '?') + ' · 分隔符 ' + esc(pv.delimiter || ',') + '</p>' +
    rows +
    '<div class="table-wrap" style="margin-top:10px"><table><thead><tr>' + previewHead +
      '</tr></thead><tbody>' + previewRows + '</tbody></table></div>' +
    '<div class="form-actions"><button type="button" class="btn btn-primary" id="impCommit">确认导入</button></div>' +
    '<div id="impResult"></div>' +
  '</div>';
}

function viewImport(root) {
  var pv = state.import.preview;
  var result = state.import.result;

  var body = '<div class="card">' +
    '<div class="card-head"><h2>导入存量客户</h2></div>' +
    '<p class="small muted">Excel 里「另存为 → CSV（逗号分隔）」再上传；V1 不支持直接读 .xlsx。</p>' +
    '<div class="field"><input type="file" id="impFile" accept=".csv,text/csv"></div>' +
    '<div class="form-actions"><button type="button" class="btn btn-primary" id="impPreview">上传并预览</button></div>' +
    '<div id="impMsg"></div>' +
  '</div>';

  if (pv && pv.kind === 'xlsx_unsupported') {
    body += '<div class="card"><p class="notice">' + esc(pv.message) + '</p></div>';
  } else if (pv) {
    body += importMappingHtml(pv);
  }

  if (result) {
    body += '<div class="card"><div class="card-head"><h2>导入结果</h2></div>' +
      '<p>成功导入 <b>' + result.imported + '</b> 行' +
      (result.skipped ? '，跳过 <b>' + result.skipped + '</b> 行（姓名为空）' : '') +
      '；文件共 ' + result.total_rows + ' 行。' +
      (result.mapping_reused ? '（本次复用了上次的列映射）' : '') + '</p>' +
      '<p><a href="#/customers">去看客户列表 →</a></p></div>';
  }

  root.innerHTML = body;

  var fileEl = $('#impFile', root);
  var previewBtn = $('#impPreview', root);

  previewBtn.addEventListener('click', function () {
    var file = fileEl.files && fileEl.files[0];
    if (!file) { toast('先选一个 CSV 文件', true); return; }
    var fd = new FormData();
    fd.append('file', file);
    previewBtn.disabled = true;
    previewBtn.textContent = '上传中…';
    state.import.result = null;
    api('/import/preview', { method: 'POST', body: fd }).then(function (res) {
      state.import.preview = res;
      if (res.kind === 'xlsx_unsupported') {
        toast('Excel 需要先另存为 CSV', true);
      } else {
        toast('解析成功，共 ' + (res.total_rows || 0) + ' 行');
      }
      return render();
    }).catch(function (err) {
      toast(err.message, true);
      previewBtn.disabled = false;
      previewBtn.textContent = '上传并预览';
    });
  });

  var useLast = $('#useLastMapping', root);
  if (useLast) {
    useLast.addEventListener('click', function () {
      var last = (state.import.preview && state.import.preview.last_mapping) || {};
      $$('select[data-imp-header]', root).forEach(function (sel) {
        var header = sel.getAttribute('data-imp-header');
        sel.value = last[header] || '';
      });
      toast('已套用上次映射');
    });
  }

  var commitBtn = $('#impCommit', root);
  if (commitBtn) {
    commitBtn.addEventListener('click', function () {
      var preview = state.import.preview;
      if (!preview || !preview.file_ref) { toast('先上传预览', true); return; }
      var mapping = {};
      $$('select[data-imp-header]', root).forEach(function (sel) {
        if (sel.value) { mapping[sel.getAttribute('data-imp-header')] = sel.value; }
      });
      var mapped = Object.keys(mapping).map(function (k) { return mapping[k]; });
      if (mapped.indexOf('name') < 0) { toast('必须把某一列映射到「姓名」', true); return; }

      commitBtn.disabled = true;
      commitBtn.textContent = '导入中…';
      api('/import/commit', {
        method: 'POST',
        body: { file_ref: preview.file_ref, column_mapping: mapping, source_name: preview.file_name }
      }).then(function (res) {
        state.import.preview = null;
        state.import.result = res;
        invalidateCustomerIndex();
        toast('导入完成：' + res.imported + ' 行');
        return render();
      }).catch(function (err) {
        toast(err.message, true);
        commitBtn.disabled = false;
        commitBtn.textContent = '确认导入';
      });
    });
  }
}
