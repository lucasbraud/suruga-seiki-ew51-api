# Suruga Seiki EW51 API - Senior Developer Architecture Analysis

## Executive Summary

**Status:** ⚠️ **PRODUCTION-READY BUT HARDWARE-DEPENDENT**

The suruga-seiki-ew51-api is a well-architected FastAPI microservice for controlling Suruga Seiki DA1000/DA1100 probe stations. However, it **critically lacks MOCK_MODE** for development without hardware, unlike the exfo-ctp10-api.

**Critical Gap:** No development/testing capability without physical hardware.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (React/TypeScript)                  │
│                     ❌ NOT YET IMPLEMENTED                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP REST + WebSocket
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│           Suruga Seiki EW51 API (Port 8001)                     │
│           FastAPI + pythonnet + WebSocket                       │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  app/main.py - Application Lifecycle                     │  │
│  │  ─────────────────────────────────────────────────────── │  │
│  │  - Background tasks (position streaming @ 10Hz)          │  │
│  │  - Connection health monitoring                          │  │
│  │  - WebSocket connection manager                          │  │
│  │  - Auto-connect on startup                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  app/controller_manager.py - Hardware Abstraction        │  │
│  │  ─────────────────────────────────────────────────────── │  │
│  │  ⚠️  PYTHONNET + .NET DLL (srgmc.dll)                    │  │
│  │  - 3,547 lines of comprehensive API wrapper              │  │
│  │  - Thread-safe with RLock                                │  │
│  │  - 12-axis motion control                                │  │
│  │  - Complex operations (alignment, profile, angle adjust) │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  app/routers/ - REST API Endpoints                       │  │
│  │  ─────────────────────────────────────────────────────── │  │
│  │  ✅ connection.py    - Connect/disconnect/status         │  │
│  │  ✅ servo.py         - On/off/batch operations           │  │
│  │  ✅ motion.py        - Move (async task-based)           │  │
│  │  ✅ position.py      - Position queries                  │  │
│  │  ✅ alignment.py     - Optical alignment                 │  │
│  │  ✅ profile.py       - Profile measurement scans         │  │
│  │  ✅ angle_adjustment.py - Angle adjustment (DA1100 only) │  │
│  │  ✅ io.py            - Digital/analog I/O                │  │
│  │  ✅ websocket.py     - WebSocket streaming               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  app/tasks/ - Async Task System                          │  │
│  │  ─────────────────────────────────────────────────────── │  │
│  │  - 202 Accepted pattern for long-running operations      │  │
│  │  - Real-time cancellation support                        │  │
│  │  - Task status polling                                   │  │
│  │  - WebSocket progress updates                            │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ pythonnet (.NET interop)
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│             Suruga Seiki .NET DLL (srgmc.dll)                   │
│             Proprietary Hardware Driver                         │
│                                                                 │
│  ⚠️  REQUIRES PHYSICAL HARDWARE CONNECTION                      │
│  ⚠️  NO MOCK/SIMULATOR MODE AVAILABLE                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ ADS Protocol
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│        Suruga Seiki DA1000/DA1100 Probe Station Hardware        │
│        12-axis motorized stage system                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Architectural Strengths

### 1. Comprehensive API Coverage ✅

**All major features implemented:**
- **Multi-axis Control:** 12 axes (linear + rotational)
- **Motion Types:** Absolute, Relative, 2D, 3D interpolation
- **Optical Alignment:** 6 types (Flat, Focus, Single, etc.)
- **Profile Measurement:** Scanning with peak detection
- **Angle Adjustment:** DA1100 specific feature
- **I/O Control:** Digital outputs, analog inputs

**Comparison to EXFO API:**
| Feature | EXFO CTP10 API | Suruga Seiki API |
|---------|---------------|------------------|
| Endpoints | 40+ | 50+ |
| Complexity | Medium | High |
| Hardware Types | 1 model | 2 models (DA1000/DA1100) |
| MOCK Mode | ✅ Yes | ❌ No |

### 2. Async Task Management ✅

**Modern 202 Accepted Pattern:**
```python
# Example: Long-running movement
@router.post("/move/absolute", status_code=202)
async def move_absolute_async(request: MoveAbsoluteRequest):
    task = task_manager.create_task(OperationType.AXIS_MOVEMENT, ...)
    asyncio.create_task(executor.execute(task.task_id, ...))
    return TaskResponse(task_id=..., status_url="/move/status/{task_id}")
```

