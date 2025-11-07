"""
Connection and system status endpoints
"""
from datetime import datetime
from fastapi import APIRouter

from ..models import ConnectionRequest, ConnectionResponse, SystemStatus
from ..dependencies import ControllerOptionalDep

router = APIRouter(prefix="/connection", tags=["Connection"])


@router.post("/connect", response_model=ConnectionResponse)
async def connect_to_controller(request: ConnectionRequest, controller: ControllerOptionalDep):
    """Connect to the probe station controller"""
    if controller.is_connected():
        return ConnectionResponse(
            success=True,
            message="Already connected",
            connected=True
        )

    # Update ADS address if different
    if request.ads_address != controller.ads_address:
        controller.ads_address = request.ads_address

    success = controller.connect()

    return ConnectionResponse(
        success=success,
        message="Connected successfully" if success else "Failed to connect",
        connected=controller.is_connected()
    )


@router.post("/disconnect")
async def disconnect_from_controller(controller: ControllerOptionalDep):
    """Disconnect from the probe station controller"""
    success = controller.disconnect()

    return {
        "success": success,
        "message": "Disconnected successfully" if success else "Failed to disconnect"
    }


@router.get("/status", response_model=SystemStatus)
async def get_system_status(controller: ControllerOptionalDep):
    """Get system status and error information"""

    is_error, error_msg = controller.check_error()

    dll_ver = None
    sys_ver = None
    is_emergency = None
    if controller.is_connected():
        try:
            dll_ver, sys_ver = controller.get_versions()
        except Exception:
            pass
        try:
            is_emergency = controller.get_emergency_asserted()
        except Exception:
            pass

    return SystemStatus(
        is_connected=controller.is_connected(),
        dll_version=dll_ver,
        system_version=sys_ver,
        is_error=is_error,
        is_emergency_asserted=is_emergency,
        error_message=error_msg,
        timestamp=datetime.now().isoformat()
    )
