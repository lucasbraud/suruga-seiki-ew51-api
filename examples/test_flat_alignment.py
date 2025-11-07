"""
Test script for flat alignment with data visualization.

This script demonstrates how to:
1. Turn on servo for both X and Y axes
2. Execute a flat (2D) optical alignment using the API with default parameters
3. Turn off servos after alignment
4. Plot the three profile graphs (Field Search, Peak Search X, Peak Search Y)
5. Display peak positions and power improvement

Flat alignment performs a two-axis (X, Y) optical alignment to maximize optical coupling.
It consists of three phases:
- Field Search: Wide spiral/raster scan to locate the signal
- Peak Search X: Fine scan along X-axis to find peak
- Peak Search Y: Fine scan along Y-axis to find peak

Configuration:
    Edit the MAIN_STAGE_X and MAIN_STAGE_Y constants to choose which axes to align:
    - MAIN_STAGE_X = 7  # Right stage X axis (default)
    - MAIN_STAGE_Y = 8  # Right stage Y axis (default)
    - Or: 1 (left X), 2 (left Y), etc.

Requirements:
    pip install requests matplotlib numpy

Usage:
    python test_flat_alignment.py
"""

import requests
import matplotlib.pyplot as plt
import numpy as np
import time
from typing import Dict, Any, Optional


# ============================================================================
# CONFIGURATION - Easily change these values
# ============================================================================

# Right stage configuration
# Linear axes
MAIN_STAGE_X = 7   # X2 - X-axis (main alignment axis)
MAIN_STAGE_Y = 8   # Y2 - Y-axis (main alignment axis)
MAIN_STAGE_Z = 9   # Z2 - Z-axis
# Rotational axes
MAIN_STAGE_TX = 10 # TX2 - θX rotation
MAIN_STAGE_TY = 11 # TY2 - θY rotation
MAIN_STAGE_TZ = 12 # TZ2 - θZ rotation

# Left stage configuration (may be needed for alignment)
LEFT_STAGE_X = 1   # X1 - X-axis
LEFT_STAGE_Y = 2   # Y1 - Y-axis
LEFT_STAGE_Z = 3   # Z1 - Z-axis
LEFT_STAGE_TX = 4  # TX1 - θX rotation
LEFT_STAGE_TY = 5  # TY1 - θY rotation
LEFT_STAGE_TZ = 6  # TZ1 - θZ rotation

# Enable ALL 12 axes (both stages) for flat alignment
# This matches the suruga_sample_program.py behavior where all axes are servo-enabled
ALL_AXES = list(range(1, 13))  # Axes 1-12
RIGHT_STAGE_AXES = [MAIN_STAGE_X, MAIN_STAGE_Y, MAIN_STAGE_Z,
                    MAIN_STAGE_TX, MAIN_STAGE_TY, MAIN_STAGE_TZ]
LEFT_STAGE_AXES = [LEFT_STAGE_X, LEFT_STAGE_Y, LEFT_STAGE_Z,
                   LEFT_STAGE_TX, LEFT_STAGE_TY, LEFT_STAGE_TZ]

# Note: The FlatAlignmentRequest model defines many parameters with conservative
# defaults (10µm range, 100µm/s speed). These defaults will be used unless
# explicitly overridden in the payload.

API_BASE_URL = "http://localhost:8001"  # Default daemon port (see config.py)
# ============================================================================

ALIGNMENT_ENDPOINT = f"{API_BASE_URL}/alignment/flat/execute"
SERVO_ENDPOINT = f"{API_BASE_URL}/servo"


