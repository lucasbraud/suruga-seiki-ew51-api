"""
FastAPI Dependencies for Suruga Seiki Controller
Centralized dependency injection for controller access with proper error handling
"""
import logging
from typing import Annotated
from fastapi import HTTPException, Depends

from .controller_manager import SurugaSeikiController

logger = logging.getLogger(__name__)


def get_controller_dependency() -> SurugaSeikiController:
    """
    FastAPI dependency for accessing the global controller instance.

    Returns:
        SurugaSeikiController: The global controller instance

    Raises:
        HTTPException: 503 if controller not initialized or not connected
    """
    from .main import controller

    if controller is None:
        logger.error("Controller not initialized")
        raise HTTPException(
            status_code=503,
            detail="Controller not initialized. Service is starting up or encountered an error."
        )

    if not controller.is_connected():
        logger.warning("Attempt to access controller while disconnected")
        raise HTTPException(
            status_code=503,
            detail="Not connected to hardware. Please connect first via /connection/connect"
        )

    return controller


def get_controller_optional() -> SurugaSeikiController:
    """
    FastAPI dependency for accessing controller without connection check.
    Use this for endpoints that need to work even when disconnected (e.g., /connect, /status).

    Returns:
        SurugaSeikiController: The global controller instance

    Raises:
        HTTPException: 503 if controller not initialized
    """
    from .main import controller

    if controller is None:
        logger.error("Controller not initialized")
        raise HTTPException(
            status_code=503,
            detail="Controller not initialized. Service is starting up or encountered an error."
        )

    return controller


# Type aliases for clean endpoint signatures
ControllerDep = Annotated[SurugaSeikiController, Depends(get_controller_dependency)]
ControllerOptionalDep = Annotated[SurugaSeikiController, Depends(get_controller_optional)]
