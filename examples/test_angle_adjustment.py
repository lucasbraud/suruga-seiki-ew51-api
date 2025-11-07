"""
Test script for angle adjustment with contact detection and data visualization.

This script demonstrates how to:
1. Turn on servos for all 12 axes
2. Record initial analog signal value from contact sensor
3. Move Z1 (left stage) or Z2 (right stage) relative -100 µm
4. Execute angle adjustment with contact detection (TX/TY disabled)
5. Measure final analog signal value from contact sensor
6. Turn off servos after adjustment
7. Plot the three profile graphs (Contact Z, Adjusting TX, Adjusting TY)

Angle adjustment performs contact detection and optionally angle optimization.
For this test, TX and TY adjustments are disabled (set to 0), so only contact
detection on the Z-axis will be performed.

The script measures analog input signals from the contact sensors (not power meter):
- LEFT stage uses analog input channel 5
- RIGHT stage uses analog input channel 6

IMPORTANT - Emergency Stop:
    If something goes wrong during angle adjustment, press Ctrl+C to immediately
    stop the adjustment and safely disable all servos. The script will:
    1. Send stop command to the angle adjustment controller
    2. Wait for the stop to take effect
    3. Disable all servos for safety

Configuration:
    Edit the STAGE constant to choose which stage to test:
    - STAGE = "LEFT"   # Uses Z1 (axis 3), signal channel 5, digital output 1
    - STAGE = "RIGHT"  # Uses Z2 (axis 9), signal channel 6, digital output 2

Requirements:
    pip install requests matplotlib numpy

Usage:
    python test_angle_adjustment.py
"""

import requests
import matplotlib.pyplot as plt
import numpy as np
import time
import threading
import signal
import sys
from typing import Dict, Any, Optional


# ============================================================================
# CONFIGURATION - Easily change these values
# ============================================================================

# Stage selection: "LEFT" or "RIGHT"
STAGE = "LEFT"  # Change to "RIGHT" to test right stage

# Stage to integer mapping for API (LEFT=1, RIGHT=2)
STAGE_VALUE_MAP = {
    "LEFT": 1,
    "RIGHT": 2
}

# Global variable to track if angle adjustment is running (for interrupt handling)
_angle_adjustment_running = False
_current_stage = None

# Axis configuration
# Left stage (uses Z1)
LEFT_STAGE_Z = 3    # Z1 axis
# Right stage (uses Z2)
RIGHT_STAGE_Z = 9   # Z2 axis

# Enable ALL 12 axes (both stages)
ALL_AXES = list(range(1, 13))  # Axes 1-12

# Angle adjustment parameters
# Only specify stage parameter - all other parameters use defaults from models.py
# The defaults are configured for contact detection with angle adjustment disabled
ANGLE_ADJUSTMENT_PARAMS = {
    # Stage selection is all that's needed - rest comes from models.py defaults
    # Stage-specific hardware parameters (signal channel, axis numbers, etc.) are
    # auto-determined by controller_manager.py based on stage selection
}

# Movement parameters
Z_MOVE_DISTANCE = -100.0  # Move Z axis -100 µm before angle adjustment

API_BASE_URL = "http://localhost:8001"  # Default daemon port (see config.py)
# ============================================================================

ANGLE_ADJUSTMENT_ENDPOINT = f"{API_BASE_URL}/angle-adjustment/execute"
ANGLE_ADJUSTMENT_STOP_ENDPOINT = f"{API_BASE_URL}/angle-adjustment/stop"
SERVO_ENDPOINT = f"{API_BASE_URL}/servo"
ANALOG_INPUT_ENDPOINT = f"{API_BASE_URL}/io/analog/input"
MOVE_ENDPOINT = f"{API_BASE_URL}/move"
DIGITAL_OUTPUT_ENDPOINT = f"{API_BASE_URL}/io/digital/output"


