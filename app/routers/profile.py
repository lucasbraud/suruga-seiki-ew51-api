"""
Profile measurement endpoints
"""
import asyncio
from fastapi import APIRouter, HTTPException, status, Response

from ..models import (
    ProfileMeasurementRequest,
    ProfileDataResponse,
    ProfileErrorCode,
    ProfileMeasurementStatus,
    TaskResponse,
    TaskStatusResponse,
)
from ..dependencies import ControllerDep
from ..task_manager import task_manager, OperationType
from ..tasks.profile_task import ProfileMeasurementTaskExecutor

router = APIRouter(prefix="/profile", tags=["Profile Measurement"])


@router.get("/error-codes")
async def get_profile_error_codes():
    """
    Get all profile measurement error codes with descriptions.
    
    Returns:
        List of error code definitions from manual section 4.7.3.1
    """
    return [error.to_dict() for error in ProfileErrorCode]


@router.get("/status-codes")
async def get_profile_status_codes():
    """
    Get all profile measurement status codes with descriptions.
    
    Returns:
        List of status code definitions from manual section 4.7.3.2
    """
    return [status_code.to_dict() for status_code in ProfileMeasurementStatus]


@router.post("/measure", response_model=ProfileDataResponse)
async def measure_profile(
    request: ProfileMeasurementRequest, 
    controller: ControllerDep,
    response: Response
):
    """
    Execute profile measurement scan with peak detection.

    Performs a profile measurement scan from the current axis position,
    sweeping the specified range, collecting signal data, and identifying
    the peak position automatically.

    Returns:
        ProfileDataResponse with complete measurement data including:
        - All data points (position, signal pairs)
        - Peak position, value, and index
        - Measurement metadata (axis numbers, scan parameters)
        
    HTTP Status Codes:
        - 200 OK: Measurement completed successfully
        - 422 Unprocessable Entity: Measurement failed due to system state 
          (servo not ready, axis error, invalid parameters, etc.)
        - 500 Internal Server Error: Controller not connected or unexpected error
    """

    profile_data = controller.measure_profile(request)

    if profile_data is None:
        # Internal error - controller not connected or invalid configuration
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Profile measurement failed: Controller not connected or invalid axis"
        )

    if not profile_data.success:
        # Measurement failed due to system state - return 422 with detailed error info
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return profile_data

    # Success - return 200 OK with measurement data
    return profile_data


# ========== Async task-based profile measurement ==========

@router.post("/measure/execute", status_code=status.HTTP_202_ACCEPTED, response_model=TaskResponse)
async def execute_profile_measurement(
    request: ProfileMeasurementRequest,
    controller: ControllerDep,
):
    """
    Execute profile measurement asynchronously as a managed task.

    Returns 202 with task info. Poll status and allow cancellation.
    """
    if not controller.is_connected():
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Controller not connected")

    try:
        task = task_manager.create_task(
            operation_type=OperationType.PROFILE_MEASUREMENT,
            request_data={
                "scan_axis": request.scan_axis,
                "scan_range": request.scan_range,
                "scan_speed": request.scan_speed,
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    executor = ProfileMeasurementTaskExecutor(task_manager=task_manager)
    asyncio.create_task(executor.execute(task.task_id, request, controller))

    return TaskResponse(
        task_id=task.task_id,
        operation_type=task.operation_type.value,
        status=task.status.value,
        status_url=f"/profile/status/{task.task_id}",
        message=f"Profile measurement task created on axis {request.scan_axis}",
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_profile_measurement_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")

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
async def stop_profile_measurement_task(task_id: str, controller: ControllerDep):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")

    if task.status.value not in ["pending", "running"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task {task_id} is {task.status.value} and cannot be cancelled",
        )

    try:
        task_manager.cancel_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Issue hardware stop as well (best-effort)
    controller.stop_profile_measurement()

    return {
        "success": True,
        "task_id": task_id,
        "status": task.status.value,
        "message": "Cancellation requested, profile measurement stopping",
    }
