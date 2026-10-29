# 天窗天幕 CRM · V1 运维手册（@ops）

> 版本：v1.0（2026-10-29）
> 对应规格：`/root/crm-v1-planner-spec.md`
> 本机：10.113.9.77（内网） / 出网通道 101.200.62.239

---

## 1. 现场勘察结论（实测，非估计）

| 项 | 实测结果 | 影响 |
|---|---|---|
| 现有网关 | 容器 `nginx`，只 `listen 80`，宿主 `8000→80`，已稳定 6 周 | CRM 挂 `location /crm/`，**不新建 server 块** |
| 公网 80/443 | 被 `kbms-nuzar-nginx-external-1` 占用；容器内只 `listen 80`，**443 无 TLS 监听**（openssl 握手失败） | 443 是"名义占用"，**没有任何可用证书** |
| 全机证书 | `/etc/letsencrypt` 不存在，无业务 `.crt/.pem` | 公网 HTTPS 必须从零申请 |
| 公网通道 | frpc 隧道 6000→22、6001→9119、6002→8000、6003→8001、6004→8002，**全明文 TCP** | 传输层无加密 |
| 云主机 | 101.200.62.239：80 开、443 **关**、7000(frps) 开、9000(MinIO) 开 | 443 可用，需放行安全组 |
| 磁盘 | 468G，可用 280G | 充足 |
| 内存 | 15G，已用 11G，**free 仅 791M，swap 2G 已用满（剩 18M）** | **硬约束**：单进程、不加容器、不做多 worker |
| 系统 python | `/usr/bin/python3` = 3.10.12，dist-packages 内有 fastapi 0.141.1 / pydantic 2.13.2 / minio 7.2.20 | 可直跑，但见 §2 的坑 |
| 在跑服务 | 8001 learning_kb（venv，`/health` 正常）、8002 platform（systemd，active） | **一律不动** |

---

## 2. 部署的一个真实坑（已复现，务必注意）

在本机 shell 里执行 `/usr/bin/python3 -c "import fastapi"` 会直接报：

```
ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
```

**原因不是缺少依赖**，而是当前 shell 的 `PYTHONPATH` 被指向了某个 **python3.14** 的 venv：

```
PYTHONPATH=/root/.hermes/installs/.../venv/lib/python3.14/site-packages
```

3.10 的解释器去加载 3.14 的编译产物，必然失败。清掉即正常：

```bash
env -u PYTHONPATH -u VIRTUAL_ENV /usr/bin/python3 -c 'import fastapi,pydantic;print("OK")'
# → OK
```

**应对**：`crm-api.service` 里显式 `Environment=PYTHONPATH=/opt/data/crm` 钉死，
不让登录 shell 的污染带进服务。这也是"手工能跑、服务起不来"这类问题的通用排查点——
**先看 `systemctl show crm-api -p Environment`，再看 `import` 报错的真实路径**。

---

## 3. 端口与路径规划

| 用途 | 值 | 说明 |
|---|---|---|
| 后端监听 | `0.0.0.0:8010` | 单进程 uvicorn，**不占 8001/8002/80** |
| 对外路径 | `http://10.113.9.77:8000/crm/` | 现有 nginx `location /crm/` |
| API 路径 | `/crm/api/...` → `127.0.0.1:8010/api/crm/...` | 片段见 `nginx-crm-location.conf` |
| 前端静态 | `/root/nginx/html/crm/` | 容器内 `/usr/share/nginx/html/crm/` |
| 数据库 | `/opt/data/crm/crm.db` | SQLite 单文件 |
| 照片 | `/opt/data/crm/uploads/YYYY/MM/DD/<uuid>` | 本地目录，不上 MinIO |
| 备份 | `/opt/data/crm/backups/YYYY-MM-DD/` | 本地 14 天 + 异机 90 天 |
| systemd | `crm-api` / `crm-backup.timer` | 对齐 `platform.service` 写法 |

---

## 4. 上线步骤（T1 之后执行，每步可回退）

```bash
# 0) 备份 nginx 配置（铁律：改配置前先备份）
cp /root/nginx/conf.d/default.conf /root/nginx/conf.d/default.conf.bak-$(date +%Y%m%d-%H%M%S)

# 1) 装运维单元（幂等）
bash /opt/data/crm/ops/install-ops.sh

# 2) 合入 nginx 片段（把 nginx-crm-location.conf 内容插进 default.conf）
#    语法检查 → 热加载（不是 restart，避免瞬时断流）
docker exec nginx nginx -t && docker exec nginx nginx -s reload

# 3) 启服务并验证
systemctl enable --now crm-api
curl -s http://10.113.9.77:8010/health        # 期望 200
curl -s http://10.113.9.77:8000/crm/health    # 期望 200（走 nginx）
curl -s -o /dev/null -w '%{http_code}\n' http://10.113.9.77:8000/crm/   # 期望 200

# 4) 开备份定时器（crm.db 已存在才可开）
systemctl enable --now crm-backup.timer
systemctl start crm-backup && journalctl -u crm-backup -n 20

# 5) 回归：确认没碰坏既有服务
curl -s http://10.113.9.77:8001/health        # learning_kb 必须仍健康
curl -s -o /dev/null -w '%{http_code}\n' http://10.113.9.77:8000/kb/
```

---

## 5. 回滚预案（三种粒度）

| 场景 | 动作 | 耗时 |
|---|---|---|
| 只是服务起不来 | `systemctl stop crm-api`（nginx 侧 `/crm/` 会 502，不影响其它服务） | 秒级 |
| nginx 配置改坏 | `cp default.conf.bak-<stamp> default.conf && docker exec nginx nginx -t && docker exec nginx nginx -s reload` | <1 分钟 |
| 数据出问题 | 停服务 → 解包 `backups/<日期>/crm-*.tar.gz` 覆盖 `crm.db` 与 `uploads/` → 起服务 | <5 分钟 |

