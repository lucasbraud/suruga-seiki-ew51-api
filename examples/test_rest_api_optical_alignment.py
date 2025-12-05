"""
Test REST API flat optical alignment with async task management.

This example demonstrates flat (2D) optical alignment optimization:
1. Sequential alignment: Right stage first, then Left stage
2. Full flat alignment with power meter readings
3. Cancellation test

Uses async task-based pattern with task tracking:
- POST /alignment/flat/execute (202 Accepted)
- GET /alignment/status/{task_id}
- POST /alignment/stop/{task_id}

Requirements:
    - FastAPI server running: fastapi dev app/main.py
    - httpx installed: pip install httpx
    - matplotlib installed: pip install matplotlib

Usage:
    python examples/test_rest_api_optical_alignment.py
"""

import asyncio
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path

import httpx
import numpy as np
import matplotlib.pyplot as plt

BASE_URL = "http://localhost:8003"

# All 12 axes for servo control
# NOTE: Power meter only works correctly when ALL servos are enabled
ALL_AXES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

# Stage configurations
RIGHT_STAGE = {
    "name": "RIGHT",
    "x_axis": 7,  # X2
    "y_axis": 8,  # Y2
    "axes": [7, 8]
}

LEFT_STAGE = {
    "name": "LEFT",
    "x_axis": 1,  # X1
    "y_axis": 2,  # Y1
    "axes": [1, 2]
}


async def set_servo_batch(client: httpx.AsyncClient, axes: list, state: bool) -> bool:
    """Turn servos on or off for specified axes."""
    action = "on" if state else "off"
    print(f"{'Enabling' if state else 'Disabling'} servos for axes {axes}...")
    resp = await client.post(f"/servo/batch/{action}", json={"axis_ids": axes})
    if resp.status_code == 200:
        print(f"  ✓ Servos {'ON' if state else 'OFF'}")
        return True
    print(f"  ✗ Servo {action} failed: {resp.status_code} {resp.text}")
    return False


async def get_power_reading(client: httpx.AsyncClient, pm_ch: int = 1) -> Optional[float]:
    """Get current power reading from power meter."""
    try:
        resp = await client.get(f"/power/reading", params={"channel": pm_ch})
        if resp.status_code == 200:
            data = resp.json()
            power_dbm = data.get("power_dbm")
            return power_dbm
        else:
            print(f"  ⚠ Power reading failed: {resp.status_code}")
            return None
    except Exception as e:
        print(f"  ⚠ Power reading error: {e}")
        return None


async def enable_servos_and_check_power(client: httpx.AsyncClient, pm_ch: int = 1) -> bool:
    """Enable all servos, wait for stabilization, and display power reading."""
    if not await set_servo_batch(client, ALL_AXES, True):
        return False

    # Wait for power to stabilize
    print(f"  Waiting 0.5s for power to stabilize...")
    await asyncio.sleep(0.5)

    # Read and display power
    power = await get_power_reading(client, pm_ch)
    if power is not None:
        status = "✓ OK" if power > -50.0 else "⚠ LOW"
        print(f"  Power reading: {power:.2f} dBm [{status}]")
    else:
        print(f"  ⚠ Could not read power")

    return True


