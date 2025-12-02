"""
Factory for creating controller instances.

Chooses between real hardware controller and mock controller based on configuration.
"""
import logging
from typing import Union

from .config import settings

logger = logging.getLogger(__name__)


def create_controller() -> Union["SurugaSeikiController", "MockSurugaSeikiController"]:
    """
    Create controller instance based on MOCK_MODE setting.

    Returns:
        SurugaSeikiController if MOCK_MODE=false (real hardware)
        MockSurugaSeikiController if MOCK_MODE=true (simulated hardware)

    Environment Variables:
        SURUGA_MOCK_MODE: Set to 'true' to enable mock mode
    """
    if settings.mock_mode:
        logger.info("🎭 MOCK MODE ENABLED - Using simulated probe station")
        from .mock_controller import MockSurugaSeikiController
        return MockSurugaSeikiController(ads_address=settings.ads_address)
    else:
        logger.info("🔧 Using real hardware controller")
        from .controller_manager import SurugaSeikiController
        return SurugaSeikiController(ads_address=settings.ads_address)