**回滚前必做**：先 `cp crm.db crm.db.pre-rollback-<stamp>`，别用坏的盖掉还可能挽救的。

---

## 6. 备份与恢复（已实测通过）

- 脚本：`/opt/data/crm/ops/backup.py`（SQLite 在线备份 API，非 cp）
- 计划：`crm-backup.timer` 每日 **03:10**（`Persistent=true`，关机错过会补跑）
- 本地：`/opt/data/crm/backups/YYYY-MM-DD/crm-<stamp>.tar.gz`，保留 **14 天**
- 异机：MinIO `101.200.62.239:9000` / bucket `crm-backups` / 前缀 `YYYY/MM/`，保留 **90 天**
  （该机与本机不是同一块磁盘，满足"异机存放"）
- 校验：快照做 `PRAGMA integrity_check`，上传后 `stat_object` 比对大小，不符即失败
- 退出码：`0` 成功 / `1` 备份或校验失败（本地无备份，**必须告警**）/ `2` 本地成功但异机失败

**自测记录（2026-10-29 实跑）**：2 客户 2 商机 1 张照片 →
本地 702B 归档 → 异机 `s3://crm-backups/2026/10/...` 上传成功 →
解包 `integrity_check: ok`，行数 2/2，照片 5004B 完整还原 →
保留策略验证：20 天前目录被清理，14 天内保留。

**恢复演练（每季度做一次，别等真出事才试）**：

```bash
systemctl stop crm-api
cp /opt/data/crm/crm.db /opt/data/crm/crm.db.before-restore-$(date +%s)
tar xzf /opt/data/crm/backups/<日期>/crm-*.tar.gz -C /tmp/crm-restore
cp /tmp/crm-restore/crm.db /opt/data/crm/crm.db
rsync -a /tmp/crm-restore/uploads/ /opt/data/crm/uploads/
systemctl start crm-api && curl -s http://127.0.0.1:8010/health
```

---

## 7. 域名 + HTTPS 预案（等用户拍板，采购不阻塞开发）

### 7.1 为什么必须要域名
"她在外地/客户现场能用"是核心痛点。绕过域名的方案都不稳：

| 方案 | 结论 |
|---|---|
| IP + 自签证书 | 手机浏览器红色警告页，她不会点"继续" | 
| 免费动态隧道（ngrok 类） | 地址会变、有限速，业务不能用 |
| Cloudflare Tunnel | 仍需自有域名 |
| **域名 + Let's Encrypt** | **唯一稳的路径**，成本 30–60 元/年 |

### 7.2 落地路径（用户买完域名后，我这边约 1 小时）
1. 域名 A 记录 → `101.200.62.239`
2. 云主机安全组放行 **80 和 443**（实测 443 当前是关的）
3. 云主机装 nginx + certbot，`certbot --nginx -d crm.xxx.com`（HTTP-01 验证走 80）
4. 加一段 frp TCP 隧道：云机 443 → 本机 8010（或 8000 走现有网关）
5. 本机 nginx `location /crm/` 已就绪，只需保证 `X-Forwarded-Proto https`
6. 证书自动续期：certbot timer，需监控"到期前 15 天"告警

### 7.3 过渡方案（不买域名也能先给她用）
用 frp 新增一条 `web-8010 → remotePort 6005`，她手机访问 `http://101.200.62.239:6005/crm/`。
**能立刻用，但明文传输**，只适合"先试用、数据先录、不填敏感信息"，**正式用之前必须切 HTTPS**。
这条我可以在 10 分钟内加上，等 @manager 说要不要。

---

## 8. 安全发现（需要团队处理，我没有擅自改）

**`101.200.62.239:9000` 的 MinIO 对公网开放，且用的是默认口令 `minioadmin/minioadmin`。**
实测从本机可直接列出全部 bucket（`a-bucket`、`yeahteams`）。任何人都能读写 learning_kb 的照片数据。

建议处置顺序（改动会影响 8001 现有服务，需 @manager 批准后由我执行）：
1. 云主机安全组把 9000 限定为仅 `10.113.9.77` 出口 IP 可访问；
2. 轮换 MinIO 凭据，同步更新 learning_kb 配置并重启 8001（安排低峰）；
3. 我的备份脚本凭据放 `backup.env`（已 `chmod 600`，不进 git）。

另：`/root/frpc/frpc.toml` 里的 frp token 是明文弱口令，建议一并轮换。

---

## 9. 监控项（上线后每天看这 5 条）

| 指标 | 采集方式 | 阈值 |
|---|---|---|
| 服务存活 | `systemctl is-active crm-api` + `GET /crm/health` | 非 active 即告警 |
| 内存占用 | `systemctl show crm-api -p MemoryCurrent` | > 700M 关注（硬顶 1G） |
| 错误率 | `journalctl -u crm-api` 中的 5xx | 5 分钟 > 3 次告警 |
| 备份新鲜度 | `ls /opt/data/crm/backups` 最新目录日期 | 超过 30 小时未更新即告警 |
| 磁盘 | `df -h /opt/data` | 可用 < 50G 告警 |

---

## 10. 文件清单

```
/opt/data/crm/ops/
├── backup.py                    # 备份脚本（已实测）
├── backup.env                   # 异机凭据（600，勿外传）
├── crm-api.service              # 服务单元（含内存护栏）
├── crm-backup.service / .timer  # 备份单元（每日 03:10）
├── install-ops.sh               # 幂等安装脚本
├── nginx-crm-location.conf      # 待 T1 合入 nginx 的片段
└── OPS-部署与运维手册.md         # 本文件
```
