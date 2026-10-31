"""
CRM V2 数据字典 API（PLANNER-V3 §5.10）。

分级权限在服务层强制（不是前端隐藏按钮）：
    A 可增删改 | B 仅改名+排序 | C 仅改名 | D 只读
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from app import dicts as dict_svc
from app import labels as labels_svc
from app.dicts import DICT_REGISTRY
from app.errors import ApiError
from app.routers.auth import require_auth

router = APIRouter(
    prefix="/api/crm/dicts",
    tags=["dicts"],
    dependencies=[Depends(require_auth)],
)

#: key 允许中文（product_type 的 key 就是「天窗」这类业务名），但禁止引号/空格/路径字符
KEY_PATTERN = re.compile(r"^[\w\u4e00-\u9fa5\-]{1,32}$")


def _dict_or_404(code: str) -> Dict[str, Any]:
    if code not in DICT_REGISTRY:
        raise ApiError(status_code=404, code="dict_not_found", message=f"字典 {code} 不存在")
    return DICT_REGISTRY[code]


def _pack(code: str) -> Dict[str, Any]:
    info = DICT_REGISTRY[code]
    return {
        "code": code,
        "name": info["name"],
        "level": info["level"],
        "desc": dict_svc.desc(code),
        "items": dict_svc.items(code),
    }


# ---------------- 读 ----------------


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]], include_in_schema=False)
def list_dicts() -> List[Dict[str, Any]]:
    """12 张字典总览（含每项 used）。"""
    return [_pack(code) for code in DICT_REGISTRY]


@router.get("/product_model", response_model=List[Dict[str, Any]])
def search_product_models(
    q: Optional[str] = Query(default=None, description="型号/尺寸关键字，如 XW、1200"),
    product: Optional[str] = Query(default=None, description="产品类型，如 天窗"),
) -> List[Dict[str, Any]]:
    """型号可搜索下拉 —— 必须声明在 /{code} 之前，否则会被当字典 code 吞掉。"""
    return dict_svc.search_product_models(q, product)


@router.get("/{code}", response_model=Dict[str, Any])
def get_dict(code: str) -> Dict[str, Any]:
    _dict_or_404(code)
    return _pack(code)


# ---------------- 写（分级）----------------


@router.post("/{code}/items", response_model=Dict[str, Any])
def create_item(code: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    info = _dict_or_404(code)
    if info["level"] != "A":
        raise ApiError(
            status_code=403,
            code="dict_level_forbidden",
            message=f"「{info['name']}」是 {info['level']} 类字典，只能改名/排序，不能新增",
        )

    key = str(payload.get("key") or "").strip()
    label = str(payload.get("label") or "").strip()
    if not key or not KEY_PATTERN.match(key):
        raise ApiError(
            status_code=400,
            code="dict_key_invalid",
            message="key 只能用 1–32 位汉字、字母、数字、下划线或连字符",
        )
    if not label:
        raise ApiError(status_code=400, code="dict_label_required", message="显示名不能为空")
    if dict_svc.exists(code, key):
        raise ApiError(status_code=409, code="dict_key_exists", message=f"「{key}」已存在")

    meta = payload.get("meta")
    if meta is not None and not isinstance(meta, dict):
        raise ApiError(status_code=400, code="dict_meta_invalid", message="meta 必须是对象")

    labels_svc.invalidate()
    return dict_svc.create_item(
        code,
        key=key,
        label=label,
        sort=int(payload.get("sort") or 0),
        enabled=bool(payload.get("enabled", True)),
        meta=meta,
    )


#: 各分级允许修改的字段（PLANNER-V3 §1.3 / §4.2）
_LEVEL_FIELDS = {
    "A": {"label", "sort", "enabled", "meta"},
    "B": {"label", "sort"},
    "C": {"label"},
    "D": set(),
}


@router.put("/{code}/items/{key}", response_model=Dict[str, Any])
def update_item(code: str, key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    info = _dict_or_404(code)
    lv = info["level"]
    allowed = _LEVEL_FIELDS.get(lv, set())
    if lv == "D":
        raise ApiError(
            status_code=403,
            code="dict_level_forbidden",
            message=f"「{info['name']}」是系统只读字典，不能修改",
        )
    # 字段级权限：B 只能改名/排序，C 只能改名（越权一律 403，不静默忽略）
    illegal = [f for f in ("label", "sort", "enabled", "meta") if f in payload and f not in allowed]
    if illegal:
        names = {"label": "显示名", "sort": "排序", "enabled": "启用/停用", "meta": "元数据"}
        raise ApiError(
            status_code=403,
            code="dict_field_forbidden",
            message=(
                f"「{info['name']}」是 {lv} 类字典，只能改"
                + "、".join(names[f] for f in sorted(allowed, key=lambda x: list(names).index(x)))
                + f"；不允许改 " + "、".join(names[f] for f in illegal)
            ),
        )
    if "key" in payload and str(payload["key"]) != key:
        raise ApiError(
            status_code=400,
            code="dict_key_immutable",
            message="key 是历史数据依据，保存后不能修改（改显示名即可）",
        )
    if not dict_svc.exists(code, key):
        raise ApiError(status_code=404, code="dict_item_not_found", message=f"字典项 {key} 不存在")

    fields: Dict[str, Any] = {}
    if "label" in payload:
        label = str(payload.get("label") or "").strip()
        if not label:
            raise ApiError(status_code=400, code="dict_label_required", message="显示名不能为空")
        fields["label"] = label
    if "sort" in payload:
        fields["sort"] = int(payload.get("sort") or 0)
    if "enabled" in payload:
        fields["enabled"] = bool(payload["enabled"])
    if "meta" in payload:
        if payload["meta"] is not None and not isinstance(payload["meta"], dict):
            raise ApiError(status_code=400, code="dict_meta_invalid", message="meta 必须是对象")
        fields["meta"] = payload["meta"]
    if not fields:
        raise ApiError(status_code=400, code="dict_nothing_to_update", message="没有要更新的字段")

    return dict_svc.update_item(code, key, **fields)


@router.delete("/{code}/items/{key}", response_model=Dict[str, Any])
def delete_item(code: str, key: str) -> Dict[str, Any]:
    info = _dict_or_404(code)
    if info["level"] != "A":
        raise ApiError(
            status_code=403,
            code="dict_level_forbidden",
            message=f"「{info['name']}」是 {info['level']} 类字典，只能停用，不能删除",
        )
    if not dict_svc.exists(code, key):
        raise ApiError(status_code=404, code="dict_item_not_found", message=f"字典项 {key} 不存在")

    used = dict_svc.used_count(code, key)
    if used > 0:
        raise ApiError(
            status_code=409,
            code="dict_item_in_use",
            message=f"有 {used} 条数据在用，只能停用",
        )
    dict_svc.delete_item(code, key)
    return {"key": key, "deleted": True}