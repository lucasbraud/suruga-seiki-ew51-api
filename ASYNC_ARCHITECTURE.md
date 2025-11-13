# Async Task Architecture

This document describes the new asynchronous task architecture that enables non-blocking long-running operations with real-time progress updates and cancellation support.

## Problem Statement

The original implementation used blocking synchronous endpoints:
- Long-running operations (angle adjustment, alignment, motion) blocked the FastAPI worker
- No way to stop operations mid-flight without waiting for completion
- Clients had to wait for full operation completion before getting a response
- No real-time progress updates during execution

## Solution Overview

Industry-standard async task pattern:
1. **POST /execute** → Returns **202 Accepted** with `task_id` immediately
2. **Background execution** → Task runs in thread pool with progress streaming
3. **WebSocket updates** → Real-time progress broadcasts to connected clients
4. **POST /stop/{task_id}** → Graceful cancellation during execution
5. **GET /status/{task_id}** → Poll-based status checking for clients without WebSocket

## Architecture Components

### 1. Task Manager (`app/task_manager.py`)

Central singleton for task state management:

```python
from app.task_manager import task_manager, OperationType, TaskStatus

# Create a task
task = task_manager.create_task(
    operation_type=OperationType.AXIS_MOVEMENT,
    request_data={"axis": 3, "distance": 100}
)

# Get task status
task = task_manager.get_task(task_id)
print(f"Status: {task.status}")  # pending, running, completed, etc.

# Cancel a task
task_manager.cancel_task(task_id)
```

**Features:**
- Single task at a time enforcement (configurable)
- Task history with automatic pruning
- Cancellation via `asyncio.Event`
- Progress tracking with arbitrary data structures

### 2. Base Task Executor (`app/tasks/base_task.py`)

Abstract base class for all operation executors:

```python
from app.tasks.base_task import BaseTaskExecutor

class MyOperationExecutor(BaseTaskExecutor):
    async def execute_operation(self, task, request, controller):
        # Your operation logic here
        result = await controller.my_operation_async(
            request=request,
            cancellation_event=task.cancellation_event,
            progress_callback=self.create_progress_callback(task.task_id)
        )
        return result
```

**Features:**
- Automatic lifecycle management (pending → running → completed/failed/cancelled)
- WebSocket progress broadcasting
- Error handling and logging
- Cancellation checking

### 3. Controller Async Wrappers (`app/controller_manager.py`)

Each long-running operation has an async variant:

```python
# Synchronous (blocking) - OLD
result = controller.move_relative(axis=3, distance=100, speed=50)

# Asynchronous (non-blocking) - NEW
result = await controller.move_relative_async(
    axis_number=3,
    distance=100,
    speed=50,
    cancellation_event=cancellation_event,  # Check this in polling loop
    progress_callback=progress_callback      # Called with progress updates
)
```

**How it works:**
1. Async method wraps synchronous .NET calls in `asyncio.to_thread()`
2. Polling loop checks `cancellation_event.is_set()` on every iteration
3. If cancelled, calls `.Stop()` on .NET object and raises exception
4. Progress callback emits updates during polling (phase changes, position, etc.)

### 4. Task Models (`app/models.py`)

Pydantic models for API responses:

```python
# 202 Accepted response when task is created
class TaskResponse(BaseModel):
    task_id: str
    operation_type: str
    status: str
    status_url: str  # URL to GET /status/{task_id}

# Status polling response
class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending, running, completed, etc.
    progress: dict  # Operation-specific progress data
    result: Optional[dict]  # Result when completed
    error: Optional[str]  # Error message if failed
```

## Implemented Operations

### ✅ Motion (Axis Movement)

**Controller Methods:**
- `move_absolute_async(axis_number, position, speed, cancellation_event, progress_callback)`
- `move_relative_async(axis_number, distance, speed, cancellation_event, progress_callback)`

**Task Executor:**
- `app/tasks/motion_task.py` → `MotionTaskExecutor`