def get_analog_input(channel: int) -> Optional[float]:
    """
    Get analog input voltage from contact sensor.

    Args:
        channel: Analog input channel number (5 for LEFT, 6 for RIGHT)

    Returns:
        Voltage in V, or None if error
    """
    url = f"{ANALOG_INPUT_ENDPOINT}/{channel}"

    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data.get('voltage')
        else:
            print(f"  ✗ Error reading analog input: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"  ✗ Exception reading analog input: {e}")
        return None


def get_digital_output(channel: int) -> Optional[bool]:
    """
    Get digital output state (contact sensor lock state).

    Args:
        channel: Digital output channel number (1 for LEFT, 2 for RIGHT)

    Returns:
        True if LOCKED, False if UNLOCKED, None if error
    """
    url = f"{DIGITAL_OUTPUT_ENDPOINT}/{channel}"

    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data.get('value')
        else:
            print(f"  ✗ Error reading digital output: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"  ✗ Exception reading digital output: {e}")
        return None


def set_digital_output(channel: int, value: bool) -> bool:
    """
    Set digital output state (contact sensor lock state).

    Args:
        channel: Digital output channel number (1 for LEFT, 2 for RIGHT)
        value: True for LOCKED, False for UNLOCKED

    Returns:
        True if successful, False otherwise
    """
    url = DIGITAL_OUTPUT_ENDPOINT
    payload = {
        "channel": channel,
        "value": value
    }

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            return True
        else:
            print(f"  ✗ Error setting digital output: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"  ✗ Exception setting digital output: {e}")
        return False


def move_axis_relative(axis: int, distance: float) -> bool:
    """
    Move axis relative to current position.

    Args:
        axis: Axis number (1-12)
        distance: Distance to move in µm (negative for reverse)

    Returns:
        True if successful, False otherwise
    """
    url = f"{MOVE_ENDPOINT}/relative"
    payload = {
        "axis_id": axis,
        "distance": distance,
        "speed": 100.0  # µm/s
    }

    print(f"  Moving axis {axis} relative {distance:+.1f} µm...")

    try:
        response = requests.post(url, json=payload, timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            if data.get('success', False):
                print(f"    ✓ Move complete")
                return True
            else:
                print(f"    ✗ Move failed: {data.get('error_message', 'Unknown error')}")
                return False
        else:
            print(f"    ✗ Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"    ✗ Exception: {e}")
        return False


def unlock_contact_sensor(stage: str) -> bool:
    """
    Unlock the contact sensor digital output before angle adjustment.
    Checks current state first and only sets if necessary.

    Args:
        stage: "LEFT" or "RIGHT"

    Returns:
        True if successful (already unlocked or successfully unlocked), False otherwise
    """
    channel = 1 if stage == "LEFT" else 2

    # First, check current state
    print(f"  Checking {stage} contact sensor lock state (digital output {channel})...")
    current_state = get_digital_output(channel)

    if current_state is None:
        print(f"    ✗ Failed to read current lock state")
        return False

    if current_state is False:
        # Already unlocked
        print(f"    ✓ Contact sensor already unlocked")
        return True

    # Need to unlock (current state is True = LOCKED)
    print(f"    Contact sensor is LOCKED, unlocking...")
    url = DIGITAL_OUTPUT_ENDPOINT
    payload = {
        "channel": channel,
        "value": False  # False = UNLOCKED
    }

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print(f"    ✓ Contact sensor unlocked")
            return True
        else:
            print(f"    ✗ Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"    ✗ Exception: {e}")
        return False


def stop_angle_adjustment(stage: str) -> bool:
    """
    Stop a currently running angle adjustment.

    Args:
        stage: "LEFT" or "RIGHT"

    Returns:
        True if stop command was sent successfully, False otherwise
    """
    url = ANGLE_ADJUSTMENT_STOP_ENDPOINT
    payload = {"stage": STAGE_VALUE_MAP[stage]}

    try:
        response = requests.post(url, json=payload, timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            if data.get('success', False):
                print(f"\n  ✓ Stop command sent to {stage} angle adjustment")
                return True
            else:
                print(f"\n  ✗ Failed to stop angle adjustment")
                return False
        else:
            print(f"\n  ✗ Error stopping angle adjustment: {response.status_code}")
            return False
    except Exception as e:
        print(f"\n  ✗ Exception stopping angle adjustment: {e}")
        return False


def test_angle_adjustment(stage: str) -> Optional[Dict[str, Any]]:
    """
    Execute angle adjustment with contact detection for specified stage.

    Args:
        stage: "LEFT" or "RIGHT"

    Returns:
        Dictionary containing the adjustment results, or None if failed
    """
    global _angle_adjustment_running, _current_stage

    # Build payload with parameters from user requirements
    # Convert stage string to integer value (LEFT=1, RIGHT=2)
    payload = {
        "stage": STAGE_VALUE_MAP[stage],
        **ANGLE_ADJUSTMENT_PARAMS
    }

    try:
        # Set flags to indicate angle adjustment is running
        _angle_adjustment_running = True
        _current_stage = stage

        # Make API request
        print(f"\n  Starting {stage} stage angle adjustment... (this may take 10-30 seconds)")
        print(f"  Press Ctrl+C to stop the adjustment if something goes wrong")
        response = requests.post(ANGLE_ADJUSTMENT_ENDPOINT, json=payload, timeout=60)

        if response.status_code != 200:
            print(f"  ✗ Error: API returned status {response.status_code}")
            print(f"  Response: {response.text}")
            return None

        data = response.json()

        # Check if adjustment was successful
        if not data.get('success', False):
            print(f"  ✗ Angle adjustment failed!")
            if data.get('error_message'):
                print(f"  Error: {data['error_message']}")
            if data.get('status_description'):
                print(f"  Status: {data['status_description']} (code: {data.get('status_code', 'N/A')})")
            return None

        # Print summary
        print(f"\n  ✓ Angle adjustment completed successfully!")
        print(f"    Status: {data['status_description']} (code: {data['status_code']})")
        print(f"    Final phase: {data['phase_description']} (code: {data['phase_code']})")

        if data.get('initial_signal') is not None:
            print(f"    Initial signal: {data['initial_signal']:.6f} V")
        if data.get('final_signal') is not None:
            print(f"    Final signal: {data['final_signal']:.6f} V")
        if data.get('signal_improvement') is not None:
            print(f"    Signal improvement: {data['signal_improvement']:+.6f} V")

        print(f"    Execution time: {data.get('execution_time', 0):.2f}s")

        # Profile data point counts
        if data.get('contact_z_profile'):
            print(f"    Contact Z data points: {len(data['contact_z_profile'])}")
        if data.get('adjusting_tx_profile'):
            print(f"    Adjusting TX data points: {len(data['adjusting_tx_profile'])}")
        if data.get('adjusting_ty_profile'):
            print(f"    Adjusting TY data points: {len(data['adjusting_ty_profile'])}")

        return data

    except requests.exceptions.Timeout:
        print(f"  ✗ Request timed out after 60 seconds")
        return None
    except Exception as e:
        print(f"  ✗ Exception during angle adjustment: {e}")
        return None
    finally:
        # Clear flags when adjustment completes (success or failure)
        _angle_adjustment_running = False
        _current_stage = None


def plot_angle_adjustment_profiles(data: Dict[str, Any], stage: str,
                                   initial_signal: Optional[float] = None,
                                   final_signal: Optional[float] = None,
                                   save_path: str = None):
    """
    Plot the three angle adjustment profile graphs.

    Creates three vertically-stacked subplots:
    1. Contact Z Profile - Contact detection on Z-axis
    2. Adjusting TX Profile - TX angle adjustment (if performed)
    3. Adjusting TY Profile - TY angle adjustment (if performed)

    Args:
        data: Angle adjustment results from the API
        stage: "LEFT" or "RIGHT"
        initial_signal: Initial analog signal reading in V
        final_signal: Final analog signal reading in V
        save_path: Optional path to save the plot (default: display only)
    """
    if data is None or not data.get('success', False):
        print("No valid data to plot")
        return

    def filter_zeros(positions, signals):
        """Remove trailing zeros from signal data."""
        if not signals:
            return [], []

        # Find last non-zero signal index
        last_valid_index = len(signals) - 1
        for i in range(len(signals) - 1, -1, -1):
            if signals[i] != 0.0:
                last_valid_index = i
                break

        return positions[:last_valid_index + 1], signals[:last_valid_index + 1]

    # Create figure with three subplots
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))

    # Color scheme
    colors = {'contact_z': 'blue', 'adjusting_tx': 'red', 'adjusting_ty': 'green'}

    # ========================================================================
    # Plot 1: Contact Z Profile
    # ========================================================================
    contact_z = data.get('contact_z_profile', [])
    if contact_z:
        positions = [p['position'] for p in contact_z]
        signals = [p['signal'] for p in contact_z]

        # Filter out trailing zeros
        positions, signals = filter_zeros(positions, signals)

        axes[0].plot(positions, signals, color=colors['contact_z'], linewidth=1.5, alpha=0.8)
        axes[0].set_title(f'{stage} Stage - Contact Z Detection Profile', fontsize=12, fontweight='bold')
        axes[0].set_ylabel('Signal (V)', fontsize=11)
        axes[0].grid(True, alpha=0.3, linestyle='--')

        # Add statistics
        if signals:
            max_signal = max(signals)
            axes[0].text(0.02, 0.98, f'Points: {len(positions)}\nMax signal: {max_signal:.6f} V',
                        transform=axes[0].transAxes, fontsize=9,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
    else:
        axes[0].text(0.5, 0.5, 'No contact Z data available',
                    transform=axes[0].transAxes, ha='center', va='center',
                    fontsize=12, color='red')
        axes[0].set_title(f'{stage} Stage - Contact Z Detection Profile', fontsize=12, fontweight='bold')

    # ========================================================================
    # Plot 2: Adjusting TX Profile
    # ========================================================================
    adjusting_tx = data.get('adjusting_tx_profile', [])

    if adjusting_tx:
        positions = [p['position'] for p in adjusting_tx]
        signals = [p['signal'] for p in adjusting_tx]

        # Filter out trailing zeros
        positions, signals = filter_zeros(positions, signals)

        axes[1].plot(positions, signals, color=colors['adjusting_tx'], linewidth=1.5, alpha=0.8,
                    label='TX adjustment')

        axes[1].set_title(f'{stage} Stage - TX Angle Adjustment Profile', fontsize=12, fontweight='bold')
        axes[1].set_ylabel('Signal (V)', fontsize=11)
        axes[1].legend(fontsize=10, loc='best')
        axes[1].grid(True, alpha=0.3, linestyle='--')

        # Add statistics
        if signals:
            max_signal = max(signals)
            axes[1].text(0.02, 0.98, f'Points: {len(positions)}\nMax signal: {max_signal:.6f} V',
                        transform=axes[1].transAxes, fontsize=9,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightcoral', alpha=0.7))
    else:
        axes[1].text(0.5, 0.5, 'No TX adjustment data available\n(TX adjustment disabled)',
                    transform=axes[1].transAxes, ha='center', va='center',
                    fontsize=12, color='gray')
        axes[1].set_title(f'{stage} Stage - TX Angle Adjustment Profile', fontsize=12, fontweight='bold')

    # ========================================================================
    # Plot 3: Adjusting TY Profile
    # ========================================================================
    adjusting_ty = data.get('adjusting_ty_profile', [])

    if adjusting_ty:
        positions = [p['position'] for p in adjusting_ty]
        signals = [p['signal'] for p in adjusting_ty]

        # Filter out trailing zeros
        positions, signals = filter_zeros(positions, signals)

        axes[2].plot(positions, signals, color=colors['adjusting_ty'], linewidth=1.5, alpha=0.8,
                    label='TY adjustment')

        axes[2].set_title(f'{stage} Stage - TY Angle Adjustment Profile', fontsize=12, fontweight='bold')
        axes[2].set_xlabel('Position (µm)', fontsize=11, fontweight='bold')
        axes[2].set_ylabel('Signal (V)', fontsize=11)
        axes[2].legend(fontsize=10, loc='best')
        axes[2].grid(True, alpha=0.3, linestyle='--')

        # Add statistics
        if signals:
            max_signal = max(signals)
            axes[2].text(0.02, 0.98, f'Points: {len(positions)}\nMax signal: {max_signal:.6f} V',
                        transform=axes[2].transAxes, fontsize=9,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))
    else:
        axes[2].text(0.5, 0.5, 'No TY adjustment data available\n(TY adjustment disabled)',
                    transform=axes[2].transAxes, ha='center', va='center',
                    fontsize=12, color='gray')
        axes[2].set_title(f'{stage} Stage - TY Angle Adjustment Profile', fontsize=12, fontweight='bold')
        axes[2].set_xlabel('Position (µm)', fontsize=11, fontweight='bold')

    # ========================================================================
    # Overall figure title with summary
    # ========================================================================
    title_text = f"Angle Adjustment Results - {stage} Stage\n"

    # Prioritize manual measurements if provided, otherwise use data from response
    if initial_signal is not None and final_signal is not None:
        signal_improvement = final_signal - initial_signal
        title_text += f"Signal: {initial_signal:.6f} → {final_signal:.6f} V "
        title_text += f"(Improvement: {signal_improvement:+.6f} V)"
    elif data.get('initial_signal') is not None and data.get('final_signal') is not None:
        title_text += f"Signal: {data['initial_signal']:.6f} → {data['final_signal']:.6f} V "
        title_text += f"(Improvement: {data['signal_improvement']:+.6f} V)"

    fig.suptitle(title_text, fontsize=14, fontweight='bold')

    plt.tight_layout(rect=[0, 0, 1, 0.97])  # Leave room for suptitle

    # Save or show
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"\n✓ Plot saved to: {save_path}")

    plt.show()


def enable_all_servos(axes: list) -> bool:
    """
    Enable servos for all specified axes.

    Args:
        axes: List of axis numbers to enable

    Returns:
        True if all servos enabled successfully, False otherwise
    """
    print(f"Enabling servos for all {len(axes)} axes...", end=" ", flush=True)

    url = f"{SERVO_ENDPOINT}/batch/on"
    payload = {"axis_ids": axes}

    try:
        response = requests.post(url, json=payload, timeout=15.0)
        if response.status_code != 200:
            print(f"\n  ✗ Failed to enable servos: {response.status_code}")
            print(f"  Response: {response.text}")
            return False

        data = response.json()
        if not data.get('success', False):
            print(f"\n  ✗ Failed to enable servos")
            return False
    except Exception as e:
        print(f"\n  ✗ Exception enabling servos: {e}")
        return False

    print(f"✓")
    return True


def disable_all_servos(axes: list):
    """
    Disable servos for all specified axes.

    Args:
        axes: List of axis numbers to disable
    """
    print(f"Disabling all {len(axes)} servos...", end=" ", flush=True)

    url = f"{SERVO_ENDPOINT}/batch/off"
    payload = {"axis_ids": axes}

    try:
        response = requests.post(url, json=payload, timeout=15.0)
        if response.status_code == 200:
            print(f"✓")
        else:
            print(f"⚠ (some may have failed)")
    except Exception:
        print(f"⚠ (request failed)")


def main():
    """
    Main test function:
    1. Turn on servos for ALL 12 axes
    2. Record initial analog signal value
    3. Move Z1 (LEFT) or Z2 (RIGHT) relative -100 µm
    4. Unlock contact sensor
    5. Run angle adjustment with contact detection
    6. Measure final analog signal value
    7. Unlock contact sensor (locked by angle adjustment) and verify state
    8. Turn off servos
    9. Plot three profile graphs (Contact Z, Adjusting TX, Adjusting TY)
    """
    print("=" * 70)
    print("Angle Adjustment Test & Visualization")
    print("=" * 70)

    # Determine Z axis and signal channel based on stage selection
    z_axis = LEFT_STAGE_Z if STAGE == "LEFT" else RIGHT_STAGE_Z
    signal_channel = 5 if STAGE == "LEFT" else 6

    print(f"\nStage: {STAGE}")
    print(f"  Z-axis: {z_axis} ({'Z1' if STAGE == 'LEFT' else 'Z2'})")
    print(f"  Signal channel: {signal_channel}")
    print(f"  Digital output: {1 if STAGE == 'LEFT' else 2}")
    print(f"\nAngle adjustment mode: Contact detection only (TX/TY disabled)")

    initial_signal = None
    final_signal = None

    try:
        # Step 1: Turn on servos for ALL 12 axes
        print(f"\n[Step 1/9] Servo Control - Enable All Axes (1-12)")
        if not enable_all_servos(ALL_AXES):
            print(f"  ✗ Failed to enable servos. Aborting test.")
            return

        # Step 2: Record initial analog signal value
        print(f"\n[Step 2/9] Record Initial Analog Signal Value")
        initial_signal = get_analog_input(channel=signal_channel)
        if initial_signal is not None:
            print(f"  Initial signal: {initial_signal:.6f} V")
        else:
            print(f"  ⚠ Could not read initial signal (will continue anyway)")

        # Step 3: Move Z axis relative -100 µm
        print(f"\n[Step 3/9] Move Z-axis Relative {Z_MOVE_DISTANCE:+.1f} µm")
        if not move_axis_relative(z_axis, Z_MOVE_DISTANCE):
            print(f"  ✗ Failed to move Z-axis. Aborting test.")
            print("\n[Step 8/9] Servo Control - Disable All Axes")
            disable_all_servos(ALL_AXES)
            return

        # Step 4: Unlock contact sensor
        print(f"\n[Step 4/9] Unlock Contact Sensor")
        if not unlock_contact_sensor(STAGE):
            print(f"  ✗ Failed to unlock contact sensor. Aborting test.")
            print("\n[Step 8/9] Servo Control - Disable All Axes")
            disable_all_servos(ALL_AXES)
            return

        # Step 5: Run angle adjustment
        print(f"\n[Step 5/9] Angle Adjustment Execution")
        data = test_angle_adjustment(STAGE)

        adjustment_success = data is not None

        # Step 6: Measure final analog signal value
        print(f"\n[Step 6/9] Record Final Analog Signal Value")
        final_signal = get_analog_input(channel=signal_channel)
        if final_signal is not None:
            print(f"  Final signal: {final_signal:.6f} V")
            if initial_signal is not None:
                signal_improvement = final_signal - initial_signal
                print(f"  Signal improvement: {signal_improvement:+.6f} V")
        else:
            print(f"  ⚠ Could not read final signal")

        # Step 7: Check and unlock contact sensor if needed
        # Angle adjustment may lock the sensor at the end
        digital_output_channel = 1 if STAGE == "LEFT" else 2
        print(f"\n[Step 7/9] Check and Unlock Contact Sensor After Adjustment")

        # Check current state before unlocking
        print(f"  Checking current {STAGE} contact sensor state...")
        current_lock_state = get_digital_output(digital_output_channel)
        if current_lock_state is not None:
            state_str = "LOCKED" if current_lock_state else "UNLOCKED"
            print(f"    Current state: {state_str} ({current_lock_state})")

            # Only unlock if currently locked
            if current_lock_state:
                print(f"  Setting {STAGE} contact sensor to UNLOCKED...")
                if set_digital_output(digital_output_channel, False):
                    print(f"    ✓ Contact sensor unlocked")

                    # Verify the unlock was successful
                    print(f"  Verifying unlock...")
                    final_lock_state = get_digital_output(digital_output_channel)
                    if final_lock_state is not None:
                        state_str = "LOCKED" if final_lock_state else "UNLOCKED"
                        print(f"    Final state: {state_str} ({final_lock_state})")
                    else:
                        print(f"    ✗ Could not verify final state")
                else:
                    print(f"    ✗ Failed to unlock contact sensor")
            else:
                print(f"  Contact sensor is already UNLOCKED, no action needed")
        else:
            print(f"    ✗ Could not read contact sensor state")

        # Step 8: Turn off servos (always execute)
        print(f"\n[Step 8/9] Servo Control - Disable All Axes")
        disable_all_servos(ALL_AXES)

        # Step 9: Plot results (only if adjustment was successful)
        if adjustment_success:
            print(f"\n[Step 9/9] Plotting Results")
            plot_angle_adjustment_profiles(
                data,
                STAGE,
                initial_signal=initial_signal,
                final_signal=final_signal,
                save_path=f'angle_adjustment_{STAGE.lower()}_result.png'
            )

            print("\n" + "=" * 70)
            print("Test completed successfully!")
            print("=" * 70)
        else:
            print(f"\n[Step 9/9] Skipping Plot - Angle Adjustment Failed")
            print("\n" + "=" * 70)
            print("Test completed with errors. Angle adjustment did not succeed.")
            print("=" * 70)

    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()

        # Try to turn off servos in case of error
        print(f"\nAttempting to turn off all servos...")
        disable_all_servos(ALL_AXES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Test interrupted by user (Ctrl+C)")

        # If angle adjustment is running, send stop command
        if _angle_adjustment_running and _current_stage:
            print(f"  Sending stop command to {_current_stage} angle adjustment...")
            stop_angle_adjustment(_current_stage)
            time.sleep(1.0)  # Give time for stop command to take effect

        print("  Attempting to turn off all servos...")
        disable_all_servos(ALL_AXES)
    except requests.exceptions.ConnectionError:
        print("\n✗ Error: Could not connect to API server")
        print(f"  Please ensure the daemon is running at {API_BASE_URL}")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
