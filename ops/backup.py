#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CRM V1 每日备份
================
职责：SQLite 在线快照 + 照片目录打包 + 14 天本地保留 + 异机（MinIO）存放 + 完整性校验。

设计要点（为什么这么写）：
1. 用 SQLite 在线备份 API（src.backup），不是 cp。cp 一个正在写入的库可能拿到半截页，
   恢复时会损坏；backup API 是事务一致的。
2. 备份完成立刻对快照做 PRAGMA integrity_check，不通过直接失败并保留上一份好的备份，
   不能"备了个坏文件还以为安全"。
3. 本地保留 14 天（按日期目录），异机保留 90 天（MinIO 前缀日期）。
4. 全程加文件锁，避免 timer 与手工执行撞车。
5. 退出码：0 成功；1 备份/校验失败；2 本地成功但异机上传失败（本地仍有备份，需告警）。

用法：
    /usr/bin/python3 /opt/data/crm/ops/backup.py
    /usr/bin/python3 /opt/data/crm/ops/backup.py --no-offsite   # 只做本地
"""
import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone

# ---------- 可配置项（环境变量优先） ----------
DB_PATH       = os.environ.get("CRM_DB", "/opt/data/crm/crm.db")
DB_ENGINE     = os.environ.get("CRM_DB_ENGINE", "sqlite").strip().lower()
UPLOADS_DIR   = os.environ.get("CRM_UPLOADS", "/opt/data/crm/uploads")
BACKUP_ROOT   = os.environ.get("CRM_BACKUP_ROOT", "/opt/data/crm/backups")
LOG_FILE      = os.environ.get("CRM_BACKUP_LOG", "/opt/data/crm/logs/backup.log")
RETENTION_DAYS = int(os.environ.get("CRM_BACKUP_KEEP_DAYS", "14"))

MINIO_ENDPOINT = os.environ.get("CRM_MINIO_ENDPOINT", "<公网中转IP>:9000")
MINIO_ACCESS   = os.environ.get("CRM_MINIO_ACCESS", "")
MINIO_SECRET   = os.environ.get("CRM_MINIO_SECRET", "")
MINIO_BUCKET   = os.environ.get("CRM_MINIO_BUCKET", "crm-backups")
MINIO_KEEP_DAYS = int(os.environ.get("CRM_MINIO_KEEP_DAYS", "90"))

TZ = timezone(timedelta(hours=8))  # 业务在中国，日志统一 CST


def log(level, msg, **extra):
    rec = {"ts": datetime.now(TZ).isoformat(timespec="seconds"),
           "level": level, "msg": msg}
    rec.update(extra)
    line = json.dumps(rec, ensure_ascii=False)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:  # 日志失败不能影响备份本身
        print("log write failed: %r" % (e,), file=sys.stderr, flush=True)


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f%s" % (n, u)
        n /= 1024.0
    return "%.1fTB" % n


def snapshot_db(src_path, dst_path):
    """SQLite 在线一致性快照"""
    src = sqlite3.connect("file:%s?mode=ro" % src_path, uri=True, timeout=30)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)  # 页级复制，事务一致
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()


def integrity_ok(db_path):
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("PRAGMA integrity_check").fetchone()
        return (row and row[0] == "ok"), (row[0] if row else "no-result")
    finally:
        con.close()


def make_archive(stamp, db_snapshot, out_path):
    """把快照库和照片目录打成 tar.gz"""
    with tarfile.open(out_path, "w:gz") as tar:
        tar.add(db_snapshot, arcname="crm.db")
        if os.path.isdir(UPLOADS_DIR) and os.listdir(UPLOADS_DIR):
            tar.add(UPLOADS_DIR, arcname="uploads")
    return os.path.getsize(out_path)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def prune_local(keep_days):
    """按 YYYY-MM-DD 目录名清理本地过期备份"""
    removed = []
    if not os.path.isdir(BACKUP_ROOT):
        return removed
    cutoff = datetime.now(TZ).date() - timedelta(days=keep_days)
    for name in sorted(os.listdir(BACKUP_ROOT)):
        p = os.path.join(BACKUP_ROOT, name)
        if not os.path.isdir(p):
            continue
        try:
            d = datetime.strptime(name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < cutoff:
            shutil.rmtree(p, ignore_errors=True)
            removed.append(name)
    return removed


def upload_offsite(local_file, stamp):
    """上传 MinIO 并回读校验大小（异机 = <公网中转IP>，与本机不是同一台磁盘）"""
    from minio import Minio
    from minio.error import S3Error

    cli = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=False)
    if not cli.bucket_exists(MINIO_BUCKET):
        cli.make_bucket(MINIO_BUCKET)

    obj = "%s/%s/%s" % (stamp[:4], stamp[4:6], os.path.basename(local_file))
    cli.fput_object(MINIO_BUCKET, obj, local_file)
    st = cli.stat_object(MINIO_BUCKET, obj)
    if st.size != os.path.getsize(local_file):
        raise RuntimeError("上传大小不一致: local=%d remote=%d" % (os.path.getsize(local_file), st.size))
    return "s3://%s/%s" % (MINIO_BUCKET, obj)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-offsite", action="store_true", help="只做本地备份")
    args = ap.parse_args()

    if DB_ENGINE != "sqlite":
        log(
            "ERROR",
            "当前不是 SQLite 备份脚本支持的数据库引擎，请使用 mysqldump",
            engine=DB_ENGINE,
            doc="docs/DATABASE-MYSQL-BACKUP-RESTORE.md",
        )
        return 1

    t0 = time.time()
    lock_path = "/tmp/crm-backup.lock"
    lock_fp = open(lock_path, "w")
    try:
        fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("WARN", "已有备份进程在跑，本次跳过")
        return 0

    if not os.path.exists(DB_PATH):
        log("ERROR", "数据库不存在，中止", db=DB_PATH)
        return 1

    now = datetime.now(TZ)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    day_dir = os.path.join(BACKUP_ROOT, now.strftime("%Y-%m-%d"))
    os.makedirs(day_dir, exist_ok=True)

    snapshot = os.path.join(day_dir, "crm.db")
    try:
        snapshot_db(DB_PATH, snapshot)
    except Exception as e:
        log("ERROR", "数据库快照失败", error=repr(e))
        return 1

    ok, detail = integrity_ok(snapshot)
    if not ok:
        log("ERROR", "快照完整性校验失败，已保留旧备份", detail=detail)
        try:
            os.remove(snapshot)
        except OSError:
            pass
        return 1

    archive = os.path.join(day_dir, "crm-%s.tar.gz" % stamp)
    try:
        size = make_archive(stamp, snapshot, archive)
    except Exception as e:
        log("ERROR", "打包失败", error=repr(e))
        return 1
    finally:
        try:
            os.remove(snapshot)  # 中间快照不长期留，避免误用
        except OSError:
            pass

    digest = sha256(archive)
    log("INFO", "本地备份完成", file=archive, size=human(size), sha256=digest)

    pruned = prune_local(RETENTION_DAYS)
    if pruned:
        log("INFO", "清理本地过期备份", removed=pruned, keep_days=RETENTION_DAYS)

    if args.no_offsite:
        log("INFO", "跳过异机上传（--no-offsite）", elapsed="%.1fs" % (time.time() - t0))
        return 0

    if not (MINIO_ACCESS and MINIO_SECRET):
        log("WARN", "未配置异机凭据，本地备份成功但异机未上传", hint="检查 /opt/data/crm/ops/backup.env")
        return 2

    try:
        uri = upload_offsite(archive, stamp)
        log("INFO", "异机备份完成", uri=uri, elapsed="%.1fs" % (time.time() - t0))
    except Exception as e:
        log("ERROR", "异机上传失败（本地备份仍有效）", error=repr(e))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
