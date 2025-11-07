"""
Motion control endpoints (single axis, 2D, 3D movements)
"""
from fastapi import APIRouter

from ..models import (
    ServoRequest,
    MoveAbsoluteRequest,
    MoveRelativeRequest,
    Move2DRequest,
    Move3DRequest,
)
from ..dependencies import ControllerDep

router = APIRouter(prefix="/move", tags=["Motion Control"])


@router.post("/absolute")
async def move_absolute(request: MoveAbsoluteRequest, controller: ControllerDep):
    """Move axis to absolute position"""
    axis_id = request.axis_id
    success = controller.move_absolute(
        axis_id,
        request.position,
        request.speed
    )

    return {
        "success": success,
        "axis_id": axis_id,
        "position": request.position,
        "speed": request.speed
    }


@router.post("/relative")
async def move_relative(request: MoveRelativeRequest, controller: ControllerDep):
    """Move axis relative to current position"""
    axis_id = request.axis_id
    success = controller.move_relative(
        axis_id,
        request.distance,
        request.speed
    )

    return {
        "success": success,
        "axis_id": axis_id,
        "distance": request.distance,
        "speed": request.speed
    }


@router.post("/stop")
async def stop_axis(request: ServoRequest, controller: ControllerDep):
    """Stop movement of specified axis"""
    axis_id = request.axis_id
    success = controller.stop_axis(axis_id)

    return {
        "success": success,
        "axis_id": axis_id,
        "message": "Axis stopped" if success else "Failed to stop axis"
    }


@router.post("/emergency_stop")
async def emergency_stop(controller: ControllerDep):
    """Emergency stop all axes"""
    success = controller.emergency_stop()

    return {
        "success": success,
        "message": "Emergency stop executed" if success else "Failed to execute emergency stop"
    }


@router.post("/2d")
async def move_2d(request: Move2DRequest, controller: ControllerDep):
    """Execute 2D interpolation movement"""

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
    """Execute 3D interpolation movement"""
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