async def start_flat_alignment_async(
    client: httpx.AsyncClient,
    stage_config: Dict[str, Any],
    pm_ch: int = 1,
    wavelength: int = 1310,
    # Search parameters with defaults from FlatAlignmentRequest
    search_range_x: float = 15.0,
    search_range_y: float = 10.0,
    peak_search_threshold: float = 10.0,
    field_search_speed_x: float = 100.0,
    field_search_speed_y: float = 100.0,
    peak_search_speed_x: float = 10.0,
    peak_search_speed_y: float = 10.0,
    smoothing_range_x: int = 40,
    smoothing_range_y: int = 40
) -> Optional[str]:
    """Start async flat alignment task; return task_id if accepted."""
    payload = {
        "mainStageNumberX": stage_config["x_axis"],
        "mainStageNumberY": stage_config["y_axis"],
        "pmCh": pm_ch,
        "wavelength": wavelength,
        # Include search parameters
        "searchRangeX": search_range_x,
        "searchRangeY": search_range_y,
        "peakSearchThreshold": peak_search_threshold,
        "fieldSearchSpeedX": field_search_speed_x,
        "fieldSearchSpeedY": field_search_speed_y,
        "peakSearchSpeedX": peak_search_speed_x,
        "peakSearchSpeedY": peak_search_speed_y,
        "smoothingRangeX": smoothing_range_x,
        "smoothingRangeY": smoothing_range_y
    }
    print(f"\n  Starting flat (2D) optical alignment for {stage_config['name']} stage...")
    print(f"    Stage: X={stage_config['x_axis']}, Y={stage_config['y_axis']}")
    print(f"    Power meter: CH={pm_ch}, Wavelength={wavelength}nm")
    print(f"    Search range: X={search_range_x}µm, Y={search_range_y}µm")
    print(f"    Field search speed: X={field_search_speed_x}µm/s, Y={field_search_speed_y}µm/s")
    print(f"    Peak search speed: X={peak_search_speed_x}µm/s, Y={peak_search_speed_y}µm/s")
    print(f"    Peak threshold: {peak_search_threshold}%")
    print(f"    Smoothing range: X={smoothing_range_x}, Y={smoothing_range_y} samples")
    resp = await client.post("/alignment/flat/execute", json=payload)
    if resp.status_code == 202:
        data = resp.json()
        task_id = data["task_id"]
        print(f"  ✓ Task created: {task_id}")
        return task_id
    elif resp.status_code == 409:
        print(f"  ✗ Concurrent task running: {resp.json().get('detail')}")
    else:
        print(f"  ✗ Request failed: {resp.status_code} {resp.text}")
    return None


async def poll_alignment_status(
    client: httpx.AsyncClient,
    task_id: str,
    *,
    poll_seconds: float = 0.5,
    max_polls: int = 240
) -> Dict[str, Any]:
    """Poll flat alignment task until terminal status or timeout."""
    print(f"  Polling status (max {max_polls} polls @ {poll_seconds}s)...")
    for i in range(max_polls):
        await asyncio.sleep(poll_seconds)
        r = await client.get(f"/alignment/status/{task_id}")
        data = r.json()
        status = data.get("status")
        progress = data.get("progress", {})
        msg = progress.get("message", "")
        phase = progress.get("phase", "")

        # Print every 5th poll to reduce noise
        if (i + 1) % 5 == 0 or status in ["completed", "failed", "cancelled"]:
            print(f"    Poll #{i+1}: {status}{' - ' + phase if phase else ''}{' | ' + msg if msg else ''}")

        if status in ["completed", "failed", "cancelled"]:
            return data

    print(f"  ⚠ Timeout after {max_polls} polls")
    return data


async def cancel_alignment_task(client: httpx.AsyncClient, task_id: str, controller_dep=None) -> None:
    """Cancel a running flat alignment task."""
    resp = await client.post(f"/alignment/stop/{task_id}")
    if resp.status_code == 200:
        print("  ✓ Cancellation requested")
    else:
        print(f"  ✗ Cancel request failed: {resp.status_code} {resp.text}")



async def test_flat_alignment_basic(client: httpx.AsyncClient, stage_config: Dict[str, Any]) -> None:
    """Test: Basic flat alignment execution and completion for a single stage."""
    print("=" * 70)
    print(f"[TEST] Basic Flat Alignment - {stage_config['name']} Stage")
    print("=" * 70)
    print()

    print(f"[1] Enabling ALL 12 servos and checking power...")
    if not await enable_servos_and_check_power(client, pm_ch=1):
        return

    try:
        print(f"\n[2] Starting async flat (2D) alignment...")
        task_id = await start_flat_alignment_async(client, stage_config, pm_ch=1, wavelength=1310.0)
        if not task_id:
            return

        print("\n[3] Polling for completion...")
        status_data = await poll_alignment_status(client, task_id)

        if status_data.get("status") == "completed":
            print("\n[4] ✓ Alignment completed successfully!")
            result = status_data.get("result", {})
            print(f"  Result data: {result}")
        else:
            print(f"  ✗ Alignment did not complete: {status_data.get('status')}")
            if status_data.get("error"):
                print(f"    Error: {status_data['error']}")
    finally:
        print(f"\n[5] Disabling all servos...")
        await set_servo_batch(client, ALL_AXES, False)

    print()
    print("=" * 70)
    print(f"{stage_config['name']} Stage Alignment Test completed!")
    print("=" * 70)
    print()


