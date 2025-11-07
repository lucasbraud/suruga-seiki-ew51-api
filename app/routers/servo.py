"""
Servo control endpoints
"""
from fastapi import APIRouter
from typing import List
from pydantic import BaseModel

from ..models import ServoRequest
from ..dependencies import ControllerDep

router = APIRouter(prefix="/servo", tags=["Servo Control"])


class ServoBatchRequest(BaseModel):
    """Request for batch servo operations"""
    axis_ids: List[int]


@router.post("/on")
async def turn_on_servo(request: ServoRequest, controller: ControllerDep):
    """Turn on servo for specified axis"""
    axis_id = request.axis_id
    success = controller.turn_on_servo(axis_id)

    return {
        "success": success,
        "axis_id": axis_id,
        "message": f"Servo turned on for axis {axis_id}" if success else "Failed to turn on servo"
    }


@router.post("/off")
async def turn_off_servo(request: ServoRequest, controller: ControllerDep):
    """Turn off servo for specified axis"""
    axis_id = request.axis_id
    success = controller.turn_off_servo(axis_id)

    return {
        "success": success,
        "axis_id": axis_id,
        "message": f"Servo turned off for axis {axis_id}" if success else "Failed to turn off servo"
    }


@router.post("/batch/on")
async def turn_on_servos_batch(request: ServoBatchRequest, controller: ControllerDep):
    """
    Turn on servos for multiple axes at once (batch operation).
    
    This is much faster than calling /servo/on multiple times as it eliminates
    the HTTP request overhead and executes all servo commands in one go.
    """
    success = controller.turn_on_servos_batch(request.axis_ids)
    
    return {
        "success": success,
        "axis_ids": request.axis_ids,
        "message": f"Servos turned on for {len(request.axis_ids)} axes" if success else "Failed to turn on some servos"
    }


@router.post("/batch/off")
async def turn_off_servos_batch(request: ServoBatchRequest, controller: ControllerDep):
    """
    Turn off servos for multiple axes at once (batch operation).
    """
    success = controller.turn_off_servos_batch(request.axis_ids)
    
    return {
        "success": success,
        "axis_ids": request.axis_ids,
        "message": f"Servos turned off for {len(request.axis_ids)} axes" if success else "Failed to turn off some servos"
    }


@router.post("/batch/wait_ready")
async def wait_for_servos_ready_batch(request: ServoBatchRequest, controller: ControllerDep):
    """
    Wait for multiple axes to reach InPosition status after being turned on.
    
    This checks all axes in parallel rather than sequentially, making it much faster
    than calling /servo/wait_ready multiple times.
    """
    success = controller.wait_for_axes_ready_batch(request.axis_ids, timeout=10.0)
    
    return {
        "success": success,
        "axis_ids": request.axis_ids,
        "message": f"All {len(request.axis_ids)} axes are ready" if success else "Some axes did not reach ready state"
    }


@router.post("/wait_ready")
async def wait_for_servo_ready(request: ServoRequest, controller: ControllerDep):
    """
    Wait for axis servo to reach InPosition status after being turned on.

    This endpoint should be called after /servo/on to ensure the axis is fully
    ready for alignment or movement operations. It prevents "ServoIsNotReady" errors
    by polling the axis status until it reaches "InPosition".

    Returns after the axis is ready (InPosition) or timeout occurs (10 seconds default).
    """
    axis_id = request.axis_id
    success = controller.wait_for_axis_ready(axis_id, timeout=10.0)

    return {
        "success": success,
        "axis_id": axis_id,
        "message": f"Axis {axis_id} is ready (InPosition)" if success else f"Axis {axis_id} did not reach ready state (timeout or error)"
    }
