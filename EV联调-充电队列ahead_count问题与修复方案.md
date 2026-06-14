# EV 联调：充电队列 `ahead_count` 问题与修复方案

> **文档用途**：供 EV 项目组对照修改后端逻辑。  
> **联调场景**：我方前端（EChargeDispatch）调用 EV 后端（如 `comgender-blog.top`）。  
> **关联现象**：管理端桩队列显示有排队，用户端却显示「队列第一位，可以开始充电」；调用 `POST /api/charging/start` 返回 `3003 尚未轮到该车辆充电`。

---

## 1. 问题现象

### 1.1 用户端

- `GET /api/charging/queue-status` 返回 `status=dispatched`，`ahead_count=0`
- 页面提示：**「您已调度至充电桩 #N，队列第一位，可以开始充电」**
- 点击「开始充电」→ `POST /api/charging/start` 失败：

```json
{
  "code": 3003,
  "message": "尚未轮到该车辆充电",
  "data": null
}
```

### 1.2 管理端（同一时刻）

- 某慢桩（如 pile_id=5 / T3）状态为 **充电中**
- 占用 **2/3**（含正在充电车辆）
- 队首为 **V002 · 已充 20.0 度**（`status=charging`）
- 队列中还有第 2 位 **dispatched** 等待车辆

**结论**：管理端队列数据正确，用户端「前方 0 辆」与「可以开始充电」为**错误展示**，与 `start` 接口校验不一致。

---

## 2. 根因分析

### 2.1 管理端与用户端数据来源不同

| 接口 | 队列数据来源 | 是否包含「正在充电」占桩 |
|------|----------------|--------------------------|
| `GET /api/queue/pile/{id}`（管理端） | `pile_queue` 表，按 `position` 排序 | **是**（position=1 常为 charging） |
| `GET /api/charging/queue-status`（用户端） | `QueueService.get_car_position()` | 依赖 `ahead_count` 计算 |

管理端看到的「2/3 占用」来自 `PileQueueDAO.get_count_by_pile()` 及队列明细；用户端能否开始充电，取决于 `ahead_count` 是否与 `pile_queue.position` 一致。

### 2.2 EV 当前 `ahead_count` 逻辑（问题点）

文件：`EV/backend/services/queue_service.py` → `get_car_position()`

```python
if car_request.status in ("dispatched", "charging", "pending_reschedule"):
    ahead = 0
    if car_request.pile_id:
        entry = PileQueue.query.filter_by(
            pile_id=car_request.pile_id,
            request_id=car_request.request_id,
        ).first()
        if entry:
            ahead = max(0, entry.position - 1)
    return { ..., "ahead_count": ahead }
```

**正常情况**（有 `pile_queue` 记录）：

- V002 在 position=1 充电，用户在 position=2 → `ahead = 2 - 1 = 1` ✓

**异常情况**（无 `pile_queue` 记录，但 `status=dispatched` 且 `pile_id` 已赋值）：

- `ahead` 保持默认 **0** ✗
- 用户端误以为队首可充

**与 `start_charging` 不一致**：

文件：`EV/backend/services/charging_service.py`

```python
first = PileQueueDAO.get_first(pile_id)  # position == 1
if not first or first.request_id != req.request_id:
    return None, "not_first_in_queue"
```

- 队首由 `pile_queue` 的 position=1 决定
- 若用户无队列记录，或队首是 V002，则 `start` 必然失败
- 但 `queue-status` 仍可能返回 `ahead_count=0`

### 2.3 典型触发场景

1. 桩上已有车辆 **charging**（占 position=1），后续车辆 **dispatched** 到 position=2  
   → 若 `pile_queue` 记录完整，理论上 `ahead=1`；若记录缺失则误报 `0`。
