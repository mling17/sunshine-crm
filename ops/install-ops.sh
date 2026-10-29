#!/bin/bash
# CRM V1 运维安装脚本（幂等，可重复执行）
# 职责：装 systemd 单元、建目录、开定时备份。不碰 nginx（nginx 改动由 T1 单独做并备份）。
set -euo pipefail

CRM_HOME=/opt/data/crm
OPS=$CRM_HOME/ops
STAMP=$(date +%Y%m%d-%H%M%S)

echo "== 1/4 目录与权限 =="
mkdir -p "$CRM_HOME"/{uploads,backups,logs,ops}
chmod 700 "$OPS/backup.env"
echo "  ok: $CRM_HOME"

echo "== 2/4 前置检查：系统 python 能否导入依赖 =="
# 必须清掉继承来的 PYTHONPATH，否则会踩到别的 venv 的 pydantic_core（实测踩过）
if ! env -u PYTHONPATH -u VIRTUAL_ENV /usr/bin/python3 -c 'import fastapi, uvicorn, minio' 2>/dev/null; then
    echo "  [FATAL] 系统 python3 依赖不全："
    env -u PYTHONPATH -u VIRTUAL_ENV /usr/bin/python3 -c 'import fastapi, uvicorn, minio' || true
    echo "  处理：/usr/bin/python3 -m pip install fastapi uvicorn minio python-multipart openpyxl"
    exit 1
fi
echo "  ok: fastapi/uvicorn/minio 均可导入"

echo "== 3/4 安装 systemd 单元 =="
install -m 644 "$OPS/crm-api.service"    /etc/systemd/system/crm-api.service
install -m 644 "$OPS/crm-backup.service" /etc/systemd/system/crm-backup.service
install -m 644 "$OPS/crm-backup.timer"   /etc/systemd/system/crm-backup.timer
systemctl daemon-reload
echo "  ok: 单元已安装（服务尚未启动）"

echo "== 4/4 备份定时器 =="
if [ -f "$CRM_HOME/crm.db" ]; then
    systemctl enable --now crm-backup.timer
    echo "  ok: crm-backup.timer 已启用（每日 03:10）"
else
    echo "  [SKIP] crm.db 还没建，暂不启用备份定时器（避免每日空跑报错）"
    echo "         T1 建库后执行：systemctl enable --now crm-backup.timer"
fi

echo
echo "启动服务（T1 完成后）：systemctl enable --now crm-api"
echo "查看状态：systemctl status crm-api；journalctl -u crm-api -f"
echo "手工备份：systemctl start crm-backup && journalctl -u crm-backup -n 30"
