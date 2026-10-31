"""线索管理。

设计要点（已拍板，别再改）：
- 线索字段：手机号/微信号（至少填一个才能创建）、类型/公司名/来源/地区/标签/备注/意向等级
- 状态机：`新线索 → 跟进中 → 已转化 / 已失效`
- 转化：建商机 + 新建客户（线索档案迁移）；去重：命中已有客户 → 提示
- 跟进：挂在线索上的跟进记录（见 3.8 统一模型）
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import db_conn
from app.models import (
    LeadConvertCheckOut,
    LeadConvertIn,
    LeadConvertOut,
    LeadDetailOut,
    LeadIn,
    LeadListOut,
    LeadOut,
    LeadUpdate,
    MAX_TAGS,
)
from app.routers.auth import require_auth
from app.security import now_iso
from app.services import convert_lead, read_images

router = APIRouter(
    prefix="/api/crm",
    tags=["leads"],
    dependencies=[Depends(require_auth)],
)


# ---------------- 查询helper ----------------


def _fetch_lead(conn, lead_id: int) -> LeadOut:
    row = conn.execute(
        """
        SELECT id, name, phone, wechat, lead_type, company_name, source,
               source_other, location, note, intent_level, status,
               invalid_reason, invalid_reason_other, converted_customer_id,
               converted_deal_id, owner, created_at, updated_at
        FROM leads WHERE id = ?
        """,
        (lead_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    tag_rows = conn.execute(
        "SELECT t.name FROM tags t JOIN lead_tags lt ON t.id = lt.tag_id WHERE lt.lead_id = ? ORDER BY t.id",
        (lead_id,),
    ).fetchall()
    return LeadOut(**dict(row), tags=[r[0] for r in tag_rows])


def _fetch_lead_detail(conn, lead_id: int) -> LeadDetailOut:
    row = conn.execute(
        """
        SELECT id, name, phone, wechat, lead_type, company_name, source,
               source_other, location, note, intent_level, status,
               invalid_reason, invalid_reason_other, converted_customer_id,
               converted_deal_id, owner, created_at, updated_at
        FROM leads WHERE id = ?
        """,
        (lead_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    
    # 获取标签
    tags = conn.execute(
        """
        SELECT t.name FROM tags t
        JOIN lead_tags lt ON t.id = lt.tag_id
        WHERE lt.lead_id = ?
        """,
        (lead_id,),
    ).fetchall()
    tag_names = [tag[0] for tag in tags]
    
    # 获取跟进记录
    follow_ups = conn.execute(
        """
        SELECT fu.id, fu.customer_id, fu.deal_id, fu.content, fu.next_date, fu.created_at
        FROM follow_ups fu
        WHERE fu.object_type = 'lead' AND fu.object_id = ?
        ORDER BY fu.created_at DESC
        """,
        (lead_id,),
    ).fetchall()
    
    return LeadDetailOut(
        **dict(row),
        tags=tag_names,
        follow_ups=[dict(row) for row in follow_ups],
    )


# ---------------- 路由 ----------------


@router.get("/leads", response_model=LeadListOut)
def list_leads(
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    intent_level: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> LeadListOut:
    """线索列表。"""
    where_parts: list[str] = []
    params: list[object] = []
    
    if status is not None:
        where_parts.append("status = ?")
        params.append(status)
    if source is not None:
        where_parts.append("source = ?")
        params.append(source)
    if intent_level is not None:
        where_parts.append("intent_level = ?")
        params.append(intent_level)
    if search is not None:
        where_parts.append("(name LIKE ? OR phone LIKE ? OR wechat LIKE ? OR location LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    
    with db_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM leads {where_sql}",
            params,
        ).fetchone()["n"]
        
        offset = (page - 1) * size
        rows = conn.execute(
            f"""
            SELECT id, name, phone, wechat, lead_type, company_name, source,
                   source_other, location, note, intent_level, status,
                   invalid_reason, invalid_reason_other, converted_customer_id,
                   converted_deal_id, owner, created_at, updated_at
            FROM leads {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [size, offset],
        ).fetchall()
        
        items = [LeadOut(**dict(row)) for row in rows]
    
    return LeadListOut(items=items, total=total, page=page, size=size)