2. 故障重调度 / 手动调度后，只更新了 `charging_request.pile_id`，未写入 `pile_queue`。
3. 联调文档 §3.7 曾约定顶层返回 `ahead_count`；若线上版本充电区 `position` 未带该字段，前端可能误用默认值 `0`（我方前端已通过 `normalizeQueueStatus` 做兼容，**后端仍应保证语义正确**）。

---

## 3. 修复目标

1. **`ahead_count` 与 `pile_queue.position` 一致**：前方车辆数 = `max(0, position - 1)`。
2. **`queue-status` 与 `start_charging` 使用同一套判断**，避免「显示可开始、接口拒绝」。
3. **无 `pile_queue` 记录时保守处理**：不可默认 `ahead_count=0`。
4. **桩上已有他人活跃充电会话时**，后续 dispatched 车辆不可开始（兜底）。

修复后预期：

| 场景 | `ahead_count` | `POST /charging/start` |
|------|---------------|-------------------------|
| 桩空闲，用户 position=1 | 0 | 成功 |
| 队首 charging，用户 position=2 | 1 | 3003 |
| dispatched 但无 pile_queue 记录 | ≥1（保守） | 3003 |

---

## 4. EV 修改方案

### 4.1 【必改】`EV/backend/services/queue_service.py`

新增 `pile_ahead_count()`，供 `get_car_position` 与 `start_charging` 共用：

```python
from ..dao.pile_queue_dao import PileQueueDAO
from ..dao.user_dao import ChargingSessionDAO


class QueueService:
    # ... 现有方法保持不变 ...

    @staticmethod
    def pile_ahead_count(car_request):
        """充电区前方车辆数，与管理端 pile_queue.position 一致。"""
        if car_request.status == "charging":
            return 0
        pile_id = car_request.pile_id
        if not pile_id:
            return 0

        from ..models.pile_queue import PileQueue
        entry = (
            PileQueue.query
            .filter_by(pile_id=pile_id, request_id=car_request.request_id)
            .first()
        )
        if entry:
            return max(0, entry.position - 1)

        # 已 dispatched 但无 pile_queue 记录：不可默认可开始
        active = ChargingSessionDAO.find_active_by_pile_id(pile_id)
        if active and active.request_id != car_request.request_id:
            return 1
        return PileQueueDAO.get_count_by_pile(pile_id)

    @staticmethod
    def get_car_position(car_request):
        if car_request.status in ("dispatched", "charging", "pending_reschedule"):
            ahead = QueueService.pile_ahead_count(car_request)
            return {
                "position": "充电区",
                "queue_num": car_request.queue_num,
                "pile_id": car_request.pile_id,
                "ahead_count": ahead,
            }
        front_count = WaitingQueueDAO.get_front_count(car_request.request_id)
        return {
            "position": "等候区",
            "queue_num": car_request.queue_num,
            "ahead_count": front_count,
            "front_count": front_count,
        }
```

`request_service.query_state()` **无需修改**（已从 `position.ahead_count` 写入顶层 `ahead_count`）。

### 4.2 【建议】`EV/backend/services/charging_service.py`

在 `start_charging()` 中，与 `queue-status` 对齐：

```python
from ..services.queue_service import QueueService

@staticmethod
def start_charging(car_id, pile_id):
    req = ChargingRequestDAO.find_active_by_car_id(car_id)
    # ... 现有 status / pile_id / pile 校验 ...

    # 与 queue-status 同一逻辑
    if QueueService.pile_ahead_count(req) > 0:
        return None, "not_first_in_queue"

    # 桩上已有他人在充（数据异常兜底）
    active = ChargingSessionDAO.find_active_by_pile_id(pile_id)
    if active and active.car_id != car_id:
        return None, "not_first_in_queue"

    first = PileQueueDAO.get_first(pile_id)
    if not first or first.request_id != req.request_id:
        return None, "not_first_in_queue"

    # ... 创建 session、更新状态（不变）...
```

`request_controller.py` 中错误映射可保持不变：

```python
if err == "not_first_in_queue":
    return error(3003, "尚未轮到该车辆充电")
```