async def test_sequential_alignment_both_stages(client: httpx.AsyncClient) -> None:
    """Test: Sequential alignment - Right stage first, then Left stage."""
    print("=" * 70)
    print("[TEST] Sequential Alignment - Right Stage → Left Stage")
    print("=" * 70)
    print()

    print(f"[1] Enabling ALL 12 servos and checking power...")
    if not await enable_servos_and_check_power(client, pm_ch=1):
        return

    try:
        # RIGHT STAGE ALIGNMENT
        print("\n" + "=" * 70)
        print("STEP 1: RIGHT STAGE ALIGNMENT")
        print("=" * 70)

        print(f"\n[1.1] Starting RIGHT stage alignment...")
        right_task_id = await start_flat_alignment_async(client, RIGHT_STAGE, pm_ch=1, wavelength=1310.0)
        if not right_task_id:
            return

        print("\n[1.2] Polling RIGHT stage alignment...")
        right_status = await poll_alignment_status(client, right_task_id)

        if right_status.get("status") == "completed":
            print("\n[1.3] ✓ RIGHT stage alignment completed successfully!")
            result = right_status.get("result", {})
            print(f"  Result data: {result}")
        else:
            print(f"  ✗ RIGHT stage alignment failed: {right_status.get('status')}")
            if right_status.get("error"):
                print(f"    Error: {right_status['error']}")
            return  # Don't continue to left stage if right failed

        # LEFT STAGE ALIGNMENT
        print("\n" + "=" * 70)
        print("STEP 2: LEFT STAGE ALIGNMENT")
        print("=" * 70)

        print(f"\n[2.1] Starting LEFT stage alignment...")
        left_task_id = await start_flat_alignment_async(client, LEFT_STAGE, pm_ch=1, wavelength=1310.0)
        if not left_task_id:
            return

        print("\n[2.2] Polling LEFT stage alignment...")
        left_status = await poll_alignment_status(client, left_task_id)

        if left_status.get("status") == "completed":
            print("\n[2.3] ✓ LEFT stage alignment completed successfully!")
            result = left_status.get("result", {})
            print(f"  Result data: {result}")
        else:
            print(f"  ✗ LEFT stage alignment failed: {left_status.get('status')}")
            if left_status.get("error"):
                print(f"    Error: {left_status['error']}")

    finally:
        print(f"\n[3] Disabling all servos...")
        await set_servo_batch(client, ALL_AXES, False)

    print()
    print("=" * 70)
    print("Sequential Alignment Test completed!")
    print("=" * 70)
    print()


async def test_flat_alignment_with_power_meter(client: httpx.AsyncClient, stage_config: Dict[str, Any]) -> None:
    """Test: Flat alignment with custom wavelength (1310 nm instead of default 1550 nm)."""
    print("=" * 70)
    print(f"[TEST] Flat Alignment with Custom Wavelength - {stage_config['name']} Stage")
    print("=" * 70)
    print()

    print(f"[1] Enabling ALL 12 servos and checking power...")
    if not await enable_servos_and_check_power(client, pm_ch=1):
        return

    try:
        print(f"\n[2] Starting flat alignment with custom wavelength...")
        print(f"  Power meter channel: 1")
        print(f"  Wavelength: 1310.0 nm")
        task_id = await start_flat_alignment_async(client, stage_config, pm_ch=1, wavelength=1310.0)
        if not task_id:
            return

        print("\n[3] Polling for completion...")
        status_data = await poll_alignment_status(client, task_id)

        if status_data.get("status") == "completed":
            print("\n[4] ✓ Alignment completed successfully!")
            result = status_data.get("result", {})
            progress = status_data.get("progress", {})

            print(f"  Final status: {status_data.get('status')}")
            if progress:
                print(f"  Progress info: {progress.get('message', 'N/A')}")
            if result:
                print(f"  Result data: {result}")
        else:
            print(f"  ✗ Alignment did not complete: {status_data.get('status')}")
            if status_data.get("error"):
                print(f"    Error: {status_data['error']}")
    finally:
        print(f"\n[5] Disabling all servos...")
        await set_servo_batch(client, ALL_AXES, False)

    print()
    print("=" * 70)
    print("Custom Wavelength Test completed!")
    print("=" * 70)
    print()