**Progress Updates:**
```python
{
    "axis": 3,
    "current_position": 1523.45,
    "target_position": 1600.0,
    "progress_percent": 65,
    "elapsed_time": 1.3,
    "message": "Movement in progress"
}
```

**Example:** See `examples/test_simple_async_motion_stop.py`

### ✅ Angle Adjustment

**Controller Method:**
- `execute_angle_adjustment_async(request, cancellation_event, progress_callback)`

**Task Executor:**
- `app/tasks/angle_adjustment_task.py` → `AngleAdjustmentTaskExecutor`

**Progress Updates:**
```python
{
    "phase": "AdjustingTx",
    "phase_description": "Adjusting Tx axis",
    "elapsed_time": 15.3,
    "progress_percent": 60,
    "message": "Phase: AdjustingTx"
}
```

### 🚧 Alignment (Flat & Focus) - TODO

Will follow same pattern:
- `execute_flat_alignment_async(...)`
- `execute_focus_alignment_async(...)`

### 🚧 Profile Measurement - TODO

Will follow same pattern:
- `measure_profile_async(...)`

## Usage Examples

### Example 1: Direct Controller Usage (Simple)

```python
import asyncio
from app.controller_manager import SurugaSeikiController

async def move_and_cancel():
    controller = SurugaSeikiController()
    controller.connect("5.146.68.190.1.1")

    # Create cancellation event
    cancel_event = asyncio.Event()

    # Start movement
    movement_task = asyncio.create_task(
        controller.move_relative_async(
            axis_number=3,
            distance=100.0,
            speed=50.0,
            cancellation_event=cancel_event
        )
    )

    # Wait a bit, then cancel
    await asyncio.sleep(0.5)
    cancel_event.set()  # Signal cancellation

    try:
        await movement_task
    except Exception as e:
        print(f"Cancelled: {e}")

    controller.disconnect()

asyncio.run(move_and_cancel())
```

### Example 2: Task System Usage (Full-Featured)

```python
import asyncio
from app.task_manager import task_manager, OperationType
from app.tasks.motion_task import MotionTaskExecutor
from app.controller_manager import SurugaSeikiController

async def move_with_task_system():
    controller = SurugaSeikiController()
    controller.connect("5.146.68.190.1.1")

    # Create task
    request = {
        "movement_type": "relative",
        "axis_number": 3,
        "distance": 100.0,
        "speed": 50.0
    }

    task = task_manager.create_task(
        operation_type=OperationType.AXIS_MOVEMENT,
        request_data=request
    )

    # Create executor
    executor = MotionTaskExecutor(task_manager=task_manager)

    # Execute in background
    task_future = asyncio.create_task(
        executor.execute(task.task_id, request, controller)
    )

    # Cancel after delay
    await asyncio.sleep(0.5)
    task_manager.cancel_task(task.task_id)

    # Wait for completion
    try:
        result = await task_future
    except Exception as e:
        print(f"Task failed: {e}")

    # Check final status
    print(f"Task status: {task.status}")

    controller.disconnect()

asyncio.run(move_with_task_system())
```

### Example 3: REST API Usage (When Implemented)

```bash
# Start movement (returns immediately with 202 Accepted)
curl -X POST http://localhost:8000/move/relative \
  -H "Content-Type: application/json" \
  -d '{"axis_id": 3, "distance": 100, "speed": 50}'

# Response:
# {
#   "task_id": "a1b2c3d4-e5f6-...",
#   "status": "pending",
#   "status_url": "/move/status/a1b2c3d4-e5f6-...",
#   "operation_type": "axis_movement"
# }

# Check status
curl http://localhost:8000/move/status/a1b2c3d4-e5f6-...

# Cancel movement
curl -X POST http://localhost:8000/move/stop/a1b2c3d4-e5f6-...
```

## Testing

### Run Simple Test

```bash
# Direct controller async test (no task system)
python examples/test_simple_async_motion_stop.py
```

**Expected output:**
- Movement starts
- After 0.3 seconds, cancellation is requested
- Axis stops mid-flight (< 100um traveled)
- Shows actual distance traveled vs requested

