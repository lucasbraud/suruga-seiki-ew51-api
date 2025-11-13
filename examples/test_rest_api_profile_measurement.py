"""
Async REST API profile measurement tests with data visualization and task control.

This script now supports both:
- Synchronous measurement: POST /profile/measure (200 OK)
- Async task-based measurement: POST /profile/measure/execute (202 + task_id)
    - GET /profile/status/{task_id}
    - POST /profile/stop/{task_id}

It includes tests similar to angle adjustment:
1) Cancellation while measuring
2) Full measurement to completion and plotting
3) Concurrent task rejection (409 Conflict)

Usage:
        python examples/test_rest_api_profile_measurement.py
"""

import asyncio
from typing import Dict, Any, Optional, Tuple

import httpx
import numpy as np
import matplotlib.pyplot as plt

BASE_URL = "http://localhost:8000"

# Main axis configuration (linear axes only: 1, 2, 3, 7, 8, 9)
SCAN_AXIS = 7  # Common: 1 (X1), 7 (X2), 2 (Y1), 8 (Y2), 3 (Z1), 9 (Z2)
AXES_LIST = [SCAN_AXIS]


async def set_servo(client: httpx.AsyncClient, axis: int, state: bool) -> bool:
    """Turn servo on or off for specified axis."""
    action = "on" if state else "off"
    print(f"{'Enabling' if state else 'Disabling'} servo for axis {axis}...")
    resp = await client.post(f"/servo/{action}", json={"axis_id": axis})
    if resp.status_code == 200:
        print(f"  ✓ Servo {'ON' if state else 'OFF'}")
        return True
    print(f"  ✗ Servo {action} failed: {resp.status_code} {resp.text}")
    return False


async def run_profile_measurement_sync(client: httpx.AsyncClient, scan_axis: int) -> Optional[Dict[str, Any]]:
    """Execute profile measurement synchronously via REST API (200 OK)."""
    payload = {
        "scan_axis": scan_axis
        # Using defaults for all other parameters (see ProfileMeasurementRequest)
    }

    print("\nSending profile measurement request...")
    print(f"  Scan axis: {scan_axis}")
    print(f"  Using server defaults for ranges/speed/smoothing")

    resp = await client.post("/profile/measure", json=payload)

    if resp.status_code == 200:
        data = resp.json()
        print("\n  ✓ Profile measurement completed successfully!")
        print(f"    Total data points: {data['total_points']}")
        print(f"    Peak position: {data['peak_position']:.3f} µm")
        print(f"    Peak value: {data['peak_value']:.6f}")
        print(f"    Peak index: {data['peak_index']}")
        print(f"    Initial position: {data['main_axis_initial_position']:.3f} µm")
        print(f"    Final position: {data['main_axis_final_position']:.3f} µm")
        return data

    if resp.status_code == 422:
        # Structured error from controller state or parameters
        data = resp.json()
        print("  ✗ Profile measurement failed (422)")
        err = data
        if err.get("error_description"):
            print(f"    Error: {err['error_description']} (code: {err.get('error_code')})")
        elif err.get("status_description"):
            print(f"    Status: {err['status_description']} (code: {err.get('status_code')})")
        else:
            print(f"    Details: {data}")
        return None

    print(f"  ✗ Request failed: {resp.status_code} {resp.text}")
    return None


async def start_profile_measurement_async(client: httpx.AsyncClient, scan_axis: int) -> Optional[str]:
    """Start async profile measurement; return task_id if accepted."""
    payload = {"scan_axis": scan_axis}
    print("\nSending async profile measurement request...")
    resp = await client.post("/profile/measure/execute", json=payload)
    if resp.status_code == 202:
        data = resp.json()
        task_id = data["task_id"]
        print(f"  ✓ Task created: {task_id}")
        print(f"    Status URL: {data['status_url']}")
        return task_id
    print(f"  ✗ Request failed: {resp.status_code} {resp.text}")
    return None


