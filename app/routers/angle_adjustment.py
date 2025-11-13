"""
Angle adjustment endpoints

Updated to support async task management with:
- 202 Accepted responses with task_id
- Non-blocking background execution
- Real-time cancellation support
- Task status polling
"""
import asyncio
from fastapi import APIRouter, HTTPException, status, Response

from ..models import (
    AngleAdjustmentRequest,
    AngleAdjustmentResponse,
    StopAngleAdjustmentRequest,
    AngleAdjustmentErrorCode,
    AngleAdjustmentStatus,
    AdjustingStatus,
    TaskResponse,
    TaskStatusResponse,
)
from ..dependencies import ControllerDep
from ..task_manager import task_manager, OperationType
from ..tasks.angle_adjustment_task import AngleAdjustmentTaskExecutor

router = APIRouter(prefix="/angle-adjustment", tags=["Angle Adjustment"])


@router.get("/error-codes")
async def get_angle_adjustment_error_codes():
    """
    Get all angle adjustment error codes with descriptions.

    Returns:
        List of error code definitions
    """
    return [error.to_dict() for error in AngleAdjustmentErrorCode]


@router.get("/status-codes")
async def get_angle_adjustment_status_codes():
    """
    Get all angle adjustment status codes with descriptions.

    Returns:
        List of status code definitions
    """
    return [status_code.to_dict() for status_code in AngleAdjustmentStatus]


@router.get("/phase-codes")
async def get_adjusting_phase_codes():
    """
    Get all adjusting phase codes with descriptions.

    Returns:
        List of phase code definitions
    """
    return [phase.to_dict() for phase in AdjustingStatus]


@router.post("/execute", status_code=status.HTTP_202_ACCEPTED, response_model=TaskResponse)
async def execute_angle_adjustment(
    request: AngleAdjustmentRequest,
    controller: ControllerDep
):
    """
    Execute angle adjustment for the specified stage (LEFT or RIGHT) - async with task tracking.

    Returns immediately with 202 Accepted and task_id.
    Use GET /angle-adjustment/status/{task_id} to check progress.
    Use POST /angle-adjustment/stop/{task_id} to cancel adjustment.

    The adjustment process involves:
    1. Contact detection on Z-axis
    2. Angle adjustment on Tx-axis
    3. Angle adjustment on Ty-axis

    The stage selection is specified in the request body via the `stage` field.

    Returns:
        TaskResponse with task_id for status polling

    HTTP Status Codes:
        - 202 Accepted: Task created and execution started
        - 409 Conflict: Another task is already running
        - 500 Internal Server Error: Controller not connected or unexpected error
    """
    # Check controller connection
    if not controller.is_connected():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Controller not connected"
        )

    # Create task
    try:
        task = task_manager.create_task(
            operation_type=OperationType.ANGLE_ADJUSTMENT,
            request_data={
                "stage": request.stage.value,
                "gap": request.gap,
                "signal_lower_limit": request.signal_lower_limit,
            }
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    # Create executor and launch background task
    executor = AngleAdjustmentTaskExecutor(task_manager=task_manager)

    asyncio.create_task(
        executor.execute(
            task.task_id,
            request,
            controller
        )
    )

    # Return 202 Accepted with task info
    return TaskResponse(
        task_id=task.task_id,
        operation_type=task.operation_type.value,
        status=task.status.value,
        status_url=f"/angle-adjustment/status/{task.task_id}",
        message=f"{request.stage.name} angle adjustment task created and execution started"
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_angle_adjustment_status(task_id: str):
    """
    Get status of an angle adjustment task.

    Returns current task state including:
    - Task status (pending, running, completed, failed, cancelled)
    - Progress data (phase, signal values, etc.)
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
async def stop_angle_adjustment_task(task_id: str, controller: ControllerDep):
    """
    Cancel a running angle adjustment task.

    Sends cancellation signal to the background task.
    The angle adjustment will stop via AngleAdjustment.Stop() in the polling loop.
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
    # Extract stage from task request data
    if task.request_data and "stage" in task.request_data:
        from ..models import AngleAdjustmentStage
        stage_value = task.request_data["stage"]
        stage = AngleAdjustmentStage(stage_value)
        controller.stop_angle_adjustment(stage)

    return {
        "success": True,
        "task_id": task_id,
        "status": task.status.value,
        "message": "Cancellation requested, angle adjustment stopping"
    }


@router.post("/stop")
async def stop_angle_adjustment(
    request: StopAngleAdjustmentRequest,
    controller: ControllerDep
):
    """
    Immediately stop angle adjustment for specified stage (bypasses task system).

    Use this for emergency stops or when you need immediate hardware stop
    without task tracking.

    For task-based angle adjustments, use POST /angle-adjustment/stop/{task_id} instead.

    Args:
        request: StopAngleAdjustmentRequest containing the stage to stop (LEFT or RIGHT)

    Returns:
        Success status indicating whether the stop command was sent

    HTTP Status Codes:
        - 200 OK: Stop command sent successfully
        - 500 Internal Server Error: Controller not connected or stage not initialized
    """
    success = controller.stop_angle_adjustment(request.stage)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop angle adjustment: Controller not connected or {request.stage.name} stage not initialized"
        )

    return {
        "success": True,
        "message": f"{request.stage.name} angle adjustment stop command sent"
    }
