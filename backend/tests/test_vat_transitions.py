"""染缸状态迁移端到端测试：三条改状态路径、409 中文、看板/列表一致性、种子。"""

import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.auth import hash_password  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    db.add(User(username="admin", hashed_password=hash_password("123456"),
                role="admin", display_name="主管"))
    db.commit()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # 直接放行鉴权，测试聚焦状态机
    from app.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: db.query(User).first()
    yield db
    app.dependency_overrides.clear()
    db.close()


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def make_vat(client, code="V-1", status="ready", house_id=None):
    if house_id is None:
        r = client.post("/api/dye-houses", json={"name": "坊", "waterNote": "井水", "notes": ""})
        house_id = r.json()["id"]
    r = client.post("/api/vats", json={
        "dyeHouseId": house_id, "vatCode": code, "fiberType": "棉",
        "capacityL": 500, "status": status,
    })
    assert r.status_code == 201, r.text
    return r.json()


def lot_payload(vat_id):
    return {
        "vatId": vat_id,
        "recipeName": "靛蓝",
        "fabricKg": 10,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "operatorName": "工",
    }


# ---------- 合法迁移 ----------

def test_happy_flow_all_edges(client):
    vat = make_vat(client)
    assert vat["status"] == "ready"
    assert vat["allowedNextStatuses"] == ["dyeing"]

    # 开染程：ready -> dyeing
    r = client.post("/api/dye-lots", json=lot_payload(vat["id"]))
    assert r.status_code == 201, r.text
    assert client.get(f"/api/vats/{vat['id']}").json()["status"] == "dyeing"

    # 排液口：dyeing -> drain
    r = client.post(f"/api/vats/{vat['id']}/drain")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "drain"
    assert r.json()["allowedNextStatuses"] == ["ready"]

    # 染程未处理：drain -> ready 必须 409
    r = client.put(f"/api/vats/{vat['id']}", json={"status": "ready"})
    assert r.status_code == 409
    assert "未作废染程" in r.json()["detail"]

    # 作废染程后 drain -> ready 放行
    lot = client.get(f"/api/dye-lots?vatId={vat['id']}").json()[0]
    r = client.put(f"/api/dye-lots/{lot['id']}", json={"status": "void"})
    assert r.status_code == 200, r.text
    r = client.put(f"/api/vats/{vat['id']}", json={"status": "ready"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready"


def test_manual_ready_dyeing_both_directions(client):
    vat = make_vat(client)
    r = client.put(f"/api/vats/{vat['id']}", json={"status": "dyeing"})
    assert r.status_code == 200 and r.json()["status"] == "dyeing"
    assert set(r.json()["allowedNextStatuses"]) == {"ready", "drain"}
    r = client.put(f"/api/vats/{vat['id']}", json={"status": "ready"})
    assert r.status_code == 200 and r.json()["status"] == "ready"


def test_self_transition_is_idempotent(client):
    vat = make_vat(client, status="dyeing")
    # 向已在染程中的缸再开一条染程：dyeing -> dyeing 幂等
    r = client.post("/api/dye-lots", json=lot_payload(vat["id"]))
    assert r.status_code == 201, r.text
    # drain -> drain 排液口幂等
    v2 = make_vat(client, code="V-2", status="drain")
    r = client.post(f"/api/vats/{v2['id']}/drain")
    assert r.status_code == 200, r.text


# ---------- 非法跳跃：三条路径都必须 409 中文 ----------

def test_illegal_manual_jumps_409_chinese(client):
    ready = make_vat(client, code="R")
    drain = make_vat(client, code="D", status="drain")

    # 路径3（手工改状态）：ready -> drain
    r = client.put(f"/api/vats/{ready['id']}", json={"status": "drain"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "非法状态跳跃" in detail and "就绪" in detail and "排液" in detail

    # 路径3：drain -> dyeing
    r = client.put(f"/api/vats/{drain['id']}", json={"status": "dyeing"})
    assert r.status_code == 409
    assert "非法状态跳跃" in r.json()["detail"]


def test_illegal_drain_endpoint_from_ready_409(client):
    # 路径2（排液口）：ready -> drain
    ready = make_vat(client)
    r = client.post(f"/api/vats/{ready['id']}/drain")
    assert r.status_code == 409
    assert "非法状态跳跃" in r.json()["detail"]


def test_create_lot_on_drain_vat_409(client):
    # 路径1（开染程）：drain -X-> dyeing
    drain = make_vat(client, status="drain")
    r = client.post("/api/dye-lots", json=lot_payload(drain["id"]))
    assert r.status_code == 409
    assert "非法状态跳跃" in r.json()["detail"]
    # 状态未被污染
    assert client.get(f"/api/vats/{drain['id']}").json()["status"] == "drain"


def test_relot_to_drain_vat_409(client):
    # 路径1 变体：染程改挂到排液缸同样 409
    src = make_vat(client, code="SRC")
    client.post("/api/dye-lots", json=lot_payload(src["id"]))
    lot = client.get(f"/api/dye-lots?vatId={src['id']}").json()[0]
    drain = make_vat(client, code="DST", status="drain")
    r = client.put(f"/api/dye-lots/{lot['id']}", json={"vatId": drain["id"]})
    assert r.status_code == 409
    assert client.get(f"/api/dye-lots/{lot['id']}").json()["vatId"] == src["id"]


def test_delete_lot_then_drain_to_ready(client):
    # 删除染程也算「处理染程」
    vat = make_vat(client)
    client.post("/api/dye-lots", json=lot_payload(vat["id"]))
    client.post(f"/api/vats/{vat['id']}/drain")
    lot = client.get(f"/api/dye-lots?vatId={vat['id']}").json()[0]
    r = client.delete(f"/api/dye-lots/{lot['id']}")
    assert r.status_code == 204
    r = client.put(f"/api/vats/{vat['id']}", json={"status": "ready"})
    assert r.status_code == 200


# ---------- 看板排液缸数与列表一致 ----------

def test_dashboard_drain_count_matches_list(client):
    make_vat(client, code="A", status="ready")
    make_vat(client, code="B", status="dyeing")
    make_vat(client, code="C", status="drain")
    make_vat(client, code="D", status="drain")

    stats = client.get("/api/dashboard/stats").json()
    rows = client.get("/api/vats").json()
    drain_rows = [v for v in rows if v["status"] == "drain"]
    assert stats["vatDrainCount"] == len(drain_rows) == 2


# ---------- 种子：一口排液缸 + 一口染程中缸 ----------

def test_seed_contains_drain_and_dyeing_vats(monkeypatch):
    import app.seed as seed_mod
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(seed_mod, "SessionLocal", SessionLocal)

    seed_mod.seed()

    db = SessionLocal()
    from app.models.vat import Vat
    from app.models.dye_lot import DyeLot
    drains = db.query(Vat).filter(Vat.status == "drain").all()
    dyeings = db.query(Vat).filter(Vat.status == "dyeing").all()
    assert len(drains) >= 1 and len(dyeings) >= 1
    # 排液缸上的染程必须全部已作废，否则种子自身就无法回就绪
    for v in drains:
        active = db.query(DyeLot).filter(
            DyeLot.vat_id == v.id, DyeLot.status != "void"
        ).count()
        assert active == 0
    db.close()
