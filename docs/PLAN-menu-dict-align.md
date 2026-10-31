# PLAN：菜单对齐 demo + 数据字典页移植（2026-10-31）

## 背景（Manager 勘察结论）

用户反馈：正式版菜单与 demo v2.1（定稿版）不一致，且缺少数据字典菜单。

菜单差异：

| demo 定稿菜单（9 项） | 正式版现状 | 处置 |
|---|---|---|
| 工作台 | 「看板」 | 改文案为「工作台」 |
| 线索/客户/商机/订单/售后/物流/统计 | 一致 | 不动 |
| 数据字典 (#/dict) | **无** | 新增菜单 + 页面 |
| — | 「跟进」在顶栏 | **撤出顶栏**（页面保留 URL 直达） |
| — | 「导入」在顶栏 | **撤出顶栏**（页面保留 URL 直达） |

关键事实：
- 数据字典**后端 API 已存在**（T1 交付）：`app/routers/dicts.py` — GET `/dicts`（11 张总览）、GET `/dicts/{code}`、GET `/dicts/product_model`、POST `/dicts/{code}/items`、PUT `/dicts/{code}/items/{key}`、DELETE `/dicts/{code}/items/{key}`，含 A/B/C/D 分级与被引用项（used>0）禁删规则。**本任务禁止改后端。**
- demo 视图 `static/demo/views/dict.js`（203 行）可移植，但它对编辑/改名/删除是**内存直改**（`dict.items.forEach...`，配合 mock api）；正式版必须改为真实 API 调用 + 变更后重新拉取。
- `DICT_LEVEL` 常量定义在 demo/views/dict.js 第 7 行，随文件一起移植。
- demo 的裸名工具（api/$/$$/toast 等）在正式版由 `app.js` 共享段提供，移植时逐个核对应用的裸名是否都存在。

## 已拍板决策（勿再问）

- **D1**：顶栏菜单与 demo 完全一致 9 项：工作台·线索·客户·商机·订单·售后·物流·统计·数据字典。
- **D2**：数据字典页照 demo dict.js 移植，接真实 `/api/dicts`；总览 + 单张编辑（A 可增删改 / B 仅改名排序 / C 仅改名 / D 只读；被引用项删除按钮禁用）。
- **D3**：「跟进」「导入」**撤出顶栏菜单**（用户定稿）。注意：`customers.js` / `dashboard.js` / `leads.js` 里内嵌的「记跟进 / 全部跟进 / + 记一条」按钮、以及 followups.js / import.js 页面本身**一律保留**（它们是页内入口，不是顶栏菜单项）。

## 改动文件清单（最小范围）

1. `static/index.html`
   - nav 改 9 项（文案「看板」→「工作台」，删 跟进/导入 两个 `<a>`，统计后插 `<a href="#/dict" data-view="dict">数据字典</a>`）
   - `<script>` 区：在 import.js 之后、app.js 之前加 `<script src="/crm/views/dict.js"></script>`
2. `static/app.js`
   - `render()` 加 `else if (view === 'dict') { job = viewDict(root, route); }` 分支
   - 顺带文案一致性：404 兜底「回看板」及 grep 到的其它顶栏文案「看板」统一为「工作台」（只改指向 nav 的文案，不动页面内容里的业务名词）
3. `static/views/dict.js`（新建）
   - 移植 demo dict.js 的 viewDict / 总览 / 编辑弹窗 / DICT_LEVEL；所有写操作改为 API：
     新增 `api('/dicts/'+code+'/items', {method:'POST', body:...})`；改名/排序/停用 `PUT /dicts/{code}/items/{key}`；删除 `DELETE /dicts/{code}/items/{key}`
     （先读 `app/routers/dicts.py` 的请求体字段与响应结构，再写；错误分支按 app.js 既有错误提示约定）
   - 每次写操作成功后重新 `api('/dicts')` 或 `api('/dicts/{code}')` 刷新，**禁止**直接改本地对象冒充成功
4. `static/sw.js`
   - SHELL 加 `'/crm/views/dict.js'`；`CACHE = 'crm-shell-v4'` → `'crm-shell-v5'`（失效旧壳）

## 红线

- 不改 `app/`、`tests/`、`static/demo/`、`followups.js`、`import.js`
- 撤菜单 ≠ 撤功能：`#/followups`、`#/import` 仍可 URL 直达，页内跳转按钮不动
- 不碰生产数据：dict 冒烟只允许 GET
- 部署 = 静态同步，**不需要重启后端服务**（`crm-api` systemd 服务不动）

## 基线

- `env -u PYTHONPATH -u VIRTUAL_ENV /usr/bin/python3 -m unittest discover -s tests` → `Ran 264 tests in 36.9s / OK`（全绿，无既有红）。
- 本任务纯前端：后端回归用例只增不减，完成时 N' ≥ 264 且全绿。
- 派发时已查无 running/ready/todo 旧卡占用同文件；gateway 无 parked profile。

## 独立验证标准（kanban_complete 前必须逐条贴出）

1. 整行回归命令原文输出：`env -u PYTHONPATH -u VIRTUAL_ENV /usr/bin/python3 -m unittest discover -s tests` → 期望 `Ran 264 tests ... OK`（≥264）
2. `git log --oneline -1` 的 commit hash（无 commit = 未完成）+ 改动文件清单
3. `bash ops/deploy-frontend.sh` 结尾输出「自检通过 ✅」原文
4. md5 比对（源 vs 线上 /root/nginx/html/crm）：index.html、app.js、views/dict.js、sw.js 各一行 `md5sum` 对照，一致才算同步完成（nginx try_files 会对缺失文件回退 index.html 仍返 200，必须 md5 不是状态码）
5. `grep -o 'data-view="[a-z]*"' /root/nginx/html/crm/index.html` 输出 9 项且顺序 = 工作台/leads/customers/deals/orders/aftersales/logistics/stats/dict
6. dict 只读冒烟（不知道生产密码也能验）：向生产库 `sessions` 表插一条带 future 过期时间的临时 token，`curl -b '<cookie名>=<token>'` 调 `http://127.0.0.1:8010/api/crm/dicts` 期望 200 且返回 ≥11 张字典；**验完 DELETE 该临时 token**，并贴 token 已删的证据。全程对生产 dict 数据只做 GET。
   > ⚠️ 勘误（coder 实测）：CRM API 在 **8010**（systemd `crm-api`），真实路由前缀是 **`/api/crm/dicts`**（`/api/dicts` 实测 404）；8002 是 platform 服务，勿用。