@router.post("/leads", response_model=LeadOut)
def create_lead(lead_in: LeadIn) -> LeadOut:
    """建线索。手机/微信至少一个（400 `missing_contact`）；来源必填（400 `invalid_enum`）。"""
    # 验证手机号和微信至少有一个
    if not lead_in.phone and not lead_in.wechat:
        raise HTTPException(status_code=400, detail="手机和微信至少填一个")
    
    # 验证来源枚举
    if lead_in.source not in ["wechat", "phone", "referral", "existing", "stock", "other"]:
        raise HTTPException(status_code=400, detail="来源无效")
    
    created_at = now_iso()
    with db_conn() as conn:
        # 检查是否有重复线索或客户（Q6）
        duplicate_hint = None
        if lead_in.phone:
            # 检查线索
            lead_row = conn.execute(
                "SELECT id, name FROM leads WHERE phone = ?",
                (lead_in.phone,),
            ).fetchone()
            if lead_row:
                duplicate_hint = {
                    "object_type": "lead",
                    "object_id": lead_row["id"],
                    "name": lead_row["name"] or "未知"
                }
            else:
                # 检查客户
                customer_row = conn.execute(
                    "SELECT id, name FROM customers WHERE phone = ?",
                    (lead_in.phone,),
                ).fetchone()
                if customer_row:
                    duplicate_hint = {
                        "object_type": "customer",
                        "object_id": customer_row["id"],
                        "name": customer_row["name"] or "未知"
                    }
        
        if not duplicate_hint and lead_in.wechat:
            # 检查线索
            lead_row = conn.execute(
                "SELECT id, name FROM leads WHERE wechat = ?",
                (lead_in.wechat,),
            ).fetchone()
            if lead_row:
                duplicate_hint = {
                    "object_type": "lead",
                    "object_id": lead_row["id"],
                    "name": lead_row["name"] or "未知"
                }
            else:
                # 检查客户
                customer_row = conn.execute(
                    "SELECT id, name FROM customers WHERE wechat = ?",
                    (lead_in.wechat,),
                ).fetchone()
                if customer_row:
                    duplicate_hint = {
                        "object_type": "customer",
                        "object_id": customer_row["id"],
                        "name": customer_row["name"] or "未知"
                    }

        cur = conn.execute(
            """
            INSERT INTO leads 
                (name, phone, wechat, lead_type, company_name, source, source_other,
                 location, note, intent_level, status, owner, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead_in.name,
                lead_in.phone,
                lead_in.wechat,
                lead_in.lead_type,
                lead_in.company_name,
                lead_in.source,
                lead_in.source_other,
                lead_in.location,
                lead_in.note,
                lead_in.intent_level,
                "new",
                lead_in.owner,
                created_at,
                created_at,
            ),
        )
        lead_id = int(cur.lastrowid or 0)
        
        # 保存标签
        if lead_in.tags:
            for tag_name in lead_in.tags[:MAX_TAGS]:
                # 查找或创建标签
                tag_row = conn.execute(
                    "SELECT id FROM tags WHERE name = ?",
                    (tag_name,),
                ).fetchone()
                if tag_row is None:
                    cur = conn.execute(
                        "INSERT INTO tags (name, created_at) VALUES (?, ?)",
                        (tag_name, now_iso()),
                    )
                    tag_id = int(cur.lastrowid or 0)
                else:
                    tag_id = tag_row["id"]
                
                # 关联标签
                conn.execute(
                    "INSERT OR IGNORE INTO lead_tags (lead_id, tag_id) VALUES (?, ?)",
                    (lead_id, tag_id),
                )
        
        lead = _fetch_lead(conn, lead_id)
    
    if duplicate_hint:
        return LeadOut(**lead.model_dump(exclude={"duplicate_hint"}), duplicate_hint=duplicate_hint)
    return lead


@router.get("/leads/convert-check", response_model=LeadConvertCheckOut)
def convert_check(phone: str | None = None, wechat: str | None = None) -> LeadConvertCheckOut:
    """转化前检查：手机/微信命中已有客户 → 提示。"""
    matches = []
    
    with db_conn() as conn:
        # 检查手机
        if phone:
            # 检查线索
            lead_rows = conn.execute(
                "SELECT id, name FROM leads WHERE phone = ?",
                (phone,),
            ).fetchall()
            for row in lead_rows:
                matches.append({
                    "object_type": "lead",
                    "object_id": row["id"],
                    "name": row["name"] or "未知"
                })
            
            # 检查客户
            customer_rows = conn.execute(
                "SELECT id, name FROM customers WHERE phone = ?",
                (phone,),
            ).fetchall()
            for row in customer_rows:
                matches.append({
                    "object_type": "customer",
                    "object_id": row["id"],
                    "name": row["name"] or "未知"
                })
        
        # 检查微信
        if wechat:
            # 检查线索
            lead_rows = conn.execute(
                "SELECT id, name FROM leads WHERE wechat = ?",
                (wechat,),
            ).fetchall()
            for row in lead_rows:
                matches.append({
                    "object_type": "lead",
                    "object_id": row["id"],
                    "name": row["name"] or "未知"
                })
            
            # 检查客户
            customer_rows = conn.execute(
                "SELECT id, name FROM customers WHERE wechat = ?",
                (wechat,),
            ).fetchall()
            for row in customer_rows:
                matches.append({
                    "object_type": "customer",
                    "object_id": row["id"],
                    "name": row["name"] or "未知"
                })
    
    return LeadConvertCheckOut(has_match=bool(matches), matches=matches)


@router.get("/leads/{lead_id}", response_model=LeadDetailOut)
def get_lead(lead_id: int) -> LeadDetailOut:
    """获取线索详情。"""
    with db_conn() as conn:
        return _fetch_lead_detail(conn, lead_id)


@router.put("/leads/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: int, lead_update: LeadUpdate) -> LeadOut:
    """改线索。终态改 → 409 `lead_closed`。"""
    with db_conn() as conn:
        # 检查线索是否存在
        lead = conn.execute(
            "SELECT status FROM leads WHERE id = ?",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise HTTPException(status_code=404, detail="线索不存在")
        
        # 检查是否为终态
        if lead["status"] in ("converted", "invalid"):
            raise HTTPException(status_code=409, detail="线索已转化或已失效，无法修改")
        
        # 构造更新字段
        updates = []
        params = []
        
        if lead_update.name is not None:
            updates.append("name = ?")
            params.append(lead_update.name)
        if lead_update.phone is not None:
            updates.append("phone = ?")
            params.append(lead_update.phone)
        if lead_update.wechat is not None:
            updates.append("wechat = ?")
            params.append(lead_update.wechat)
        if lead_update.lead_type is not None:
            updates.append("lead_type = ?")
            params.append(lead_update.lead_type)
        if lead_update.company_name is not None:
            updates.append("company_name = ?")
            params.append(lead_update.company_name)
        if lead_update.source is not None:
            updates.append("source = ?")
            params.append(lead_update.source)
        if lead_update.source_other is not None:
            updates.append("source_other = ?")
            params.append(lead_update.source_other)
        if lead_update.location is not None:
            updates.append("location = ?")
            params.append(lead_update.location)
        if lead_update.note is not None:
            updates.append("note = ?")
            params.append(lead_update.note)
        if lead_update.intent_level is not None:
            updates.append("intent_level = ?")
            params.append(lead_update.intent_level)
        
        if updates:
            updates.append("updated_at = ?")
            params.append(now_iso())
            params.append(lead_id)
            sql = f"UPDATE leads SET {', '.join(updates)} WHERE id = ?"
            conn.execute(sql, params)
            
            # 处理标签更新
            if lead_update.tags is not None:
                # 删除现有标签
                conn.execute("DELETE FROM lead_tags WHERE lead_id = ?", (lead_id,))
                
                # 添加新标签
                if lead_update.tags:
                    for tag_name in lead_update.tags[:MAX_TAGS]:
                        # 查找或创建标签
                        tag_row = conn.execute(
                            "SELECT id FROM tags WHERE name = ?",
                            (tag_name,),
                        ).fetchone()
                        if tag_row is None:
                            cur = conn.execute(
                                "INSERT INTO tags (name) VALUES (?)",
                                (tag_name,),
                            )
                            tag_id = int(cur.lastrowid or 0)
                        else:
                            tag_id = tag_row["id"]
                        
                        # 关联标签
                        conn.execute(
                            "INSERT OR IGNORE INTO lead_tags (lead_id, tag_id) VALUES (?, ?)",
                            (lead_id, tag_id),
                        )
        
        return _fetch_lead(conn, lead_id)


@router.post("/leads/{lead_id}/invalidate", response_model=LeadOut)
def invalidate_lead(lead_id: int, reason: dict) -> LeadOut:
    """置失效。必选原因（`other` 需文本）。"""
    invalid_reason = reason.get("invalid_reason")
    invalid_reason_other = reason.get("invalid_reason_other")
    
    if not invalid_reason:
        raise HTTPException(status_code=400, detail="必须指定失效原因")
    
    # 验证失效原因枚举
    valid_reasons = ["invalid_phone", "blacklist", "no_intent", "duplicate", "other"]
    if invalid_reason not in valid_reasons:
        raise HTTPException(status_code=400, detail="失效原因无效")
    
    if invalid_reason == "other" and not invalid_reason_other:
        raise HTTPException(status_code=400, detail="失效原因为'其他'时必须填写详细说明")
    
    with db_conn() as conn:
        # 检查线索是否存在
        lead = conn.execute(
            "SELECT status FROM leads WHERE id = ?",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise HTTPException(status_code=404, detail="线索不存在")
        
        # 检查是否为终态
        if lead["status"] in ("converted", "invalid"):
            raise HTTPException(status_code=409, detail="线索已转化或已失效")
        
        updated_at = now_iso()
        conn.execute(
            """
            UPDATE leads 
            SET status = 'invalid', invalid_reason = ?, invalid_reason_other = ?, updated_at = ?
            WHERE id = ?
            """,
            (invalid_reason, invalid_reason_other, updated_at, lead_id),
        )
        
        return _fetch_lead(conn, lead_id)



@router.post("/leads/{lead_id}/convert", response_model=LeadConvertOut)
def convert_lead_endpoint(lead_id: int, convert_in: LeadConvertIn) -> LeadConvertOut:
    """线索转化。"""
    with db_conn() as conn:
        return convert_lead(conn, lead_id, convert_in)