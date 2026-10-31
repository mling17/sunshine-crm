# 部署文档：菜单对齐 demo 9 项 + 数据字典页（纯前端）

- 提交：`9ed3c74 feat(menu): 顶栏对齐 demo 9 项（工作台/数据字典）+ 数据字典页移植接真实 API`
- 规格：`docs/PLAN-menu-dict-align.md`（D1/D2/D3）
- 影响面：**纯静态前端**，不动 `app/`、`tests/`、`static/demo/`；`crm-api`（:8010）**不重启**

## 1. 改动文件

| 文件 | 说明 |
|---|---|
| `static/index.html` | 顶栏 9 项（看板→工作台；跟进/导入撤出顶栏；统计后加 `#/dict`）；加载 `views/dict.js`；`app.css`/`app.js` 版本号 → `?v=20261031e4` |
| `static/app.js` | `render()` 增加 `dict` 分支；404 兜底「回看板」→「回工作台」 |
| `static/views/dict.js`（新增 301 行） | 移植 demo `dict.js`，全部写操作走真实 API（POST/PUT/DELETE `/dicts/{code}/items`），写完必重新 GET 回读；A/B/C/D 分级 UI 与「被引用项禁删」照 demo |
| `static/sw.js` | `SHELL` 增 `/crm/views/dict.js`；`CACHE` v4 → **v5**（旧壳失效） |
| `static/app.css` | 追加 `.dict-*` / `button.dict-row` / `.switch` / `.modal-content.wide`（从 demo.css 移植，仅字典页生效） |

## 2. 部署（一条命令，静态同步）

```bash
cd /opt/data/crm
bash ops/deploy-frontend.sh      # 结束输出「自检通过 ✅」
```

脚本把 `static/` 整目录 `cp -a` 到 `/root/nginx/html/crm`，并对 index/app.js/app.css/sw.js 做自检。
**不要重启 `crm-api`**：本次没有任何后端改动。

> 注意：CRM 前端由 **Docker nginx（宿主 8000 端口，`/root/nginx/docker-compose.yml`）** 提供，
> `location /crm/ { alias /usr/share/nginx/html/crm/; try_files ... }`；宿主上的 nginx:8080 是另一套站，
> 不要拿 8080 验证 `/crm/`。

## 3. 验证清单（实测已通过）

```bash
# 回归（后端用例只增不减）
env -u PYTHONPATH -u VIRTUAL_ENV /usr/bin/python3 -m unittest discover -s tests
# → Ran 264 tests in 36.878s / OK

# 静态同步（nginx 对缺失文件会回退 index.html 仍 200，必须比 md5）
for f in index.html app.js views/dict.js sw.js; do md5sum static/$f /root/nginx/html/crm/$f; done

# 菜单 9 项顺序
grep -o 'data-view="[a-z]*"' /root/nginx/html/crm/index.html

# 线上可达
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/crm/views/dict.js   # 200
```

## 4. 生产只读冒烟（GET，不改字典数据）

生产 API 实际监听 **127.0.0.1:8010**（nginx `proxy_pass http://<内网服务器IP>:8010/api/`），
路由前缀是 `/api/crm/dicts`（不是任务卡里写的 `/api/dicts`；`8002` 是 `/opt/data/platform` 服务）。

```bash
# 1) 往 sessions 插一条 12h 后过期的临时 token
python3 - <<'PY'
import secrets, sqlite3
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc).replace(microsecond=0)
fmt = lambda d: d.isoformat().replace("+00:00", "Z")
tok = "smoke_" + secrets.token_hex(16)
c = sqlite3.connect('/opt/data/crm/crm.db')
c.execute("INSERT INTO sessions (token,username,created_at,expires_at) VALUES (?,?,?,?)",
          (tok, "chen", fmt(now), fmt(now + timedelta(hours=12))))
c.commit(); print(tok)
PY
# 2) 只读取字典总览（Cookie 名 crm_sid，见 app/routers/auth.py）
curl -s -b "crm_sid=<token>" http://127.0.0.1:8010/api/crm/dicts      # 200 + 12 张字典
# 3) 用完立刻删
python3 -c "import sqlite3;c=sqlite3.connect('/opt/data/crm/crm.db');\
print(c.execute(\"DELETE FROM sessions WHERE token='<token>'\").rowcount);c.commit()"
```

实测：`http=200`，返回 **12 张**字典（7 张 A / 3 张 B / 1 张 C / 1 张 D）；删 token 后同 cookie 再请求 → `401`。

字典写接口的请求体契约在**生产库副本**上验过（不碰生产数据）：

```
POST   /api/crm/dicts/{code}/items        {"key","label","sort","enabled"}   → 200
PUT    /api/crm/dicts/{code}/items/{key}  {"label"} / {"sort"} / {"enabled"} → 200
DELETE /api/crm/dicts/{code}/items/{key}                                     → 200
```

## 5. 回滚

```bash
cd /opt/data/crm
git checkout 9ed3c74^ -- static/index.html static/app.js static/sw.js static/app.css
git rm --cached static/views/dict.js   # 本地文件可保留（不再被 index.html 引用）
bash ops/deploy-frontend.sh
```

回滚后 sw.js 的 `CACHE` 回到 `crm-shell-v4`，浏览器下一次加载会自动换壳；无需重启任何服务。

## 6. 已知边界

- 字典写操作按**单字段 change 即时落库**（无「保存修改」按钮）。demo 里的「保存」在真实后端下是第二个假动作，
  故去掉；弹窗底部已写明「改动即时保存到服务器」。
- 停用项不显示：`GET /dicts/{code}` 默认只回 `enabled=1`（后端既有行为，本任务不改后端），
  因此「停用」后该行会从列表消失，**字典弹窗里已内置提示**告知用户需找管理员恢复；
  根治办法是后端加 `?include_disabled=1`（建议单开一张后端卡，不在本任务红线内）。
- `#/followups`、`#/import` 仍可 URL 直达（只撤顶栏菜单，页内「记跟进」等按钮未动）。
