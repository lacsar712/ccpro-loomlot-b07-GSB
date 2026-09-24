"""染缸状态迁移的唯一判定入口。

三条改状态路径必须共用本模块，不得在路由里另写判断：
1. 开染程（POST /api/dye-lots、染程改挂染缸）—— 自动进入「染程中」；
2. 排液口（POST /api/vats/{id}/drain）—— 进入「排液」；
3. 手工改状态（PUT /api/vats/{id} 的 status）。

迁移图：
    就绪 ready  ⇄  染程中 dyeing  →  排液 drain  →  就绪 ready
排液回到就绪时，该缸不得仍有未作废染程，否则 409。
"""

from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

READY = "ready"
DYEING = "dyeing"
DRAIN = "drain"

VAT_STATUSES = (READY, DYEING, DRAIN)

STATUS_LABELS = {
    READY: "就绪",
    DYEING: "染程中",
    DRAIN: "排液",
}

# 严格邻接边（不含自身）。自身 → 自身视为无变化，一律放行（幂等），
# 例如向已在染程中的缸再开一条染程。
NEXT_STATUS: dict[str, tuple[str, ...]] = {
    READY: (DYEING,),
    DYEING: (READY, DRAIN),
    DRAIN: (READY,),
}

# 染程状态：进行中 / 已作废
LOT_ACTIVE = "active"
LOT_VOID = "void"
LOT_STATUSES = (LOT_ACTIVE, LOT_VOID)
LOT_STATUS_LABELS = {
    LOT_ACTIVE: "进行中",
    LOT_VOID: "已作废",
}


def next_statuses(current: str) -> List[str]:
    """供列表展示「允许的下一状态」提示。"""
    return list(NEXT_STATUS.get(current, ()))


def has_active_lot(db: Session, vat_id: int) -> bool:
    # 局部导入，避免 models -> services -> models 的导入环。
    from app.models.dye_lot import DyeLot

    return (
        db.query(DyeLot.id)
        .filter(DyeLot.vat_id == vat_id, DyeLot.status != LOT_VOID)
        .first()
        is not None
    )


def assert_vat_transition(db: Session, vat, target: str) -> None:
    """校验 vat.status -> target 是否合法；非法一律抛 409（中文说明）。"""
    current = vat.status
    if target == current:
        return
    if target not in NEXT_STATUS.get(current, ()):
        allowed = NEXT_STATUS.get(current, ())
        allowed_text = "、".join(f"「{STATUS_LABELS[s]}」" for s in allowed) or "无"
        raise HTTPException(
            status_code=409,
            detail=(
                f"非法状态跳跃：染缸不能从「{STATUS_LABELS.get(current, current)}」"
                f"直接改为「{STATUS_LABELS.get(target, target)}」；"
                f"允许的下一状态为 {allowed_text}"
            ),
        )
    if current == DRAIN and target == READY and has_active_lot(db, vat.id):
        raise HTTPException(
            status_code=409,
            detail="该染缸仍有未作废染程，请先处理（作废或删除）染程后再回到就绪",
        )


def apply_vat_status(db: Session, vat, target: str) -> None:
    """三条路径共用的改状态入口：先校验，通过后落值。"""
    assert_vat_transition(db, vat, target)
    vat.status = target
