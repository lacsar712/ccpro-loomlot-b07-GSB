"""染缸状态迁移的唯一判定入口。

迁移图::

    ready ⇄ dyeing → drain → ready

- ready（就绪）与 dyeing（染程中）可互转
- dyeing（染程中）可进 drain（排液）
- drain（排液）只能回到 ready（就绪）
- drain → ready 时，若该缸仍存在未作废染程，则拒绝，要求先处理染程

开染程自动入 dyeing、排液口、手工改状态三条路径必须共用本模块，
任何路由都不得自行 setattr(vat, "status", ...) 后绕过校验。
"""

from typing import Dict, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.dye_lot import DyeLot
from app.models.vat import Vat

READY = "ready"
DYEING = "dyeing"
DRAIN = "drain"

# 当前状态 -> 允许迁移到的下一状态
ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
    READY: [DYEING],
    DYEING: [READY, DRAIN],
    DRAIN: [READY],
}

STATUS_LABELS: Dict[str, str] = {
    READY: "就绪",
    DYEING: "染程中",
    DRAIN: "排液",
}


def next_statuses(vat: Vat) -> List[str]:
    """返回该染缸当前允许进入的下一状态（不含当前状态）。"""
    return list(ALLOWED_TRANSITIONS.get(vat.status, []))


def transition_vat_status(db: Session, vat: Vat, target: str) -> None:
    """校验并执行染缸状态迁移。

    非法跳跃统一抛 409，detail 为中文。调用方在本函数返回后自行 commit。
    """
    current = vat.status
    if target == current:
        return

    allowed = ALLOWED_TRANSITIONS.get(current, [])
    if target not in allowed:
        cur_label = STATUS_LABELS.get(current, current)
        allowed_text = "、".join(STATUS_LABELS.get(s, s) for s in allowed) or "无"
        raise HTTPException(
            status_code=409,
            detail=f"染缸当前为「{cur_label}」，不能直接改为「{STATUS_LABELS.get(target, target)}」，"
            f"允许的下一状态：{allowed_text}",
        )

    # 排液回到就绪前，缸上不得残留未作废染程。
    if current == DRAIN and target == READY:
        open_lot = (
            db.query(DyeLot.id)
            .filter(DyeLot.vat_id == vat.id)
            .first()
        )
        if open_lot is not None:
            raise HTTPException(
                status_code=409,
                detail="该染缸仍有未处理染程，请先处理（改挂或删除）染程后再回到就绪",
            )

    vat.status = target