### Run Full Task System Test

```bash
# Complete task management system test
python examples/test_async_motion_with_stop.py
```

**Expected output:**
- Task created with UUID
- Movement starts in background
- Cancellation processed through task manager
- Task status shows "cancelled"
- Demonstrates full task lifecycle

## Key Design Decisions

### 1. Thread Pool for .NET Calls

**Why:** pythonnet is synchronous and blocks the thread during .NET calls

**Solution:** Use `asyncio.to_thread()` to run blocking operations in thread pool

```python
async def my_async_wrapper():
    def sync_work():
        # Blocking .NET calls here
        axis.MoveRelative(100)
        while axis.IsMoving():
            time.sleep(0.05)

    # Run in thread pool
    return await asyncio.to_thread(sync_work)
```

### 2. Cancellation via asyncio.Event

**Why:** Need thread-safe way to signal cancellation from async code to thread pool

**Solution:** `asyncio.Event` works across threads, checked in polling loops

```python
while True:
    # Check cancellation FIRST
    if cancellation_event.is_set():
        axis.Stop()
        raise Exception("Cancelled")

    # Continue operation
    if not axis.IsMoving():
        break

    time.sleep(0.05)
```

### 3. Progress Callbacks from Thread Pool

**Why:** Need to emit progress from sync thread to async WebSocket broadcasts

**Solution:** Use `asyncio.run_coroutine_threadsafe()` to schedule async from sync

```python
def progress_callback(data):
    loop = asyncio.get_event_loop()
    asyncio.run_coroutine_threadsafe(
        broadcast_progress(data),
        loop
    )
```

### 4. Single Task at a Time

**Why:** Hardware can only perform one angle adjustment / alignment at a time

**Solution:** TaskManager enforces only one task in running/pending state

```python
task = task_manager.create_task(...)  # Raises RuntimeError if task already running
```

## Future Enhancements

### TODO: Implement for Remaining Operations

- [ ] Flat alignment router update
- [ ] Focus alignment router update
- [ ] Profile measurement router update
- [ ] Motion router update (integrate with existing endpoints)

### TODO: WebSocket Integration

- [ ] Add task progress message type to WebSocket broadcasts
- [ ] Emit progress during task execution
- [ ] Update `main.py` to broadcast task updates

### TODO: Lifecycle Management

- [ ] Graceful shutdown: cancel running tasks
- [ ] Wait for .NET Stop() to complete
- [ ] Cleanup task history on shutdown

### Nice to Have

- [ ] Task history endpoint (GET /tasks/history)
- [ ] Task metrics (average duration, success rate)
- [ ] Pause/resume support (if .NET API supports it)
- [ ] Priority queue for multiple tasks

## Troubleshooting

### Task Won't Cancel

**Symptoms:** Cancellation requested but operation continues

**Causes:**
1. Cancellation not checked in polling loop
2. .NET Stop() not called
3. Polling interval too long

**Fix:** Ensure cancellation check is FIRST in while loop:
```python
while True:
    if cancellation_event.is_set():  # Must be first!
        axis.Stop()
        raise Exception("Cancelled")
    # ... rest of loop
```

### Progress Callback Not Working

**Symptoms:** No progress updates during operation

**Causes:**
1. Callback not passed to async method
2. asyncio event loop not running
3. WebSocket not connected

**Fix:** Use `create_progress_callback()` from BaseTaskExecutor:
```python
progress_callback = self.create_progress_callback(task.task_id)
```

### Task Hangs in "stopping" State

**Symptoms:** Task status stuck at "stopping"

**Causes:**
1. .NET Stop() takes time to complete
2. Thread pool task not finishing

**Fix:** Add timeout after Stop() call:
```python
axis.Stop()
time.sleep(0.2)  # Wait for stop to take effect
```

## References

- FastAPI Background Tasks: https://fastapi.tiangolo.com/tutorial/background-tasks/
- asyncio to_thread: https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread
- Industry pattern: GitHub Actions API, AWS Step Functions, Stripe webhooks