**Benefits:**
- ✅ Non-blocking API responses
- ✅ Real-time progress updates via WebSocket
- ✅ Cancellation support (POST /move/stop/{task_id})
- ✅ Task status polling (GET /move/status/{task_id})

**Unlike EXFO which uses:**
- Blocking `wait=True` parameter
- Simple polling pattern

### 3. Real-Time WebSocket Streaming ✅

**Production-Ready Features:**
```python
# Background task at 10 Hz (configurable)
async def position_streaming_task():
    while not is_shutting_down:
        positions = controller.get_all_positions()
        digital_outputs = controller.get_all_digital_outputs()
        analog_inputs = controller.get_all_analog_inputs()
        power_value = controller.get_power(channel)

        await manager.broadcast({
            "type": "position_update",
            "timestamp": ...,
            "positions": {...},  # All 12 axes
            "digital_outputs": {...},
            "analog_inputs": {...},
            "power_meter": {...}
        })

        await asyncio.sleep(1.0 / settings.ws_update_rate_hz)
```

**Comparison:**
| Feature | EXFO WebSocket | Suruga WebSocket |
|---------|----------------|------------------|
| Data Streamed | 4-channel power | 12-axis positions + I/O + power |
| Update Rate | 10 Hz (fixed) | 10 Hz (configurable) |
| Reconnection | ✅ Gold Standard | ✅ Connection health monitoring |
| Multi-client | ✅ Yes | ✅ Yes |

### 4. Hardware Abstraction Layer ✅

**controller_manager.py (3,547 lines):**
- Wraps entire .NET DLL API
- Thread-safe with RLock
- Comprehensive error handling
- Type-safe Python interface

**Example:**
```python
class SurugaSeikiController:
    def __init__(self, ads_address: str = "5.146.68.190.1.1"):
        self._lock = threading.RLock()
        self._connected = False
        self._system = None  # .NET Motion.System.Instance
        self._axis_components: Dict[int, Any] = {}  # 1-12 axes

    def connect(self) -> bool:
        # Load .NET DLL
        self._system = Motion.System.Instance
        self._system.SetAddress(self.ads_address)
        # Wait for connection with timeout
        # Initialize 12 axis components
        # Initialize alignment, profile, angle adjustment APIs
```

---

## Critical Architectural Weaknesses

### 1. ❌ NO MOCK MODE (Critical Gap)

**Problem:**
```python
# controller_manager.py line 19-20
import clr
clr.AddReference(str(dll_path / "srgmc.dll"))  # ← REQUIRES PHYSICAL DLL
import SurugaSeiki.Motion as Motion
```

**Impact:**
- ❌ Cannot develop frontend without hardware
- ❌ Cannot run automated tests in CI/CD
- ❌ Cannot demo application without probe station
- ❌ High friction for new developers

**Comparison:**
```python
# EXFO CTP10 has MOCK_MODE
if settings.MOCK_MODE:
    return MockCTP10Manager()
else:
    return CTP10Manager()
```

**What's Needed:**
1. Create `MockSurugaSeikiController` class
2. Add `MOCK_MODE` environment variable
3. Implement simulated positions, movements, I/O
4. Maintain same API interface

### 2. ⚠️ Pythonnet Dependency

**Current Implementation:**
```python
# Requires .NET runtime + Windows (typically)
import pythonnet
pythonnet.load("coreclr")
import clr
```

**Issues:**
- Platform-dependent (.NET CoreCLR on macOS/Linux, .NET Framework on Windows)
- Complex deployment (DLL must be bundled)
- Debugging difficulty (Python ↔ .NET boundary)

**Not necessarily a weakness** (hardware drivers often require this), but adds complexity.

### 3. ⚠️ No Frontend Integration Yet

**Currently Missing:**
- No frontend page for manual control
- No UI for jog controls (+/- buttons)
- No real-time position display
- No servo on/off interface

**EXFO has:**
- Frontend pages in zero-db
- Real-time power charts
- TLS config UI
- Sweep controls

---

## Comparison: EXFO vs Suruga

