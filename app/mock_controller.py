"""
Mock Suruga Seiki Controller for Development Without Hardware

This module provides a simulated probe station controller that:
- Maintains same API interface as real controller
- Simulates realistic position updates during movement
- Supports all 12 axes (X1, Y1, Z1, Tx1, Ty1, Tz1, X2, Y2, Z2, Tx2, Ty2, Tz2)
- Simulates servo on/off state
- Provides simulated I/O values
- Enables frontend development and testing without $50K+ hardware

Usage:
    SURUGA_MOCK_MODE=true python -m app.main
"""
import asyncio
import logging
import threading
import time
import random
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime

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


class MockSurugaSeikiController:
    """
    Simulated Suruga Seiki DA1000/DA1100 probe station controller.

    Provides identical API to SurugaSeikiController but with simulated behavior.
    Perfect for development, testing, and demos without physical hardware.
    """

    # Axis configurations (name, units, soft limits)
    AXIS_CONFIG = {
        1: ("X1", "µm", -25000, 25000),    # Left stage X
        2: ("Y1", "µm", -25000, 25000),    # Left stage Y
        3: ("Z1", "µm", -15000, 15000),    # Left stage Z
        4: ("Tx1", "deg", -10, 10),        # Left stage Tx (rotation)
        5: ("Ty1", "deg", -10, 10),        # Left stage Ty (rotation)
        6: ("Tz1", "deg", -180, 180),      # Left stage Tz (rotation)
        7: ("X2", "µm", -25000, 25000),    # Right stage X
        8: ("Y2", "µm", -25000, 25000),    # Right stage Y
        9: ("Z2", "µm", -15000, 15000),    # Right stage Z
        10: ("Tx2", "deg", -10, 10),       # Right stage Tx (rotation)
        11: ("Ty2", "deg", -10, 10),       # Right stage Ty (rotation)
        12: ("Tz2", "deg", -180, 180),     # Right stage Tz (rotation)
    }

    def __init__(self, ads_address: str = "5.146.68.190.1.1"):
        """
        Initialize the mock controller.

        Args:
            ads_address: ADS address (ignored in mock mode, kept for API compatibility)
        """
        self.ads_address = ads_address
        self._lock = threading.RLock()
        self._connected = False

        # Axis state
        self._positions: Dict[int, float] = {i: 0.0 for i in range(1, 13)}
        self._target_positions: Dict[int, Optional[float]] = {i: None for i in range(1, 13)}
        self._servos_on: Dict[int, bool] = {i: False for i in range(1, 13)}
        self._moving: Dict[int, bool] = {i: False for i in range(1, 13)}
        self._speeds: Dict[int, float] = {i: 1000.0 for i in range(1, 13)}
        self._errors: Dict[int, bool] = {i: False for i in range(1, 13)}
        self._error_codes: Dict[int, int] = {i: 0 for i in range(1, 13)}

        # I/O state
        self._digital_outputs: Dict[int, bool] = {1: False, 2: False}  # 1=LEFT, 2=RIGHT
        self._analog_inputs: Dict[int, float] = {
            1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5,
            5: 2.8, 6: 2.8, 7: 0.5, 8: 0.5  # Channels 5,6 for contact sensors
        }

        # System state
        self._is_error = False
        self._is_emergency_asserted = False

        # Movement simulation (background thread)
        self._movement_thread: Optional[threading.Thread] = None
        self._movement_stop_event = threading.Event()

        logger.info(f"MOCK: Initialized MockSurugaSeikiController for ADS address: {ads_address}")

    def get_versions(self) -> Tuple[Optional[str], Optional[str]]:
        """Return mock DLL and system versions."""
        return ("MockDLL v1.0.0", "MockSystem v2.0.0")

    def get_emergency_asserted(self) -> Optional[bool]:
        """Return mock emergency state."""
        return self._is_emergency_asserted

    # ========== Connection Management ==========

    def connect(self) -> bool:
        """
        Simulate connection to probe station.

        Returns:
            True (always succeeds in mock mode)
        """
        with self._lock:
            logger.info(f"MOCK: Connecting to simulated probe station at {self.ads_address}")
            time.sleep(0.5)  # Simulate connection delay

            # Start movement simulation thread
            if self._movement_thread is None or not self._movement_thread.is_alive():
                self._movement_stop_event.clear()
                self._movement_thread = threading.Thread(
                    target=self._movement_simulation_loop,
                    daemon=True
                )
                self._movement_thread.start()

            self._connected = True
            logger.info("MOCK: Successfully connected to simulated probe station")
            return True

    def disconnect(self) -> bool:
        """
        Simulate disconnection from probe station.

        Returns:
            True
        """
        with self._lock:
            logger.info("MOCK: Disconnecting from simulated probe station")

            # Turn off all servos
            for axis_num in range(1, 13):
                self._servos_on[axis_num] = False
                self._moving[axis_num] = False

            # Stop movement simulation
            if self._movement_thread and self._movement_thread.is_alive():
                self._movement_stop_event.set()

            self._connected = False
            logger.info("MOCK: Disconnected from simulated probe station")
            return True

    def is_connected(self) -> bool:
        """Check if connected to controller."""
        return self._connected

    def check_error(self) -> Tuple[bool, str]:
        """
        Check if there's a system error based on axis error codes and status.

        Returns:
            Tuple of (is_error, error_message)
        """
        if not self.is_connected():
            return True, "Not connected to controller"

        with self._lock:
            is_error = False
            error_msgs = []

            # Check all axes for errors
            for axis_num in range(1, 13):
                if self._errors[axis_num]:
                    is_error = True
                    error_code = self._error_codes[axis_num]
                    axis_name = self.AXIS_CONFIG[axis_num][0]
                    error_msgs.append(f"Axis {axis_num} ({axis_name}): Error code {error_code}")

            if is_error:
                return True, "; ".join(error_msgs)
            else:
                return False, "No errors"

    # ========== Servo Control ==========

    def turn_on_servo(self, axis_number: int) -> bool:
        """Turn on servo for specified axis."""
        with self._lock:
            if not self._connected:
                logger.error(f"MOCK: Cannot turn on servo - not connected")
                return False

            if axis_number < 1 or axis_number > 12:
                logger.error(f"MOCK: Invalid axis number: {axis_number}")
                return False

            self._servos_on[axis_number] = True
            logger.info(f"MOCK: Servo ON for axis {axis_number} ({self.AXIS_CONFIG[axis_number][0]})")
            return True

    def turn_off_servo(self, axis_number: int) -> bool:
        """Turn off servo for specified axis."""
        with self._lock:
            if not self._connected:
                return False

            if axis_number < 1 or axis_number > 12:
                return False

            self._servos_on[axis_number] = False
            self._moving[axis_number] = False  # Stop movement when servo turns off
            self._target_positions[axis_number] = None
            logger.info(f"MOCK: Servo OFF for axis {axis_number} ({self.AXIS_CONFIG[axis_number][0]})")
            return True

    def turn_on_servos_batch(self, axis_numbers: List[int]) -> bool:
        """Turn on servos for multiple axes."""
        with self._lock:
            if not self._connected:
                return False

            for axis_num in axis_numbers:
                if 1 <= axis_num <= 12:
                    self._servos_on[axis_num] = True

            logger.info(f"MOCK: Batch servo ON for {len(axis_numbers)} axes")
            return True

    def turn_off_servos_batch(self, axis_numbers: List[int]) -> bool:
        """Turn off servos for multiple axes."""
        with self._lock:
            if not self._connected:
                return False

            for axis_num in axis_numbers:
                if 1 <= axis_num <= 12:
                    self._servos_on[axis_num] = False
                    self._moving[axis_num] = False
                    self._target_positions[axis_num] = None

            logger.info(f"MOCK: Batch servo OFF for {len(axis_numbers)} axes")
            return True

    def wait_for_axis_ready(self, axis_number: int, timeout: float = 10.0) -> bool:
        """
        Simulate waiting for axis to reach InPosition status.

        In mock mode, this always succeeds immediately after a small delay.
        """
        if not self._servos_on.get(axis_number, False):
            return False

        time.sleep(0.1)  # Simulate servo settling time
        return True

    def wait_for_axes_ready_batch(self, axis_numbers: List[int], timeout: float = 10.0) -> bool:
        """Simulate waiting for multiple axes to be ready."""
        time.sleep(0.1)  # Simulate servo settling time
        return True

    # ========== Position Queries ==========

    def get_position(self, axis_number: int) -> Optional[AxisStatus]:
        """Get current position and status of an axis."""
        with self._lock:
            if not self._connected or axis_number < 1 or axis_number > 12:
                return None

            return AxisStatus(
                axis_number=axis_number,
                actual_position=round(self._positions[axis_number], 3),
                is_moving=self._moving[axis_number],
                is_servo_on=self._servos_on[axis_number],
                is_error=self._errors[axis_number],
                error_code=self._error_codes[axis_number]
            )

    def get_all_positions(self) -> Dict[int, AxisStatus]:
        """Get positions for all axes."""
        with self._lock:
            if not self._connected:
                return {}

            return {
                axis_num: AxisStatus(
                    axis_number=axis_num,
                    actual_position=round(self._positions[axis_num], 3),
                    is_moving=self._moving[axis_num],
                    is_servo_on=self._servos_on[axis_num],
                    is_error=self._errors[axis_num],
                    error_code=self._error_codes[axis_num]
                )
                for axis_num in range(1, 13)
            }

    # ========== Motion Control ==========

    def move_absolute(
        self,
        axis_number: int,
        position: float,
        speed: float
    ) -> Tuple[bool, str]:
        """
        Move axis to absolute position (simulated).

        Returns:
            (success, message)
        """
        with self._lock:
            if not self._connected:
                return False, "Not connected"

            if not self._servos_on.get(axis_number, False):
                return False, f"Servo not on for axis {axis_number}"

            # Check soft limits
            _, _, min_pos, max_pos = self.AXIS_CONFIG[axis_number]
            if position < min_pos or position > max_pos:
                return False, f"Position {position} outside limits [{min_pos}, {max_pos}]"

            # Start simulated movement
            self._target_positions[axis_number] = position
            self._speeds[axis_number] = speed
            self._moving[axis_number] = True

            axis_name = self.AXIS_CONFIG[axis_number][0]
            logger.info(f"MOCK: Moving {axis_name} to {position} at {speed} µm/s")
            return True, f"Movement started for axis {axis_number}"

    def move_relative(
        self,
        axis_number: int,
        distance: float,
        speed: float
    ) -> Tuple[bool, str]:
        """Move axis relative to current position."""
        with self._lock:
            if not self._connected:
                return False, "Not connected"

            target = self._positions[axis_number] + distance
            return self.move_absolute(axis_number, target, speed)

    def stop_axis(self, axis_number: int) -> bool:
        """Stop axis movement."""
        with self._lock:
            if axis_number < 1 or axis_number > 12:
                return False

            self._moving[axis_number] = False
            self._target_positions[axis_number] = None
            logger.info(f"MOCK: Stopped axis {axis_number}")
            return True

    def stop_all_axes(self) -> bool:
        """Stop all axis movements."""
        with self._lock:
            for axis_num in range(1, 13):
                self._moving[axis_num] = False
                self._target_positions[axis_num] = None

            logger.info("MOCK: Stopped all axes")
            return True

    # ========== I/O Operations ==========

    def set_digital_output(self, channel: int, value: bool) -> bool:
        """Set digital output (LOCK/UNLOCK control)."""
        with self._lock:
            if channel not in [1, 2]:
                return False

            self._digital_outputs[channel] = value
            state_str = "LOCKED" if value else "UNLOCKED"
            side = "LEFT" if channel == 1 else "RIGHT"
            logger.info(f"MOCK: Digital output {channel} ({side}): {state_str}")
            return True

    def get_digital_output(self, channel: int) -> Optional[bool]:
        """Get digital output state."""
        with self._lock:
            return self._digital_outputs.get(channel)

    def get_all_digital_outputs(self) -> Dict[int, bool]:
        """Get all digital outputs."""
        with self._lock:
            return dict(self._digital_outputs)

    def get_analog_input(self, channel: int) -> Optional[float]:
        """Get analog input value (simulated)."""
        with self._lock:
            # Simulate slight voltage fluctuation
            base_value = self._analog_inputs.get(channel, 0.5)
            # Channels 5 and 6 (contact sensors) have more noticeable fluctuation
            if channel in [5, 6]:
                noise = random.uniform(-0.05, 0.05)
            else:
                noise = random.uniform(-0.02, 0.02)
            return round(base_value + noise, 4)

    def get_all_analog_inputs(self) -> Dict[int, float]:
        """Get all analog inputs (all 8 channels)."""
        with self._lock:
            return {
                ch: self.get_analog_input(ch) or 0.0
                for ch in range(1, 9)  # Channels 1-8
            }

    def get_power(self, channel: int) -> Optional[float]:
        """Get power meter reading (simulated dBm)."""
        # Simulate power meter reading
        # Value depends on whether we're "aligned" (higher power near center positions)
        with self._lock:
            # Simple simulation: power is higher when X/Y positions are near 0
            x_offset = abs(self._positions.get(1, 0)) / 1000.0  # Normalize
            y_offset = abs(self._positions.get(2, 0)) / 1000.0
            total_offset = (x_offset + y_offset) / 2.0

            # Power ranges from -40 dBm (far) to -10 dBm (aligned)
            base_power = -40 + (30 * (1.0 - min(total_offset, 1.0)))
            noise = random.uniform(-0.5, 0.5)
            return round(base_power + noise, 2)

    # ========== Complex Operations (Simplified Mocks) ==========

    def start_profile_measurement(self, request: ProfileMeasurementRequest) -> str:
        """Start profile measurement (returns task_id for mock)."""
        task_id = f"mock_profile_{int(time.time())}"
        logger.info(f"MOCK: Started profile measurement, task_id={task_id}")
        return task_id

    def get_profile_data(self, task_id: str) -> ProfileDataResponse:
        """Get profile measurement data (simulated)."""
        # Return simulated Gaussian profile
        num_points = 100
        positions = [i * 0.2 for i in range(num_points)]
        signals = [random.gauss(0.5, 0.1) * (1.0 - abs(i - 50) / 50.0) for i in range(num_points)]

        data_points = [
            ProfileDataPoint(position=p, signal=s)
            for p, s in zip(positions, signals)
        ]

        peak_idx = max(range(len(signals)), key=lambda i: signals[i])

        return ProfileDataResponse(
            success=True,
            data_points=data_points,
            total_points=num_points,
            peak_position=positions[peak_idx],
            peak_value=signals[peak_idx],
            peak_index=peak_idx,
            main_axis_number=1,
            main_axis_initial_position=0.0,
            main_axis_final_position=20.0,
            signal_ch_number=1,
            scan_range=20.0,
            scan_speed=25.0
        )

    def execute_angle_adjustment(
        self,
        stage: AngleAdjustmentStage,
        request: AngleAdjustmentRequest
    ) -> AngleAdjustmentResponse:
        """Execute angle adjustment (simplified mock)."""
        logger.info(f"MOCK: Executing angle adjustment for {stage.name} stage")
        time.sleep(1.0)  # Simulate operation

        return AngleAdjustmentResponse(
            success=True,
            status_code="Success",
            status_value=1,
            status_description="Angle adjustment completed successfully",
            phase_code="NotAdjusting",
            phase_value=0,
            phase_description="Not adjusting",
            initial_signal=0.3,
            final_signal=0.8,
            signal_improvement=0.5,
            execution_time=1.0
        )

    # ========== Background Movement Simulation ==========

    def _movement_simulation_loop(self):
        """
        Background thread that simulates gradual position changes during movement.

        Updates positions at 20 Hz to create smooth, realistic motion.
        """
        logger.info("MOCK: Movement simulation thread started")

        while not self._movement_stop_event.is_set():
            try:
                with self._lock:
                    for axis_num in range(1, 13):
                        if not self._moving[axis_num]:
                            continue

                        target = self._target_positions[axis_num]
                        if target is None:
                            self._moving[axis_num] = False
                            continue

                        current = self._positions[axis_num]
                        speed = self._speeds[axis_num]

                        # Calculate distance to move this iteration (50ms @ speed)
                        distance = abs(target - current)
                        step = min(speed * 0.05, distance)  # 50ms update

                        if distance < 0.01:  # Reached target (within 0.01 µm/deg)
                            self._positions[axis_num] = target
                            self._moving[axis_num] = False
                            self._target_positions[axis_num] = None
                            logger.info(f"MOCK: Axis {axis_num} reached target {target}")
                        else:
                            # Move towards target
                            direction = 1 if target > current else -1
                            self._positions[axis_num] += direction * step

            except Exception as e:
                logger.error(f"MOCK: Error in movement simulation: {e}")

            time.sleep(0.05)  # 20 Hz update rate

        logger.info("MOCK: Movement simulation thread stopped")
