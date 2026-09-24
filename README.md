# LoomLot-01 · 染坊缸染与色牢度抽检

靛蓝染坊台：按 **染坊 → 染缸 → 染程 → 色牢度** 工序推进，聚焦缸染调度与抽检，不是库存出入库系统。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Backend | FastAPI + SQLAlchemy 2 + Pydantic v2 + Postgres + JWT |
| Frontend | Svelte 4 + Vite + svelte-spa-router |
| 部署 | docker-compose（db + backend + frontend/nginx） |

## 端口

| 服务 | 端口 |
| --- | --- |
| 前端 | **3600** |
| 后端 API | **8600** |
| PostgreSQL | **5439** |

数据库账号：`loomlot` / `loomlot` / 库名 `loomlot`。

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 染坊主管 |
| `dyer` | `123456` | 染程操作员 |

容器启动时 entrypoint 自动建表并 seed。

## 快速启动

```bash
cd D:\work\document\bytecode\claudeCodePro\LoomLot\LoomLot-01
docker compose up -d --build
```

浏览器：http://localhost:3600  
API：http://localhost:8600/api/health

停止：

```bash
docker compose down
```

## 业务实体

1. **DyeHouse** — `name`, `waterNote`, `notes`
2. **Vat** — `dyeHouseId`, `vatCode`, `fiberType`, `capacityL`, `status` ∈ `ready|dyeing|drain`
3. **DyeLot** — `vatId`, `recipeName`, `fabricKg`, `startedAt`, `operatorName`, `status` ∈ `active|void`
4. **FastnessCheck** — `dyeLotId`, `checkedAt`, `washFastness`(1–5), `rubFastness`(>0), `tempC`, `notes`

### 规则

染缸状态迁移收拢在后端唯一函数 `app.services.vat_status.apply_vat_status`，开染程、排液口、手工改状态三条路径共用；任何散落判断导致的非法跳跃都视为缺陷。

状态迁移图（自身 → 自身幂等放行）：

```
                 开染程
   ┌──────────────────────────────┐
   ▼                               │
 就绪 ready  ⇄  染程中 dyeing  ──▶  排液 drain
   ▲              排液口 POST/drain      │
   └────────────── 回到就绪 ◀────────────┘
```

| 当前状态 | 允许的下一状态 |
| --- | --- |
| `ready` 就绪 | `dyeing` |
| `dyeing` 染程中 | `ready`、`drain` |
| `drain` 排液 | `ready` |

- 就绪与染程中可互转；染程中可进排液；**排液只能回到就绪**。
- 一切非法跳跃（如 `ready → drain`、`drain → dyeing`）返回 **409**，`detail` 为中文并列出允许的下一状态。
- 开染程（`POST /api/dye-lots`，含染程改挂目标缸）自动把染缸置为 `dyeing`，同样经过统一判定：排液缸上开染程会 409。
- **排液回到就绪时**，若该缸仍存在未作废染程（`DyeLot.status != "void"`），返回 409，要求先处理染程（作废 `PUT /api/dye-lots/{id}` 置 `status=void`，或删除）。
- `GET /api/vats` 每个染缸返回 `allowedNextStatuses`，供列表展示允许的下一状态提示。
- 看板 `GET /api/dashboard/stats` 的 `vatDrainCount`（排液缸数）与染缸列表中 `status=drain` 的行数一致。

## 主要 API

- `POST /api/auth/login`（OAuth2 表单）
- `GET /api/auth/me`
- `GET/POST/PUT/DELETE /api/dye-houses`
- `GET/POST/PUT/DELETE /api/vats` · `POST /api/vats/{id}/drain`
- `GET/POST/PUT/DELETE /api/dye-lots`
- `GET/POST/PUT/DELETE /api/fastness-checks`
- `GET /api/dashboard/stats`

除登录外需 `Authorization: Bearer <token>`。字段对外为 camelCase。

## 目录

```
LoomLot-01/
├── docker-compose.yml
├── backend/          # FastAPI
├── frontend/         # Svelte 4 + Vite + nginx
└── README.md
```

## 本地开发

### 数据库

```bash
docker compose up -d db
```

### 后端

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
$env:DATABASE_URL="postgresql+psycopg2://loomlot:loomlot@127.0.0.1:5439/loomlot"
python -c "from app.database import Base, engine; from app import models; Base.metadata.create_all(bind=engine)"
python -c "from app.seed import seed; seed()"
uvicorn app.main:app --reload --port 8600
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

开发态 Vite 将 `/api` 代理到 `http://127.0.0.1:8600`。