async def poll_profile_status(client: httpx.AsyncClient, task_id: str, *, poll_seconds: float = 0.5, max_polls: int = 240) -> Dict[str, Any]:
    """Poll profile measurement task until terminal status or timeout."""
    for i in range(max_polls):
        await asyncio.sleep(poll_seconds)
        r = await client.get(f"/profile/status/{task_id}")
        data = r.json()
        status = data.get("status")
        progress = data.get("progress", {})
        msg = progress.get("message")
        phase = progress.get("phase")
        print(f"  Poll #{i+1}: Status={status}{' - ' + phase if phase else ''}{' | ' + msg if msg else ''}")
        if status in ["completed", "failed", "cancelled"]:
            return data
    return data


async def cancel_profile_task(client: httpx.AsyncClient, task_id: str) -> None:
    resp = await client.post(f"/profile/stop/{task_id}")
    if resp.status_code == 200:
        print("  ✓ Cancellation requested")
    else:
        print(f"  ✗ Cancel request failed: {resp.status_code} {resp.text}")


def calculate_mode_field_diameter(positions: list, signals: list, peak_value: float, peak_index: int) -> Optional[Tuple[float, float, float]]:
    """Calculate the mode field diameter (MFD) using the 1/e² method."""
    if len(positions) < 3 or len(signals) < 3:
        return None

    threshold = peak_value / (np.e ** 2)

    # Find left crossing
    left_pos = None
    for i in range(peak_index, -1, -1):
        if signals[i] <= threshold:
            if i < peak_index:
                x1, y1 = positions[i], signals[i]
                x2, y2 = positions[i + 1], signals[i + 1]
                left_pos = x1 + (threshold - y1) * (x2 - x1) / (y2 - y1) if y2 != y1 else x1
            else:
                left_pos = positions[i]
            break

    # Find right crossing
    right_pos = None
    for i in range(peak_index, len(signals)):
        if signals[i] <= threshold:
            if i > peak_index:
                x1, y1 = positions[i - 1], signals[i - 1]
                x2, y2 = positions[i], signals[i]
                right_pos = x1 + (threshold - y1) * (x2 - x1) / (y2 - y1) if y2 != y1 else x2
            else:
                right_pos = positions[i]
            break

    if left_pos is not None and right_pos is not None:
        return right_pos - left_pos, left_pos, right_pos
    return None


