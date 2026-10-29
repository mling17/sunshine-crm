#!/usr/bin/env bash
# 把 /opt/data/crm/static/ 同步到 nginx 静态目录（只复制文件，不改 nginx 配置）。
#
#   bash ops/deploy-frontend.sh            # 复制 + 自检
#   SRC=... DST=... bash ops/deploy-frontend.sh
#
# 回滚：把备份目录拷回去即可（脚本每次覆盖前不做删除，旧文件会留着；
#      要完全回退，用 git 里上一版 static/ 重新跑一次本脚本）。
set -euo pipefail

SRC="${SRC:-/opt/data/crm/static}"
DST="${DST:-/root/nginx/html/crm}"

[ -f "$SRC/index.html" ] || { echo "源目录不对：$SRC 下没有 index.html" >&2; exit 1; }

install -d -m 755 "$DST"
cp -a "$SRC"/. "$DST"/

echo "已复制到 $DST，文件清单："
find "$DST" -type f -printf '  %P  (%s bytes)\n' | sort

echo
echo "== 自检 =="
fail=0
for f in index.html app.js app.css manifest.json icons/icon-192.png icons/icon-512.png icons/icon-maskable-512.png sw.js; do
  if [ -f "$DST/$f" ]; then echo "  OK   $f"; else echo "  MISS $f"; fail=1; fi
done

echo "-- index.html 引用 --"
grep -nE '(href|src)="/crm/(app\.(js|css)|manifest\.json|icons/)' "$DST/index.html" || fail=1
echo "-- API_BASE（必须是绝对路径） --"
grep -n "const API_BASE" "$DST/app.js" || fail=1
echo "-- 登录表单：禁存密码 --"
grep -n 'id="loginForm" autocomplete="off"' "$DST/index.html" || fail=1
grep -n 'autocomplete="new-password"' "$DST/index.html" || fail=1
echo "-- 不允许出现的浏览器存储写入 --"
if grep -nE '(localStorage|sessionStorage)\.(setItem|getItem)' "$DST/app.js"; then
  echo "  ERROR: app.js 里不应有任何 localStorage/sessionStorage 读写" >&2; fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "自检未通过" >&2
  exit 1
fi
echo "自检通过 ✅（nginx 的 /crm/ location 由 T9 合入后才能从 8000 端口访问）"
