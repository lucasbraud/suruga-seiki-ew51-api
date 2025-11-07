"""
Angle adjustment endpoints
"""
from fastapi import APIRouter, HTTPException, status, Response

from ..models import (
    AngleAdjustmentRequest,
    AngleAdjustmentResponse,
    StopAngleAdjustmentRequest,
    AngleAdjustmentErrorCode,
    AngleAdjustmentStatus,
    AdjustingStatus
)
from ..dependencies import ControllerDep

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


@router.post("/execute", response_model=AngleAdjustmentResponse)
async def execute_angle_adjustment(
    request: AngleAdjustmentRequest,
    controller: ControllerDep,
    response: Response
):
    """
    Execute angle adjustment for the specified stage (LEFT or RIGHT).

    Configures parameters, starts adjustment, waits for completion,
    and returns detailed results.

    The adjustment process involves:
    1. Contact detection on Z-axis
    2. Angle adjustment on Tx-axis
    3. Angle adjustment on Ty-axis

    The stage selection is specified in the request body via the `stage` field.

    Returns:
        AngleAdjustmentResponse with complete adjustment results including:
        - Success status
        - Final status and phase codes with descriptions
        - Execution time
        - Detailed error information if failed

    HTTP Status Codes:
        - 200 OK: Adjustment completed successfully
        - 422 Unprocessable Entity: Adjustment failed due to system state
          (servo not ready, invalid parameters, contact detection failed, etc.)
        - 500 Internal Server Error: Controller not connected or unexpected error
    """

    adjustment_result = controller.execute_angle_adjustment(request)

    if adjustment_result is None:
        # Internal error - controller not connected or not initialized
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Angle adjustment failed: Controller not connected or {request.stage.name} stage not initialized"
        )

    if not adjustment_result.success:
        # Adjustment failed due to system state - return 422 with detailed error info
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return adjustment_result

    # Success - return 200 OK with adjustment results
    return adjustment_result


@router.post("/stop")
async def stop_angle_adjustment(
    request: StopAngleAdjustmentRequest,
    controller: ControllerDep
):
    """
    Stop a currently running angle adjustment for the specified stage.

    This endpoint sends a stop command to the AngleAdjustment controller,
    immediately halting any running adjustment operation on the specified stage.

    The stop command is asynchronous - it sends the stop signal but does not
    wait for the adjustment to fully terminate. The execute endpoint will
    detect the stopped state and return with an appropriate status.

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