def plot_profile_data(data: Dict[str, Any], save_path: Optional[str] = None) -> None:
    """Plot the profile measurement data with peak annotation and MFD calculation."""
    if data is None or not data.get("success", False):
        print("No valid data to plot")
        return

    all_positions = [p["position"] for p in data["data_points"]]
    all_signals = [p["signal"] for p in data["data_points"]]

    # Trim trailing zero padding (if any)
    last_valid_idx = len(all_positions) - 1
    for i in range(len(all_positions) - 1, -1, -1):
        if all_positions[i] != 0 or all_signals[i] != 0:
            last_valid_idx = i
            break

    positions = all_positions[: last_valid_idx + 1]
    signals = all_signals[: last_valid_idx + 1]

    peak_position = data["peak_position"]
    peak_value = data["peak_value"]
    peak_index = data["peak_index"]

    mfd_result = calculate_mode_field_diameter(positions, signals, peak_value, peak_index)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(positions, signals, "b-", linewidth=1.5, label="Signal", alpha=0.8)

    # Peak marker and line
    ax.plot(peak_position, peak_value, "ro", markersize=12, label=f"Peak: {peak_value:.6f} @ {peak_position:.3f} µm", zorder=5)
    ax.axvline(x=peak_position, color="r", linestyle="--", alpha=0.5, linewidth=1.5)

    # 1/e² MFD visuals
    if mfd_result is not None:
        mfd, left_pos, right_pos = mfd_result
        threshold_value = peak_value / (np.e ** 2)
        ax.axhline(y=threshold_value, color="purple", linestyle=":", alpha=0.5, linewidth=1.5,
                   label=f"1/e² threshold: {threshold_value:.6f}")
        ax.plot([left_pos, right_pos], [threshold_value, threshold_value], "go", markersize=10, zorder=5)
        ax.annotate("", xy=(right_pos, threshold_value), xytext=(left_pos, threshold_value),
                    arrowprops=dict(arrowstyle="<->", color="green", lw=2.5))
        mid_pos = (left_pos + right_pos) / 2
        ax.text(mid_pos, threshold_value * 1.15, f"MFD = {mfd:.3f} µm", ha="center", va="bottom",
                fontsize=11, fontweight="bold", bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgreen", alpha=0.8))

    # Initial/final markers
    ax.axvline(x=data["main_axis_initial_position"], color="g", linestyle=":", alpha=0.5, linewidth=1.5,
               label=f"Initial: {data['main_axis_initial_position']:.2f} µm")
    ax.axvline(x=data["main_axis_final_position"], color="orange", linestyle=":", alpha=0.5, linewidth=1.5,
               label=f"Final: {data['main_axis_final_position']:.2f} µm")

    ax.set_xlabel("Position (µm)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Signal (V)", fontsize=12, fontweight="bold")
    title = (f"Profile Measurement - Axis {data['main_axis_number']} "
             f"(Range: {data['scan_range']:.1f} µm, Speed: {data['scan_speed']:.1f} µm/s)")
    if mfd_result is not None:
        title += f"\nMode Field Diameter (1/e²): {mfd_result[0]:.3f} µm"
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(fontsize=10, loc="best")
    ax.grid(True, alpha=0.3, linestyle="--")

    # Stats box
    valid_signals = [s for s in signals if s != 0]
    stats_text = f"Valid points: {len(positions)}/{data['total_points']}\n"
    stats_text += f"Peak index: {peak_index}\n"
    if valid_signals:
        stats_text += f"Signal range: [{min(valid_signals):.6f}, {max(valid_signals):.6f}]\n"
    else:
        stats_text += "Signal range: No valid data\n"
    if mfd_result is not None:
        mfd, left_pos, right_pos = mfd_result
        stats_text += f"MFD (1/e²): {mfd:.3f} µm\nLeft edge: {left_pos:.3f} µm\nRight edge: {right_pos:.3f} µm"

    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=10, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="lightblue", alpha=0.7))

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"\n✓ Plot saved to: {save_path}")
    plt.show()


async def test_profile_cancellation(client: httpx.AsyncClient) -> None:
    print("=" * 70)
    print("[TEST 1] Profile measurement with cancellation")
    print("=" * 70)
    print()

    # Enable servo using batch endpoint to mirror angle pattern
    print("[1.1] Enabling servos for selected axis...")
    resp = await client.post("/servo/batch/on", json={"axis_ids": AXES_LIST})
    if resp.status_code == 200:
        print("  ✓ Servo(s) enabled")
    else:
        print(f"  ✗ Failed to enable servo(s): {resp.text}")
        return

    try:
        print("\n[1.2] Starting async profile measurement...")
        task_id = await start_profile_measurement_async(client, SCAN_AXIS)
        if not task_id:
            return

        # Brief delay then request cancellation
        await asyncio.sleep(0.3)
        print("\n[1.3] Cancelling task...")
        await cancel_profile_task(client, task_id)

        # Poll for terminal state after cancellation
        print("\n[1.4] Polling for terminal status after cancel...")
        fdata = await poll_profile_status(client, task_id, poll_seconds=0.3, max_polls=40)
        print(f"  Final status: {fdata.get('status')}")
        if fdata.get("status") == "cancelled":
            print("  ✓ Profile measurement successfully cancelled")
        else:
            print("  ⚠ Unexpected terminal status")
    finally:
        print("\n[1.5] Disabling servo(s)...")
        await client.post("/servo/batch/off", json={"axis_ids": AXES_LIST})
        print("  ✓ Servo(s) disabled")

    print()
    print("=" * 70)
    print("Test 1 completed!")
    print()


