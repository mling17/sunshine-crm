"""
CRM V2 数据字典 API 路由。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Dict, List, Optional

from app.db import db_conn
from app.dicts import (
    DICT_REGISTRY,
    DICT_SEEDS,
    items,
    label_map,
    level,
    validate,
    used_count,
)
from app.routers.auth import require_auth
from app.errors import ApiError


router = APIRouter(
    prefix="/api/crm/dicts",
    tags=["dicts"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=List[Dict[str, Any]])
def list_dicts() -> List[Dict[str, Any]]:
    """获取所有字典列表"""
    result = []
    for code, info in DICT_REGISTRY.items():
        result.append({
            "code": code,
            "name": info["name"],
            "level": info["level"],
            "desc": "",
            "items": items(code)
        })
    return result


@router.get("/{code}", response_model=Dict[str, Any])
def get_dict(code: str) -> Dict[str, Any]:
    """获取单个字典详情"""
    if code not in DICT_REGISTRY:
        raise HTTPException(status_code=404, detail="字典不存在")
    
    info = DICT_REGISTRY[code]
    return {
        "code": code,
        "name": info["name"],
        "level": info["level"],
        "desc": "",
        "items": items(code)
    }


@router.get("/product_model", response_model=List[Dict[str, Any]])
def get_product_models(
    q: Optional[str] = Query(default=None),
    product: Optional[str] = Query(default=None)
) -> List[Dict[str, Any]]:
    """获取产品型号字典项（支持筛选）"""
    all_items = items("product_model")
    
    # 筛选逻辑
    if q:
        all_items = [item for item in all_items if q.lower() in item["label"].lower()]
    
    if product:
        all_items = [item for item in all_items if item.get("meta", {}).get("product") == product]
    
    return all_items


@router.post("/{code}/items", response_model=Dict[str, Any])
def create_dict_item(
    code: str,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """创建字典项（仅 A 类）"""
    # 检查字典是否存在
    if code not in DICT_REGISTRY:
        raise HTTPException(status_code=404, detail="字典不存在")
    
    # 检查字典级别
    dict_level = level(code)
    if dict_level != "A":
        raise HTTPException(status_code=403, detail="该字典不支持新增项")
    
    # 验证 key 格式
    key = payload.get("key", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key 不能为空")
    
    if not key.replace("-", "").replace("_", "").isalnum() or len(key) > 32:
        raise HTTPException(status_code=400, detail="key 格式不正确，必须是 1-32 字符的字母数字、下划线或连字符")
    
    # 检查是否已存在
    if validate(code, key):
        raise ApiError(status_code=409, code="dict_key_exists", message="字典项已存在")
    
    # 获取 label 和 sort
    label = payload.get("label", "").strip()
    sort = payload.get("sort", 0)
    
    # 插入数据库
    try:
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO dict_items (dict_code, key, label, sort, enabled, used) VALUES (?, ?, ?, ?, ?, ?)",
                (code, key, label, sort, 1, 0)
            )
            # 清除缓存
            label_map.cache_clear()
            
            return {
                "key": key,
                "label": label,
                "sort": sort,
                "enabled": True,
                "used": 0
            }
    except Exception as e:
        raise ApiError(status_code=400, code="dict_create_failed", message="创建字典项失败")


@router.put("/{code}/items/{key}", response_model=Dict[str, Any])
def update_dict_item(
    code: str,
    key: str,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """更新字典项（仅 A/B/C 类）"""
    # 检查字典是否存在
    if code not in DICT_REGISTRY:
        raise HTTPException(status_code=404, detail="字典不存在")
    
    # 检查字典级别
    dict_level = level(code)
    if dict_level not in ["A", "B", "C"]:
        raise HTTPException(status_code=403, detail="该字典不支持修改项")
    
    # 检查 key 是否改变（不能修改 key）
    if "key" in payload and payload["key"] != key:
        raise HTTPException(status_code=400, detail="key 不能修改")
    
    # 检查项是否存在
    if not validate(code, key):
        raise HTTPException(status_code=404, detail="字典项不存在")
    
    # 构造更新语句
    updates = {}
    if "label" in payload:
        updates["label"] = payload["label"]
    if "sort" in payload:
        updates["sort"] = payload["sort"]
    if "enabled" in payload:
        updates["enabled"] = 1 if payload["enabled"] else 0
    
    if not updates:
        raise HTTPException(status_code=400, detail="至少需要更新一个字段")
    
    # 执行更新
    try:
        with db_conn() as conn:
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [code, key]
            
            conn.execute(
                f"UPDATE dict_items SET {set_clause} WHERE dict_code = ? AND key = ?",
                values
            )
            # 清除缓存
            label_map.cache_clear()
            
            # 返回更新后的项
            item = items(code, include_disabled=True)[0] if items(code, include_disabled=True) else None
            if item:
                return item
            else:
                return {
                    "key": key,
                    "label": updates.get("label", ""),
                    "sort": updates.get("sort", 0),
                    "enabled": bool(updates.get("enabled", 1)),
                    "used": 0
                }
    except Exception as e:
        raise ApiError(status_code=400, code="dict_update_failed", message="更新字典项失败")


@router.delete("/{code}/items/{key}", response_model=Dict[str, Any])
def delete_dict_item(
    code: str,
    key: str
) -> Dict[str, Any]:
    """删除字典项（仅 A 类且 used=0）"""
    # 检查字典是否存在
    if code not in DICT_REGISTRY:
        raise HTTPException(status_code=404, detail="字典不存在")
    
    # 检查字典级别
    dict_level = level(code)
    if dict_level != "A":
        raise HTTPException(status_code=403, detail="该字典不支持删除项")
    
    # 检查项是否存在
    if not validate(code, key):
        raise HTTPException(status_code=404, detail="字典项不存在")
    
    # 检查是否被使用
    used = used_count(code, key)
    if used > 0:
        raise ApiError(
            status_code=409,
            code="dict_item_in_use",
            message=f"有 {used} 条数据在用，只能停用"
        )
    
    # 执行删除
    try:
        with db_conn() as conn:
            conn.execute(
                "DELETE FROM dict_items WHERE dict_code = ? AND key = ?",
                (code, key)
            )
            # 清除缓存
            label_map.cache_clear()
            
            return {"key": key, "deleted": True}
    except Exception as e:
        raise ApiError(status_code=400, code="dict_delete_failed", message="删除字典项失败")