from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.dye_house import DyeHouse
from app.models.user import User
from app.models.vat import Vat
from app.schemas.vat import VatCreate, VatUpdate, VatOut
from app.services.vat_status import DRAIN, apply_vat_status, next_statuses

router = APIRouter(prefix="/api/vats", tags=["vats"])


def to_out(vat: Vat) -> VatOut:
    out = VatOut.model_validate(vat)
    return out.model_copy(update={"allowed_next_statuses": next_statuses(vat.status)})


@router.get("", response_model=List[VatOut])
def list_vats(
    dye_house_id: Optional[int] = Query(None, alias="dyeHouseId"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Vat)
    if dye_house_id is not None:
        q = q.filter(Vat.dye_house_id == dye_house_id)
    return [to_out(v) for v in q.order_by(Vat.id).all()]


@router.post("", response_model=VatOut, status_code=status.HTTP_201_CREATED)
def create_vat(
    payload: VatCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    house = db.query(DyeHouse).filter(DyeHouse.id == payload.dye_house_id).first()
    if not house:
        raise HTTPException(status_code=400, detail="染坊不存在")
    item = Vat(
        dye_house_id=payload.dye_house_id,
        vat_code=payload.vat_code,
        fiber_type=payload.fiber_type,
        capacity_l=payload.capacity_l,
        status=payload.status,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="同坊染缸编号已存在")
    db.refresh(item)
    return to_out(item)


@router.get("/{vat_id}", response_model=VatOut)
def get_vat(
    vat_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = db.query(Vat).filter(Vat.id == vat_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="染缸不存在")
    return to_out(item)


@router.put("/{vat_id}", response_model=VatOut)
def update_vat(
    vat_id: int,
    payload: VatUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = db.query(Vat).filter(Vat.id == vat_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="染缸不存在")
    data = payload.model_dump(exclude_unset=True)
    if "dye_house_id" in data:
        house = db.query(DyeHouse).filter(DyeHouse.id == data["dye_house_id"]).first()
        if not house:
            raise HTTPException(status_code=400, detail="染坊不存在")
    new_status = data.pop("status", None)
    for k, v in data.items():
        setattr(item, k, v)
    if new_status is not None:
        # 手工改状态：与开染程、排液口共用同一判定函数。
        apply_vat_status(db, item, new_status)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="同坊染缸编号已存在")
    db.refresh(item)
    return to_out(item)


@router.post("/{vat_id}/drain", response_model=VatOut)
def drain_vat(
    vat_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """排液口：染程中 → 排液。非法来源状态返回 409。"""
    item = db.query(Vat).filter(Vat.id == vat_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="染缸不存在")
    apply_vat_status(db, item, DRAIN)
    db.commit()
    db.refresh(item)
    return to_out(item)


@router.delete("/{vat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vat(
    vat_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = db.query(Vat).filter(Vat.id == vat_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="染缸不存在")
    db.delete(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="该染缸仍有关联记录，无法删除")