async def test_profile_completion_and_plot(client: httpx.AsyncClient) -> None:
    print("=" * 70)
    print("[TEST 2] Profile measurement to completion + plot")
    print("=" * 70)
    print()

    print("[2.1] Enabling servos for selected axis...")
    resp = await client.post("/servo/batch/on", json={"axis_ids": AXES_LIST})
    if resp.status_code == 200:
        print("  ✓ Servo(s) enabled")
    else:
        print(f"  ✗ Failed to enable servo(s): {resp.text}")
        return

    try:
        print("\n[2.2] Starting async profile measurement...")
        task_id = await start_profile_measurement_async(client, SCAN_AXIS)
        if not task_id:
            return

        print("\n[2.3] Polling for completion...")
        status_data = await poll_profile_status(client, task_id, poll_seconds=0.5, max_polls=240)

        if status_data.get("status") == "completed":
            print("\n[2.4] ✓ Measurement completed. Plotting data...")
            result = status_data.get("result", {})
            # The task result dict is a summary, fetch full data in a synchronous call for plotting
            data = await run_profile_measurement_sync(client, SCAN_AXIS)
            if data:
                plot_profile_data(data, save_path="profile_measurement_result.png")
        else:
            print(f"  ✗ Measurement did not complete successfully: {status_data.get('status')}")
            if status_data.get("error"):
                print(f"    Error: {status_data['error']}")
    finally:
        print("\n[2.5] Disabling servo(s)...")
        await client.post("/servo/batch/off", json={"axis_ids": AXES_LIST})
        print("  ✓ Servo(s) disabled")

    print()
    print("=" * 70)
    print("Test 2 completed!")
    print()


async def test_profile_concurrent_rejection(client: httpx.AsyncClient) -> None:
    print("=" * 70)
    print("[TEST 3] Concurrent task rejection (single active task)")
    print("=" * 70)
    print()

    print("[3.1] Enabling servos for selected axis...")
    resp = await client.post("/servo/batch/on", json={"axis_ids": AXES_LIST})
    if resp.status_code == 200:
        print("  ✓ Servo(s) enabled")
    else:
        print(f"  ✗ Failed to enable servo(s): {resp.text}")
        return

    try:
        print("\n[3.2] Starting first async profile measurement...")
        t1 = await start_profile_measurement_async(client, SCAN_AXIS)
        if not t1:
            return

        print("\n[3.3] Trying to start second task (should 409)...")
        payload = {"scan_axis": SCAN_AXIS}
        r = await client.post("/profile/measure/execute", json=payload)
        if r.status_code == 409:
            print("  ✓ Correctly rejected with 409 Conflict")
            print(f"    Message: {r.json().get('detail')}")
        else:
            print(f"  ⚠ Unexpected status: {r.status_code}")

        print("\n[3.4] Cancelling first task...")
        await cancel_profile_task(client, t1)
        await asyncio.sleep(0.5)
        print("  ✓ First task cancelled")
    finally:
        print("\n[3.5] Disabling servo(s)...")
        await client.post("/servo/batch/off", json={"axis_ids": AXES_LIST})
        print("  ✓ Servo(s) disabled")

    print()
    print("=" * 70)
    print("Test 3 completed!")
    print()


async def main() -> None:
    print("=" * 70)
    print("REST API Profile Measurement Tests - Async Task Pattern")
    print("=" * 70)
    print(f"\nScan axis: {SCAN_AXIS}")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180.0) as client:
        # Test 1
        user_input = input("Run TEST 1: Profile cancellation? (yes/no): ")
        if user_input.lower() == "yes":
            await test_profile_cancellation(client)
        else:
            print("Skipping Test 1\n")

        # Test 2
        user_input = input("Run TEST 2: Profile completion + plot? (yes/no): ")
        if user_input.lower() == "yes":
            await test_profile_completion_and_plot(client)
        else:
            print("Skipping Test 2\n")

        # Test 3
        user_input = input("Run TEST 3: Concurrent task rejection? (yes/no): ")
        if user_input.lower() == "yes":
            await test_profile_concurrent_rejection(client)
        else:
            print("Skipping Test 3\n")

        print("=" * 70)
        print("All selected tests completed!")
        print("=" * 70)


if __name__ == "__main__":
    print()
    print("Make sure FastAPI server is running:")
    print("  fastapi dev app/main.py")
    print()
    input("Press Enter to continue...")
    print()
    asyncio.run(main())
