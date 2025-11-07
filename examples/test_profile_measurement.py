"""
Test script for profile measurement with data visualization.

This script demonstrates how to:
1. Turn on servo for the axis
2. Execute a profile measurement using the API with default parameters
3. Turn off servo after measurement
4. Plot the position vs signal data
5. Calculate and display the mode field diameter (MFD) using the 1/e² method

The mode field diameter is calculated by finding where the signal intensity
drops to 1/e² (≈13.5%) of the peak value, which is the standard definition
for Gaussian beam characterization in fiber optics.

Configuration:
    Edit the SCAN_AXIS constant to choose which axis to measure:
    - SCAN_AXIS = 1  # X1 axis
    - SCAN_AXIS = 7  # X2 axis (default)
    - SCAN_AXIS = 2  # Y1 axis
    - SCAN_AXIS = 8  # Y2 axis
    - Or any axis from 1-12

Requirements:
    pip install requests matplotlib numpy

Usage:
    python test_profile_measurement.py
"""

import requests
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, Any, Optional, Tuple


# ============================================================================
# CONFIGURATION - Easily change these values
# ============================================================================

# Main axis configuration
SCAN_AXIS = 7  # Main axis to scan for profile measurement (1-12)
               # Common values: 1 (X1), 7 (X2), 2 (Y1), 8 (Y2), 3 (Z1), 9 (Z2)

# Note: Profile measurement scans ONE axis only and returns position data for that axis.
# For multi-axis (X,Y) profile data, use the Optical Alignment API instead.

API_BASE_URL = "http://localhost:8001"  # Default daemon port (see config.py)
# ============================================================================

PROFILE_ENDPOINT = f"{API_BASE_URL}/profile/measure"
SERVO_ENDPOINT = f"{API_BASE_URL}/servo"


