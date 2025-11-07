"""
Optical alignment endpoints for flat and focus alignment
"""
from fastapi import APIRouter, HTTPException, status, Response, Query
from pydantic import BaseModel

from ..models import (
    FlatAlignmentRequest,
    FocusAlignmentRequest,
    AlignmentResponse,
    AlignmentErrorCode,
    OpticalAlignmentStatus,
    AligningStatusPhase
)
from ..dependencies import ControllerDep

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


@router.post("/flat/execute", response_model=AlignmentResponse)
async def execute_flat_alignment(
    request: FlatAlignmentRequest,
    controller: ControllerDep,
    response: Response
):
    """
    Execute flat (2D) optical alignment.

    Performs a 2D optical alignment scan to maximize optical power coupling
    by optimizing X and Y stage positions. The process includes:
    1. Field search to locate the signal
    2. Peak search on X-axis
    3. Peak search on Y-axis
    4. Convergence iterations if needed

    Returns:
        AlignmentResponse with complete alignment results including:
        - Success status
        - Optical power measurements (initial, final, improvement)
        - Peak positions (X, Y)
        - Profile data from all search phases
        - Execution metadata

    HTTP Status Codes:
        - 200 OK: Alignment completed successfully
        - 422 Unprocessable Entity: Alignment failed due to system state
          (servo not ready, field search failed, peak search failed, etc.)
        - 500 Internal Server Error: Controller not connected or unexpected error
    """

    alignment_result = controller.execute_flat_alignment(request)

    if alignment_result is None:
        # Internal error - controller not connected or not initialized
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Flat alignment failed: Controller not connected or Alignment not initialized"
        )

    if not alignment_result.success:
        # Alignment failed due to system state - return 422 with detailed error info
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return alignment_result

    # Success - return 200 OK with alignment results
    return alignment_result


@router.post("/focus/execute", response_model=AlignmentResponse)
async def execute_focus_alignment(
    request: FocusAlignmentRequest,
    controller: ControllerDep,
    response: Response
):
    """
    Execute focus (3D) optical alignment with Z-axis optimization.

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
        AlignmentResponse with complete alignment results including:
        - Success status
        - Optical power measurements (initial, final, improvement)
        - Peak positions (X, Y, Z)
        - Profile data from all search phases (including Z-axis)
        - Execution metadata

    HTTP Status Codes:
        - 200 OK: Alignment completed successfully
        - 422 Unprocessable Entity: Alignment failed due to system state
          (servo not ready, field search failed, peak search failed, etc.)
        - 500 Internal Server Error: Controller not connected or unexpected error
    """

    alignment_result = controller.execute_focus_alignment(request)

    if alignment_result is None:
        # Internal error - controller not connected or not initialized
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Focus alignment failed: Controller not connected or Alignment not initialized"
        )

    if not alignment_result.success:
        # Alignment failed due to system state - return 422 with detailed error info
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return alignment_result

    # Success - return 200 OK with alignment results
    return alignment_result
