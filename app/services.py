"""业务逻辑层：线索转化、图片读取等。"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.db import db_conn
from app.enums import (
    CUSTOMER_TYPE,
    INTENT_LEVEL,
    LEAD_STATUS,
    LEAD_INVALID_REASON,
    SOURCE,
    DEAL_STAGE,
    AFTERSALE_STATUS,
    ORDER_STATUS,
    FOLLOW_OBJECT,
    FOLLOW_METHOD,
    ATTACH_OBJECT,
)
from app.errors import ApiError
from app.models import (
    CustomerOut,
    DealOut,
    LeadOut,
    LeadConvertIn,
    LeadConvertOut,
    LeadDetailOut,
    DuplicateHint,
    OrderOut,
    OrderDetailOut,
    OrderIn,
    OrderUpdate,
    OrderTransitionIn,
    OrderTransitionOut,
    OrderStatusLogOut,
    CarrierOut,
    CarrierIn,
    CarrierUpdate,
)
from app.security import now_iso, now_local_iso

if TYPE_CHECKING:
    from sqlite3 import Connection


def next_no(conn: Connection, table: str, column: str, prefix: str, day: str) -> str:
    """SO-20261031-001 / AS-20261031-001（PLANNER-V3 §5.6：日期段不带横线）。

    调用方常传 ``now_local_iso()[:8]``（形如 ``2026-10-31``），这里统一把非数字剔掉，
    否则会生成 ``SO-2026-10--001`` 这种双横线单号（V2 遗留 bug G-05）。
    单用户单 worker，事务内 MAX+1 足够；UNIQUE 约束是最后一道保险。
    """
    digits = re.sub(r"\D", "", str(day or ""))
    if len(digits) != 8:
        from datetime import datetime as _dt

        digits = _dt.now().strftime("%Y%m%d")
    like = f"{prefix}-{digits}-%"
    row = conn.execute(
        f"SELECT COALESCE(MAX(CAST(substr({column}, -3) AS INTEGER)), 0) AS n "
        f"FROM {table} WHERE {column} LIKE ?",
        (like,),
    ).fetchone()
    return f"{prefix}-{digits}-{int(row['n']) + 1:03d}"


def read_images(photos: list) -> list[tuple[str, str, str, bytes]]:
    """读取图片文件：空条目跳过、非图片 400、单张超 20MB 400、总数 >3 400。

    先全部读完再落盘/写库，保证 400 时磁盘和 DB 都干净（不留半截数据）。
    """
    from app.storage import MAX_PHOTO_BYTES, ext_and_mime
    
    prepared: list[tuple[str, str, str, bytes]] = []
    for upload in photos or []:
        # 确保 upload 是 UploadFile 对象
        if hasattr(upload, 'read'):
            data = upload.read()
            filename = getattr(upload, 'filename', '') or ''
        else:
            # 处理已经读取的数据
            data = upload[3] if len(upload) > 3 else b''
            filename = upload[0] if len(upload) > 0 else ''
            
        # 浏览器空 file input 会送一个 filename 为空、内容为空的条目，直接忽略
        if not filename and not data:
            continue
            
        ext, mime = ext_and_mime(filename, None)
        if not data:
            raise HTTPException(status_code=400, detail=f"照片 {filename} 是空文件")
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"照片 {filename} 超过 {MAX_PHOTO_BYTES // (1024 * 1024)}MB",
            )
        prepared.append((filename or f"photo{ext}", mime, ext, data))

    if len(prepared) > 3:
        raise HTTPException(
            status_code=400, detail=f"一条跟进最多 3 张照片"
        )
    return prepared


def read_files(files: list, *, max_count: int | None = None) -> list[tuple[str, str, str, bytes]]:
    """读取任意类型附件（PLANNER-V3 §6.5）：白名单 + 单文件 20MB + 单条上限 10。

    先全部读完再落盘/写库，保证 400 时磁盘和 DB 都干净。
    """
    from app.storage import MAX_FILE_BYTES, MAX_FILES_PER_FOLLOWUP, ext_and_mime_any

    limit = max_count or MAX_FILES_PER_FOLLOWUP
    prepared: list[tuple[str, str, str, bytes]] = []
    for upload in files or []:
        filename = getattr(upload, "filename", "") or ""
        data = upload.read() if hasattr(upload, "read") else b""
        if not filename and not data:
            continue  # 空 file input
        if not data:
            raise HTTPException(status_code=400, detail=f"附件 {filename} 是空文件")
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"附件 {filename} 超过 {MAX_FILE_BYTES // (1024 * 1024)}MB",
            )
        ext, mime = ext_and_mime_any(filename)
        prepared.append((filename or f"file{ext}", mime, ext, data))
    if len(prepared) > limit:
        raise HTTPException(
            status_code=400,
            detail=f"一条跟进最多 {limit} 个附件，本次选了 {len(prepared)} 个",
        )
    return prepared


def convert_lead(conn: Connection, lead_id: int, convert_in: LeadConvertIn) -> LeadConvertOut:
    """线索转化（单事务 8 步）。

    1. 取线索，status ∈ (new, following) 否则 409 lead_closed
    2. 线索手机与微信都为空 → 400 missing_contact
    3. 去重查询：SELECT id,name,phone,wechat FROM customers
               WHERE (phone = ? AND ? <> '') OR (wechat = ? AND ? <> '')
       命中时：
         mode="link" + link_customer_id ∈ 命中集合        → linked（不建客户）
         mode="new"  + force_new=true                      → forced（强制新建）
         mode="new"  + force_new 非 true                    → 409 duplicate_customer
                                                          （body 带 matches[]，D4 的"提示"）
         mode="link" + link_customer_id 不在命中集合/不存在   → 400 invalid_link_customer
    4. mode=link  → customer = 已存在客户（不改其档案，只挂商机）
       mode=new   → INSERT customers(...)
    5. INSERT deals(customer_id, title, product_type, model, spec, amount,
                   stage='confirm', owner, created_at=now, updated_at=now)
    6. 档案迁移：
       INSERT OR IGNORE INTO customer_tags(customer_id, tag_id)
         SELECT ?, tag_id FROM lead_tags WHERE lead_id = ?
       UPDATE follow_ups SET object_type='customer', object_id=<customer_id>,
              customer_id=<customer_id>
        WHERE object_type='lead' AND object_id=<lead_id>      -- 历史跟进全部搬到客户名下
    7. UPDATE leads SET status='converted', converted_customer_id=?, converted_deal_id=?, 
         updated_at=? WHERE id=?
    8. COMMIT
    """
    # 1. 取线索，status ∈ (new, following) 否则 409 lead_closed
    lead_row = conn.execute(
        "SELECT id, status, phone, wechat, name, lead_type, company_name, "
        "source, source_other, location, note, intent_level, owner "
        "FROM leads WHERE id = ?",
        (lead_id,),
    ).fetchone()
    if lead_row is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    
    if lead_row["status"] not in ("new", "following"):
        raise HTTPException(status_code=409, detail="线索已转化或已失效，无法转化")
    
    # 2. 线索手机与微信都为空 → 400 missing_contact
    if not lead_row["phone"] and not lead_row["wechat"]:
        raise HTTPException(status_code=400, detail="手机和微信至少填一个")
    
    # 3. 去重查询
    duplicate_matches = []
    if lead_row["phone"]:
        customer_rows = conn.execute(
            "SELECT id, name, phone, wechat FROM customers "
            "WHERE (phone = ? AND ? <> '')",
            (lead_row["phone"], lead_row["phone"]),
        ).fetchall()
        for row in customer_rows:
            duplicate_matches.append({
                "object_type": "customer",
                "object_id": row["id"],
                "name": row["name"] or "未知"
            })
    if not duplicate_matches and lead_row["wechat"]:
        customer_rows = conn.execute(
            "SELECT id, name, phone, wechat FROM customers "
            "WHERE (wechat = ? AND ? <> '')",
            (lead_row["wechat"], lead_row["wechat"]),
        ).fetchall()
        for row in customer_rows:
            duplicate_matches.append({
                "object_type": "customer",
                "object_id": row["id"],
                "name": row["name"] or "未知"
            })
    
    # 检查是否需要去重提示
    if convert_in.mode == "new" and not convert_in.force_new:
        if duplicate_matches:
            raise ApiError(
                status_code=409,
                code="duplicate_customer",
                message="已存在相同客户",
                matches=duplicate_matches,
            )
    
    # 检查 link_customer_id 是否在命中集合
    if convert_in.mode == "link":
        if not convert_in.link_customer_id:
            raise HTTPException(status_code=400, detail="链接模式需要指定 link_customer_id")
        
        # 检查客户是否存在且在命中集合中
        customer_exists = False
        for match in duplicate_matches:
            if match["object_id"] == convert_in.link_customer_id:
                customer_exists = True
                break
        
        if not customer_exists:
            raise HTTPException(status_code=400, detail="指定的客户不在去重命中集合中")
    
    # 4. 处理客户创建或链接
    customer_id = None
    dedupe_mode = "none"
    
    if convert_in.mode == "link":
        # 链接到已存在客户
        customer_id = convert_in.link_customer_id
        dedupe_mode = "linked"
    else:
        # 新建客户
        created_at = now_iso()
        
        # 根据线索类型决定客户名称
        if lead_row["lead_type"] == "company":
            customer_name = lead_row["company_name"] or lead_row["name"] or "未知公司"
        else:
            customer_name = lead_row["name"] or "未知"
        
        # 插入客户
        cur = conn.execute(
            """
            INSERT INTO customers 
                (name, phone, wechat, customer_type, company_name, source, 
                 source_other, location, note, intent_level, owner, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_name,
                lead_row["phone"],
                lead_row["wechat"],
                lead_row["lead_type"],
                lead_row["company_name"],
                lead_row["source"],
                lead_row["source_other"],
                lead_row["location"],
                lead_row["note"],
                lead_row["intent_level"],
                lead_row["owner"],
                created_at,
                created_at,
            ),
        )
        customer_id = int(cur.lastrowid or 0)
        dedupe_mode = "forced"
    
    # 5. 插入商机
    deal_in = convert_in.deal
    created_at = now_iso()
    
    # 验证商机阶段（非法枚举 → 400 invalid_enum，计划 §2.6）
    _stages = {"confirm", "quote", "negotiate", "won", "lost"}
    if deal_in.stage is not None and deal_in.stage not in _stages:
        raise HTTPException(status_code=400, detail=f"非法阶段 '{deal_in.stage}'，合法值：confirm、quote、negotiate、won、lost")
    # 验证商机信息
    if not deal_in.title:
        raise HTTPException(status_code=400, detail="商机名称不能为空")
    if deal_in.amount <= 0:
        raise HTTPException(status_code=400, detail="商机金额必须大于0")
    
    cur = conn.execute(
        """
        INSERT INTO deals 
            (customer_id, title, product_type, model, spec, amount, 
             stage, owner, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            deal_in.title,
            deal_in.product_type,
            deal_in.model,
            deal_in.spec,
            deal_in.amount,
            "confirm",  # 默认阶段
            deal_in.owner,
            created_at,
            created_at,
        ),
    )
    deal_id = int(cur.lastrowid or 0)
    
    # 6. 档案迁移
    # 迁移标签
    conn.execute(
        """
        INSERT OR IGNORE INTO customer_tags (customer_id, tag_id)
        SELECT ?, tag_id FROM lead_tags WHERE lead_id = ?
        """,
        (customer_id, lead_id),
    )
    
    # 更新跟进记录
    conn.execute(
        """
        UPDATE follow_ups 
        SET object_type = 'customer', object_id = ?, customer_id = ?
        WHERE object_type = 'lead' AND object_id = ?
        """,
        (customer_id, customer_id, lead_id),
    )
    
    # 7. 更新线索状态
    updated_at = now_iso()
    conn.execute(
        """
        UPDATE leads 
        SET status = 'converted', converted_customer_id = ?, converted_deal_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (customer_id, deal_id, updated_at, lead_id),
    )
    
    # 8. 构造返回结果
    # 获取线索详情
    lead_row = conn.execute(
        "SELECT id, name, phone, wechat, lead_type, company_name, source, "
        "source_other, location, note, intent_level, status, invalid_reason, "
        "invalid_reason_other, converted_customer_id, converted_deal_id, owner, "
        "created_at, updated_at "
        "FROM leads WHERE id = ?",
        (lead_id,),
    ).fetchone()
    
    # 获取客户详情
    customer_row = conn.execute(
        "SELECT id, name, phone, wechat, customer_type, company_name, source, "
        "source_other, location, note, intent_level, owner, created_at, updated_at "
        "FROM customers WHERE id = ?",
        (customer_id,),
    ).fetchone()
    
    # 获取商机详情
    deal_row = conn.execute(
        "SELECT id, customer_id, product_type, model, spec, amount, stage, "
        "closed_at, created_at, updated_at "
        "FROM deals WHERE id = ?",
        (deal_id,),
    ).fetchone()
    
    lead = LeadOut(**dict(lead_row))
    customer = CustomerOut(**dict(customer_row)) if customer_row else None
    deal = DealOut(**dict(deal_row)) if deal_row else None
    
    return LeadConvertOut(lead=lead, customer=customer, deal=deal, dedupe=dedupe_mode)