### 4.3 【排查】调度入队完整性（可选）

正常路径 `_dispatch_to_best_pile` / `_apply_assignments` 已调用 `PileQueueDAO.add()`。若仍出现「dispatched 无 pile_queue」，请检查：

- `fault_service.manual_dispatch`
- 故障重调度 `dispatch_pending_reschedules` 再入队逻辑

**原则**：只要 `charging_request.status = dispatched` 且 `pile_id` 非空，必须存在对应 `pile_queue` 记录。

---

## 5. 接口约定（联调确认）

### 5.1 `GET /api/charging/queue-status`（已调度到充电区）

```json
{
  "code": 0,
  "data": {
    "has_request": true,
    "status": "dispatched",
    "pile_id": 5,
    "ahead_count": 1,
    "position": {
      "position": "充电区",
      "pile_id": 5,
      "queue_num": "T3",
      "ahead_count": 1
    }
  }
}
```

**要求**：

- 顶层 `ahead_count` 与 `position.ahead_count` **一致**
- 充电区 **必须** 返回 `ahead_count`（不可省略让调用方默认为 0）

### 5.2 `POST /api/charging/start`

- 仅当 `ahead_count == 0` 且用户为 `pile_queue` position=1 时成功
- 否则返回 `3003`，文案「尚未轮到该车辆充电」

---

## 6. 验收用例

### 用例 A：前车充电中，后车等待

1. 管理员上电并 `start` 全部充电桩
2. **V002** 提交慢充请求 → 调度 → `start` 开始充电（pile_id=5）
3. **V003** 提交慢充请求 → 调度到 **同一 pile_id=5**
4. **V003** 调用 `GET /api/charging/queue-status`  
   - 期望：`ahead_count=1`，`position.ahead_count=1`
5. **V003** 调用 `POST /api/charging/start`  
   - 期望：`code=3003`
6. 管理端 `GET /api/queue/pile/5`  
   - 期望：2 条记录，position=1 为 V002/charging，position=2 为 V003/dispatched

### 用例 B：桩空闲，队首可充

1. 桩无活跃 session，用户为 position=1  
2. `ahead_count=0`，`POST /charging/start` 成功

### 用例 C：数据一致性

- 任意时刻：`ahead_count == 0` 的用户，必须能通过 `start`（在无其他故障前提下）
- 任意时刻：`ahead_count > 0` 的用户，`start` 必须返回 3003

---

## 7. 我方已做兼容（供参考）

| 项目 | 说明 |
|------|------|
| 我方 Django 后端 | 已修复同类 `pile_ahead_count` 逻辑（联调场景 B：EV 前端调我方后端） |
| 我方前端 | `normalizeQueueStatus()` 合并顶层与 `position` 的 `ahead_count`；充电区缺字段时不默认可开始 |
| 联调文档 | 见 `docs/联合验收交叉联调问题与方案.md` §3.7 |

**EV 完成本文 §4 修改并部署后**，我方前端指向 EV 后端时，用户端排队展示应与 `POST /charging/start` 行为一致。

---

## 8. 修改文件清单

| 优先级 | 文件 | 改动 |
|--------|------|------|
| P0 | `EV/backend/services/queue_service.py` | 新增 `pile_ahead_count()`，修改 `get_car_position()` |
| P1 | `EV/backend/services/charging_service.py` | `start_charging()` 调用 `pile_ahead_count()` + 活跃会话检查 |
| P2 | `EV/tests/test_security_and_queue.py` | 增加用例 A/B（见 §6） |

---

## 9. 联系人 / 版本

- 问题发现方：EChargeDispatch 联调（场景 A：我方前端 → EV 后端）
- 文档版本：2026-06-14
- 如有疑问，可对照 EV 本地 `backend/services/queue_service.py` 与联调脚本 `EChargeDispatch/backend/scripts/cross_integration_test.py` 场景 A
