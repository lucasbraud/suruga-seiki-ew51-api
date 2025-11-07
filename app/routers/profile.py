"""
Profile measurement endpoints
"""
from fastapi import APIRouter, HTTPException, status, Response

from ..models import ProfileMeasurementRequest, ProfileDataResponse, ProfileErrorCode, ProfileMeasurementStatus
from ..dependencies import ControllerDep

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