async def test_flat_alignment_cancellation(client: httpx.AsyncClient, stage_config: Dict[str, Any]) -> None:
    """Test: Flat alignment cancellation."""
    print("=" * 70)
    print(f"[TEST] Flat Alignment Cancellation Test - {stage_config['name']} Stage")
    print("=" * 70)
    print()

    print(f"[1] Enabling ALL 12 servos and checking power...")
    if not await enable_servos_and_check_power(client, pm_ch=1):
        return

    try:
        print(f"\n[2] Starting async flat alignment...")
        task_id = await start_flat_alignment_async(client, stage_config, pm_ch=1, wavelength=1310.0)
        if not task_id:
            return

        # Brief delay then cancel
        print("\n[3] Waiting 1.0s then cancelling...")
        await asyncio.sleep(1.0)
        await cancel_alignment_task(client, task_id)

        # Poll for terminal status
        print("\n[4] Polling for terminal status...")
        final_data = await poll_alignment_status(client, task_id, poll_seconds=0.3, max_polls=40)

        final_status = final_data.get("status")
        print(f"  Final status: {final_status}")

        if final_status == "cancelled":
            print("  ✓ Flat alignment successfully cancelled")
        else:
            print(f"  ⚠ Unexpected terminal status: {final_status}")

    finally:
        print(f"\n[5] Disabling all servos...")
        await set_servo_batch(client, ALL_AXES, False)

    print()
    print("=" * 70)
    print("Cancellation Test completed!")
    print("=" * 70)
    print()


async def main() -> None:
    print("=" * 70)
    print("REST API Optical Alignment Tests - Async Task Pattern")
    print("=" * 70)
    print()
    print("Stage Configurations:")
    print(f"  RIGHT Stage: X-Axis={RIGHT_STAGE['x_axis']}, Y-Axis={RIGHT_STAGE['y_axis']}")
    print(f"  LEFT Stage:  X-Axis={LEFT_STAGE['x_axis']}, Y-Axis={LEFT_STAGE['y_axis']}")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180.0) as client:
        # Test 1: Sequential alignment (RIGHT then LEFT)
        user_input = input("\nRun TEST 1: Sequential Alignment (RIGHT → LEFT)? (yes/no): ")
        if user_input.lower() == "yes":
            await test_sequential_alignment_both_stages(client)
        else:
            print("Skipping Test 1\n")

        # Test 2: Single stage alignment with custom wavelength
        user_input = input("Run TEST 2: Single stage with custom wavelength (1310 nm)? (yes/no): ")
        if user_input.lower() == "yes":
            stage_choice = input("  Which stage? (right/left): ").strip().lower()
            if stage_choice == "right":
                await test_flat_alignment_with_power_meter(client, RIGHT_STAGE)
            elif stage_choice == "left":
                await test_flat_alignment_with_power_meter(client, LEFT_STAGE)
            else:
                print("  Invalid choice, skipping test\n")
        else:
            print("Skipping Test 2\n")

        # Test 3: Basic single stage alignment
        user_input = input("Run TEST 3: Basic single stage alignment? (yes/no): ")
        if user_input.lower() == "yes":
            stage_choice = input("  Which stage? (right/left): ").strip().lower()
            if stage_choice == "right":
                await test_flat_alignment_basic(client, RIGHT_STAGE)
            elif stage_choice == "left":
                await test_flat_alignment_basic(client, LEFT_STAGE)
            else:
                print("  Invalid choice, skipping test\n")
        else:
            print("Skipping Test 3\n")

        # Test 4: Cancellation test
        user_input = input("Run TEST 4: Flat alignment cancellation? (yes/no): ")
        if user_input.lower() == "yes":
            stage_choice = input("  Which stage? (right/left): ").strip().lower()
            if stage_choice == "right":
                await test_flat_alignment_cancellation(client, RIGHT_STAGE)
            elif stage_choice == "left":
                await test_flat_alignment_cancellation(client, LEFT_STAGE)
            else:
                print("  Invalid choice, skipping test\n")
        else:
            print("Skipping Test 4\n")

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
