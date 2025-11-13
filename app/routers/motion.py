"""
Motion control endpoints (single axis, 2D, 3D movements)

Updated to support async task management with:
- 202 Accepted responses with task_id
- Non-blocking background execution
- Real-time cancellation support
- Task status polling
"""
import asyncio
from fastapi import APIRouter, HTTPException, status
from typing import Optional

from ..models import (
    ServoRequest,
    MoveAbsoluteRequest,
    MoveRelativeRequest,
    Move2DRequest,
    Move3DRequest,
    TaskResponse,
    TaskStatusResponse,
)
from ..dependencies import ControllerDep
from ..task_manager import task_manager, OperationType
from ..tasks.motion_task import MotionTaskExecutor

router = APIRouter(prefix="/move", tags=["Motion Control"])


# ========== Async Task-Based Endpoints (NEW) ==========

@router.post("/absolute", status_code=status.HTTP_202_ACCEPTED, response_model=TaskResponse)
async def move_absolute_async(request: MoveAbsoluteRequest, controller: ControllerDep):
    """
    Move axis to absolute position (async with task tracking).

    Returns immediately with 202 Accepted and task_id.
    Use GET /move/status/{task_id} to check progress.
    Use POST /move/stop/{task_id} to cancel movement.
    """
    # Create task
    try:
        task = task_manager.create_task(
            operation_type=OperationType.AXIS_MOVEMENT,
            request_data={
                "movement_type": "absolute",
                "axis_number": request.axis_id,
                "position": request.position,
                "speed": request.speed,
            }
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    # Create executor and launch background task
    executor = MotionTaskExecutor(task_manager=task_manager)

    asyncio.create_task(
        executor.execute(
            task.task_id,
            {
                "movement_type": "absolute",
                "axis_number": request.axis_id,
                "position": request.position,
                "speed": request.speed,
            },
            controller
        )
    )

    # Return 202 Accepted with task info
    return TaskResponse(
        task_id=task.task_id,
        operation_type=task.operation_type.value,
        status=task.status.value,
        status_url=f"/move/status/{task.task_id}",
        message="Movement task created and execution started"
    )


@router.post("/relative", status_code=status.HTTP_202_ACCEPTED, response_model=TaskResponse)
async def move_relative_async(request: MoveRelativeRequest, controller: ControllerDep):
    """
    Move axis relative to current position (async with task tracking).

    Returns immediately with 202 Accepted and task_id.
    Use GET /move/status/{task_id} to check progress.
    Use POST /move/stop/{task_id} to cancel movement.
    """
    # Create task
    try:
        task = task_manager.create_task(
            operation_type=OperationType.AXIS_MOVEMENT,
            request_data={
                "movement_type": "relative",
                "axis_number": request.axis_id,
                "distance": request.distance,
                "speed": request.speed,
            }
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    # Create executor and launch background task
    executor = MotionTaskExecutor(task_manager=task_manager)

    asyncio.create_task(
        executor.execute(
            task.task_id,
            {
                "movement_type": "relative",
                "axis_number": request.axis_id,
                "distance": request.distance,
                "speed": request.speed,
            },
            controller
        )
    )

    # Return 202 Accepted with task info
    return TaskResponse(
        task_id=task.task_id,
        operation_type=task.operation_type.value,
        status=task.status.value,
        status_url=f"/move/status/{task.task_id}",
        message="Movement task created and execution started"
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_movement_status(task_id: str):
    """
    Get status of a movement task.

    Returns current task state including:
    - Task status (pending, running, completed, failed, cancelled)
    - Progress data (position, percentage, etc.)
    - Result data when completed
    - Error message if failed
    """
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )

    return TaskStatusResponse(
        task_id=task.task_id,
        operation_type=task.operation_type.value,
        status=task.status.value,
        progress=task.progress,
        result=task.result,
        error=task.error,
        created_at=task.created_at.isoformat() if task.created_at else None,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


@router.post("/stop/{task_id}")
async def stop_movement_task(task_id: str, controller: ControllerDep):
    """
    Cancel a running movement task.

    Sends cancellation signal to the background task.
    The axis will stop via axis.Stop() in the polling loop.
    """
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )

    if task.status.value not in ["pending", "running"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task {task_id} is {task.status.value} and cannot be cancelled"
        )

    # Set cancellation event
    try:
        task_manager.cancel_task(task_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Also call controller stop for immediate hardware stop
    # Extract axis number from task request data
    if task.request_data and "axis_number" in task.request_data:
        axis_number = task.request_data["axis_number"]
        controller.stop_axis(axis_number)

    return {
        "success": True,
        "task_id": task_id,
        "status": task.status.value,
        "message": "Cancellation requested, movement stopping"
    }


# ========== Direct Control Endpoints (for emergency/immediate stop) ==========

@router.post("/stop")
async def stop_axis_direct(request: ServoRequest, controller: ControllerDep):
    """
    Immediately stop movement of specified axis (bypasses task system).

    Use this for emergency stops or when you need immediate hardware stop
    without task tracking.

    For task-based movements, use POST /move/stop/{task_id} instead.
    """
    axis_id = request.axis_id
    success = controller.stop_axis(axis_id)

    return {
        "success": success,
        "axis_id": axis_id,
        "message": "Axis stopped" if success else "Failed to stop axis"
    }


@router.post("/emergency_stop")
async def emergency_stop(controller: ControllerDep):
    """
    Emergency stop all axes immediately (bypasses task system).

    Cancels any running task and stops all hardware motion.
    """
    # Cancel current task if any
    current_task = task_manager.get_current_task()
    if current_task and current_task.status.value in ["pending", "running"]:
        try:
            task_manager.cancel_task(current_task.task_id)
        except Exception:
            pass

    # Hardware emergency stop
    success = controller.emergency_stop()

    return {
        "success": success,
        "message": "Emergency stop executed" if success else "Failed to execute emergency stop"
    }


# ========== 2D/3D Movement Endpoints (synchronous - no task system yet) ==========

@router.post("/2d")
async def move_2d(request: Move2DRequest, controller: ControllerDep):
    """
    Execute 2D interpolation movement.

    Note: This endpoint is currently synchronous (blocks until complete).
    Task-based async version coming soon.
    """
    if request.relative:
        success = controller.move_2d_relative(
            request.axis1,
            request.axis2,
            request.x,
            request.y,
            request.speed,
            request.angle_offset
        )
    else:
        success = controller.move_2d_absolute(
            request.axis1,
            request.axis2,
            request.x,
            request.y,
            request.speed,
            request.angle_offset
        )

    return {
        "success": success,
        "axes": [request.axis1, request.axis2],
        "x": request.x,
        "y": request.y,
        "relative": request.relative
    }


@router.post("/3d")
async def move_3d(request: Move3DRequest, controller: ControllerDep):
    """
    Execute 3D interpolation movement.

    Note: This endpoint is currently synchronous (blocks until complete).
    Task-based async version coming soon.
    """
    success = controller.move_3d_absolute(
        request.axis1,
        request.axis2,
        request.axis3,
        request.x,
        request.y,
        request.z,
        request.speed,
        request.rotation_center_x,
        request.rotation_center_y
    )

    return {
        "success": success,
        "axes": [request.axis1, request.axis2, request.axis3],
        "x": request.x,
        "y": request.y,
        "z": request.z
    }
