"""
Optical alignment endpoints for flat and focus alignment

Updated to support async task management with:
- 202 Accepted responses with task_id
- Non-blocking background execution
- Real-time cancellation support
- Task status polling
"""
import asyncio
from fastapi import APIRouter, HTTPException, status, Response, Query
from pydantic import BaseModel

from ..models import (
    FlatAlignmentRequest,
    FocusAlignmentRequest,
    AlignmentResponse,
    AlignmentErrorCode,
    OpticalAlignmentStatus,
    AligningStatusPhase,
    TaskResponse,
    TaskStatusResponse,
)
from ..dependencies import ControllerDep
from ..task_manager import task_manager, OperationType
from ..tasks.alignment_task import AlignmentTaskExecutor

router = APIRouter(prefix="/alignment", tags=["Optical Alignment"])


class PowerMeterResponse(BaseModel):
    """Response model for power meter readings"""
    channel: int
    value_dbm: float
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "channel": 1,
                "value_dbm": -15.3,
                "timestamp": "2025-11-06T10:30:45.123456"
            }
        }


@router.get("/power", response_model=PowerMeterResponse)
async def get_power_meter_reading(
    controller: ControllerDep,
    channel: int = Query(default=1, ge=1, le=2, description="Power meter channel number (1 or 2)")
):
    """
    Get current optical power reading from the power meter.

    This endpoint provides on-demand power meter readings for alignment
    and diagnostic purposes. For continuous streaming of power values,
    use the WebSocket endpoint which includes power_meter data in the
    position_update messages.

    Args:
        channel: Power meter channel number (1 or 2)

    Returns:
        PowerMeterResponse with current power reading in dBm

    HTTP Status Codes:
        - 200 OK: Power reading retrieved successfully
        - 500 Internal Server Error: Controller not connected or power meter error
    """
    from datetime import datetime

    power_value = controller.get_power(channel)

    if power_value is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read power meter channel {channel}: Controller not connected or power meter error"
        )

    return PowerMeterResponse(
        channel=channel,
        value_dbm=power_value,
        timestamp=datetime.now().isoformat()
    )


@router.get("/error-codes")
async def get_alignment_error_codes():
    """
    Get all optical alignment error codes with descriptions.

    Returns:
        List of error code definitions
    """
    return [error.to_dict() for error in AlignmentErrorCode]


@router.get("/status-codes")
async def get_alignment_status_codes():
    """
    Get all optical alignment status codes with descriptions.

    Returns:
        List of status code definitions
    """
    return [status_code.to_dict() for status_code in OpticalAlignmentStatus]


@router.get("/phase-codes")
async def get_aligning_phase_codes():
    """
    Get all aligning phase codes with descriptions.

    Returns:
        List of phase code definitions
    """
    return [phase.to_dict() for phase in AligningStatusPhase]


@router.post("/flat/execute", status_code=status.HTTP_202_ACCEPTED, response_model=TaskResponse)
async def execute_flat_alignment(
    request: FlatAlignmentRequest,
    controller: ControllerDep
):
    """
    Execute flat (2D) optical alignment - async with task tracking.

    Returns immediately with 202 Accepted and task_id.
    Use GET /alignment/status/{task_id} to check progress.
    Use POST /alignment/stop/{task_id} to cancel alignment.

    Performs a 2D optical alignment scan to maximize optical power coupling
    by optimizing X and Y stage positions. The process includes:
    1. Field search to locate the signal
    2. Peak search on X-axis
    3. Peak search on Y-axis
    4. Convergence iterations if needed

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
            operation_type=OperationType.FLAT_ALIGNMENT,
            request_data={
                "alignment_type": "flat",
                "pm_ch": request.pmCh,
                "wavelength": request.wavelength,
            }
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    # Create executor and launch background task
    executor = AlignmentTaskExecutor(task_manager=task_manager)

    asyncio.create_task(
        executor.execute(
            task.task_id,
            {
                "alignment_type": "flat",
                "request": request
            },
            controller
        )
    )

    # Return 202 Accepted with task info
    return TaskResponse(
        task_id=task.task_id,
        operation_type=task.operation_type.value,
        status=task.status.value,
        status_url=f"/alignment/status/{task.task_id}",
        message="Flat alignment task created and execution started"
    )


@router.post("/focus/execute", status_code=status.HTTP_202_ACCEPTED, response_model=TaskResponse)
async def execute_focus_alignment(
    request: FocusAlignmentRequest,
    controller: ControllerDep
):
    """
    Execute focus (3D) optical alignment with Z-axis optimization - async with task tracking.

    Returns immediately with 202 Accepted and task_id.
    Use GET /alignment/status/{task_id} to check progress.
    Use POST /alignment/stop/{task_id} to cancel alignment.

    Performs a 3D optical alignment scan to maximize optical power coupling
    by optimizing X, Y, and Z stage positions. The process includes:
    1. Field search to locate the signal
    2. Peak search on X-axis
    3. Peak search on Y-axis
    4. Peak search on Z-axis (focus optimization)
    5. Convergence iterations if needed

    The zMode parameter controls the Z-axis scan pattern:
    - "Round": Circular/spiral scan pattern
    - "Triangle": Triangular scan pattern
    - "Linear": Linear scan pattern

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
            operation_type=OperationType.FOCUS_ALIGNMENT,
            request_data={
                "alignment_type": "focus",
                "pm_ch": request.pmCh,
                "wavelength": request.wavelength,
                "z_mode": request.zMode,
            }
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    # Create executor and launch background task
    executor = AlignmentTaskExecutor(task_manager=task_manager)

    asyncio.create_task(
        executor.execute(
            task.task_id,
            {
                "alignment_type": "focus",
                "request": request
            },
            controller
        )
    )

    # Return 202 Accepted with task info
    return TaskResponse(
        task_id=task.task_id,
        operation_type=task.operation_type.value,
        status=task.status.value,
        status_url=f"/alignment/status/{task.task_id}",
        message=f"Focus alignment task created and execution started (zMode={request.zMode})"
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_alignment_status(task_id: str):
    """
    Get status of an optical alignment task (flat or focus).

    Returns current task state including:
    - Task status (pending, running, completed, failed, cancelled)
    - Progress data (phase, optical power, etc.)
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
async def stop_alignment_task(task_id: str, controller: ControllerDep):
    """
    Cancel a running optical alignment task.

    Sends cancellation signal to the background task.
    The alignment will stop via Alignment.Stop() in the polling loop.
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
    controller.stop_alignment()

    return {
        "success": True,
        "task_id": task_id,
        "status": task.status.value,
        "message": "Cancellation requested, alignment stopping"
    }