| Aspect | EXFO CTP10 API | Suruga Seiki API | Winner |
|--------|----------------|------------------|--------|
| **Architecture** | ||||
| Lines of Code | ~2,000 | ~5,000 | Tie |
| Routers | 6 | 9 | Suruga |
| Async Pattern | Basic (wait param) | Advanced (202 Accepted) | Suruga |
| Task Management | No | Yes (full system) | Suruga |
| **Hardware** | |||
| Mock Mode | ✅ Yes | ❌ No | EXFO |
| Hardware Library | pymeasure (Python) | .NET DLL (pythonnet) | EXFO |
| Platform Support | Cross-platform | .NET required | EXFO |
| **WebSocket** | |||
| Streaming | Power data (4 channels) | Positions + I/O (12+ channels) | Suruga |
| Update Rate | Fixed 10Hz | Configurable 1-100Hz | Suruga |
| Heartbeat | ✅ 30s | ✅ Connection health | Tie |
| Reconnection | ✅ Gold Standard | ✅ Auto-reconnect | Tie |
| **Frontend** | |||
| Control Pages | ✅ Yes | ❌ No | EXFO |
| Real-time Charts | ✅ Yes | ❌ No | EXFO |
| Integration | ✅ Complete | ❌ Pending | EXFO |
| **Overall** | Mature, tested | Feature-rich, needs polish | Tie |

---

## Recommended Improvements

### Priority 1: MOCK MODE (CRITICAL) 🔥

**Why:** Enables development without $50K+ hardware

**Implementation Plan:**
```python
# app/mock_controller.py
class MockSurugaSeikiController:
    """Simulated probe station for development."""

    def __init__(self, ads_address: str = "5.146.68.190.1.1"):
        self._lock = threading.RLock()
        self._connected = False
        self._positions: Dict[int, float] = {i: 0.0 for i in range(1, 13)}
        self._servos_on: Dict[int, bool] = {i: False for i in range(1, 13)}
        self._moving: Dict[int, bool] = {i: False for i in range(1, 13)}

    def connect(self) -> bool:
        """Simulate successful connection."""
        self._connected = True
        logger.info("MOCK: Connected to simulated probe station")
        return True

    def move_absolute(self, axis: int, position: float, speed: float):
        """Simulate movement with gradual position update."""
        self._moving[axis] = True
        # Simulate movement over time (update in background task)
        # ...

    def get_position(self, axis: int) -> AxisStatus:
        """Return simulated position."""
        return AxisStatus(
            axis_number=axis,
            actual_position=self._positions[axis],
            is_moving=self._moving[axis],
            is_servo_on=self._servos_on[axis],
            is_error=False,
            error_code=0
        )
```

**Factory Pattern:**
```python
# app/factory.py
from app.config import settings

def create_controller():
    if settings.MOCK_MODE:
        from app.mock_controller import MockSurugaSeikiController
        return MockSurugaSeikiController(settings.ads_address)
    else:
        from app.controller_manager import SurugaSeikiController
        return SurugaSeikiController(settings.ads_address)
```

**Environment Variable:**
```bash
# .env
SURUGA_MOCK_MODE=true  # Enable mock mode for development
```

### Priority 2: Frontend Control Page 🎨

**Requirement:** Match Suruga Seiki Software GUI shown in user's image

**Features to Implement:**

1. **Axis Control Panel (12 axes):**
   - X1, Y1, Z1, Tx1, Ty1, Tz1 (Left stage)
   - X2, Y2, Z2, Tx2, Ty2, Tz2 (Right stage)

2. **Per-Axis Controls:**
   - **Position Display:** Current position in µm or degrees
   - **Target Input:** Text field for absolute position
   - **Jog Buttons:** `-` and `+` for incremental moves
   - **Speed Control:** Dropdown or slider
   - **Servo Status:** Indicator (green = on, gray = off)

3. **Batch Operations:**
   - **All Servos ON** button
   - **All Servos OFF** button
   - **Stop All** emergency stop

4. **Real-Time Updates:**
   - WebSocket connection to `/ws`
   - Live position updates @ 10Hz
   - Moving indicator (animated)