def transition(conn: Connection, order_id: int, to_status: str, payload: dict) -> dict:
    """
    统一的订单状态转换函数，实现以下功能：
    1. 状态校验（符合状态流转规则）
    2. 字段校验（根据状态需要的字段进行校验）
    3. 单事务处理
    4. 日志记录
    
    Args:
        conn: 数据库连接
        order_id: 订单ID
        to_status: 目标状态
        payload: 包含转换所需参数的字典
    
    Returns:
        包含订单和状态日志的字典
        
    Raises:
        ApiError: 状态转换失败时抛出
    """
    # 获取原始订单信息
    order_row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order_row is None:
        raise ApiError(
            status_code=404,
            code="order_not_found",
            message="订单不存在"
        )
    
    from_status = order_row["status"]
    
    # 验证状态流转是否合法
    valid_transitions = {
        "pending_payment": ["deposit_paid"],
        "deposit_paid": ["producing"],
        "producing": ["balance_paid"],
        "balance_paid": ["ready_to_ship"],
        "ready_to_ship": ["shipped"],
        "shipped": ["completed"],
        "completed": [],
    }
    
    if to_status not in valid_transitions.get(from_status, []):
        raise ApiError(
            status_code=400,
            code="invalid_transition",
            message=f"订单状态从 '{from_status}' 不能流转到 '{to_status}'"
        )
    
    # 开始事务
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except Exception:
            # 调用方可能已开启事务（如先落附件再跃迁）：沿用外层事务
            pass
        
        # 根据目标状态执行相应的逻辑
        if to_status == "deposit_paid":
            # 支付押金逻辑（Q-D：必须等于应收押金，且只能收一次）
            deposit = round(float(payload.get("deposit") or 0), 2)
            due = order_row["deposit_amount"]
            if float(order_row["deposit_paid"] or 0) > 0:
                raise ApiError(
                    status_code=409,
                    code="already_paid",
                    message="押金已经收过了",
                )
            if due is None:
                if deposit <= 0 or deposit > float(order_row["amount"] or 0):
                    raise ApiError(
                        status_code=400,
                        code="invalid_deposit",
                        message="押金金额必须大于 0 且不超过订单总额",
                    )
            elif deposit != round(float(due), 2):
                raise ApiError(
                    status_code=400,
                    code="amount_mismatch",
                    message=f"押金应收 ¥{float(due):,.2f}，实收 ¥{deposit:,.2f}",
                )
            
            # 押金落库（DDL 列：deposit_paid）
            conn.execute(
                "UPDATE orders SET deposit_paid = ?, status = ?, updated_at = ? WHERE id = ?",
                (deposit, to_status, now_iso(), order_id)
            )
            
        elif to_status == "balance_paid":
            # 支付尾款（Q-D：押金未收齐不许收尾款；尾款必须等于应收尾款）
            balance = round(float(payload.get("balance") or 0), 2)
            due_deposit = order_row["deposit_amount"]
            if due_deposit is not None and round(float(order_row["deposit_paid"] or 0), 2) < round(float(due_deposit), 2):
                raise ApiError(
                    status_code=409,
                    code="deposit_unpaid",
                    message="押金还没收齐，不能收尾款",
                )
            due = order_row["balance_amount"]
            if due is None:
                due = round(float(order_row["amount"] or 0) - float(order_row["deposit_paid"] or 0), 2)
            if balance != round(float(due), 2):
                raise ApiError(
                    status_code=400,
                    code="amount_mismatch",
                    message=f"尾款应收 ¥{float(due):,.2f}，实收 ¥{balance:,.2f}",
                )
            
            conn.execute(
                "UPDATE orders SET balance_paid = ?, status = ?, updated_at = ? WHERE id = ?",
                (balance, to_status, now_iso(), order_id)
            )
            
        elif to_status == "producing":
            # 财务确认（系统外）后点"下一步"：仅推进状态
            conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                (to_status, now_iso(), order_id)
            )

        elif to_status == "ready_to_ship":
            # 发货准备逻辑
            logistics_mode = payload.get("logistics_mode")
            carrier_id = payload.get("carrier_id")
            tracking_number = payload.get("tracking_number")
            
            # 根据物流方式验证必要字段
            if logistics_mode in ("free", "agent"):
                if not carrier_id:
                    raise ApiError(
                        status_code=400,
                        code="missing_carrier",
                        message="使用物流公司时必须指定物流公司ID"
                    )
                if not tracking_number:
                    raise ApiError(
                        status_code=400,
                        code="missing_tracking_number",
                        message="使用物流公司时必须填写运单号"
                    )
                # 验证物流公司是否存在
                carrier_row = conn.execute(
                    "SELECT * FROM carriers WHERE id = ?", 
                    (carrier_id,)
                ).fetchone()
                if not carrier_row:
                    raise ApiError(
                        status_code=400,
                        code="carrier_not_found",
                        message="物流公司不存在"
                    )
            else:
                # 自送模式
                carrier_id = None
                tracking_number = "无"
            
            # 更新订单物流信息
            conn.execute(
                "UPDATE orders SET carrier_id = ?, tracking_no = ?, status = ?, updated_at = ? WHERE id = ?",
                (
                    carrier_id,
                    tracking_number,
                    to_status,
                    now_iso(),
                    order_id
                )
            )
            
        elif to_status == "shipped":
            # 已发货：写发货时间
            conn.execute(
                "UPDATE orders SET status = ?, shipped_at = ?, updated_at = ? WHERE id = ?",
                (to_status, now_local_iso(), now_iso(), order_id)
            )
            
        elif to_status == "completed":
            # 已完成：收齐才允许（Q-D：已收 = 总额）
            paid = round(float(order_row["deposit_paid"] or 0) + float(order_row["balance_paid"] or 0), 2)
            total = round(float(order_row["amount"] or 0), 2)
            if paid < total:
                raise ApiError(
                    status_code=409,
                    code="payment_incomplete",
                    message=f"还差 ¥{total - paid:,.2f} 未收，不能标记完成",
                )
            # 已完成：写完成时间（客户确认收货）
            conn.execute(
                "UPDATE orders SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
                (to_status, payload.get("received_at") or now_local_iso(), now_iso(), order_id)
            )
            
        # 插入状态日志（PLANNER-V3 §3.5：event_type 区分 收款/发货/状态变更）
        import json as _json

        note = payload.get("note") or ""
        event_type = {
            "deposit_paid": "pay",
            "balance_paid": "pay",
            "shipped": "ship",
        }.get(to_status, "stage")
        if event_type == "pay":
            money = payload.get("deposit") if to_status == "deposit_paid" else payload.get("balance")
            note = note or f"收{'押金' if to_status == 'deposit_paid' else '尾款'} ¥{float(money or 0):,.2f}"
            detail = _json.dumps({"amount": float(money or 0)}, ensure_ascii=False)
        elif event_type == "ship":
            note = note or f"已发货，运单号 {order_row['tracking_no'] or '—'}"
            detail = _json.dumps({"tracking_no": order_row["tracking_no"]}, ensure_ascii=False)
        else:
            detail = None
        conn.execute(
            "INSERT INTO order_status_log"
            " (order_id, from_status, to_status, event_type, note, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (order_id, from_status, to_status, event_type, note, detail, now_iso()),
        )
        
        # 提交事务
        conn.commit()
        
        # 获取更新后的订单
        updated_order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        
        # 获取最新的状态日志
        latest_log = conn.execute(
            "SELECT * FROM order_status_log WHERE order_id = ? ORDER BY created_at DESC LIMIT 1",
            (order_id,)
        ).fetchone()
        
        return {
            "order": OrderOut(**dict(updated_order)),
            "status_log": OrderStatusLogOut(**dict(latest_log))
        }
        
    except Exception as e:
        # 回滚事务
        conn.rollback()
        raise e