def set_servo(axis: int, state: bool) -> bool:
    """
    Turn servo on or off for specified axis.

    Args:
        axis: Axis number (1-12)
        state: True to turn on, False to turn off

    Returns:
        True if successful, False otherwise
    """
    action = "on" if state else "off"
    url = f"{SERVO_ENDPOINT}/{action}"
    payload = {"axis_id": axis}
    
    print(f"{'Enabling' if state else 'Disabling'} servo for axis {axis}...")
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print(f"  ✓ Servo {'ON' if state else 'OFF'}")
            return True
        else:
            print(f"  ✗ Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


def test_profile_measurement(
    scan_axis: int = SCAN_AXIS
) -> Optional[Dict[str, Any]]:
    """
    Execute a profile measurement scan on a single axis.

    Args:
        scan_axis: Main axis to scan (1-12). Default from SCAN_AXIS config.

    Uses default values from ProfileMeasurementRequest model:
    - signal_ch1_number: 1
    - scan_range: 20.0 µm
    - scan_speed: 100.0 µm/s
    - accel_rate: 1000.0 µm/s²
    - decel_rate: 1000.0 µm/s²
    - smoothing: 0

    Note: Profile measurement scans ONE axis only. For multi-axis (X,Y) profile data,
    use the Optical Alignment API which provides separate PeakSearchX and PeakSearchY profiles.

    Returns:
        Dictionary containing the measurement results, or None if failed
    """
    # Build payload with main axis only
    payload = {
        "scan_axis": scan_axis
    }

    print(f"\nSending profile measurement request...")
    print(f"  Scan axis: {scan_axis}")
    print(f"  Using defaults: signal_ch1_number=1, scan_range=20.0, scan_speed=100.0")

    try:
        # Make API request
        response = requests.post(PROFILE_ENDPOINT, json=payload)

        if response.status_code != 200:
            print(f"  ✗ Error: API returned status {response.status_code}")
            print(f"  Response: {response.text}")
            return None

        data = response.json()

        # Check if measurement was successful
        if not data.get('success', False):
            print(f"  ✗ Profile measurement failed!")
            if data.get('error_description'):
                print(f"  Error: {data['error_description']} (code: {data.get('error_code')})")
            return None

        # Print summary
        print(f"\n  ✓ Profile measurement completed successfully!")
        print(f"    Total data points: {data['total_points']}")
        print(f"    Peak position: {data['peak_position']:.3f} µm")
        print(f"    Peak value: {data['peak_value']:.6f}")
        print(f"    Peak index: {data['peak_index']}")
        print(f"    Initial position: {data['main_axis_initial_position']:.3f} µm")
        print(f"    Final position: {data['main_axis_final_position']:.3f} µm")

        return data
    
    except Exception as e:
        print(f"  ✗ Exception during measurement: {e}")
        return None




def calculate_mode_field_diameter(positions: list, signals: list, peak_value: float, peak_index: int) -> Optional[Tuple[float, float, float]]:
    """
    Calculate the mode field diameter (MFD) using the 1/e² method.
    
    The mode field diameter is defined as the diameter at which the intensity
    drops to 1/e² (≈13.5%) of the peak value for a Gaussian beam.
    
    Args:
        positions: List of position values in micrometers
        signals: List of signal values
        peak_value: Peak signal value
        peak_index: Index of the peak in the data
    
    Returns:
        Tuple of (mfd, left_position, right_position) in micrometers, or None if calculation fails
        - mfd: Full width at 1/e² intensity
        - left_position: Position where signal drops to 1/e² on the left side
        - right_position: Position where signal drops to 1/e² on the right side
    """
    if len(positions) < 3 or len(signals) < 3:
        return None
    
    # Calculate 1/e² threshold (13.5% of peak)
    threshold = peak_value / (np.e ** 2)
    
    # Find left crossing point (searching backwards from peak)
    left_pos = None
    for i in range(peak_index, -1, -1):
        if signals[i] <= threshold:
            # Linear interpolation between this point and the previous one
            if i < peak_index:
                x1, y1 = positions[i], signals[i]
                x2, y2 = positions[i + 1], signals[i + 1]
                if y2 != y1:  # Avoid division by zero
                    left_pos = x1 + (threshold - y1) * (x2 - x1) / (y2 - y1)
                else:
                    left_pos = x1
            else:
                left_pos = positions[i]
            break
    
    # Find right crossing point (searching forwards from peak)
    right_pos = None
    for i in range(peak_index, len(signals)):
        if signals[i] <= threshold:
            # Linear interpolation between this point and the previous one
            if i > peak_index:
                x1, y1 = positions[i - 1], signals[i - 1]
                x2, y2 = positions[i], signals[i]
                if y2 != y1:  # Avoid division by zero
                    right_pos = x1 + (threshold - y1) * (x2 - x1) / (y2 - y1)
                else:
                    right_pos = x2
            else:
                right_pos = positions[i]
            break
    
    # If we found both crossing points, calculate MFD
    if left_pos is not None and right_pos is not None:
        mfd = right_pos - left_pos
        return mfd, left_pos, right_pos
    
    return None


def plot_profile_data(data: Dict[str, Any], save_path: str = None):
    """
    Plot the profile measurement data with peak annotation and MFD calculation.
    
    Note: Profile measurement scans only ONE axis. For multi-axis (X,Y) data,
    use the Optical Alignment API instead, which provides separate profile data
    for FieldSearch, PeakSearchX, and PeakSearchY.

    Args:
        data: Profile measurement results from the API
        save_path: Optional path to save the plot (default: display only)
    """
    if data is None or not data.get('success', False):
        print("No valid data to plot")
        return

    # Extract data points and filter out zero-padded entries
    all_positions = [point['position'] for point in data['data_points']]
    all_signals = [point['signal'] for point in data['data_points']]
    
    # Find the last non-zero position (excluding trailing zeros)
    last_valid_idx = len(all_positions) - 1
    for i in range(len(all_positions) - 1, -1, -1):
        if all_positions[i] != 0 or all_signals[i] != 0:
            last_valid_idx = i
            break
    
    # Use only valid data
    positions = all_positions[:last_valid_idx + 1]
    signals = all_signals[:last_valid_idx + 1]

    peak_position = data['peak_position']
    peak_value = data['peak_value']
    peak_index = data['peak_index']

    # Calculate mode field diameter
    mfd_result = calculate_mode_field_diameter(positions, signals, peak_value, peak_index)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot profile data
    ax.plot(positions, signals, 'b-', linewidth=1.5, label='Signal', alpha=0.8)

    # Highlight peak position
    ax.plot(peak_position, peak_value, 'ro', markersize=12,
            label=f'Peak: {peak_value:.6f} @ {peak_position:.3f} µm', zorder=5)

    # Add vertical line at peak
    ax.axvline(x=peak_position, color='r', linestyle='--', alpha=0.5, linewidth=1.5)

    # Plot mode field diameter if calculated
    if mfd_result is not None:
        mfd, left_pos, right_pos = mfd_result
        threshold_value = peak_value / (np.e ** 2)
        
        # Draw horizontal line at 1/e² threshold
        ax.axhline(y=threshold_value, color='purple', linestyle=':', alpha=0.5, linewidth=1.5,
                   label=f'1/e² threshold: {threshold_value:.6f}')
        
        # Mark the MFD points
        ax.plot([left_pos, right_pos], [threshold_value, threshold_value], 
                'go', markersize=10, zorder=5)
        
        # Draw MFD span
        ax.annotate('', xy=(right_pos, threshold_value), xytext=(left_pos, threshold_value),
                    arrowprops=dict(arrowstyle='<->', color='green', lw=2.5))
        
        # Add MFD label
        mid_pos = (left_pos + right_pos) / 2
        ax.text(mid_pos, threshold_value * 1.15, f'MFD = {mfd:.3f} µm',
                ha='center', va='bottom', fontsize=11, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8))

    # Mark initial and final positions
    ax.axvline(x=data['main_axis_initial_position'], color='g', linestyle=':', 
               alpha=0.5, linewidth=1.5, label=f"Initial: {data['main_axis_initial_position']:.2f} µm")
    ax.axvline(x=data['main_axis_final_position'], color='orange', linestyle=':', 
               alpha=0.5, linewidth=1.5, label=f"Final: {data['main_axis_final_position']:.2f} µm")

    # Labels and title
    ax.set_xlabel('Position (µm)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Signal (V)', fontsize=12, fontweight='bold')
    
    title = (f'Profile Measurement - Axis {data["main_axis_number"]} '
             f'(Range: {data["scan_range"]:.1f} µm, Speed: {data["scan_speed"]:.1f} µm/s)')
    if mfd_result is not None:
        title += f'\nMode Field Diameter (1/e²): {mfd_result[0]:.3f} µm'
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend(fontsize=10, loc='best')
    ax.grid(True, alpha=0.3, linestyle='--')

    # Add statistics annotation
    valid_signals = [s for s in signals if s != 0]
    stats_text = f'Valid points: {len(positions)}/{data["total_points"]}\n'
    stats_text += f'Peak index: {peak_index}\n'
    if valid_signals:
        stats_text += f'Signal range: [{min(valid_signals):.6f}, {max(valid_signals):.6f}]\n'
    else:
        stats_text += 'Signal range: No valid data\n'
    
    # Add MFD to stats if available
    if mfd_result is not None:
        mfd, left_pos, right_pos = mfd_result
        stats_text += f'MFD (1/e²): {mfd:.3f} µm\n'
        stats_text += f'Left edge: {left_pos:.3f} µm\n'
        stats_text += f'Right edge: {right_pos:.3f} µm'

    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
            fontsize=10, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))

    plt.tight_layout()

    # Save or show
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"\n✓ Plot saved to: {save_path}")
    
    plt.show()