5. **Layout:**
   ```
   ┌─────────────────────────────────────────────────────────────┐
   │  Suruga Seiki Stage Control                                 │
   │                                                             │
   │  [All Servos ON]  [All Servos OFF]  [Emergency Stop]       │
   │                                                             │
   │  Left Stage (X1, Y1, Z1, Tx1, Ty1, Tz1)                    │
   │  ┌──────────┬────────────┬────────────┬────────────────┐   │
   │  │ X1       │ Target: __ │ [-] [+]    │ Speed: ___     │   │
   │  │ 0.00 µm  │ Current    │ Jog        │ Servo: ON/OFF  │   │
   │  └──────────┴────────────┴────────────┴────────────────┘   │
   │  ... (repeat for Y1, Z1, Tx1, Ty1, Tz1)                    │
   │                                                             │
   │  Right Stage (X2, Y2, Z2, Tx2, Ty2, Tz2)                   │
   │  ... (similar layout)                                       │
   │                                                             │
   │  I/O Status                                                 │
   │  Digital Out: LEFT [LOCKED/UNLOCKED]  RIGHT [LOCKED/...]   │
   │  Analog In: CH1: ___ V  CH2: ___ V                         │
   │  Power Meter: CH1: ___ dBm                                 │
   └─────────────────────────────────────────────────────────────┘
   ```

### Priority 3: Documentation & Examples 📚

**Add:**
- API usage examples (like exfo-ctp10-api has)
- Mock mode testing guide
- Frontend integration guide
- Architecture diagrams

---

## Implementation Roadmap

### Phase 1: MOCK Mode (Estimated: 4-6 hours)

1. ✅ Create `app/mock_controller.py`
2. ✅ Add MOCK_MODE config to `app/config.py`
3. ✅ Implement factory pattern in `app/factory.py`
4. ✅ Update `app/main.py` to use factory
5. ✅ Test all endpoints with MOCK_MODE=true
6. ✅ Document MOCK_MODE usage

**Deliverables:**
- Fully functional API without hardware
- Same API interface as real controller
- Simulated movements, positions, I/O

### Phase 2: Frontend Control Page (Estimated: 6-8 hours)

1. ✅ Create feature branch `feature/suruga-control-ui`
2. ✅ Add Suruga route in zero-db frontend
3. ✅ Implement axis control components
4. ✅ Add WebSocket integration for real-time updates
5. ✅ Implement jog buttons (+/- movement)
6. ✅ Add batch servo controls
7. ✅ Style to match Suruga Software GUI
8. ✅ Test with MOCK_MODE backend

**Deliverables:**
- `/suruga` page in zero-db frontend
- Real-time position updates
- Full manual control interface
- WebSocket connection with reconnection

### Phase 3: Testing & Polish (Estimated: 2-3 hours)

1. ✅ End-to-end testing (frontend + MOCK backend)
2. ✅ Error handling (connection loss, etc.)
3. ✅ Performance optimization (WebSocket throttling?)
4. ✅ Documentation updates

---

## Technical Debt & Future Work

1. **Consider Removing pythonnet Dependency (Long-term)**
   - Investigate direct hardware protocol (if documented)
   - Or stick with .NET interop (vendor-supported)

2. **Add Authentication**
   - Currently no auth (like EXFO API)
   - Should integrate with zero-db auth system

3. **Add Logging & Monitoring**
   - Structured logging
   - Prometheus metrics
   - Error tracking (Sentry)

4. **CI/CD Pipeline**
   - Automated tests (requires MOCK_MODE)
   - Docker build & deployment
   - E2E tests

---

## Conclusion

**Overall Assessment: 8/10**

**Strengths:**
- ✅ Comprehensive API coverage
- ✅ Modern async task management
- ✅ Production-ready WebSocket streaming
- ✅ Well-structured codebase
- ✅ Good error handling

**Weaknesses:**
- ❌ No MOCK mode (critical for development)
- ❌ No frontend integration yet
- ⚠️ Platform dependency (pythonnet)

**Comparison to EXFO:**
- Suruga is more feature-rich (task system, more axes)
- EXFO is more mature (MOCK mode, frontend, testing)
- Both are production-quality code

**Recommendation:**
1. **Immediately implement MOCK_MODE** (highest priority)
2. **Build frontend control page** (user-facing value)
3. **Add comprehensive testing** (enabled by MOCK mode)
4. **Document extensively** (for team adoption)

With MOCK_MODE and frontend, this will be a **10/10 production system**.
