"""
Comprehensive Suruga Seiki DA1000/DA1100 Controller Manager
Wraps the full .NET API for Python integration with proper error handling and type safety
"""
import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Callable
from enum import Enum
import time

# pythonnet imports for .NET interop
import pythonnet
pythonnet.load("coreclr")
import clr

# Add reference to the Suruga Seiki DLL
dll_path = Path(__file__).parent / "dll"
clr.AddReference(str(dll_path / "srgmc.dll"))

# Import the .NET namespace
import SurugaSeiki.Motion as Motion # type: ignore
from .config import settings
from .models import (
    AxisStatus,
    ProfileDataResponse,
    ProfileDataPoint,
    ProfileErrorCode,
    ProfileMeasurementStatus,
    ProfileMeasurementRequest,
    AngleAdjustmentStage,
    AngleAdjustmentRequest,
    AngleAdjustmentResponse,
    AngleAdjustmentStatus,
    AdjustingStatus
)

logger = logging.getLogger(__name__)


class SurugaSeikiController:
    """
    Comprehensive wrapper for Suruga Seiki DA1000/DA1100 probe station controller.

    This class provides full API coverage including:
    - Connection management
    - Multi-axis motion control (up to 12 axes)
    - 2D and 3D interpolation movement
    - Automated alignment routines (6 types)
    - Profile measurement and scanning
    - Angle adjustment (DA1100 only)
    - Digital and analog I/O control
    """

    def __init__(
        self,
        ads_address: str = "5.146.68.190.1.1",
    ):
        """
        Initialize the controller manager.

        Args:
            ads_address: ADS address of the probe station (format: "x.x.x.x.x.x")
        """
        self.ads_address = ads_address
        self._lock = threading.RLock()
        self._connected = False

        # .NET API instances
        self._system: Optional[Any] = None
        self._axis_components: Dict[int, Any] = {}
        self._axis2d: Optional[Any] = None
        self._axis3d: Optional[Any] = None
        self._alignment: Optional[Any] = None
        self._profile: Optional[Any] = None
        self._angle_adjustment_left: Optional[Any] = None
        self._angle_adjustment_right: Optional[Any] = None
        self._io: Optional[Any] = None

        logger.info(f"Initialized SurugaSeikiController for ADS address: {ads_address}")

    def get_versions(self) -> Tuple[Optional[str], Optional[str]]:
        """Return (dll_version, system_version) if available."""
        if not self._system:
            return None, None
        dll_ver = None
        sys_ver = None
        try:
            dll_ver = str(self._system.DllVersion)
        except Exception:
            pass
        try:
            sys_ver = str(self._system.SystemVersion)
        except Exception:
            pass
        return dll_ver, sys_ver

    def get_emergency_asserted(self) -> Optional[bool]:
        """Return emergency asserted state if available on the DLL, else None."""
        if not self._system:
            return None
        try:
            # Some DLLs may expose IsEmergencyAsserted or similar
            return bool(self._system.IsEmergencyAsserted)
        except Exception:
            return None

    # ========== Connection Management ==========

    def connect(self) -> bool:
        """
        Connect to the probe station controller.

        Returns:
            True if connection successful, False otherwise
        """
        with self._lock:
            try:
                # Get the System singleton instance
                self._system = Motion.System.Instance

                # Set the ADS address
                self._system.SetAddress(self.ads_address)

                # Wait for connection to establish with timeout (similar to legacy daemon)
                timeout_s = getattr(settings, "connection_timeout_s", 5.0)
                poll_interval = 0.5
                start_time = time.time()
                while True:
                    try:
                        if self._system.Connected:
                            break
                    except Exception:
                        # If property access throws, keep waiting until timeout
                        pass

                    if time.time() - start_time > timeout_s:
                        logger.error(f"Failed to connect to probe station within {timeout_s}s")
                        return False
                    time.sleep(poll_interval)

                # Initialize axis components (1-12)
                for axis_num in range(1, 13):
                    self._axis_components[axis_num] = Motion.AxisComponents(axis_num)

                # Initialize other API components
                # Axis2D supports a parameterless constructor; we'll set axis numbers per move
                self._axis2d = Motion.Axis2D()
                # Axis3D does NOT expose a parameterless constructor in the DLL; instantiate on demand per move
                self._axis3d = None
                self._alignment = Motion.Alignment()
                self._profile = Motion.Profile()

                # Initialize angle adjustment for both stages (DA1100 only)
                try:
                    # AngleAdjustment requires stage argument: 1=LEFT, 2=RIGHT
                    self._angle_adjustment_left = Motion.AngleAdjustment(AngleAdjustmentStage.LEFT.value)
                    self._angle_adjustment_right = Motion.AngleAdjustment(AngleAdjustmentStage.RIGHT.value)
                    logger.info("AngleAdjustment initialized for both LEFT and RIGHT stages")
                except Exception as e:
                    logger.error(f"Failed to initialize AngleAdjustment (DA1000 model or error): {e}", exc_info=True)
                    return False

                # Initialize I/O control
                self._io = Motion.IO()

                self._connected = True
                logger.info(f"Successfully connected to probe station at {self.ads_address}")
                return True

            except Exception as e:
                logger.error(f"Error connecting to probe station: {e}", exc_info=True)
                self._connected = False
                return False

    def disconnect(self) -> bool:
        """
        Disconnect from the probe station.

        Returns:
            True if disconnection successful
        """
        with self._lock:
            try:
                # Turn off all servos before disconnecting
                for axis_num in self._axis_components.keys():
                    try:
                        self.turn_off_servo(axis_num)
                    except Exception as e:
                        logger.warning(f"Error turning off servo for axis {axis_num}: {e}")

                # Clear references
                self._system = None
                self._axis_components.clear()
                self._axis2d = None
                self._axis3d = None
                self._alignment = None
                self._profile = None
                self._angle_adjustment_left = None
                self._angle_adjustment_right = None
                self._io = None

                self._connected = False
                logger.info("Disconnected from probe station")
                return True

            except Exception as e:
                logger.error(f"Error disconnecting: {e}", exc_info=True)
                return False

    def is_connected(self) -> bool:
        """Check if connected to the controller"""
        try:
            return self._connected and self._system is not None and bool(self._system.Connected)
        except Exception:
            return False

    def check_error(self) -> Tuple[bool, str]:
        """
        Check if there's a system error based on axis error codes and status.

        Returns:
            Tuple of (is_error, error_message)
        """
        if not self.is_connected():
            return True, "Not connected to controller"

        try:
            is_error = False
            error_msgs = []

            # Prefer explicit axis error codes over opaque system flags
            for axis_num, axis in self._axis_components.items():
                try:
                    error_code = int(axis.GetErrorCode())
                    if error_code != 0:
                        is_error = True
                        error_msgs.append(f"Axis {axis_num}: Error code {error_code}")
                except Exception:
                    # Fallback: use status string if available
                    try:
                        status_str = str(axis.GetStatus())
                        if status_str and status_str.lower() == "error":
                            is_error = True
                            error_msgs.append(f"Axis {axis_num}: Status error")
                    except Exception:
                        pass

            if is_error:
                return True, "; ".join(error_msgs) if error_msgs else "Unknown error"

            return False, ""

        except Exception as e:
            logger.error(f"Error checking system status: {e}")
            return True, str(e)

    # ========== Single Axis Control (AxisComponents) ==========

    def turn_on_servo(self, axis_number: int) -> bool:
        """
        Turn on servo for specified axis.

        Args:
            axis_number: Axis number (1-12)

        Returns:
            True if successful
        """
        if not self._validate_axis(axis_number):
            return False

        try:
            axis = self._axis_components[axis_number]
            axis.TurnOnServo()
            logger.info(f"Turned on servo for axis {axis_number}")
            return True
        except Exception as e:
            logger.error(f"Error turning on servo for axis {axis_number}: {e}")
            return False

    def turn_off_servo(self, axis_number: int) -> bool:
        """
        Turn off servo for specified axis.

        Args:
            axis_number: Axis number (1-12)

        Returns:
            True if successful
        """
        if not self._validate_axis(axis_number):
            return False

        try:
            axis = self._axis_components[axis_number]
            axis.TurnOffServo()
            logger.info(f"Turned off servo for axis {axis_number}")
            return True
        except Exception as e:
            logger.error(f"Error turning off servo for axis {axis_number}: {e}")
            return False

    def turn_on_servos_batch(self, axis_numbers: List[int]) -> bool:
        """
        Turn on servos for multiple axes at once (batch operation).
        
        This is more efficient than calling turn_on_servo() multiple times
        as it avoids the overhead of individual HTTP requests.

        Args:
            axis_numbers: List of axis numbers (1-12)

        Returns:
            True if all servos turned on successfully
        """
        if not self.is_connected():
            logger.error("Not connected to controller")
            return False

        failed_axes = []
        for axis_number in axis_numbers:
            if axis_number not in self._axis_components:
                logger.error(f"Invalid axis number: {axis_number}")
                failed_axes.append(axis_number)
                continue

            try:
                axis = self._axis_components[axis_number]
                axis.TurnOnServo()
            except Exception as e:
                logger.error(f"Error turning on servo for axis {axis_number}: {e}")
                failed_axes.append(axis_number)

        if failed_axes:
            logger.error(f"Failed to turn on servos for axes: {failed_axes}")
            return False

        logger.info(f"Turned on servos for axes: {axis_numbers}")
        return True

    def turn_off_servos_batch(self, axis_numbers: List[int]) -> bool:
        """
        Turn off servos for multiple axes at once (batch operation).

        Args:
            axis_numbers: List of axis numbers (1-12)

        Returns:
            True if all servos turned off successfully
        """
        if not self.is_connected():
            logger.error("Not connected to controller")
            return False

        failed_axes = []
        for axis_number in axis_numbers:
            if axis_number not in self._axis_components:
                logger.error(f"Invalid axis number: {axis_number}")
                failed_axes.append(axis_number)
                continue

            try:
                axis = self._axis_components[axis_number]
                axis.TurnOffServo()
            except Exception as e:
                logger.error(f"Error turning off servo for axis {axis_number}: {e}")
                failed_axes.append(axis_number)

        if failed_axes:
            logger.error(f"Failed to turn off servos for axes: {failed_axes}")
            return False

        logger.info(f"Turned off servos for axes: {axis_numbers}")
        return True

    def wait_for_axes_ready_batch(self, axis_numbers: List[int], timeout: float = 10.0) -> bool:
        """
        Wait for multiple axes to reach InPosition status after servos are turned on.
        
        This checks all axes in parallel rather than sequentially, making it much faster.

        Args:
            axis_numbers: List of axis numbers (1-12)
            timeout: Maximum wait time in seconds (default: 10)

        Returns:
            True if all axes reached InPosition, False if timeout or error
        """
        if not self.is_connected():
            logger.error("Not connected to controller")
            return False

        start_time = time.time()
        pending_axes = set(axis_numbers)

        while pending_axes:
            if time.time() - start_time > timeout:
                logger.error(f"Timeout waiting for axes to reach ready state: {pending_axes}")
                return False

            axes_to_remove = set()
            for axis_number in pending_axes:
                if axis_number not in self._axis_components:
                    logger.error(f"Invalid axis number: {axis_number}")
                    return False

                try:
                    axis = self._axis_components[axis_number]
                    status = str(axis.GetStatus())
                    
                    if status == "InPosition":
                        axes_to_remove.add(axis_number)
                        logger.debug(f"Axis {axis_number} reached InPosition")
                    elif status in ["Alarm", "Error"]:
                        logger.error(f"Axis {axis_number} in error state: {status}")
                        return False
                        
                except Exception as e:
                    logger.error(f"Error checking status for axis {axis_number}: {e}")
                    return False

            pending_axes -= axes_to_remove
            
            if pending_axes:
                time.sleep(0.1)  # Small delay between checks

        logger.info(f"All axes ready: {axis_numbers}")
        return True

    def move_absolute(self, axis_number: int, position: float, speed: float = 50.0) -> bool:
        """
        Move axis to absolute position and wait for completion.

        Args:
            axis_number: Axis number (1-12)
            position: Target position in micrometers
            speed: Movement speed in um/s

        Returns:
            True if movement completed successfully
        """
        if not self._validate_axis(axis_number):
            return False

        try:
            axis = self._axis_components[axis_number]
            axis.SetMaxSpeed(speed)
            axis.MoveAbsolute(position)
            logger.info(f"Moving axis {axis_number} to absolute position {position} um at {speed} um/s")

            # Wait for movement to complete
            time.sleep(0.1)  # Initial delay to allow movement to start
            timeout = 60  # 60 seconds timeout
            start_time = time.time()

            while True:
                try:
                    is_moving = bool(axis.IsMoving())
                except Exception:
                    try:
                        is_moving = str(axis.GetStatus()).lower() == "moving"
                    except Exception:
                        is_moving = False

                if not is_moving:
                    logger.info(f"Axis {axis_number} movement completed")
                    return True

                if time.time() - start_time > timeout:
                    logger.error(f"Axis {axis_number} movement timed out after {timeout}s")
                    return False

                time.sleep(0.05)  # Poll every 50ms

        except Exception as e:
            logger.error(f"Error moving axis {axis_number} absolute: {e}")
            return False

    def move_relative(self, axis_number: int, distance: float, speed: float = 1000.0) -> bool:
        """
        Move axis relative to current position and wait for completion.

        Args:
            axis_number: Axis number (1-12)
            distance: Relative distance in micrometers
            speed: Movement speed in um/s

        Returns:
            True if movement completed successfully
        """
        if not self._validate_axis(axis_number):
            return False

        try:
            axis = self._axis_components[axis_number]
            axis.SetMaxSpeed(speed)
            axis.MoveRelative(distance)
            logger.info(f"Moving axis {axis_number} relative {distance} um at {speed} um/s")

            # Wait for movement to complete
            time.sleep(0.1)  # Initial delay to allow movement to start
            timeout = 60  # 60 seconds timeout
            start_time = time.time()

            while True:
                try:
                    is_moving = bool(axis.IsMoving())
                except Exception:
                    try:
                        is_moving = str(axis.GetStatus()).lower() == "moving"
                    except Exception:
                        is_moving = False

                if not is_moving:
                    logger.info(f"Axis {axis_number} movement completed")
                    return True

                if time.time() - start_time > timeout:
                    logger.error(f"Axis {axis_number} movement timed out after {timeout}s")
                    return False

                time.sleep(0.05)  # Poll every 50ms

        except Exception as e:
            logger.error(f"Error moving axis {axis_number} relative: {e}")
            return False

    def stop_axis(self, axis_number: int) -> bool:
        """
        Stop movement of specified axis.

        Args:
            axis_number: Axis number (1-12)

        Returns:
            True if successful
        """
        if not self._validate_axis(axis_number):
            return False

        try:
            axis = self._axis_components[axis_number]
            axis.Stop()
            logger.info(f"Stopped axis {axis_number}")
            return True
        except Exception as e:
            logger.error(f"Error stopping axis {axis_number}: {e}")
            return False

    async def move_absolute_async(
        self,
        axis_number: int,
        position: float,
        speed: float = 100.0,
        cancellation_event: Optional[asyncio.Event] = None,
        progress_callback: Optional[Callable[[dict], None]] = None
    ) -> dict[str, Any]:
        """
        Async wrapper for move_absolute with cancellation and progress support.

        Args:
            axis_number: Axis number (1-12)
            position: Target position in micrometers
            speed: Movement speed in um/s
            cancellation_event: Optional event to signal cancellation
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with movement result information

        Raises:
            Exception: If movement fails or is cancelled
        """
        def sync_execution():
            """Synchronous execution in thread pool."""
            if not self._validate_axis(axis_number):
                raise Exception(f"Invalid axis number: {axis_number}")

            try:
                axis = self._axis_components[axis_number]

                # Check if servo is ON before attempting movement
                try:
                    is_servo_on = bool(axis.IsServoOn())
                    if not is_servo_on:
                        raise Exception(
                            f"Servo is OFF for axis {axis_number}. "
                            f"Enable servo using POST /servo/on with axis_id={axis_number} before moving."
                        )
                except Exception as e:
                    if "Servo is OFF" in str(e):
                        raise  # Re-raise our custom message
                    # If we can't check servo status, log warning but continue
                    logger.warning(f"Could not verify servo status for axis {axis_number}: {e}")

                # Get initial position
                try:
                    initial_position = float(axis.GetActualPosition())
                except Exception:
                    initial_position = None

                # Start movement
                axis.SetMaxSpeed(speed)
                axis.MoveAbsolute(position)
                logger.info(f"Axis {axis_number} moving to {position} um at {speed} um/s")

                if progress_callback:
                    progress_callback({
                        "axis": axis_number,
                        "target_position": position,
                        "current_position": initial_position,
                        "speed": speed,
                        "message": f"Movement started to {position} um"
                    })

                time.sleep(0.1)  # Initial delay
                timeout = 60
                start_time = time.time()

                while True:
                    # Check cancellation FIRST
                    if cancellation_event and cancellation_event.is_set():
                        logger.info(f"Axis {axis_number} movement cancellation requested")
                        axis.Stop()
                        time.sleep(0.2)  # Wait for stop

                        raise Exception("Movement cancelled by user")

                    # Check if still moving
                    try:
                        is_moving = bool(axis.IsMoving())
                    except Exception:
                        try:
                            is_moving = str(axis.GetStatus()).lower() == "moving"
                        except Exception:
                            is_moving = False

                    # Get current position for progress
                    try:
                        current_position = float(axis.GetActualPosition())
                    except Exception:
                        current_position = None

                    # Calculate progress
                    if initial_position is not None and current_position is not None:
                        total_distance = abs(position - initial_position)
                        traveled = abs(current_position - initial_position)
                        progress_percent = min(100, int((traveled / total_distance * 100) if total_distance > 0 else 100))

                        if progress_callback:
                            progress_callback({
                                "axis": axis_number,
                                "target_position": position,
                                "current_position": current_position,
                                "progress_percent": progress_percent,
                                "elapsed_time": time.time() - start_time
                            })

                    if not is_moving:
                        # Settling time: allow encoder to stabilize after motion stops
                        time.sleep(0.5)

                        # Re-read position after settling
                        try:
                            current_position = float(axis.GetActualPosition())
                        except Exception:
                            pass

                        elapsed = time.time() - start_time
                        logger.info(f"Axis {axis_number} movement completed in {elapsed:.2f}s")

                        if progress_callback:
                            progress_callback({
                                "axis": axis_number,
                                "current_position": current_position,
                                "progress_percent": 100,
                                "elapsed_time": elapsed,
                                "message": "Movement completed"
                            })

                        return {
                            "success": True,
                            "axis": axis_number,
                            "target_position": position,
                            "final_position": current_position,
                            "initial_position": initial_position,
                            "execution_time": elapsed
                        }

                    if time.time() - start_time > timeout:
                        axis.Stop()
                        raise Exception(f"Movement timed out after {timeout}s")

                    time.sleep(0.05)

            except Exception as e:
                logger.error(f"Error in axis {axis_number} absolute movement: {e}")
                raise

        return await asyncio.to_thread(sync_execution)

    async def move_relative_async(
        self,
        axis_number: int,
        distance: float,
        speed: float = 1000.0,
        cancellation_event: Optional[asyncio.Event] = None,
        progress_callback: Optional[Callable[[dict], None]] = None
    ) -> dict[str, Any]:
        """
        Async wrapper for move_relative with cancellation and progress support.

        Args:
            axis_number: Axis number (1-12)
            distance: Relative distance in micrometers
            speed: Movement speed in um/s
            cancellation_event: Optional event to signal cancellation
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with movement result information

        Raises:
            Exception: If movement fails or is cancelled
        """
        def sync_execution():
            """Synchronous execution in thread pool."""
            if not self._validate_axis(axis_number):
                raise Exception(f"Invalid axis number: {axis_number}")

            try:
                axis = self._axis_components[axis_number]

                # Check if servo is ON before attempting movement
                try:
                    is_servo_on = bool(axis.IsServoOn())
                    if not is_servo_on:
                        raise Exception(
                            f"Servo is OFF for axis {axis_number}. "
                            f"Enable servo using POST /servo/on with axis_id={axis_number} before moving."
                        )
                except Exception as e:
                    if "Servo is OFF" in str(e):
                        raise  # Re-raise our custom message
                    # If we can't check servo status, log warning but continue
                    logger.warning(f"Could not verify servo status for axis {axis_number}: {e}")

                # Get initial position
                try:
                    initial_position = float(axis.GetActualPosition())
                    target_position = initial_position + distance
                except Exception:
                    initial_position = None
                    target_position = None

                # Start movement
                axis.SetMaxSpeed(speed)
                axis.MoveRelative(distance)
                logger.info(f"Axis {axis_number} moving relative {distance} um at {speed} um/s")

                if progress_callback:
                    progress_callback({
                        "axis": axis_number,
                        "distance": distance,
                        "initial_position": initial_position,
                        "target_position": target_position,
                        "speed": speed,
                        "message": f"Relative movement started: {distance:+.2f} um"
                    })

                time.sleep(0.1)  # Initial delay
                timeout = 60
                start_time = time.time()

                while True:
                    # Check cancellation FIRST
                    if cancellation_event and cancellation_event.is_set():
                        logger.info(f"Axis {axis_number} movement cancellation requested")
                        axis.Stop()
                        time.sleep(0.2)  # Wait for stop

                        raise Exception("Movement cancelled by user")

                    # Check if still moving
                    try:
                        is_moving = bool(axis.IsMoving())
                    except Exception:
                        try:
                            is_moving = str(axis.GetStatus()).lower() == "moving"
                        except Exception:
                            is_moving = False

                    # Get current position for progress
                    try:
                        current_position = float(axis.GetActualPosition())
                    except Exception:
                        current_position = None

                    # Calculate progress
                    if initial_position is not None and current_position is not None and target_position is not None:
                        total_distance = abs(distance)
                        traveled = abs(current_position - initial_position)
                        progress_percent = min(100, int((traveled / total_distance * 100) if total_distance > 0 else 100))

                        if progress_callback:
                            progress_callback({
                                "axis": axis_number,
                                "distance": distance,
                                "current_position": current_position,
                                "target_position": target_position,
                                "progress_percent": progress_percent,
                                "elapsed_time": time.time() - start_time
                            })

                    if not is_moving:
                        # Settling time: allow encoder to stabilize after motion stops
                        time.sleep(0.5)

                        # Re-read position after settling
                        try:
                            current_position = float(axis.GetActualPosition())
                        except Exception:
                            pass

                        elapsed = time.time() - start_time
                        logger.info(f"Axis {axis_number} relative movement completed in {elapsed:.2f}s")

                        if progress_callback:
                            progress_callback({
                                "axis": axis_number,
                                "current_position": current_position,
                                "progress_percent": 100,
                                "elapsed_time": elapsed,
                                "message": "Movement completed"
                            })

                        return {
                            "success": True,
                            "axis": axis_number,
                            "distance": distance,
                            "initial_position": initial_position,
                            "final_position": current_position,
                            "target_position": target_position,
                            "execution_time": elapsed
                        }

                    if time.time() - start_time > timeout:
                        axis.Stop()
                        raise Exception(f"Movement timed out after {timeout}s")

                    time.sleep(0.05)

            except Exception as e:
                logger.error(f"Error in axis {axis_number} relative movement: {e}")
                raise

        return await asyncio.to_thread(sync_execution)

    def get_position(self, axis_number: int) -> Optional[AxisStatus]:
        """
        Get current position and status of an axis.

        Args:
            axis_number: Axis number (1-12)

        Returns:
            AxisStatus object or None if error
        """
        if not self._validate_axis(axis_number):
            return None

        try:
            axis = self._axis_components[axis_number]

            # Query actual position
            actual_position = axis.GetActualPosition()

            try:
                is_moving = bool(axis.IsMoving())
            except Exception:
                try:
                    is_moving = str(axis.GetStatus()).lower() == "moving"
                except Exception:
                    is_moving = False

            try:
                is_servo_on = bool(axis.IsServoOn())
            except Exception:
                is_servo_on = False

            try:
                error_code = int(axis.GetErrorCode())
            except Exception:
                error_code = 0

            return AxisStatus(
                axis_number=axis_number,
                actual_position=actual_position,
                is_moving=is_moving,
                is_servo_on=is_servo_on,
                is_error=error_code != 0,
                error_code=error_code
            )
        except Exception as e:
            logger.error(f"Error getting position for axis {axis_number}: {e}")
            return None

    def wait_for_axis_stop(self, axis_number: int, timeout: float = 60.0) -> bool:
        """
        Wait for axis to stop moving.

        Args:
            axis_number: Axis number (1-12)
            timeout: Maximum wait time in seconds

        Returns:
            True if axis stopped, False if timeout or error
        """
        if not self._validate_axis(axis_number):
            return False

        try:
            axis = self._axis_components[axis_number]
            start_time = time.time()

            while True:
                try:
                    moving = bool(axis.IsMoving())
                except Exception:
                    try:
                        moving = str(axis.GetStatus()).lower() == "moving"
                    except Exception:
                        moving = False

                if not moving:
                    break
                if time.time() - start_time > timeout:
                    logger.warning(f"Timeout waiting for axis {axis_number} to stop")
                    return False
                time.sleep(0.1)

            # Settling time: allow servo motor to stabilize after motion completes
            # Even though axis reports not moving, closed-loop control needs time to settle
            time.sleep(0.2)
            logger.debug(f"Axis {axis_number} settling time complete")

            return True
        except Exception as e:
            logger.error(f"Error waiting for axis {axis_number}: {e}")
            return False

    def wait_for_axis_ready(self, axis_number: int, timeout: float = 10.0) -> bool:
        """
        Wait for axis to reach InPosition status after servo is turned on.

        This ensures the servo has settled and is ready for alignment or movement commands.
        Should be called after TurnOnServo() to prevent "ServoIsNotReady" errors.

        Args:
            axis_number: Axis number (1-12)
            timeout: Maximum wait time in seconds (default: 10)

        Returns:
            True if axis reached InPosition, False if timeout or error
        """
        if not self._validate_axis(axis_number):
            return False

        try:
            axis = self._axis_components[axis_number]
            start_time = time.time()
            last_status = None

            while True:
                try:
                    # Check if servo is still on
                    if not bool(axis.IsServoOn()):
                        logger.error(f"Axis {axis_number} servo turned OFF during wait")
                        return False

                    # Check status - wait for "InPosition"
                    status_str = str(axis.GetStatus())

                    # Log status changes
                    if status_str != last_status:
                        logger.debug(f"Axis {axis_number} status: {status_str}")
                        last_status = status_str

                    if status_str == "InPosition":
                        # Axis is ready - add settling time for closed-loop stabilization
                        time.sleep(0.2)
                        logger.debug(f"Axis {axis_number} ready (InPosition)")
                        return True
                    elif status_str == "Error":
                        error_code = axis.GetErrorCode()
                        logger.error(f"Axis {axis_number} in Error state (code: {error_code})")
                        return False

                except Exception as e:
                    logger.warning(f"Error checking axis {axis_number} status: {e}")

                if time.time() - start_time > timeout:
                    logger.warning(f"Timeout waiting for axis {axis_number} to reach InPosition (current: {last_status})")
                    return False

                time.sleep(0.1)  # Poll every 100ms

        except Exception as e:
            logger.error(f"Error waiting for axis {axis_number} ready: {e}")
            return False

    # ========== 2D Interpolation Movement (Axis2D) ==========

    def move_2d_absolute(
        self,
        axis1: int,
        axis2: int,
        x: float,
        y: float,
        speed: float = 1000.0,
        angle_offset: float = 0.0
    ) -> bool:
        """
        Execute 2D interpolation movement to absolute position.

        Args:
            axis1: First axis number
            axis2: Second axis number
            x: Target X position in micrometers
            y: Target Y position in micrometers
            speed: Movement speed in um/s
            angle_offset: Rotation angle offset in degrees

        Returns:
            True if command accepted
        """
        if not self.is_connected() or self._axis2d is None:
            logger.error("Not connected or Axis2D not initialized")
            return False

        try:
            self._axis2d.SetAxisNumber(axis1, axis2)
            self._axis2d.SetMaxSpeed(speed)

            if angle_offset != 0.0:
                self._axis2d.SetAngleOffset(angle_offset)

            self._axis2d.MoveAbsolute(x, y)
            logger.info(f"2D move: axes ({axis1},{axis2}) to ({x},{y}) at {speed} um/s, angle={angle_offset}")
            return True
        except Exception as e:
            logger.error(f"Error in 2D absolute move: {e}")
            return False

    def move_2d_relative(
        self,
        axis1: int,
        axis2: int,
        dx: float,
        dy: float,
        speed: float = 1000.0,
        angle_offset: float = 0.0
    ) -> bool:
        """
        Execute 2D interpolation movement relative to current position.

        Args:
            axis1: First axis number
            axis2: Second axis number
            dx: Relative X distance in micrometers
            dy: Relative Y distance in micrometers
            speed: Movement speed in um/s
            angle_offset: Rotation angle offset in degrees

        Returns:
            True if command accepted
        """
        if not self.is_connected() or self._axis2d is None:
            logger.error("Not connected or Axis2D not initialized")
            return False

        try:
            self._axis2d.SetAxisNumber(axis1, axis2)
            self._axis2d.SetMaxSpeed(speed)

            if angle_offset != 0.0:
                self._axis2d.SetAngleOffset(angle_offset)

            self._axis2d.MoveRelative(dx, dy)
            logger.info(f"2D relative move: axes ({axis1},{axis2}) by ({dx},{dy}) at {speed} um/s")
            return True
        except Exception as e:
            logger.error(f"Error in 2D relative move: {e}")
            return False

    # ========== 3D Interpolation Movement (Axis3D) ==========

    def move_3d_absolute(
        self,
        axis1: int,
        axis2: int,
        axis3: int,
        x: float,
        y: float,
        z: float,
        speed: float = 1000.0,
        rotation_center_x: float = 0.0,
        rotation_center_y: float = 0.0
    ) -> bool:
        """
        Execute 3D interpolation movement to absolute position.

        Args:
            axis1: First axis number (X)
            axis2: Second axis number (Y)
            axis3: Third axis number (Z)
            x: Target X position in micrometers
            y: Target Y position in micrometers
            z: Target Z position in micrometers
            speed: Movement speed in um/s
            rotation_center_x: Rotation center X offset
            rotation_center_y: Rotation center Y offset

        Returns:
            True if command accepted
        """
        if not self.is_connected():
            logger.error("Not connected or Axis3D not available")
            return False

        try:
            # Axis3D requires axes at construction time in the Suruga DLL
            axis3d = Motion.Axis3D(axis1, axis2, axis3)
            axis3d.SetMaxSpeed(speed)

            if rotation_center_x != 0.0 or rotation_center_y != 0.0:
                axis3d.SetRotationCenterShift(rotation_center_x, rotation_center_y)

            axis3d.MoveAbsolute(x, y, z)
            logger.info(f"3D move: axes ({axis1},{axis2},{axis3}) to ({x},{y},{z}) at {speed} um/s")
            return True
        except Exception as e:
            logger.error(f"Error in 3D absolute move: {e}")
            return False

    # ========== Profile Measurement ==========

    def _get_profile_error_info(self, error_str: str) -> dict:
        """
        Convert profile error string to detailed error information.
        
        Args:
            error_str: Error string from Profile.Start() (e.g., "Axis", "Parameter")
        
        Returns:
            Dictionary with error, value, and description
        """
        error_map = {
            "None": ProfileErrorCode.NONE,
            "Axis": ProfileErrorCode.AXIS,
            "Profiling": ProfileErrorCode.PROFILING,
            "Parameter": ProfileErrorCode.PARAMETER,
        }
        error_enum = error_map.get(error_str, ProfileErrorCode.NONE)
        return error_enum.to_dict()

    def _get_profile_status_info(self, status_str: str) -> dict:
        """
        Convert profile status string to detailed status information.
        
        Args:
            status_str: Status string from Profile.GetProfileStatus()
        
        Returns:
            Dictionary with status, value, and description
        """
        status_map = {
            "Stopping": ProfileMeasurementStatus.STOPPING,
            "Success": ProfileMeasurementStatus.SUCCESS,
            "Profiling": ProfileMeasurementStatus.PROFILING,
            "ProfileDataOver": ProfileMeasurementStatus.PROFILE_DATA_OVER,
            "InvalidParameter": ProfileMeasurementStatus.INVALID_PARAMETER,
            "ServosNotReady": ProfileMeasurementStatus.SERVOS_NOT_READY,
            "ServosAlarm": ProfileMeasurementStatus.SERVOS_ALARM,
            "StageOnLimit": ProfileMeasurementStatus.STAGE_ON_LIMIT,
            "TorqueLimit": ProfileMeasurementStatus.TORQUE_LIMIT,
        }
        status_enum = status_map.get(status_str, ProfileMeasurementStatus.STOPPING)
        return status_enum.to_dict()

    def _find_peak(self, profile_data: List[Tuple[float, float]]) -> Tuple[int, float, float]:
        """
        Find peak (maximum signal value) in profile data.

        Args:
            profile_data: List of (position, signal_value) tuples

        Returns:
            Tuple of (peak_index, peak_position, peak_value)
        """
        if not profile_data:
            return 0, 0.0, 0.0

        # Find index of maximum signal value
        peak_index = max(range(len(profile_data)), key=lambda i: profile_data[i][1])
        peak_position, peak_value = profile_data[peak_index]

        return peak_index, peak_position, peak_value

    def measure_profile(
        self,
        request: ProfileMeasurementRequest
    ) -> Optional[ProfileDataResponse]:
        """
        Execute profile measurement scan using Profile Class API.

        Uses the ProfileParameter structure and packet-based data retrieval
        as specified in the Software Reference manual (Section 4.7).

        The Profile Class performs measurement from the current axis position,
        sweeping the specified range without requiring explicit positioning.

        Args:
            request: ProfileMeasurementRequest with all measurement parameters

        Returns:
            ProfileDataResponse with peak detection or None if error
        """
        if not self.is_connected() or self._profile is None:
            logger.error("Not connected or Profile not initialized")
            return None

        # Validate axis number
        if not self._validate_axis(request.scan_axis):
            logger.error(f"Invalid scan axis number: {request.scan_axis}")
            return None

        # Get initial position of the scan axis
        try:
            axis = self._axis_components[request.scan_axis]
            initial_position = axis.GetActualPosition()
            logger.info(f"Initial position of axis {request.scan_axis}: {initial_position:.3f} µm")
        except Exception as e:
            logger.error(f"Error getting initial position for axis {request.scan_axis}: {e}")
            return None

        try:
            # Create ProfileParameter structure following manual section 4.7.2.1
            # All parameters must be set as required by the API
            profile_param = Motion.Profile.ProfileParameter()

            # Main axis (X)
            profile_param.mainAxisNumber = request.scan_axis
            profile_param.mainRange = request.scan_range

            # Sub-axes (Y and Z) - optional
            profile_param.sub1AxisNumber = request.sub1_axis_number  # Y axis
            profile_param.sub2AxisNumber = request.sub2_axis_number  # Z axis
            profile_param.sub1Range = request.sub1_range
            profile_param.sub2Range = request.sub2_range

            # Signal channels
            profile_param.signalCh1Number = request.signal_ch1_number  # Analog channel for signal
            profile_param.signalCh2Number = request.signal_ch2_number  # Optional second channel

            # Motion parameters
            profile_param.speed = request.scan_speed
            profile_param.accelRate = request.accel_rate
            profile_param.decelRate = request.decel_rate
            profile_param.smoothing = request.smoothing

            # Log all profile parameters for debugging
            log_msg = (f"Profile parameters: mainAxis={request.scan_axis}, mainRange={request.scan_range}, "
                      f"signalCh1={request.signal_ch1_number}")
            if request.sub1_axis_number > 0:
                log_msg += f", sub1Axis={request.sub1_axis_number}, sub1Range={request.sub1_range}"
            if request.sub2_axis_number > 0:
                log_msg += f", sub2Axis={request.sub2_axis_number}, sub2Range={request.sub2_range}"
            if request.signal_ch2_number > 0:
                log_msg += f", signalCh2={request.signal_ch2_number}"
            log_msg += (f", speed={request.scan_speed}, accel={request.accel_rate}, "
                       f"decel={request.decel_rate}, smoothing={request.smoothing}")
            logger.info(log_msg)

            # Configure profile measurement
            self._profile.SetProfile(profile_param)

            # Start the measurement and check for errors
            start_error_str = str(self._profile.Start())
            if start_error_str != "None":
                # Map error string to ProfileErrorCode enum
                error_info = self._get_profile_error_info(start_error_str)
                logger.error(f"Profile measurement Start() failed: {error_info['error']} "
                           f"(value={error_info['value']}) - {error_info['description']}")
                return ProfileDataResponse(
                    success=False,
                    main_axis_number=request.scan_axis,
                    main_axis_initial_position=initial_position,
                    signal_ch_number=request.signal_ch1_number,
                    scan_range=request.scan_range,
                    scan_speed=request.scan_speed,
                    error_code=error_info['error'],
                    error_value=error_info['value'],
                    error_description=error_info['description']
                )

            logger.info(f"Started profile measurement on axis {request.scan_axis} over {request.scan_range} µm")
            
            # Wait for completion by monitoring status
            while True:
                status_str = str(self._profile.GetProfileStatus())
                status_info = self._get_profile_status_info(status_str)
                logger.debug(f"Profile measurement status: {status_info['status']} "
                           f"(value={status_info['value']}) - {status_info['description']}")

                if status_str in ["Success"]:
                    break
                elif status_str in ["InvalidParameter", "ServosNotReady", "ServosAlarm",
                                   "StageOnLimit", "TorqueLimit", "ProfileDataOver"]:
                    logger.error(f"Profile measurement failed: {status_info['status']} "
                               f"(value={status_info['value']}) - {status_info['description']}")
                    return ProfileDataResponse(
                        success=False,
                        main_axis_number=request.scan_axis,
                        main_axis_initial_position=initial_position,
                        signal_ch_number=request.signal_ch1_number,
                        scan_range=request.scan_range,
                        scan_speed=request.scan_speed,
                        status_code=status_info['status'],
                        status_value=status_info['value'],
                        status_description=status_info['description']
                    )
                time.sleep(0.1)

            # Settling time: allow servo motors to stabilize after operation completes
            # Even though API reports "Success", closed-loop control needs time to settle
            time.sleep(0.2)
            logger.debug("Profile measurement settling time complete")

            # Retrieve profile data using packet-based approach (Section 4.7.1.5)
            packet_sum_index = self._profile.GetProfilePacketSumIndex()
            logger.info(f"Profile measurement completed: {packet_sum_index} packet(s)")

            # Collect all profile data from packets (1000 points per packet max)
            all_main_positions = []
            all_sub1_positions = []
            all_sub2_positions = []
            all_signals_ch1 = []
            all_signals_ch2 = []

            for packet_number in range(1, packet_sum_index + 1):
                # RequestProfileData(packetNumber, clearAfterRead)
                profile_data = self._profile.RequestProfileData(packet_number, False)

                # Extract position and signal data from packet
                # Note: Profile class uses mainPositionList (same as Alignment class in sample program)
                # despite manual showing mainAxisPositionList - the actual .NET API uses the shorter name
                all_main_positions.extend(list(profile_data.mainPositionList))
                all_signals_ch1.extend(list(profile_data.signalCh1List))

                # Extract sub-axis data if available
                # Using the actual .NET property names (not the manual's documentation names)
                if request.sub1_axis_number > 0 and hasattr(profile_data, 'subPositionList'):
                    try:
                        all_sub1_positions.extend(list(profile_data.subPositionList))
                    except Exception as e:
                        logger.warning(f"Could not retrieve subPositionList from packet {packet_number}: {e}")

                if request.sub2_axis_number > 0 and hasattr(profile_data, 'sub2PositionList'):
                    try:
                        all_sub2_positions.extend(list(profile_data.sub2PositionList))
                    except Exception as e:
                        logger.warning(f"Could not retrieve sub2PositionList from packet {packet_number}: {e}")

                if request.signal_ch2_number > 0 and hasattr(profile_data, 'signalCh2List'):
                    try:
                        all_signals_ch2.extend(list(profile_data.signalCh2List))
                    except Exception as e:
                        logger.warning(f"Could not retrieve signalCh2List from packet {packet_number}: {e}")

            # Log what data was retrieved
            logger.info(f"Retrieved data: main_positions={len(all_main_positions)}, "
                       f"sub1_positions={len(all_sub1_positions)}, "
                       f"sub2_positions={len(all_sub2_positions)}, "
                       f"signals_ch1={len(all_signals_ch1)}, "
                       f"signals_ch2={len(all_signals_ch2)}")

            # Combine into list of data points
            total_points = len(all_main_positions)
            if total_points == 0:
                logger.error("No profile data points retrieved")
                return None

            # Use main axis positions and primary signal for peak detection
            profile_data_tuples = list(zip(all_main_positions, all_signals_ch1))

            # Find peak position and value
            peak_index, peak_position, peak_value = self._find_peak(profile_data_tuples)

            # Create data points for response (main axis only - Profile measurement scans one axis)
            data_points = [
                ProfileDataPoint(position=pos, signal=sig)
                for pos, sig in profile_data_tuples
            ]

            # Get final position of the scan axis after measurement
            try:
                final_position = axis.GetActualPosition()
                logger.info(f"Final position of axis {request.scan_axis}: {final_position:.3f} µm")
            except Exception as e:
                logger.warning(f"Error getting final position for axis {request.scan_axis}: {e}")
                final_position = initial_position  # Fallback to initial position if error

            logger.info(f"Profile measurement completed: {total_points} points, "
                       f"peak={peak_value:.6f} at position {peak_position:.3f} µm (index {peak_index})")

            return ProfileDataResponse(
                success=True,
                data_points=data_points,
                total_points=total_points,
                peak_position=peak_position,
                peak_value=peak_value,
                peak_index=peak_index,
                main_axis_number=request.scan_axis,
                main_axis_initial_position=initial_position,
                main_axis_final_position=final_position,
                signal_ch_number=request.signal_ch1_number,
                scan_range=request.scan_range,
                scan_speed=request.scan_speed
            )

        except Exception as e:
            logger.error(f"Error during profile measurement: {e}", exc_info=True)
            return None

    # ========== Optical Alignment ==========

    def _get_optical_alignment_status_info(self, status_str: str) -> dict:
        """
        Convert optical alignment status string to detailed status information.

        Args:
            status_str: Status string from Alignment.GetStatus()

        Returns:
            Dictionary with status, value, and description
        """
        from .models import OpticalAlignmentStatus

        status_map = {
            "Stopping": OpticalAlignmentStatus.STOPPING,
            "Success": OpticalAlignmentStatus.SUCCESS,
            "Aligning": OpticalAlignmentStatus.ALIGNING,
            "FieldSearchRangeOver": OpticalAlignmentStatus.FIELD_SEARCH_RANGE_OVER,
            "ProfileDataOver": OpticalAlignmentStatus.PROFILE_DATA_OVER,
            "PeakSearchCountOver": OpticalAlignmentStatus.PEAK_SEARCH_COUNT_OVER,
            "PeakSearchRangeOver": OpticalAlignmentStatus.PEAK_SEARCH_RANGE_OVER,
            "InvalidParameter": OpticalAlignmentStatus.INVALID_PARAMETER,
            "ServoIsNotReady": OpticalAlignmentStatus.SERVO_IS_NOT_READY,
            "ServoIsAlarm": OpticalAlignmentStatus.SERVO_IS_ALARM,
            "StageOnLimit": OpticalAlignmentStatus.STAGE_ON_LIMIT,
            "VoltageLimit": OpticalAlignmentStatus.VOLTAGE_LIMIT,
            "PMRangeLimit": OpticalAlignmentStatus.PM_RANGE_LIMIT,
            "PMInitRangeChangeFail": OpticalAlignmentStatus.PM_INIT_RANGE_CHANGE_FAIL,
            "PMDisconnected": OpticalAlignmentStatus.PM_DISCONNECTED,
            "RotationAdjustmentFail": OpticalAlignmentStatus.ROTATION_ADJUSTMENT_FAIL,
            "InPositionFail": OpticalAlignmentStatus.IN_POSITION_FAIL,
            "TorqueLimit": OpticalAlignmentStatus.TORQUE_LIMIT,
            "Interrupted": OpticalAlignmentStatus.INTERRUPTED,
        }
        status_enum = status_map.get(status_str, OpticalAlignmentStatus.STOPPING)
        return status_enum.to_dict()

    def _get_aligning_phase_info(self, phase_str: str) -> dict:
        """
        Convert aligning phase string to detailed phase information.

        Args:
            phase_str: Phase string from Alignment.GetAligningStatus()

        Returns:
            Dictionary with phase, value, and description
        """
        from .models import AligningStatusPhase

        phase_map = {
            "NotAligning": AligningStatusPhase.NOT_ALIGNING,
            "Initializing": AligningStatusPhase.INITIALIZING,
            "FieldSearching": AligningStatusPhase.FIELD_SEARCHING,
            "PeakSearchingX": AligningStatusPhase.PEAK_SEARCHING_X,
            "PeakSearchingY": AligningStatusPhase.PEAK_SEARCHING_Y,
            "PeakSearchingZ": AligningStatusPhase.PEAK_SEARCHING_Z,
            "PeakSearchXCh2": AligningStatusPhase.PEAK_SEARCH_X_CH2,
        }
        phase_enum = phase_map.get(phase_str, AligningStatusPhase.NOT_ALIGNING)
        return phase_enum.to_dict()

    def execute_flat_alignment(
        self,
        request
    ):
        """
        Execute flat (2D) optical alignment.

        Uses the correct API pattern: create FlatParameter structure, set all parameters,
        call SetFlat(), SetMeasurementWaveLength(), StartFlat(), poll status, and retrieve
        profile data via packets.

        Args:
            request: FlatAlignmentRequest with all ~30 parameters

        Returns:
            AlignmentResponse with success status, optical power, peak positions, and profile data
        """
        from .models import AlignmentResponse, FlatAlignmentRequest

        if not self.is_connected() or self._alignment is None:
            logger.error("Not connected or Alignment not initialized")
            return None

        try:
            start_time = time.time()

            # Create FlatParameter structure
            flat_params = Motion.Alignment.FlatParameter()

            # Set all ~30 parameters from request
            flat_params.mainStageNumberX = request.mainStageNumberX
            flat_params.mainStageNumberY = request.mainStageNumberY
            flat_params.subStageNumberXY = request.subStageNumberXY
            flat_params.subAngleX = request.subAngleX
            flat_params.subAngleY = request.subAngleY

            flat_params.pmCh = request.pmCh
            flat_params.analogCh = request.analogCh
            flat_params.wavelength = request.wavelength
            flat_params.pmAutoRangeUpOn = request.pmAutoRangeUpOn
            flat_params.pmInitRangeSettingOn = request.pmInitRangeSettingOn
            flat_params.pmInitRange = request.pmInitRange

            flat_params.fieldSearchThreshold = request.fieldSearchThreshold
            flat_params.peakSearchThreshold = request.peakSearchThreshold

            flat_params.searchRangeX = request.searchRangeX
            flat_params.searchRangeY = request.searchRangeY

            flat_params.fieldSearchPitchX = request.fieldSearchPitchX
            flat_params.fieldSearchPitchY = request.fieldSearchPitchY
            flat_params.fieldSearchFirstPitchX = request.fieldSearchFirstPitchX
            flat_params.fieldSearchSpeedX = request.fieldSearchSpeedX
            flat_params.fieldSearchSpeedY = request.fieldSearchSpeedY

            flat_params.peakSearchSpeedX = request.peakSearchSpeedX
            flat_params.peakSearchSpeedY = request.peakSearchSpeedY

            flat_params.smoothingRangeX = request.smoothingRangeX
            flat_params.smoothingRangeY = request.smoothingRangeY

            flat_params.centroidThresholdX = request.centroidThresholdX
            flat_params.centroidThresholdY = request.centroidThresholdY

            flat_params.convergentRangeX = request.convergentRangeX
            flat_params.convergentRangeY = request.convergentRangeY
            flat_params.comparisonCount = request.comparisonCount
            flat_params.maxRepeatCount = request.maxRepeatCount

            # Apply parameters to alignment hardware
            self._alignment.SetFlat(flat_params)
            self._alignment.SetMeasurementWaveLength(request.pmCh, request.wavelength)

            # Measure initial optical power
            initial_power = float(self._alignment.GetPower(request.pmCh))
            logger.info(f"Flat alignment starting - Initial power: {initial_power:.3f} dBm")

            # Start flat alignment (NOT ExecuteFlat!)
            self._alignment.StartFlat()
            time.sleep(0.1)  # Short delay to ensure alignment has started

            # Poll status until completion
            last_phase_str = None
            while True:
                status_str = str(self._alignment.GetStatus())
                phase_str = str(self._alignment.GetAligningStatus())

                # Log phase changes
                if phase_str != last_phase_str:
                    phase_info = self._get_aligning_phase_info(phase_str)
                    logger.info(f"Flat alignment phase: {phase_info['phase']} - {phase_info['description']}")
                    last_phase_str = phase_str

                # Check if completed
                if status_str != "Aligning":
                    # Alignment finished (success or error)
                    status_info = self._get_optical_alignment_status_info(status_str)
                    phase_info = self._get_aligning_phase_info(phase_str)

                    execution_time = time.time() - start_time

                    if status_str == "Success":
                        # Settling time: allow servo motors to stabilize
                        time.sleep(0.2)
                        logger.debug("Flat alignment settling time complete")

                        # Measure final optical power
                        final_power = float(self._alignment.GetPower(request.pmCh))
                        power_improvement = final_power - initial_power

                        logger.info(f"Flat alignment SUCCESS - Final power: {final_power:.3f} dBm, "
                                  f"Improvement: {power_improvement:+.3f} dB, Time: {execution_time:.2f}s")

                        # Retrieve profile data via packet-based retrieval
                        field_search_profile = self._retrieve_alignment_profile_data(
                            Motion.Alignment.ProfileDataType.FieldSearch
                        )
                        peak_search_x_profile = self._retrieve_alignment_profile_data(
                            Motion.Alignment.ProfileDataType.PeakSearchX
                        )
                        peak_search_y_profile = self._retrieve_alignment_profile_data(
                            Motion.Alignment.ProfileDataType.PeakSearchY
                        )

                        # Get peak positions by reading actual axis positions after alignment
                        # (alignment moves stages to optimal position, so final position = peak)
                        peak_x = float(self._axis_components[request.mainStageNumberX].GetActualPosition())
                        peak_y = float(self._axis_components[request.mainStageNumberY].GetActualPosition())

                        return AlignmentResponse(
                            success=True,
                            status_code=status_info['status'],
                            status_value=status_info['value'],
                            status_description=status_info['description'],
                            phase_code=phase_info['phase'],
                            phase_value=phase_info['value'],
                            phase_description=phase_info['description'],
                            initial_power=initial_power,
                            final_power=final_power,
                            power_improvement=power_improvement,
                            peak_position_x=peak_x,
                            peak_position_y=peak_y,
                            execution_time=execution_time,
                            field_search_profile=field_search_profile,
                            peak_search_x_profile=peak_search_x_profile,
                            peak_search_y_profile=peak_search_y_profile
                        )
                    else:
                        # Alignment failed - get error axis ID for diagnostics
                        try:
                            error_axis_id = int(self._alignment.GetErrorAxisID())
                            logger.error(f"Flat alignment FAILED - Status: {status_info['status']} - "
                                       f"{status_info['description']}, Error Axis ID: {error_axis_id}, "
                                       f"Time: {execution_time:.2f}s")
                        except Exception as e:
                            logger.error(f"Flat alignment FAILED - Status: {status_info['status']} - "
                                       f"{status_info['description']}, Time: {execution_time:.2f}s "
                                       f"(Could not get error axis ID: {e})")

                        return AlignmentResponse(
                            success=False,
                            status_code=status_info['status'],
                            status_value=status_info['value'],
                            status_description=status_info['description'],
                            phase_code=phase_info['phase'],
                            phase_value=phase_info['value'],
                            phase_description=phase_info['description'],
                            execution_time=execution_time,
                            error_message=f"Flat alignment failed: {status_info['description']}"
                        )

                # Still running, wait before next poll
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error during flat alignment: {e}", exc_info=True)
            return None

    def _retrieve_alignment_profile_data(self, profile_type) -> Optional[List]:
        """
        Retrieve alignment profile data using packet-based retrieval.

        Args:
            profile_type: ProfileDataType enum (FieldSearch, PeakSearchX, PeakSearchY, PeakSearchZ)

        Returns:
            List of ProfileDataPoint objects, or None if no data available
        """
        from .models import ProfileDataPoint

        try:
            # Get total number of packets for this profile type
            packet_sum_index = self._alignment.GetProfilePacketSumIndex(profile_type)
            
            logger.info(f"Profile type {profile_type}: {packet_sum_index} packet(s)")

            if packet_sum_index == 0:
                return None

            profile_data = []

            # Retrieve all packets
            for packet_number in range(1, packet_sum_index + 1):
                # RequestProfileData(profileType, packetNumber, isClear)
                # isClear=False to keep data for multiple retrievals
                profile_packet = self._alignment.RequestProfileData(profile_type, packet_number, False)

                # Log packet details (same as sample program)
                if profile_packet is not None:
                    logger.info(f"  Packet {packet_number}: packetIndex={profile_packet.packetIndex}, "
                              f"dataCount={profile_packet.dataCount}")

                # Each packet contains multiple data points
                # The packet structure has mainPositionList and signalCh1List arrays
                # (as documented in suruga_sample_program.py)
                if profile_packet is not None and profile_packet.mainPositionList is not None:
                    for i in range(len(profile_packet.mainPositionList)):
                        profile_data.append(ProfileDataPoint(
                            position=float(profile_packet.mainPositionList[i]),
                            signal=float(profile_packet.signalCh1List[i])
                        ))

            # Log summary of retrieved data
            if profile_data:
                positions = [p.position for p in profile_data]
                signals = [p.signal for p in profile_data]
                logger.info(f"Retrieved {len(profile_data)} points - "
                          f"Position range: [{min(positions):.3f}, {max(positions):.3f}] µm, "
                          f"Signal range: [{min(signals):.6f}, {max(signals):.6f}]")
            
            return profile_data if profile_data else None

        except Exception as e:
            logger.warning(f"Could not retrieve alignment profile data for type {profile_type}: {e}")
            return None

    def _retrieve_angle_adjustment_profile_data(self, angle_adjustment, profile_type) -> Optional[List]:
        """
        Retrieve angle adjustment profile data using packet-based retrieval.

        Args:
            angle_adjustment: The AngleAdjustment object (left or right)
            profile_type: ProfileDataType enum value for angle adjustment
                         (ContactZ=0, AdjustmentTx=1, AdjustmentTy=2)

        Returns:
            List of ProfileDataPoint objects, or None if no data available
        """
        from .models import ProfileDataPoint

        try:
            # Get total number of packets for this profile type
            # AngleAdjustment class has GetProfilePacketSumIndex method similar to Alignment
            packet_sum_index = angle_adjustment.GetProfilePacketSumIndex(profile_type)

            logger.info(f"Angle adjustment profile type {profile_type}: {packet_sum_index} packet(s)")

            if packet_sum_index == 0:
                return None

            profile_data = []

            # Retrieve all packets
            for packet_number in range(1, packet_sum_index + 1):
                # RequestProfileData(profileDataType, index)
                # Note: AngleAdjustment.RequestProfileData only takes 2 arguments (no isClear parameter)
                profile_packet = angle_adjustment.RequestProfileData(profile_type, packet_number)

                # Log packet details
                if profile_packet is not None:
                    logger.info(f"  Packet {packet_number}: packetIndex={profile_packet.packetIndex}, "
                              f"dataCount={profile_packet.dataCount}")

                # Each packet contains multiple data points
                # The packet structure has mainPositionList and signalCh1List arrays
                if profile_packet is not None and profile_packet.mainPositionList is not None:
                    for i in range(len(profile_packet.mainPositionList)):
                        profile_data.append(ProfileDataPoint(
                            position=float(profile_packet.mainPositionList[i]),
                            signal=float(profile_packet.signalCh1List[i])
                        ))

            # Log summary of retrieved data
            if profile_data:
                positions = [p.position for p in profile_data]
                signals = [p.signal for p in profile_data]
                logger.info(f"Retrieved {len(profile_data)} points - "
                          f"Position range: [{min(positions):.3f}, {max(positions):.3f}] µm, "
                          f"Signal range: [{min(signals):.6f}, {max(signals):.6f}]")

            return profile_data if profile_data else None

        except Exception as e:
            logger.warning(f"Could not retrieve angle adjustment profile data for type {profile_type}: {e}")
            return None

    def execute_focus_alignment(
        self,
        request
    ):
        """
        Execute focus (3D) optical alignment with Z-axis optimization.

        Uses the correct API pattern: create FocusParameter structure, set all parameters,
        call SetFocus(), SetMeasurementWaveLength(), StartFocus(), poll status, and retrieve
        profile data via packets including Z-axis data.

        Args:
            request: FocusAlignmentRequest with all ~31 parameters (including zMode)

        Returns:
            AlignmentResponse with success status, optical power, peak positions (X,Y,Z), and profile data
        """
        from .models import AlignmentResponse, FocusAlignmentRequest

        if not self.is_connected() or self._alignment is None:
            logger.error("Not connected or Alignment not initialized")
            return None

        try:
            start_time = time.time()

            # Create FocusParameter structure
            focus_params = Motion.Alignment.FocusParameter()

            # Set zMode (specific to Focus alignment)
            focus_params.zMode = request.zMode  # "Round", "Triangle", or "Linear"

            # Set all ~30 parameters from request (same as Flat)
            focus_params.mainStageNumberX = request.mainStageNumberX
            focus_params.mainStageNumberY = request.mainStageNumberY
            focus_params.subStageNumberXY = request.subStageNumberXY
            focus_params.subAngleX = request.subAngleX
            focus_params.subAngleY = request.subAngleY

            focus_params.pmCh = request.pmCh
            focus_params.analogCh = request.analogCh
            focus_params.wavelength = request.wavelength
            focus_params.pmAutoRangeUpOn = request.pmAutoRangeUpOn
            focus_params.pmInitRangeSettingOn = request.pmInitRangeSettingOn
            focus_params.pmInitRange = request.pmInitRange

            focus_params.fieldSearchThreshold = request.fieldSearchThreshold
            focus_params.peakSearchThreshold = request.peakSearchThreshold

            focus_params.searchRangeX = request.searchRangeX
            focus_params.searchRangeY = request.searchRangeY

            focus_params.fieldSearchPitchX = request.fieldSearchPitchX
            focus_params.fieldSearchPitchY = request.fieldSearchPitchY
            focus_params.fieldSearchFirstPitchX = request.fieldSearchFirstPitchX
            focus_params.fieldSearchSpeedX = request.fieldSearchSpeedX
            focus_params.fieldSearchSpeedY = request.fieldSearchSpeedY

            focus_params.peakSearchSpeedX = request.peakSearchSpeedX
            focus_params.peakSearchSpeedY = request.peakSearchSpeedY

            focus_params.smoothingRangeX = request.smoothingRangeX
            focus_params.smoothingRangeY = request.smoothingRangeY

            focus_params.centroidThresholdX = request.centroidThresholdX
            focus_params.centroidThresholdY = request.centroidThresholdY

            focus_params.convergentRangeX = request.convergentRangeX
            focus_params.convergentRangeY = request.convergentRangeY
            focus_params.comparisonCount = request.comparisonCount
            focus_params.maxRepeatCount = request.maxRepeatCount

            # Apply parameters to alignment hardware
            self._alignment.SetFocus(focus_params)
            self._alignment.SetMeasurementWaveLength(request.pmCh, request.wavelength)

            # Measure initial optical power
            initial_power = float(self._alignment.GetPower(request.pmCh))
            logger.info(f"Focus alignment starting (zMode={request.zMode}) - Initial power: {initial_power:.3f} dBm")

            # Start focus alignment (NOT ExecuteFocus!)
            self._alignment.StartFocus()

            # Poll status until completion
            last_phase_str = None
            while True:
                status_str = str(self._alignment.GetStatus())
                phase_str = str(self._alignment.GetAligningStatus())

                # Log phase changes
                if phase_str != last_phase_str:
                    phase_info = self._get_aligning_phase_info(phase_str)
                    logger.info(f"Focus alignment phase: {phase_info['phase']} - {phase_info['description']}")
                    last_phase_str = phase_str

                # Check if completed
                if status_str != "Aligning":
                    # Alignment finished (success or error)
                    status_info = self._get_optical_alignment_status_info(status_str)
                    phase_info = self._get_aligning_phase_info(phase_str)

                    execution_time = time.time() - start_time

                    if status_str == "Success":
                        # Settling time: allow servo motors to stabilize
                        time.sleep(0.2)
                        logger.debug("Focus alignment settling time complete")

                        # Measure final optical power
                        final_power = float(self._alignment.GetPower(request.pmCh))
                        power_improvement = final_power - initial_power

                        logger.info(f"Focus alignment SUCCESS - Final power: {final_power:.3f} dBm, "
                                  f"Improvement: {power_improvement:+.3f} dB, Time: {execution_time:.2f}s")

                        # Retrieve profile data via packet-based retrieval (including Z-axis)
                        field_search_profile = self._retrieve_alignment_profile_data(
                            Motion.Alignment.ProfileDataType.FieldSearch
                        )
                        peak_search_x_profile = self._retrieve_alignment_profile_data(
                            Motion.Alignment.ProfileDataType.PeakSearchX
                        )
                        peak_search_y_profile = self._retrieve_alignment_profile_data(
                            Motion.Alignment.ProfileDataType.PeakSearchY
                        )
                        peak_search_z_profile = self._retrieve_alignment_profile_data(
                            Motion.Alignment.ProfileDataType.PeakSearchZ
                        )

                        # Get peak positions by reading actual axis positions after alignment
                        # (alignment moves stages to optimal position, so final position = peak)
                        peak_x = float(self._axis_components[request.mainStageNumberX].GetActualPosition())
                        peak_y = float(self._axis_components[request.mainStageNumberY].GetActualPosition())
                        # For focus alignment, need to get Z-axis peak position
                        # Assuming Z-axis is the stage used for focus (typically subStageNumberXY or a dedicated Z stage)
                        # You may need to adjust this based on your hardware configuration
                        try:
                            # Try to get Z peak position - the exact stage number may vary
                            # This is a placeholder and may need adjustment based on hardware setup
                            peak_z = float(self._axis_components[request.subStageNumberXY].GetActualPosition()) if request.subStageNumberXY > 0 else None
                        except:
                            peak_z = None
                            logger.warning("Could not retrieve Z peak position")

                        return AlignmentResponse(
                            success=True,
                            status_code=status_info['status'],
                            status_value=status_info['value'],
                            status_description=status_info['description'],
                            phase_code=phase_info['phase'],
                            phase_value=phase_info['value'],
                            phase_description=phase_info['description'],
                            initial_power=initial_power,
                            final_power=final_power,
                            power_improvement=power_improvement,
                            peak_position_x=peak_x,
                            peak_position_y=peak_y,
                            peak_position_z=peak_z,
                            execution_time=execution_time,
                            field_search_profile=field_search_profile,
                            peak_search_x_profile=peak_search_x_profile,
                            peak_search_y_profile=peak_search_y_profile,
                            peak_search_z_profile=peak_search_z_profile
                        )
                    else:
                        # Alignment failed
                        logger.error(f"Focus alignment FAILED - Status: {status_info['status']} - "
                                   f"{status_info['description']}, Time: {execution_time:.2f}s")

                        return AlignmentResponse(
                            success=False,
                            status_code=status_info['status'],
                            status_value=status_info['value'],
                            status_description=status_info['description'],
                            phase_code=phase_info['phase'],
                            phase_value=phase_info['value'],
                            phase_description=phase_info['description'],
                            execution_time=execution_time,
                            error_message=f"Focus alignment failed: {status_info['description']}"
                        )

                # Still running, wait before next poll
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error during focus alignment: {e}", exc_info=True)
            return None

    # ========== Angle Adjustment ==========

    def _get_angle_adjustment_status_info(self, status_str: str) -> dict:
        """
        Convert angle adjustment status string to detailed status information.

        Args:
            status_str: Status string from AngleAdjustment.GetStatus()

        Returns:
            Dictionary with status, value, and description
        """
        status_map = {
            "Stopping": AngleAdjustmentStatus.STOPPING,
            "Success": AngleAdjustmentStatus.SUCCESS,
            "Adjusting": AngleAdjustmentStatus.ADJUSTING,
            "ProfileDataOver": AngleAdjustmentStatus.PROFILE_DATA_OVER,
            "InvalidParameter": AngleAdjustmentStatus.INVALID_PARAMETER,
            "ServoIsNotReady": AngleAdjustmentStatus.SERVO_IS_NOT_READY,
            "ServoIsAlarm": AngleAdjustmentStatus.SERVO_IS_ALARM,
            "StageOnLimit": AngleAdjustmentStatus.STAGE_ON_LIMIT,
            "SignalLowerLimit": AngleAdjustmentStatus.SIGNAL_LOWER_LIMIT,
            "CouldNotContact": AngleAdjustmentStatus.COULD_NOT_CONTACT,
            "CouldnotContact": AngleAdjustmentStatus.COULD_NOT_CONTACT,  # API uses lowercase 'n'
            "AdjustCountOver": AngleAdjustmentStatus.ADJUST_COUNT_OVER,
            "AngleAdjustRangeOver": AngleAdjustmentStatus.ANGLE_ADJUST_RANGE_OVER,
            "LostContact": AngleAdjustmentStatus.LOST_CONTACT,
        }
        status_enum = status_map.get(status_str, AngleAdjustmentStatus.STOPPING)
        return status_enum.to_dict()

    def _get_adjusting_status_info(self, phase_str: str) -> dict:
        """
        Convert adjusting phase string to detailed phase information.

        Args:
            phase_str: Phase string from AngleAdjustment.GetAdjustingStatus()

        Returns:
            Dictionary with phase, value, and description
        """
        phase_map = {
            "NotAdjusting": AdjustingStatus.NOT_ADJUSTING,
            "Initializing": AdjustingStatus.INITIALIZING,
            "ContactingZ": AdjustingStatus.CONTACTING_Z,
            "AdjustingTx": AdjustingStatus.ADJUSTING_TX,
            "AdjustingTy": AdjustingStatus.ADJUSTING_TY,
        }
        phase_enum = phase_map.get(phase_str, AdjustingStatus.NOT_ADJUSTING)
        return phase_enum.to_dict()

    def execute_angle_adjustment(
        self,
        request: AngleAdjustmentRequest
    ) -> Optional[AngleAdjustmentResponse]:
        """
        Execute angle adjustment for the specified stage (LEFT or RIGHT).

        Configures parameters, starts adjustment, waits for completion,
        and returns detailed results.

        Args:
            request: AngleAdjustmentRequest with stage selection and all parameters

        Returns:
            AngleAdjustmentResponse with success status and details, or None if error
        """
        stage_name = request.stage.name  # "LEFT" or "RIGHT" for logging

        # Select the correct angle adjustment object based on stage
        if request.stage == AngleAdjustmentStage.LEFT:
            angle_adjustment = self._angle_adjustment_left
        else:
            angle_adjustment = self._angle_adjustment_right

        # Check connection and initialization
        if not self.is_connected() or angle_adjustment is None:
            logger.error(f"Not connected or {stage_name} AngleAdjustment not initialized")
            return None

        try:
            start_time = time.time()

            # Auto-determine stage-specific hardware parameters
            # These are constants determined by physical stage wiring and cannot be changed
            if request.stage == AngleAdjustmentStage.LEFT:
                # LEFT stage uses axes 1-6
                signal_ch_number = 5  # Analog input channel 5
                unlock_dout_ch_number = 1  # Digital output channel 1
                contact_axis_number = 3  # Z1 axis
                rotation_center_x = 1  # X1 axis
                rotation_center_y = 2  # Y1 axis
                rotation_center_z = 3  # Z1 axis
            else:  # RIGHT
                # RIGHT stage uses axes 7-12
                signal_ch_number = 6  # Analog input channel 6
                unlock_dout_ch_number = 2  # Digital output channel 2
                contact_axis_number = 9  # Z2 axis
                rotation_center_x = 7  # X2 axis
                rotation_center_y = 8  # Y2 axis
                rotation_center_z = 9  # Z2 axis

            # Configure angle adjustment parameters
            # All parameters come from request (which uses models.py defaults)
            params = Motion.AngleAdjustment.AngleAdjustmentParameter()

            # Basic parameters
            params.gap = request.gap
            params.signalChNumber = signal_ch_number  # Auto-determined
            params.signalLowerLimit = request.signal_lower_limit
            params.unlockDOutChNumber = unlock_dout_ch_number  # Auto-determined
            params.unlockDOutControlOn = request.unlock_dout_control_on

            # Contact detection parameters
            params.contactAxisNumber = contact_axis_number  # Auto-determined
            params.contactSearchRange = request.contact_search_range
            params.contactSearchSpeed = request.contact_search_speed
            params.contactSmoothing = request.contact_smoothing
            params.contactSensitivity = request.contact_sensitivity
            params.pushDistance = request.push_distance

            # Angle adjustment axes
            params.angleAxisNumberTx = request.angle_axis_number_tx
            params.angleAxisNumberTy = request.angle_axis_number_ty

            # Angle search parameters
            params.angleSearchRangeTx = request.angle_search_range_tx
            params.angleSearchRangeTy = request.angle_search_range_ty
            params.angleSearchSpeedTx = request.angle_search_speed_tx
            params.angleSearchSpeedTy = request.angle_search_speed_ty

            # Angle smoothing and sensitivity
            params.angleSmoothingTx = request.angle_smoothing_tx
            params.angleSmoothingTy = request.angle_smoothing_ty
            params.angleSensitivityTx = request.angle_sensitivity_tx
            params.angleSensitivityTy = request.angle_sensitivity_ty

            # Angle convergence parameters
            params.angleJudgeCountTx = request.angle_judge_count_tx
            params.angleJudgeCountTy = request.angle_judge_count_ty
            params.angleConvergentRangeTx = request.angle_convergent_range_tx
            params.angleConvergentRangeTy = request.angle_convergent_range_ty
            params.angleComparisonCount = request.angle_comparison_count
            params.angleMaxCount = request.angle_max_count

            # Configure rotation center parameters
            rotation_center = Motion.Axis3D.RotationCenter()
            rotation_center.enabled = request.rotation_center_enabled
            rotation_center.mainStageNumberX = rotation_center_x  # Auto-determined
            rotation_center.mainStageNumberY = rotation_center_y  # Auto-determined
            rotation_center.mainStageNumberZ = rotation_center_z  # Auto-determined

            # Log all parameters being set for debugging
            logger.info(f"{stage_name} angle adjustment parameters:")
            logger.info(f"  Basic: gap={params.gap}, signalCh={params.signalChNumber}, signalLowerLimit={params.signalLowerLimit}")
            logger.info(f"  Unlock: unlockDOutCh={params.unlockDOutChNumber}, unlockDOutControlOn={params.unlockDOutControlOn}")
            logger.info(f"  Contact: axis={params.contactAxisNumber}, searchRange={params.contactSearchRange}, "
                       f"searchSpeed={params.contactSearchSpeed}, smoothing={params.contactSmoothing}, "
                       f"sensitivity={params.contactSensitivity}, pushDistance={params.pushDistance}")
            logger.info(f"  Angle axes: Tx={params.angleAxisNumberTx}, Ty={params.angleAxisNumberTy}")
            logger.info(f"  Angle search: rangeTx={params.angleSearchRangeTx}, rangeTy={params.angleSearchRangeTy}, "
                       f"speedTx={params.angleSearchSpeedTx}, speedTy={params.angleSearchSpeedTy}")
            logger.info(f"  Angle smoothing: Tx={params.angleSmoothingTx}, Ty={params.angleSmoothingTy}")
            logger.info(f"  Angle sensitivity: Tx={params.angleSensitivityTx}, Ty={params.angleSensitivityTy}")
            logger.info(f"  Angle convergence: judgeTx={params.angleJudgeCountTx}, judgeTy={params.angleJudgeCountTy}, "
                       f"convergentTx={params.angleConvergentRangeTx}, convergentTy={params.angleConvergentRangeTy}")
            logger.info(f"  Angle limits: comparisonCount={params.angleComparisonCount}, maxCount={params.angleMaxCount}")
            logger.info(f"  Rotation center: enabled={rotation_center.enabled}, X={rotation_center.mainStageNumberX}, "
                       f"Y={rotation_center.mainStageNumberY}, Z={rotation_center.mainStageNumberZ}")

            # Apply parameters to hardware
            angle_adjustment.SetParameter(params, rotation_center)

            # Allow hardware time to process parameter configuration
            time.sleep(0.2)
            logger.info(f"{stage_name} angle adjustment parameters configured")

            # Safety check: Verify contact sensor is unlocked before starting
            # Digital output must be False (UNLOCKED) to allow movement
            digital_output_state = self.get_digital_output(unlock_dout_ch_number)
            if digital_output_state is None:
                logger.error(f"Failed to read digital output channel {unlock_dout_ch_number} state")
                return AngleAdjustmentResponse(
                    success=False,
                    status_code="Error",
                    status_value=-1,
                    status_description="Failed to read digital output state",
                    error_message=f"Cannot verify contact sensor lock state for {stage_name} stage"
                )

            if digital_output_state:  # True = LOCKED
                logger.error(f"{stage_name} stage contact sensor is LOCKED (channel {unlock_dout_ch_number})")
                return AngleAdjustmentResponse(
                    success=False,
                    status_code="InvalidParameter",
                    status_value=4,
                    status_description="Contact sensor is locked",
                    error_message=f"{stage_name} stage contact sensor must be UNLOCKED before angle adjustment. "
                                f"Digital output channel {unlock_dout_ch_number} is currently LOCKED (True). "
                                f"Please unlock the contact sensor first."
                )

            logger.info(f"{stage_name} stage contact sensor verified as UNLOCKED")

            # Measure initial analog signal before starting adjustment
            initial_signal = self.get_analog_input(signal_ch_number)
            if initial_signal is not None:
                logger.info(f"Initial signal on channel {signal_ch_number}: {initial_signal:.6f} V")
            else:
                logger.warning(f"Could not read initial signal on channel {signal_ch_number}")

            # Check status BEFORE starting to see if there's stale state
            pre_start_status = str(angle_adjustment.GetStatus())
            pre_start_phase = str(angle_adjustment.GetAdjustingStatus())
            logger.info(f"Status BEFORE Start(): status={pre_start_status}, phase={pre_start_phase}")

            # Start the adjustment
            angle_adjustment.Start()
            time.sleep(0.2)  # Short delay to ensure adjustment has started
            logger.info(f"{stage_name} angle adjustment started")

            # Check status AFTER starting to verify it changed
            post_start_status = str(angle_adjustment.GetStatus())
            post_start_phase = str(angle_adjustment.GetAdjustingStatus())
            logger.info(f"Status AFTER Start(): status={post_start_status}, phase={post_start_phase}")

            # Wait for completion
            timeout = 60  # 60 seconds timeout
            poll_interval = 0.1
            start_wait_time = time.time()

            last_phase = None
            last_status = None
            while True:
                status_str = str(angle_adjustment.GetStatus())
                phase_str = str(angle_adjustment.GetAdjustingStatus())

                # Log status changes
                if status_str != last_status:
                    status_info = self._get_angle_adjustment_status_info(status_str)
                    logger.info(f"{stage_name} angle adjustment status: {status_info['status']} - {status_info['description']}")
                    last_status = status_str

                # Log phase changes
                if phase_str != last_phase:
                    phase_info = self._get_adjusting_status_info(phase_str)
                    logger.info(f"{stage_name} angle adjustment phase: {phase_info['phase']} - {phase_info['description']}")
                    last_phase = phase_str

                # Check if adjustment is still running (following legacy code pattern)
                if status_str != "Adjusting":
                    # Adjustment finished - check if successful or error
                    if status_str == "Success":
                        # Settling time: allow servo motors to stabilize after adjustment completes
                        # Even though API reports "Success", closed-loop control needs time to settle
                        time.sleep(0.2)
                        logger.debug(f"{stage_name} angle adjustment settling time complete")

                        execution_time = time.time() - start_time
                        status_info = self._get_angle_adjustment_status_info(status_str)
                        phase_info = self._get_adjusting_status_info(phase_str)

                        # Measure final analog signal
                        final_signal = self.get_analog_input(signal_ch_number)
                        signal_improvement = None
                        if final_signal is not None and initial_signal is not None:
                            signal_improvement = final_signal - initial_signal
                            logger.info(f"{stage_name} angle adjustment SUCCESS - Final signal: {final_signal:.6f} V, "
                                      f"Improvement: {signal_improvement:+.6f} V, Time: {execution_time:.2f}s")
                        else:
                            logger.info(f"{stage_name} angle adjustment completed successfully in {execution_time:.2f}s")

                        # Retrieve profile data via packet-based retrieval
                        # Use .NET enum types for ProfileDataType (ContactZ, AdjustmentTx, AdjustmentTy)
                        contact_z_profile = self._retrieve_angle_adjustment_profile_data(
                            angle_adjustment,
                            Motion.AngleAdjustment.ProfileDataType.ContactZ
                        )
                        adjusting_tx_profile = self._retrieve_angle_adjustment_profile_data(
                            angle_adjustment,
                            Motion.AngleAdjustment.ProfileDataType.AdjustmentTx
                        )
                        adjusting_ty_profile = self._retrieve_angle_adjustment_profile_data(
                            angle_adjustment,
                            Motion.AngleAdjustment.ProfileDataType.AdjustmentTy
                        )

                        return AngleAdjustmentResponse(
                            success=True,
                            status_code=status_info['status'],
                            status_value=status_info['value'],
                            status_description=status_info['description'],
                            phase_code=phase_info['phase'],
                            phase_value=phase_info['value'],
                            phase_description=phase_info['description'],
                            initial_signal=initial_signal,
                            final_signal=final_signal,
                            signal_improvement=signal_improvement,
                            execution_time=execution_time,
                            contact_z_profile=contact_z_profile,
                            adjusting_tx_profile=adjusting_tx_profile,
                            adjusting_ty_profile=adjusting_ty_profile
                        )

                    elif status_str in ["InvalidParameter", "ServoIsNotReady", "ServoIsAlarm",
                                       "StageOnLimit", "SignalLowerLimit", "CouldNotContact", "CouldnotContact",
                                       "AdjustCountOver", "AngleAdjustRangeOver", "LostContact",
                                       "ProfileDataOver"]:
                        execution_time = time.time() - start_time
                        status_info = self._get_angle_adjustment_status_info(status_str)
                        phase_info = self._get_adjusting_status_info(phase_str)

                        logger.error(f"{stage_name} angle adjustment failed: {status_info['status']} - {status_info['description']}")
                        return AngleAdjustmentResponse(
                            success=False,
                            status_code=status_info['status'],
                            status_value=status_info['value'],
                            status_description=status_info['description'],
                            phase_code=phase_info['phase'],
                            phase_value=phase_info['value'],
                            phase_description=phase_info['description'],
                            execution_time=execution_time,
                            error_message=f"{status_info['status']}: {status_info['description']}"
                        )
                    else:
                        # Unknown status - treat as error
                        execution_time = time.time() - start_time
                        status_info = self._get_angle_adjustment_status_info(status_str)
                        phase_info = self._get_adjusting_status_info(phase_str)

                        logger.error(f"{stage_name} angle adjustment failed with unknown status: {status_str}")
                        return AngleAdjustmentResponse(
                            success=False,
                            status_code=status_info['status'],
                            status_value=status_info['value'],
                            status_description=status_info['description'],
                            phase_code=phase_info['phase'],
                            phase_value=phase_info['value'],
                            phase_description=phase_info['description'],
                            execution_time=execution_time,
                            error_message=f"Unknown status: {status_str}"
                        )

                # Check timeout
                if time.time() - start_wait_time > timeout:
                    execution_time = time.time() - start_time
                    logger.error(f"{stage_name} angle adjustment timed out after {timeout}s")
                    return AngleAdjustmentResponse(
                        success=False,
                        status_code="Timeout",
                        status_value=-1,
                        status_description=f"Adjustment timed out after {timeout} seconds",
                        execution_time=execution_time,
                        error_message=f"Timeout: Adjustment did not complete within {timeout} seconds"
                    )

                time.sleep(poll_interval)

        except Exception as e:
            logger.error(f"Error during {stage_name} angle adjustment: {e}", exc_info=True)
            return None

    def stop_angle_adjustment(self, stage: AngleAdjustmentStage) -> bool:
        """
        Stop the currently running angle adjustment for the specified stage.

        This method calls the Stop() method on the AngleAdjustment object,
        which immediately halts any running adjustment operation.

        Args:
            stage: AngleAdjustmentStage enum (LEFT or RIGHT)

        Returns:
            True if stop command was sent successfully, False otherwise
        """
        # Select the correct angle adjustment object based on stage
        if stage == AngleAdjustmentStage.LEFT:
            angle_adjustment = self._angle_adjustment_left
        else:
            angle_adjustment = self._angle_adjustment_right

        stage_name = stage.name  # "LEFT" or "RIGHT" for logging

        if not self.is_connected() or angle_adjustment is None:
            logger.error(f"Not connected or {stage_name} AngleAdjustment not initialized")
            return False

        try:
            angle_adjustment.Stop()
            logger.info(f"{stage_name} angle adjustment stop command sent")
            return True
        except Exception as e:
            logger.error(f"Error stopping {stage_name} angle adjustment: {e}", exc_info=True)
            return False

    async def execute_angle_adjustment_async(
        self,
        request: AngleAdjustmentRequest,
        cancellation_event: Optional[asyncio.Event] = None,
        progress_callback: Optional[Callable[[dict], None]] = None
    ) -> Optional[AngleAdjustmentResponse]:
        """
        Async wrapper for execute_angle_adjustment that supports cancellation and progress updates.

        Runs the synchronous .NET operations in a thread pool to avoid blocking the event loop.
        Checks cancellation event during polling and emits progress updates via callback.

        Args:
            request: AngleAdjustmentRequest with stage selection and parameters
            cancellation_event: Optional asyncio.Event to signal cancellation
            progress_callback: Optional callback for progress updates (called from thread pool)

        Returns:
            AngleAdjustmentResponse or None if cancelled/error
        """
        def sync_execution():
            """Synchronous execution function to run in thread pool."""
            stage_name = request.stage.name

            # Select the correct angle adjustment object
            if request.stage == AngleAdjustmentStage.LEFT:
                angle_adjustment = self._angle_adjustment_left
            else:
                angle_adjustment = self._angle_adjustment_right

            # Check connection
            if not self.is_connected() or angle_adjustment is None:
                logger.error(f"Not connected or {stage_name} AngleAdjustment not initialized")
                return None

            try:
                start_time = time.time()

                # Auto-determine stage-specific hardware parameters
                if request.stage == AngleAdjustmentStage.LEFT:
                    signal_ch_number = 5
                    unlock_dout_ch_number = 1
                    contact_axis_number = 3
                    rotation_center_x = 1
                    rotation_center_y = 2
                    rotation_center_z = 3
                else:  # RIGHT
                    signal_ch_number = 6
                    unlock_dout_ch_number = 2
                    contact_axis_number = 9
                    rotation_center_x = 7
                    rotation_center_y = 8
                    rotation_center_z = 9

                # Configure parameters (same as sync version)
                params = Motion.AngleAdjustment.AngleAdjustmentParameter()
                params.gap = request.gap
                params.signalChNumber = signal_ch_number
                params.signalLowerLimit = request.signal_lower_limit
                params.unlockDOutChNumber = unlock_dout_ch_number
                params.unlockDOutControlOn = request.unlock_dout_control_on
                params.contactAxisNumber = contact_axis_number
                params.contactSearchRange = request.contact_search_range
                params.contactSearchSpeed = request.contact_search_speed
                params.contactSmoothing = request.contact_smoothing
                params.contactSensitivity = request.contact_sensitivity
                params.pushDistance = request.push_distance
                params.angleAxisNumberTx = request.angle_axis_number_tx
                params.angleAxisNumberTy = request.angle_axis_number_ty
                params.angleSearchRangeTx = request.angle_search_range_tx
                params.angleSearchRangeTy = request.angle_search_range_ty
                params.angleSearchSpeedTx = request.angle_search_speed_tx
                params.angleSearchSpeedTy = request.angle_search_speed_ty
                params.angleSmoothingTx = request.angle_smoothing_tx
                params.angleSmoothingTy = request.angle_smoothing_ty
                params.angleSensitivityTx = request.angle_sensitivity_tx
                params.angleSensitivityTy = request.angle_sensitivity_ty
                params.angleJudgeCountTx = request.angle_judge_count_tx
                params.angleJudgeCountTy = request.angle_judge_count_ty
                params.angleConvergentRangeTx = request.angle_convergent_range_tx
                params.angleConvergentRangeTy = request.angle_convergent_range_ty
                params.angleComparisonCount = request.angle_comparison_count
                params.angleMaxCount = request.angle_max_count

                rotation_center = Motion.Axis3D.RotationCenter()
                rotation_center.enabled = request.rotation_center_enabled
                rotation_center.mainStageNumberX = rotation_center_x
                rotation_center.mainStageNumberY = rotation_center_y
                rotation_center.mainStageNumberZ = rotation_center_z

                logger.info(f"{stage_name} angle adjustment async execution starting")

                # Apply parameters
                angle_adjustment.SetParameter(params, rotation_center)
                time.sleep(0.2)

                # Safety check
                digital_output_state = self.get_digital_output(unlock_dout_ch_number)
                if digital_output_state is None or digital_output_state:
                    error_msg = "Contact sensor is locked or state could not be read"
                    logger.error(f"{stage_name}: {error_msg}")
                    return AngleAdjustmentResponse(
                        success=False,
                        status_code="InvalidParameter",
                        status_value=4,
                        status_description=error_msg,
                        error_message=f"{stage_name} stage contact sensor must be UNLOCKED"
                    )

                # Measure initial signal
                initial_signal = self.get_analog_input(signal_ch_number)
                if initial_signal is not None:
                    logger.info(f"Initial signal: {initial_signal:.6f} V")

                # Start adjustment
                angle_adjustment.Start()
                time.sleep(0.2)
                logger.info(f"{stage_name} angle adjustment started")

                # Emit initial progress
                if progress_callback:
                    progress_callback({
                        "phase": "Starting",
                        "elapsed_time": 0,
                        "message": f"{stage_name} angle adjustment started"
                    })

                # Wait for completion with cancellation support
                timeout = 60
                poll_interval = 0.1
                start_wait_time = time.time()
                last_phase = None
                last_status = None

                while True:
                    # Check cancellation FIRST
                    if cancellation_event and cancellation_event.is_set():
                        logger.info(f"{stage_name} angle adjustment cancellation requested")
                        angle_adjustment.Stop()

                        # Wait briefly for stop to take effect
                        time.sleep(0.5)

                        return AngleAdjustmentResponse(
                            success=False,
                            status_code="Cancelled",
                            status_value=-2,
                            status_description="Operation cancelled by user",
                            execution_time=time.time() - start_time,
                            error_message="Angle adjustment was cancelled"
                        )

                    status_str = str(angle_adjustment.GetStatus())
                    phase_str = str(angle_adjustment.GetAdjustingStatus())
                    elapsed_time = time.time() - start_wait_time

                    # Emit progress on phase changes
                    if phase_str != last_phase:
                        phase_info = self._get_adjusting_status_info(phase_str)
                        logger.info(f"{stage_name} phase: {phase_info['phase']}")
                        last_phase = phase_str

                        if progress_callback:
                            progress_callback({
                                "phase": phase_info['phase'],
                                "phase_description": phase_info['description'],
                                "elapsed_time": elapsed_time,
                                "progress_percent": self._calculate_angle_adjustment_progress(phase_str),
                                "message": f"Phase: {phase_info['phase']}"
                            })

                    # Check if adjustment finished
                    if status_str != "Adjusting":
                        if status_str == "Success":
                            time.sleep(0.2)  # Settling time
                            execution_time = time.time() - start_time
                            status_info = self._get_angle_adjustment_status_info(status_str)
                            phase_info = self._get_adjusting_status_info(phase_str)

                            final_signal = self.get_analog_input(signal_ch_number)
                            signal_improvement = None
                            if final_signal is not None and initial_signal is not None:
                                signal_improvement = final_signal - initial_signal
                                logger.info(f"{stage_name} SUCCESS - Improvement: {signal_improvement:+.6f} V")

                            # Retrieve profile data
                            contact_z_profile = self._retrieve_angle_adjustment_profile_data(
                                angle_adjustment,
                                Motion.AngleAdjustment.ProfileDataType.ContactZ
                            )
                            adjusting_tx_profile = self._retrieve_angle_adjustment_profile_data(
                                angle_adjustment,
                                Motion.AngleAdjustment.ProfileDataType.AdjustmentTx
                            )
                            adjusting_ty_profile = self._retrieve_angle_adjustment_profile_data(
                                angle_adjustment,
                                Motion.AngleAdjustment.ProfileDataType.AdjustmentTy
                            )

                            if progress_callback:
                                progress_callback({
                                    "phase": "Completed",
                                    "elapsed_time": execution_time,
                                    "progress_percent": 100,
                                    "message": "Angle adjustment completed successfully"
                                })

                            return AngleAdjustmentResponse(
                                success=True,
                                status_code=status_info['status'],
                                status_value=status_info['value'],
                                status_description=status_info['description'],
                                phase_code=phase_info['phase'],
                                phase_value=phase_info['value'],
                                phase_description=phase_info['description'],
                                initial_signal=initial_signal,
                                final_signal=final_signal,
                                signal_improvement=signal_improvement,
                                execution_time=execution_time,
                                contact_z_profile=contact_z_profile,
                                adjusting_tx_profile=adjusting_tx_profile,
                                adjusting_ty_profile=adjusting_ty_profile
                            )
                        else:
                            # Error status
                            execution_time = time.time() - start_time
                            status_info = self._get_angle_adjustment_status_info(status_str)
                            phase_info = self._get_adjusting_status_info(phase_str)

                            logger.error(f"{stage_name} failed: {status_info['status']}")

                            if progress_callback:
                                progress_callback({
                                    "phase": "Failed",
                                    "elapsed_time": execution_time,
                                    "message": f"Failed: {status_info['status']}"
                                })

                            return AngleAdjustmentResponse(
                                success=False,
                                status_code=status_info['status'],
                                status_value=status_info['value'],
                                status_description=status_info['description'],
                                phase_code=phase_info['phase'],
                                phase_value=phase_info['value'],
                                phase_description=phase_info['description'],
                                execution_time=execution_time,
                                error_message=f"{status_info['status']}: {status_info['description']}"
                            )

                    # Check timeout
                    if time.time() - start_wait_time > timeout:
                        execution_time = time.time() - start_time
                        logger.error(f"{stage_name} timed out after {timeout}s")

                        if progress_callback:
                            progress_callback({
                                "phase": "Timeout",
                                "elapsed_time": execution_time,
                                "message": "Operation timed out"
                            })

                        return AngleAdjustmentResponse(
                            success=False,
                            status_code="Timeout",
                            status_value=-1,
                            status_description=f"Timed out after {timeout} seconds",
                            execution_time=execution_time,
                            error_message="Operation timed out"
                        )

                    time.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Error during {stage_name} angle adjustment: {e}", exc_info=True)
                if progress_callback:
                    progress_callback({
                        "phase": "Error",
                        "message": f"Exception: {str(e)}"
                    })
                return None

        # Run synchronous function in thread pool
        return await asyncio.to_thread(sync_execution)

    # ========== Optical Alignment (Async with Cancellation Support) ==========

    def stop_alignment(self) -> bool:
        """
        Stop currently running optical alignment operation.

        Returns:
            True if stop command was sent successfully
        """
        if not self.is_connected() or self._alignment is None:
            logger.error("Not connected or Alignment not initialized")
            return False

        try:
            self._alignment.Stop()
            logger.info("Alignment stop command sent")
            return True
        except Exception as e:
            logger.error(f"Failed to stop alignment: {e}")
            return False

    async def execute_flat_alignment_async(
        self,
        request,
        cancellation_event: Optional[asyncio.Event] = None,
        progress_callback: Optional[Callable[[dict], None]] = None
    ):
        """
        Async wrapper for execute_flat_alignment with cancellation and progress support.

        Args:
            request: FlatAlignmentRequest with all parameters
            cancellation_event: Optional event to signal cancellation
            progress_callback: Optional callback for progress updates

        Returns:
            AlignmentResponse or None if error

        Raises:
            Exception: If alignment fails or is cancelled
        """
        def sync_execution():
            """Synchronous execution in thread pool."""
            from .models import AlignmentResponse

            if not self.is_connected() or self._alignment is None:
                raise Exception("Not connected or Alignment not initialized")

            try:
                start_time = time.time()

                # Create FlatParameter structure
                flat_params = Motion.Alignment.FlatParameter()

                # Set all ~30 parameters from request
                flat_params.mainStageNumberX = request.mainStageNumberX
                flat_params.mainStageNumberY = request.mainStageNumberY
                flat_params.subStageNumberXY = request.subStageNumberXY
                flat_params.subAngleX = request.subAngleX
                flat_params.subAngleY = request.subAngleY

                flat_params.pmCh = request.pmCh
                flat_params.analogCh = request.analogCh
                flat_params.wavelength = request.wavelength
                flat_params.pmAutoRangeUpOn = request.pmAutoRangeUpOn
                flat_params.pmInitRangeSettingOn = request.pmInitRangeSettingOn
                flat_params.pmInitRange = request.pmInitRange

                flat_params.fieldSearchThreshold = request.fieldSearchThreshold
                flat_params.peakSearchThreshold = request.peakSearchThreshold

                flat_params.searchRangeX = request.searchRangeX
                flat_params.searchRangeY = request.searchRangeY

                flat_params.fieldSearchPitchX = request.fieldSearchPitchX
                flat_params.fieldSearchPitchY = request.fieldSearchPitchY
                flat_params.fieldSearchFirstPitchX = request.fieldSearchFirstPitchX
                flat_params.fieldSearchSpeedX = request.fieldSearchSpeedX
                flat_params.fieldSearchSpeedY = request.fieldSearchSpeedY

                flat_params.peakSearchSpeedX = request.peakSearchSpeedX
                flat_params.peakSearchSpeedY = request.peakSearchSpeedY

                flat_params.smoothingRangeX = request.smoothingRangeX
                flat_params.smoothingRangeY = request.smoothingRangeY

                flat_params.centroidThresholdX = request.centroidThresholdX
                flat_params.centroidThresholdY = request.centroidThresholdY

                flat_params.convergentRangeX = request.convergentRangeX
                flat_params.convergentRangeY = request.convergentRangeY
                flat_params.comparisonCount = request.comparisonCount
                flat_params.maxRepeatCount = request.maxRepeatCount

                # Apply parameters to alignment hardware
                self._alignment.SetFlat(flat_params)
                self._alignment.SetMeasurementWaveLength(request.pmCh, request.wavelength)

                # Measure initial optical power
                initial_power = float(self._alignment.GetPower(request.pmCh))
                logger.info(f"Flat alignment starting - Initial power: {initial_power:.3f} dBm")

                if progress_callback:
                    progress_callback({
                        "phase": "Starting",
                        "initial_power": initial_power,
                        "message": f"Flat alignment started - Initial power: {initial_power:.3f} dBm"
                    })

                # Start flat alignment
                self._alignment.StartFlat()
                time.sleep(0.1)

                # Poll status until completion
                last_phase_str = None
                poll_interval = 0.5
                timeout = 300  # 5 minutes

                while True:
                    # Check cancellation FIRST
                    if cancellation_event and cancellation_event.is_set():
                        logger.info("Flat alignment cancellation requested")
                        self._alignment.Stop()
                        time.sleep(0.5)  # Wait for stop
                        raise Exception("Alignment cancelled by user")

                    status_str = str(self._alignment.GetStatus())
                    phase_str = str(self._alignment.GetAligningStatus())

                    # Log and broadcast phase changes
                    if phase_str != last_phase_str:
                        phase_info = self._get_aligning_phase_info(phase_str)
                        logger.info(f"Flat alignment phase: {phase_info['phase']} - {phase_info['description']}")

                        if progress_callback:
                            progress_callback({
                                "phase": phase_info['phase'],
                                "phase_description": phase_info['description'],
                                "elapsed_time": time.time() - start_time,
                                "message": f"Phase: {phase_info['description']}"
                            })

                        last_phase_str = phase_str

                    # Check if completed
                    if status_str != "Aligning":
                        status_info = self._get_optical_alignment_status_info(status_str)
                        phase_info = self._get_aligning_phase_info(phase_str)
                        execution_time = time.time() - start_time

                        if status_str == "Success":
                            # Settling time
                            time.sleep(0.2)

                            # Measure final optical power
                            final_power = float(self._alignment.GetPower(request.pmCh))
                            power_improvement = final_power - initial_power

                            logger.info(f"Flat alignment SUCCESS - Final power: {final_power:.3f} dBm, "
                                      f"Improvement: {power_improvement:+.3f} dB, Time: {execution_time:.2f}s")

                            # Retrieve profile data
                            field_search_profile = self._retrieve_alignment_profile_data(
                                Motion.Alignment.ProfileDataType.FieldSearch
                            )
                            peak_search_x_profile = self._retrieve_alignment_profile_data(
                                Motion.Alignment.ProfileDataType.PeakSearchX
                            )
                            peak_search_y_profile = self._retrieve_alignment_profile_data(
                                Motion.Alignment.ProfileDataType.PeakSearchY
                            )

                            # Get peak positions
                            peak_x = float(self._axis_components[request.mainStageNumberX].GetActualPosition())
                            peak_y = float(self._axis_components[request.mainStageNumberY].GetActualPosition())

                            return AlignmentResponse(
                                success=True,
                                status_code=status_info['status'],
                                status_value=status_info['value'],
                                status_description=status_info['description'],
                                phase_code=phase_info['phase'],
                                phase_value=phase_info['value'],
                                phase_description=phase_info['description'],
                                initial_power=initial_power,
                                final_power=final_power,
                                power_improvement=power_improvement,
                                peak_position_x=peak_x,
                                peak_position_y=peak_y,
                                execution_time=execution_time,
                                field_search_profile=field_search_profile,
                                peak_search_x_profile=peak_search_x_profile,
                                peak_search_y_profile=peak_search_y_profile
                            )
                        else:
                            # Alignment failed
                            logger.error(f"Flat alignment FAILED - Status: {status_info['status']} - "
                                       f"{status_info['description']}, Time: {execution_time:.2f}s")

                            raise Exception(f"Flat alignment failed: {status_info['description']}")

                    # Check timeout
                    if time.time() - start_time > timeout:
                        self._alignment.Stop()
                        raise Exception(f"Flat alignment timed out after {timeout}s")

                    time.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Error during flat alignment: {e}", exc_info=True)
                raise

        # Run synchronous function in thread pool
        return await asyncio.to_thread(sync_execution)

    async def execute_focus_alignment_async(
        self,
        request,
        cancellation_event: Optional[asyncio.Event] = None,
        progress_callback: Optional[Callable[[dict], None]] = None
    ):
        """
        Async wrapper for execute_focus_alignment with cancellation and progress support.

        Args:
            request: FocusAlignmentRequest with all parameters
            cancellation_event: Optional event to signal cancellation
            progress_callback: Optional callback for progress updates

        Returns:
            AlignmentResponse or None if error

        Raises:
            Exception: If alignment fails or is cancelled
        """
        def sync_execution():
            """Synchronous execution in thread pool."""
            from .models import AlignmentResponse

            if not self.is_connected() or self._alignment is None:
                raise Exception("Not connected or Alignment not initialized")

            try:
                start_time = time.time()

                # Create FocusParameter structure
                focus_params = Motion.Alignment.FocusParameter()

                # Set zMode (specific to Focus alignment)
                focus_params.zMode = request.zMode

                # Set all ~30 parameters from request
                focus_params.mainStageNumberX = request.mainStageNumberX
                focus_params.mainStageNumberY = request.mainStageNumberY
                focus_params.subStageNumberXY = request.subStageNumberXY
                focus_params.subAngleX = request.subAngleX
                focus_params.subAngleY = request.subAngleY

                focus_params.pmCh = request.pmCh
                focus_params.analogCh = request.analogCh
                focus_params.wavelength = request.wavelength
                focus_params.pmAutoRangeUpOn = request.pmAutoRangeUpOn
                focus_params.pmInitRangeSettingOn = request.pmInitRangeSettingOn
                focus_params.pmInitRange = request.pmInitRange

                focus_params.fieldSearchThreshold = request.fieldSearchThreshold
                focus_params.peakSearchThreshold = request.peakSearchThreshold

                focus_params.searchRangeX = request.searchRangeX
                focus_params.searchRangeY = request.searchRangeY

                focus_params.fieldSearchPitchX = request.fieldSearchPitchX
                focus_params.fieldSearchPitchY = request.fieldSearchPitchY
                focus_params.fieldSearchFirstPitchX = request.fieldSearchFirstPitchX
                focus_params.fieldSearchSpeedX = request.fieldSearchSpeedX
                focus_params.fieldSearchSpeedY = request.fieldSearchSpeedY

                focus_params.peakSearchSpeedX = request.peakSearchSpeedX
                focus_params.peakSearchSpeedY = request.peakSearchSpeedY

                focus_params.smoothingRangeX = request.smoothingRangeX
                focus_params.smoothingRangeY = request.smoothingRangeY

                focus_params.centroidThresholdX = request.centroidThresholdX
                focus_params.centroidThresholdY = request.centroidThresholdY

                focus_params.convergentRangeX = request.convergentRangeX
                focus_params.convergentRangeY = request.convergentRangeY
                focus_params.comparisonCount = request.comparisonCount
                focus_params.maxRepeatCount = request.maxRepeatCount

                # Apply parameters to alignment hardware
                self._alignment.SetFocus(focus_params)
                self._alignment.SetMeasurementWaveLength(request.pmCh, request.wavelength)

                # Measure initial optical power
                initial_power = float(self._alignment.GetPower(request.pmCh))
                logger.info(f"Focus alignment starting (zMode={request.zMode}) - Initial power: {initial_power:.3f} dBm")

                if progress_callback:
                    progress_callback({
                        "phase": "Starting",
                        "initial_power": initial_power,
                        "z_mode": request.zMode,
                        "message": f"Focus alignment started - Initial power: {initial_power:.3f} dBm"
                    })

                # Start focus alignment
                self._alignment.StartFocus()
                time.sleep(0.1)

                # Poll status until completion
                last_phase_str = None
                poll_interval = 0.5
                timeout = 300  # 5 minutes

                while True:
                    # Check cancellation FIRST
                    if cancellation_event and cancellation_event.is_set():
                        logger.info("Focus alignment cancellation requested")
                        self._alignment.Stop()
                        time.sleep(0.5)  # Wait for stop
                        raise Exception("Alignment cancelled by user")

                    status_str = str(self._alignment.GetStatus())
                    phase_str = str(self._alignment.GetAligningStatus())

                    # Log and broadcast phase changes
                    if phase_str != last_phase_str:
                        phase_info = self._get_aligning_phase_info(phase_str)
                        logger.info(f"Focus alignment phase: {phase_info['phase']} - {phase_info['description']}")

                        if progress_callback:
                            progress_callback({
                                "phase": phase_info['phase'],
                                "phase_description": phase_info['description'],
                                "elapsed_time": time.time() - start_time,
                                "message": f"Phase: {phase_info['description']}"
                            })

                        last_phase_str = phase_str

                    # Check if completed
                    if status_str != "Aligning":
                        status_info = self._get_optical_alignment_status_info(status_str)
                        phase_info = self._get_aligning_phase_info(phase_str)
                        execution_time = time.time() - start_time

                        if status_str == "Success":
                            # Settling time
                            time.sleep(0.2)

                            # Measure final optical power
                            final_power = float(self._alignment.GetPower(request.pmCh))
                            power_improvement = final_power - initial_power

                            logger.info(f"Focus alignment SUCCESS - Final power: {final_power:.3f} dBm, "
                                      f"Improvement: {power_improvement:+.3f} dB, Time: {execution_time:.2f}s")

                            # Retrieve profile data (including Z-axis)
                            field_search_profile = self._retrieve_alignment_profile_data(
                                Motion.Alignment.ProfileDataType.FieldSearch
                            )
                            peak_search_x_profile = self._retrieve_alignment_profile_data(
                                Motion.Alignment.ProfileDataType.PeakSearchX
                            )
                            peak_search_y_profile = self._retrieve_alignment_profile_data(
                                Motion.Alignment.ProfileDataType.PeakSearchY
                            )
                            peak_search_z_profile = self._retrieve_alignment_profile_data(
                                Motion.Alignment.ProfileDataType.PeakSearchZ
                            )

                            # Get peak positions (X, Y, Z)
                            peak_x = float(self._axis_components[request.mainStageNumberX].GetActualPosition())
                            peak_y = float(self._axis_components[request.mainStageNumberY].GetActualPosition())
                            # Z-axis uses subStageNumberXY (typically axis 3 for Z1)
                            peak_z = float(self._axis_components[request.subStageNumberXY].GetActualPosition())

                            return AlignmentResponse(
                                success=True,
                                status_code=status_info['status'],
                                status_value=status_info['value'],
                                status_description=status_info['description'],
                                phase_code=phase_info['phase'],
                                phase_value=phase_info['value'],
                                phase_description=phase_info['description'],
                                initial_power=initial_power,
                                final_power=final_power,
                                power_improvement=power_improvement,
                                peak_position_x=peak_x,
                                peak_position_y=peak_y,
                                peak_position_z=peak_z,
                                execution_time=execution_time,
                                field_search_profile=field_search_profile,
                                peak_search_x_profile=peak_search_x_profile,
                                peak_search_y_profile=peak_search_y_profile,
                                peak_search_z_profile=peak_search_z_profile
                            )
                        else:
                            # Alignment failed
                            logger.error(f"Focus alignment FAILED - Status: {status_info['status']} - "
                                       f"{status_info['description']}, Time: {execution_time:.2f}s")

                            raise Exception(f"Focus alignment failed: {status_info['description']}")

                    # Check timeout
                    if time.time() - start_time > timeout:
                        self._alignment.Stop()
                        raise Exception(f"Focus alignment timed out after {timeout}s")

                    time.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Error during focus alignment: {e}", exc_info=True)
                raise

        # Run synchronous function in thread pool
        return await asyncio.to_thread(sync_execution)

    def _calculate_angle_adjustment_progress(self, phase_str: str) -> int:
        """Calculate progress percentage based on adjustment phase."""
        phase_progress = {
            "NotAdjusting": 0,
            "Initializing": 20,
            "ContactingZ": 40,
            "AdjustingTx": 60,
            "AdjustingTy": 80
        }
        return phase_progress.get(phase_str, 50)

    # ========== Digital and Analog I/O ==========

    def set_digital_output(self, channel: int, value: bool) -> bool:
        """
        Set digital output value (contact sensing lock state).

        Args:
            channel: Digital output channel number (1 or 2 only)
                    1 = Left stage, 2 = Right stage
            value: True for LOCKED, False for UNLOCKED

        Returns:
            True if successful
        """
        if not self.is_connected() or self._io is None:
            logger.error("Not connected or IO not initialized")
            return False

        # Validate channel range (only CH1 and CH2 are available for contact sensing)
        if channel not in [1, 2]:
            logger.error(f"Invalid digital channel {channel}. Only channels 1 and 2 are supported.")
            return False

        try:
            self._io.SetPortState(channel, value)
            logger.info(f"Set digital output {channel} to {value}")
            return True
        except Exception as e:
            logger.error(f"Error setting digital output: {e}")
            return False

    def get_digital_output(self, channel: int) -> Optional[bool]:
        """
        Get digital output state (contact sensing lock state).

        Args:
            channel: Digital output channel number (1 or 2 only)
                    1 = Left stage, 2 = Right stage

        Returns:
            True/False for output state (LOCKED/UNLOCKED), None if error
        """
        if not self.is_connected() or self._io is None:
            logger.error("Not connected or IO not initialized")
            return None

        # Validate channel range (only CH1 and CH2 are available for contact sensing)
        if channel not in [1, 2]:
            logger.error(f"Invalid digital channel {channel}. Only channels 1 and 2 are supported.")
            return None

        try:
            # GetPortState with DigitalIOType.Output reads the OUTPUT state
            # This is used to check if contact sensor is locked/unlocked
            # Access enum through Motion.IO namespace
            io_type = Motion.IO.DigitalIOType.Output
            value = self._io.GetPortState(io_type, channel)
            return bool(value)
        except Exception as e:
            logger.error(f"Error getting digital output state: {e}", exc_info=True)
            return None

    def get_analog_input(self, channel: int) -> Optional[float]:
        """
        Get analog input voltage.

        Args:
            channel: Analog input channel number (5 or 6 only)

        Returns:
            Input voltage in volts, None if error
        """
        if not self.is_connected() or self._io is None:
            logger.error("Not connected or IO not initialized")
            return None

        # Validate channel range (only CH5 and CH6 are available)
        if channel not in [5, 6]:
            logger.error(f"Invalid analog channel {channel}. Only channels 5 and 6 are supported.")
            return None

        try:
            # GetAnalogValue requires AnalogIOType enum and channel number
            # DA1000/DA1100 support AnalogIOType.Input only (per manual section 4.9.1.5)
            # Access enum through Motion.IO namespace
            io_type = Motion.IO.AnalogIOType.Input
            voltage = self._io.GetAnalogValue(io_type, channel)
            return float(voltage)
        except Exception as e:
            logger.error(f"Error getting analog input: {e}", exc_info=True)
            return None

    # ========== Utility Methods ==========

    def _validate_axis(self, axis_number: int) -> bool:
        """Validate axis number and connection status"""
        if not self.is_connected():
            logger.error("Not connected to controller")
            return False

        if axis_number not in self._axis_components:
            logger.error(f"Invalid axis number: {axis_number} (valid: 1-12)")
            return False

        return True

    def get_all_positions(self) -> Dict[int, AxisStatus]:
        """
        Get current positions for all axes.

        Returns:
            Dictionary mapping axis number to AxisStatus
        """
        positions = {}
        for axis_num in self._axis_components.keys():
            pos = self.get_position(axis_num)
            if pos:
                positions[axis_num] = pos
        return positions

    def get_all_digital_outputs(self) -> Dict[int, bool]:
        """
        Get digital output states for all contact sensing channels.

        Returns:
            Dictionary mapping channel number (1, 2) to output state (True=LOCKED, False=UNLOCKED)
        """
        outputs = {}
        for channel in [1, 2]:
            value = self.get_digital_output(channel)
            if value is not None:
                outputs[channel] = value
        return outputs

    def get_all_analog_inputs(self) -> Dict[int, float]:
        """
        Get analog input voltages for all contact sensing channels.

        Returns:
            Dictionary mapping channel number (5, 6) to voltage value
        """
        inputs = {}
        for channel in [5, 6]:
            value = self.get_analog_input(channel)
            if value is not None:
                inputs[channel] = value
        return inputs

    def get_power(self, channel: int = 1) -> Optional[float]:
        """
        Get optical power reading from power meter.

        Args:
            channel: Power meter channel number (1 or 2)

        Returns:
            Power value in dBm, or None on error
        """
        if not self.is_connected():
            logger.error("Not connected to controller")
            return None

        if not self._alignment:
            logger.error("Alignment component not initialized")
            return None

        if channel not in [1, 2]:
            logger.error(f"Invalid power meter channel: {channel} (valid: 1, 2)")
            return None

        with self._lock:
            try:
                power = float(self._alignment.GetPower(channel))
                return power
            except Exception as e:
                logger.error(f"Error reading power meter channel {channel}: {e}", exc_info=True)
                return None

    def emergency_stop(self) -> bool:
        """
        Emergency stop all axes.

        Returns:
            True if successful
        """
        logger.warning("EMERGENCY STOP activated")
        success = True

        for axis_num in self._axis_components.keys():
            if not self.stop_axis(axis_num):
                success = False

        return success