def main():
    """
    Main test function:
    1. Turn on servo for the scan axis
    2. Run profile measurement
    3. Turn off servo
    4. Plot results with MFD calculation
    """
    print("=" * 70)
    print("Profile Measurement Test & Visualization")
    print("=" * 70)

    print(f"\nScan axis: {SCAN_AXIS}")

    try:
        # Step 1: Turn on servo
        print(f"\n[Step 1/4] Servo Control")
        if not set_servo(SCAN_AXIS, True):
            print(f"  ✗ Failed to enable servo for axis {SCAN_AXIS}. Aborting test.")
            return

        # Step 2: Run profile measurement
        print(f"\n[Step 2/4] Profile Measurement")
        data = test_profile_measurement(scan_axis=SCAN_AXIS)

        if data is None:
            print("  ✗ Profile measurement failed.")
            return

        # Step 3: Turn off servo
        print(f"\n[Step 3/4] Servo Control")
        set_servo(SCAN_AXIS, False)

        # Step 4: Plot results
        print(f"\n[Step 4/4] Plotting Results")
        plot_profile_data(data, save_path='profile_measurement_result.png')
        
        print("\n" + "=" * 70)
        print("Test completed successfully!")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()

        # Try to turn off servo in case of error
        print(f"\nAttempting to turn off servo...")
        set_servo(SCAN_AXIS, False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Test interrupted by user")
        print("Attempting to turn off servo...")
        set_servo(SCAN_AXIS, False)
    except requests.exceptions.ConnectionError:
        print("\n✗ Error: Could not connect to API server")
        print(f"  Please ensure the daemon is running at {API_BASE_URL}")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
