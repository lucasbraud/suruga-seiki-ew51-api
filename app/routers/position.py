"""
Position query endpoints
"""
from typing import Dict
from fastapi import APIRouter, HTTPException

from ..models import AxisStatus
from ..dependencies import ControllerDep

router = APIRouter(prefix="/position", tags=["Position"])


@router.get("/all", response_model=Dict[str, AxisStatus])
async def get_all_positions(controller: ControllerDep):
    """Get current positions for all axes"""
    positions = controller.get_all_positions()

    # Convert axis numbers to strings for JSON keys
    return {str(axis_num): pos for axis_num, pos in positions.items()}


@router.get("/{axis_number}", response_model=AxisStatus)
async def get_axis_position(axis_number: int, controller: ControllerDep):
    """Get current position and status of an axis"""

    if axis_number < 1 or axis_number > 12:
        raise HTTPException(status_code=400, detail="Invalid axis number (must be 1-12)")

    position = controller.get_position(axis_number)

    if not position:
        raise HTTPException(status_code=500, detail="Failed to get axis position")

    return position