def set_servo(axis: int, state: bool, silent: bool = False) -> bool:
    """
    Turn servo on or off for specified axis.

    Args:
        axis: Axis number (1-12)
        state: True to turn on, False to turn off
        silent: If True, suppress output messages

    Returns:
        True if successful, False otherwise
    """
    action = "on" if state else "off"
    url = f"{SERVO_ENDPOINT}/{action}"
    payload = {"axis_id": axis}

    if not silent:
        print(f"{'Enabling' if state else 'Disabling'} servo for axis {axis}...")

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            if not silent:
                print(f"  ✓ Servo {'ON' if state else 'OFF'}")
            return True
        else:
            print(f"  ✗ Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


def save_profile_data_to_files(data: Dict[str, Any]):
    """
    Save alignment profile data to text files (similar to suruga_sample_program.py).

    Creates six text files:
    - fieldsearchposition.txt / fieldsearchsignal.txt
    - peaksearchXposition.txt / peaksearchXsignal.txt
    - peaksearchYposition.txt / peaksearchYsignal.txt

    Note: Filters out trailing zero values that are padding in the profile arrays.
    The daemon reports the actual data count, but arrays may contain zeros beyond that point.

    Args:
        data: Flat alignment results from the API
    """
    if data is None or not data.get('success', False):
        print("    No valid data to save")
        return

    def filter_valid_data(profile_list):
        """
        Filter out trailing zeros from profile data.
        Returns positions and signals up to the last non-zero signal value.
        """
        if not profile_list:
            return [], []
        
        positions = [p['position'] for p in profile_list]
        signals = [p['signal'] for p in profile_list]
        
        # Find the last non-zero signal index
        last_valid_index = len(signals) - 1
        for i in range(len(signals) - 1, -1, -1):
            if signals[i] != 0.0:
                last_valid_index = i
                break
        
        # Return data up to and including the last valid point
        return positions[:last_valid_index + 1], signals[:last_valid_index + 1]

    # Field Search data
    field_search = data.get('field_search_profile', [])
    if field_search:
        positions, signals = filter_valid_data(field_search)
        
        with open('fieldsearchposition.txt', 'w') as f:
            f.write('\n'.join(map(str, positions)))
        
        with open('fieldsearchsignal.txt', 'w') as f:
            f.write('\n'.join(map(str, signals)))
        
        print(f"    ✓ Saved field search data ({len(positions)} points)")

    # Peak Search X data
    peak_search_x = data.get('peak_search_x_profile', [])
    if peak_search_x:
        positions, signals = filter_valid_data(peak_search_x)
        
        with open('peaksearchXposition.txt', 'w') as f:
            f.write('\n'.join(map(str, positions)))
        
        with open('peaksearchXsignal.txt', 'w') as f:
            f.write('\n'.join(map(str, signals)))
        
        print(f"    ✓ Saved peak search X data ({len(positions)} points)")

    # Peak Search Y data
    peak_search_y = data.get('peak_search_y_profile', [])
    if peak_search_y:
        positions, signals = filter_valid_data(peak_search_y)
        
        with open('peaksearchYposition.txt', 'w') as f:
            f.write('\n'.join(map(str, positions)))
        
        with open('peaksearchYsignal.txt', 'w') as f:
            f.write('\n'.join(map(str, signals)))
        
        print(f"    ✓ Saved peak search Y data ({len(positions)} points)")


def test_flat_alignment(
    main_stage_x: int = MAIN_STAGE_X,
    main_stage_y: int = MAIN_STAGE_Y
) -> Optional[Dict[str, Any]]:
    """
    Execute a flat (2D) optical alignment for X and Y axes.

    Args:
        main_stage_x: Main X-axis stage number (1-12). Default from MAIN_STAGE_X config.
        main_stage_y: Main Y-axis stage number (1-12). Default from MAIN_STAGE_Y config.

    Uses parameters similar to suruga_sample_program.py for wider search:
    - searchRangeX/Y: 500.0 µm (wide search area)
    - fieldSearchPitchX/Y: 5.0 µm (coarse grid)
    - fieldSearchSpeedX/Y: 1000.0 µm/s (fast scanning)
    - peakSearchSpeedX/Y: 5.0 µm/s (fine scanning)
    - peakSearchThreshold: 40.0 % (aggressive threshold)
    - smoothingRangeX/Y: 50 (from sample program)
    - convergentRangeX/Y: 1.0 (looser tolerance)
    - wavelength: 1310 nm
    - pmCh: 1

    Returns:
        Dictionary containing the alignment results, or None if failed
    """
    # Build payload with aggressive parameters from suruga_sample_program.py
    payload = {
        "mainStageNumberX": main_stage_x,
        "mainStageNumberY": main_stage_y,
        # Wide search parameters
        "searchRangeX": 15.0,
        "searchRangeY": 15.0,
        "fieldSearchPitchX": 1.0,
        "fieldSearchPitchY": 1.0,
        "fieldSearchSpeedX": 100.0,
        "fieldSearchSpeedY": 100.0,
        "peakSearchThreshold": 10.0,
        "smoothingRangeX": 40.0,
        "smoothingRangeY": 40.0,
        "convergentRangeX": 0.5,
        "convergentRangeY": 0.5,
    }

    try:
        # Make API request
        print(f"\n  Starting alignment... (this may take 10-60 seconds)")
        response = requests.post(ALIGNMENT_ENDPOINT, json=payload, timeout=120)

        if response.status_code != 200:
            print(f"  ✗ Error: API returned status {response.status_code}")
            print(f"  Response: {response.text}")
            return None

        data = response.json()

        # Check if alignment was successful
        if not data.get('success', False):
            print(f"  ✗ Flat alignment failed!")
            if data.get('error_message'):
                print(f"  Error: {data['error_message']}")
                if data.get('error_code'):
                    print(f"  Error code: {data['error_code']} ({data.get('error_description', 'N/A')})")
            return None

        # Print summary
        print(f"\n  ✓ Flat alignment completed successfully!")
        print(f"    Status: {data['status_description']} (code: {data['status_code']})")
        print(f"    Final phase: {data['phase_description']} (code: {data['phase_code']})")
        print(f"    Initial power: {data['initial_power']:.3f} dBm")
        print(f"    Final power: {data['final_power']:.3f} dBm")
        print(f"    Power improvement: {data['power_improvement']:+.3f} dB")

        if data.get('peak_position_x') is not None:
            print(f"    Peak X position: {data['peak_position_x']:.3f} µm")
        if data.get('peak_position_y') is not None:
            print(f"    Peak Y position: {data['peak_position_y']:.3f} µm")

        # Profile data point counts
        if data.get('field_search_profile'):
            print(f"    Field search data points: {len(data['field_search_profile'])}")
        if data.get('peak_search_x_profile'):
            print(f"    Peak search X data points: {len(data['peak_search_x_profile'])}")
        if data.get('peak_search_y_profile'):
            print(f"    Peak search Y data points: {len(data['peak_search_y_profile'])}")

        # Save profile data to files (like suruga_sample_program.py)
        save_profile_data_to_files(data)

        return data

    except requests.exceptions.Timeout:
        print(f"  ✗ Request timed out after 120 seconds")
        return None
    except Exception as e:
        print(f"  ✗ Exception during alignment: {e}")
        return None


def plot_alignment_profiles(data: Dict[str, Any], save_path: str = None):
    """
    Plot the three alignment profile graphs in the style of suruga_sample_program.py.

    Creates three vertically-stacked subplots:
    1. Field Search Profile - Wide spiral/raster scan
    2. Peak Search X Profile - Fine X-axis scan with peak marker
    3. Peak Search Y Profile - Fine Y-axis scan with peak marker

    Note: Filters out trailing zero values to avoid plotting artifacts.

    Args:
        data: Flat alignment results from the API
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
    colors = {'field': 'blue', 'peakx': 'red', 'peaky': 'green'}

    # ========================================================================
    # Plot 1: Field Search Profile
    # ========================================================================
    field_search = data.get('field_search_profile', [])
    if field_search:
        positions = [p['position'] for p in field_search]
        signals = [p['signal'] for p in field_search]
        
        # Filter out trailing zeros
        positions, signals = filter_zeros(positions, signals)

        axes[0].plot(positions, signals, color=colors['field'], linewidth=1.5, alpha=0.8)
        axes[0].set_title('Field Search Profile', fontsize=12, fontweight='bold')
        axes[0].set_ylabel('Signal (V)', fontsize=11)
        axes[0].grid(True, alpha=0.3, linestyle='--')

        # Add statistics
        if signals:
            max_signal = max(signals)
            axes[0].text(0.02, 0.98, f'Points: {len(positions)}\nMax signal: {max_signal:.6f}',
                        transform=axes[0].transAxes, fontsize=9,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
    else:
        axes[0].text(0.5, 0.5, 'No field search data available',
                    transform=axes[0].transAxes, ha='center', va='center',
                    fontsize=12, color='red')
        axes[0].set_title('Field Search Profile', fontsize=12, fontweight='bold')

    # ========================================================================
    # Plot 2: Peak Search X Profile
    # ========================================================================
    peak_search_x = data.get('peak_search_x_profile', [])
    peak_x = data.get('peak_position_x')

    if peak_search_x:
        positions = [p['position'] for p in peak_search_x]
        signals = [p['signal'] for p in peak_search_x]
        
        # Filter out trailing zeros
        positions, signals = filter_zeros(positions, signals)

        axes[1].plot(positions, signals, color=colors['peakx'], linewidth=1.5, alpha=0.8,
                    label='X-axis scan')

        # Mark peak position if available
        if peak_x is not None:
            # Find peak value (approximate from data)
            peak_value = max(signals) if signals else 0
            axes[1].plot(peak_x, peak_value, 'o', color=colors['peakx'],
                        markersize=12, markeredgecolor='black', markeredgewidth=1.5,
                        label=f'Peak: {peak_x:.3f} µm', zorder=5)
            axes[1].axvline(x=peak_x, color=colors['peakx'], linestyle='--',
                          alpha=0.5, linewidth=1.5)
        
        # Set x-axis to actual data range with small margin
        if positions:
            pos_min, pos_max = min(positions), max(positions)
            margin = (pos_max - pos_min) * 0.05
            axes[1].set_xlim(pos_min - margin, pos_max + margin)

        axes[1].set_title('X-Axis Peak Search Profile', fontsize=12, fontweight='bold')
        axes[1].set_ylabel('Signal (V)', fontsize=11)
        axes[1].legend(fontsize=10, loc='best')
        axes[1].grid(True, alpha=0.3, linestyle='--')

        # Add statistics
        if signals:
            max_signal = max(signals)
            axes[1].text(0.02, 0.98, f'Points: {len(positions)}\nMax signal: {max_signal:.6f}',
                        transform=axes[1].transAxes, fontsize=9,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightcoral', alpha=0.7))
    else:
        axes[1].text(0.5, 0.5, 'No peak search X data available',
                    transform=axes[1].transAxes, ha='center', va='center',
                    fontsize=12, color='red')
        axes[1].set_title('X-Axis Peak Search Profile', fontsize=12, fontweight='bold')

    # ========================================================================
    # Plot 3: Peak Search Y Profile
    # ========================================================================
    peak_search_y = data.get('peak_search_y_profile', [])
    peak_y = data.get('peak_position_y')

    if peak_search_y:
        positions = [p['position'] for p in peak_search_y]
        signals = [p['signal'] for p in peak_search_y]
        
        # Filter out trailing zeros
        positions, signals = filter_zeros(positions, signals)

        axes[2].plot(positions, signals, color=colors['peaky'], linewidth=1.5, alpha=0.8,
                    label='Y-axis scan')

        # Mark peak position if available
        if peak_y is not None:
            # Find peak value (approximate from data)
            peak_value = max(signals) if signals else 0
            axes[2].plot(peak_y, peak_value, 'o', color=colors['peaky'],
                        markersize=12, markeredgecolor='black', markeredgewidth=1.5,
                        label=f'Peak: {peak_y:.3f} µm', zorder=5)
            axes[2].axvline(x=peak_y, color=colors['peaky'], linestyle='--',
                          alpha=0.5, linewidth=1.5)
        
        # Set x-axis to actual data range with small margin
        if positions:
            pos_min, pos_max = min(positions), max(positions)
            margin = (pos_max - pos_min) * 0.05
            axes[2].set_xlim(pos_min - margin, pos_max + margin)

        axes[2].set_title('Y-Axis Peak Search Profile', fontsize=12, fontweight='bold')
        axes[2].set_xlabel('Position (µm)', fontsize=11, fontweight='bold')
        axes[2].set_ylabel('Signal (V)', fontsize=11)
        axes[2].legend(fontsize=10, loc='best')
        axes[2].grid(True, alpha=0.3, linestyle='--')

        # Add statistics
        if signals:
            max_signal = max(signals)
            axes[2].text(0.02, 0.98, f'Points: {len(positions)}\nMax signal: {max_signal:.6f}',
                        transform=axes[2].transAxes, fontsize=9,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))
    else:
        axes[2].text(0.5, 0.5, 'No peak search Y data available',
                    transform=axes[2].transAxes, ha='center', va='center',
                    fontsize=12, color='red')
        axes[2].set_title('Y-Axis Peak Search Profile', fontsize=12, fontweight='bold')
        axes[2].set_xlabel('Position (µm)', fontsize=11, fontweight='bold')

    # ========================================================================
    # Overall figure title with summary
    # ========================================================================
    title_text = f"Flat Alignment Results (Axes {data.get('mainStageNumberX', '?')}, {data.get('mainStageNumberY', '?')})\n"
    title_text += f"Power: {data['initial_power']:.3f} → {data['final_power']:.3f} dBm "
    title_text += f"(Improvement: {data['power_improvement']:+.3f} dB)"

    fig.suptitle(title_text, fontsize=14, fontweight='bold')

    plt.tight_layout(rect=[0, 0, 1, 0.97])  # Leave room for suptitle

    # Save or show
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"\n✓ Plot saved to: {save_path}")

    plt.show()


def wait_for_servo_ready(axis: int) -> bool:
    """
    Wait for axis servo to reach InPosition status.

    Args:
        axis: Axis number

    Returns:
        True if axis reached InPosition, False otherwise
    """
    url = f"{SERVO_ENDPOINT}/wait_ready"
    payload = {"axis_id": axis}

    try:
        response = requests.post(url, json=payload, timeout=15.0)
        if response.status_code == 200:
            data = response.json()
            return data.get('success', False)
        else:
            print(f"    ✗ Wait ready failed for axis {axis}: {response.status_code}")
            return False
    except Exception as e:
        print(f"    ✗ Exception waiting for axis {axis}: {e}")
        return False


def enable_all_servos(axes: list) -> bool:
    """
    Enable servos for all specified axes (matches suruga_sample_program.py behavior).
    
    The sample program simply turns on all servos without waiting for them to reach
    InPosition. The alignment routine itself will check servo status before executing.

    Args:
        axes: List of axis numbers to enable

    Returns:
        True if all servos enabled successfully, False otherwise
    """
    print(f"Enabling servos for all {len(axes)} axes...", end=" ", flush=True)

    # Turn on all servos in one batch request (no waiting, like sample program)
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
    
    # Turn off all servos in one batch request
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
    1. Turn on servos for ALL 12 axes (both stages)
    2. Run flat alignment
    3. Turn off servos
    4. Plot three profile graphs (field search, peak search X, peak search Y)

    Note: Enabling all 12 axes matches the suruga_sample_program.py behavior.
    The alignment controller checks servo status across the entire system.
    """
    print("=" * 70)
    print("Flat Alignment Test & Visualization")
    print("=" * 70)

    print(f"\nEnabling ALL 12 axes (both left and right stages)")
    print(f"Right stage: {RIGHT_STAGE_AXES}")
    print(f"  X2={MAIN_STAGE_X}, Y2={MAIN_STAGE_Y}, Z2={MAIN_STAGE_Z}")
    print(f"  TX2={MAIN_STAGE_TX}, TY2={MAIN_STAGE_TY}, TZ2={MAIN_STAGE_TZ}")
    print(f"Left stage: {LEFT_STAGE_AXES}")

    try:
        # Step 1: Turn on servos for ALL 12 axes (no waiting, like sample program)
        print(f"\n[Step 1/4] Servo Control - Enable All Axes (1-12)")
        if not enable_all_servos(ALL_AXES):
            print(f"  ✗ Failed to enable servos. Aborting test.")
            return

        # Step 2: Run flat alignment
        print(f"\n[Step 2/4] Flat Alignment Execution")
        data = test_flat_alignment(main_stage_x=MAIN_STAGE_X, main_stage_y=MAIN_STAGE_Y)

        if data is None:
            print("  ✗ Flat alignment failed.")
            print("\n[Step 3/4] Servo Control - Disable All Axes")
            disable_all_servos(ALL_AXES)
            return

        print(f"\n    Profile data saved to text files in current directory:")
        print(f"    - fieldsearchposition.txt / fieldsearchsignal.txt")
        print(f"    - peaksearchXposition.txt / peaksearchXsignal.txt")
        print(f"    - peaksearchYposition.txt / peaksearchYsignal.txt")

        # Step 3: Turn off servos
        print(f"\n[Step 3/4] Servo Control - Disable All Axes")
        disable_all_servos(ALL_AXES)

        # Step 4: Plot results
        print(f"\n[Step 4/4] Plotting Results")
        plot_alignment_profiles(data, save_path='flat_alignment_result.png')

        print("\n" + "=" * 70)
        print("Test completed successfully!")
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
        print("\n\n✗ Test interrupted by user")
        print("Attempting to turn off all servos...")
        disable_all_servos(ALL_AXES)
    except requests.exceptions.ConnectionError:
        print("\n✗ Error: Could not connect to API server")
        print(f"  Please ensure the daemon is running at {API_BASE_URL}")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
