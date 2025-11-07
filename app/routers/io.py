"""
Digital and analog I/O control endpoints for contact sensing
"""
from fastapi import APIRouter, HTTPException

from ..models import DigitalOutputRequest
from ..dependencies import ControllerDep

router = APIRouter(prefix="/io", tags=["I/O Control"])


@router.post("/digital/output")
async def set_digital_output(request: DigitalOutputRequest, controller: ControllerDep):
    """
    Set digital output value (contact sensing lock state)

    Channels:
    - 1: Left stage contact sensor
    - 2: Right stage contact sensor

    Values:
    - true: LOCKED
    - false: UNLOCKED
    """
    if request.channel not in [1, 2]:
        raise HTTPException(
            status_code=400,
            detail="Invalid channel. Only channels 1 and 2 are supported for digital output."
        )

    success = controller.set_digital_output(request.channel, request.value)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to set digital output")

    return {
        "success": success,
        "channel": request.channel,
        "value": request.value
    }


@router.get("/digital/output/{channel}")
async def get_digital_output(channel: int, controller: ControllerDep):
    """
    Get digital output state (contact sensing lock state)

    Channels:
    - 1: Left stage contact sensor
    - 2: Right stage contact sensor

    Returns:
    - true: LOCKED
    - false: UNLOCKED
    """
    if channel not in [1, 2]:
        raise HTTPException(
            status_code=400,
            detail="Invalid channel. Only channels 1 and 2 are supported for digital output."
        )

    value = controller.get_digital_output(channel)

    if value is None:
        raise HTTPException(status_code=500, detail="Failed to read digital output")

    return {
        "success": True,
        "channel": channel,
        "value": value
    }


@router.get("/analog/input/{channel}")
async def get_analog_input(channel: int, controller: ControllerDep):
    """
    Get analog input voltage (contact sensing)

    Channels:
    - 5: Left stage analog value
    - 6: Right stage analog value

    Values typically range from 0V to 3V.
    Contact threshold is around 2.785V.
    """
    if channel not in [5, 6]:
        raise HTTPException(
            status_code=400,
            detail="Invalid channel. Only channels 5 and 6 are supported for analog input."
        )

    voltage = controller.get_analog_input(channel)

    if voltage is None:
        raise HTTPException(status_code=500, detail="Failed to read analog input")

    return {
        "success": True,
        "channel": channel,
        "voltage": voltage
    }
