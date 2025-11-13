"""
Test REST API angle adjustment endpoints with async task management.

This example demonstrates the full async REST API workflow for angle adjustment:
1. POST /angle-adjustment/execute - Returns 202 + task_id
2. GET /angle-adjustment/status/{task_id} - Poll for progress
3. POST /angle-adjustment/stop/{task_id} - Cancel if needed
4. Verify task completion

Requirements:
    - FastAPI server running: fastapi dev app/main.py
    - httpx installed: pip install httpx

Usage:
    python examples/test_rest_api_angle_adjustment.py
"""

import asyncio
import httpx
import time
from typing import Optional


BASE_URL = "http://localhost:8000"

# Stage configuration
LEFT_STAGE_Z = 3    # Z1 axis
RIGHT_STAGE_Z = 9   # Z2 axis
ALL_AXES = list(range(1, 13))  # Axes 1-12
Z_MOVE_DISTANCE = -100.0  # Move Z axis -100 µm before angle adjustment


async def test_angle_adjustment_with_cancellation(client: httpx.AsyncClient):
    """Test 1: Angle adjustment with cancellation."""
    print("=" * 70)
    print("[TEST 1] Angle adjustment with cancellation")
    print("=" * 70)
    print()

    # Enable servos for all axes
    print("[1.1] Enabling servos for all 12 axes...")
    servo_response = await client.post("/servo/batch/on", json={"axis_ids": ALL_AXES})
    if servo_response.status_code == 200:
        print("  ✓ All servos enabled")
    else:
        print(f"  ✗ Failed to enable servos: {servo_response.json()}")
        return

    # Move Z-axis -100 µm before adjustment
    print(f"\n[1.2] Moving Z-axis (LEFT={LEFT_STAGE_Z}) relative {Z_MOVE_DISTANCE:+.1f} µm...")
    move_response = await client.post(
        "/move/relative",
        json={
            "axis_id": LEFT_STAGE_Z,
            "distance": Z_MOVE_DISTANCE,
            "speed": 100.0
        }
    )
    if move_response.status_code == 202:
        move_task_id = move_response.json()["task_id"]
        print(f"  Movement task created: {move_task_id}")
        # Poll for movement completion
        for _ in range(50):  # Max 25 seconds
            await asyncio.sleep(0.5)
            status_resp = await client.get(f"/move/status/{move_task_id}")
            status = status_resp.json()["status"]
            if status == "completed":
                print("  ✓ Z-axis movement complete")
                break
            elif status in ["failed", "cancelled"]:
                print(f"  ✗ Z-axis movement {status}")
                await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
                return
        else:
            print("  ✗ Z-axis movement timed out")
            await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
            return
    else:
        print(f"  ✗ Z-axis movement failed: {move_response.json()}")
        await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
        return

    # Check and unlock contact sensor
    print("\n[1.3] Checking contact sensor lock state (digital output 1)...")
    dout_check = await client.get("/io/digital/output/1")
    if dout_check.status_code == 200:
        is_locked = dout_check.json().get("value")
        print(f"  Contact sensor state: {'LOCKED' if is_locked else 'UNLOCKED'}")
        
        if is_locked:
            print("  Unlocking contact sensor...")
            unlock_response = await client.post(
                "/io/digital/output",
                json={"channel": 1, "value": False}
            )
            if unlock_response.status_code == 200:
                print("  ✓ Contact sensor unlocked")
            else:
                print(f"  ✗ Failed to unlock: {unlock_response.json()}")
                await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
                return
        else:
            print("  ✓ Contact sensor already unlocked")
    else:
        print(f"  ✗ Failed to check digital output: {dout_check.json()}")
        await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
        return

    # Start angle adjustment
    print("\n[1.4] Starting angle adjustment on LEFT stage...")
    response = await client.post(
        "/angle-adjustment/execute",
        json={
            "stage": 1,  # 1 = LEFT, 2 = RIGHT
            "gap": 4.0,
            "signal_lower_limit": 0.4,
        }
    )

    print(f"  Status: {response.status_code}")

    if response.status_code == 202:
        data = response.json()
        task_id = data["task_id"]
        print(f"  ✓ Task created: {task_id}")
        print(f"    Operation: {data['operation_type']}")
        print(f"    Status: {data['status']}")
        print(f"    Status URL: {data['status_url']}")
    else:
        print(f"  ✗ Failed: {response.json()}")
        await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
        return

    # Check status
    print(f"\n[1.5] Checking task status...")
    status_response = await client.get(f"/angle-adjustment/status/{task_id}")
    status_data = status_response.json()

    print(f"  Task ID: {status_data['task_id']}")
    print(f"  Status: {status_data['status']}")
    print(f"  Progress: {status_data.get('progress', {})}")

    # Cancel the adjustment
    print(f"\n[1.6] Cancelling angle adjustment...")
    cancel_response = await client.post(f"/angle-adjustment/stop/{task_id}")
    cancel_data = cancel_response.json()

    print(f"  Success: {cancel_data['success']}")
    print(f"  Message: {cancel_data['message']}")

    # Wait briefly for cancellation to take effect
    await asyncio.sleep(0.5)

    # Check final status
    print(f"\n[1.7] Checking final status...")
    final_status = await client.get(f"/angle-adjustment/status/{task_id}")
    final_data = final_status.json()

    print(f"  Status: {final_data['status']}")
    if final_data.get('error'):
        print(f"  Error: {final_data['error']}")

    if final_data['status'] == 'cancelled':
        print("  ✓ Angle adjustment successfully cancelled!")
    else:
        print(f"  ⚠ Unexpected status: {final_data['status']}")

    # Disable servos after test
    print("\n[1.8] Disabling all servos...")
    await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
    print("  ✓ All servos disabled")

    print()
    print("=" * 70)
    print("Test 1 completed!")
    print()


async def test_full_angle_adjustment(client: httpx.AsyncClient):
    """Test 2: Full angle adjustment to completion."""
    print("=" * 70)
    print("[TEST 2] Full angle adjustment to completion")
    print("=" * 70)
    print()
    print("⚠ WARNING: This test will run a full angle adjustment sequence.")
    print("   Make sure the stage is ready and there's adequate clearance.")
    print()

    # Enable servos for all axes
    print("[2.1] Enabling servos for all 12 axes...")
    servo_response = await client.post("/servo/batch/on", json={"axis_ids": ALL_AXES})
    if servo_response.status_code == 200:
        print("  ✓ All servos enabled")
    else:
        print(f"  ✗ Failed to enable servos: {servo_response.json()}")
        return

    # Move Z-axis -100 µm before adjustment
    print(f"\n[2.2] Moving Z-axis (LEFT={LEFT_STAGE_Z}) relative {Z_MOVE_DISTANCE:+.1f} µm...")
    move_response = await client.post(
        "/move/relative",
        json={
            "axis_id": LEFT_STAGE_Z,
            "distance": Z_MOVE_DISTANCE,
            "speed": 100.0
        }
    )
    if move_response.status_code == 202:
        move_task_id = move_response.json()["task_id"]
        print(f"  Movement task created: {move_task_id}")
        # Poll for movement completion
        for _ in range(50):  # Max 25 seconds
            await asyncio.sleep(0.5)
            status_resp = await client.get(f"/move/status/{move_task_id}")
            status = status_resp.json()["status"]
            if status == "completed":
                print("  ✓ Z-axis movement complete")
                break
            elif status in ["failed", "cancelled"]:
                print(f"  ✗ Z-axis movement {status}")
                await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
                return
        else:
            print("  ✗ Z-axis movement timed out")
            await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
            return
    else:
        print(f"  ✗ Z-axis movement failed: {move_response.json()}")
        await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
        return

    # Check and unlock contact sensor
    print("\n[2.3] Checking contact sensor lock state (digital output 1)...")
    dout_check = await client.get("/io/digital/output/1")
    if dout_check.status_code == 200:
        is_locked = dout_check.json().get("value")
        print(f"  Contact sensor state: {'LOCKED' if is_locked else 'UNLOCKED'}")
        
        if is_locked:
            print("  Unlocking contact sensor...")
            unlock_response = await client.post(
                "/io/digital/output",
                json={"channel": 1, "value": False}
            )
            if unlock_response.status_code == 200:
                print("  ✓ Contact sensor unlocked")
            else:
                print(f"  ✗ Failed to unlock: {unlock_response.json()}")
                await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
                return
        else:
            print("  ✓ Contact sensor already unlocked")
    else:
        print(f"  ✗ Failed to check digital output: {dout_check.json()}")
        await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
        return

    # Start angle adjustment
    print(f"\n[2.4] Starting full angle adjustment on LEFT stage...")
    response = await client.post(
        "/angle-adjustment/execute",
        json={
            "stage": 1,  # 1 = LEFT, 2 = RIGHT
            "gap": 4.0,
            "signal_lower_limit": 0.4,
        }
    )

    if response.status_code == 202:
        data = response.json()
        task_id = data["task_id"]
        print(f"  ✓ Task created: {task_id}")
    else:
        print(f"  ✗ Failed: {response.json()}")
        await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
        return

    # Poll for completion
    print(f"\n[2.5] Polling for completion (this may take 30-60 seconds)...")
    completed = False
    poll_count = 0

    while not completed and poll_count < 200:  # Max 200 polls (100 seconds)
        await asyncio.sleep(0.5)  # Poll every 500ms
        poll_count += 1

        status_response = await client.get(f"/angle-adjustment/status/{task_id}")
        status_data = status_response.json()

        status = status_data['status']
        progress = status_data.get('progress', {})

        # Show progress
        if progress:
            phase = progress.get('phase', '?')
            message = progress.get('message', '')
            print(f"  Poll #{poll_count}: Status={status}, Phase={phase}")
            if message:
                print(f"    {message}")
        else:
            print(f"  Poll #{poll_count}: Status={status}")

        if status in ['completed', 'failed', 'cancelled']:
            completed = True

    # Check final result
    print(f"\n[2.6] Final result:")
    if status_data['status'] == 'completed':
        result = status_data.get('result', {})
        print(f"  ✓ Angle adjustment completed successfully!")
        print(f"    Success: {result.get('success', '?')}")
        print(f"    Status: {result.get('status_description', '?')}")
        print(f"    Phase: {result.get('phase_description', '?')}")
        print(f"    Initial signal: {result.get('initial_signal', '?')}")
        print(f"    Final signal: {result.get('final_signal', '?')}")
        print(f"    Signal improvement: {result.get('signal_improvement', '?')}")
        print(f"    Execution time: {result.get('execution_time', '?'):.2f}s")
    else:
        print(f"  ✗ Angle adjustment {status_data['status']}")
        if status_data.get('error'):
            print(f"    Error: {status_data['error']}")

    # Disable servos after test
    print("\n[2.7] Disabling all servos...")
    await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
    print("  ✓ All servos disabled")

    print()
    print("=" * 70)
    print("Test 2 completed!")
    print()


async def test_concurrent_task_rejection(client: httpx.AsyncClient):
    """Test 3: Concurrent task rejection."""
    print("=" * 70)
    print("[TEST 3] Concurrent task rejection (only one at a time)")
    print("=" * 70)
    print()

    # Enable servos for all axes
    print("[3.1] Enabling servos for all 12 axes...")
    servo_response = await client.post("/servo/batch/on", json={"axis_ids": ALL_AXES})
    if servo_response.status_code == 200:
        print("  ✓ All servos enabled")
    else:
        print(f"  ✗ Failed to enable servos: {servo_response.json()}")
        return

    # Move Z-axis -100 µm before adjustment (for LEFT stage)
    print(f"\n[3.2] Moving Z-axis (LEFT={LEFT_STAGE_Z}) relative {Z_MOVE_DISTANCE:+.1f} µm...")
    move_response = await client.post(
        "/move/relative",
        json={
            "axis_id": LEFT_STAGE_Z,
            "distance": Z_MOVE_DISTANCE,
            "speed": 100.0
        }
    )
    if move_response.status_code == 202:
        move_task_id = move_response.json()["task_id"]
        print(f"  Movement task created: {move_task_id}")
        # Poll for movement completion
        for _ in range(50):  # Max 25 seconds
            await asyncio.sleep(0.5)
            status_resp = await client.get(f"/move/status/{move_task_id}")
            status = status_resp.json()["status"]
            if status == "completed":
                print("  ✓ Z-axis movement complete")
                break
            elif status in ["failed", "cancelled"]:
                print(f"  ✗ Z-axis movement {status}")
                await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
                return
        else:
            print("  ✗ Z-axis movement timed out")
            await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
            return
    else:
        print(f"  ✗ Z-axis movement failed: {move_response.json()}")
        await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
        return

    # Check and unlock contact sensor for LEFT
    print("\n[3.3] Unlocking LEFT contact sensor (digital output 1)...")
    dout_check = await client.get("/io/digital/output/1")
    if dout_check.status_code == 200:
        is_locked = dout_check.json().get("value")
        if is_locked:
            await client.post("/io/digital/output", json={"channel": 1, "value": False})
            print("  ✓ Contact sensor unlocked")
        else:
            print("  ✓ Contact sensor already unlocked")

    # Start first adjustment
    print("\n[3.4] Starting first angle adjustment...")
    response1 = await client.post(
        "/angle-adjustment/execute",
        json={"stage": 1, "gap": 4.0, "signal_lower_limit": 0.4}  # 1 = LEFT
    )

    if response1.status_code == 202:
        task1_id = response1.json()["task_id"]
        print(f"  ✓ First task created: {task1_id}")
    else:
        print(f"  ✗ Failed: {response1.json()}")
        await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
        return

    # Try to start second adjustment immediately
    print("\n[3.5] Trying to start second adjustment (should fail)...")
    response2 = await client.post(
        "/angle-adjustment/execute",
        json={"stage": 2, "gap": 4.0, "signal_lower_limit": 0.4}  # 2 = RIGHT
    )

    if response2.status_code == 409:
        print(f"  ✓ Correctly rejected with 409 Conflict")
        print(f"    Message: {response2.json()['detail']}")
    else:
        print(f"  ⚠ Unexpected status: {response2.status_code}")

    # Cancel first task
    print(f"\n[3.6] Cancelling first task...")
    await client.post(f"/angle-adjustment/stop/{task1_id}")
    await asyncio.sleep(1.0)
    print("  ✓ First task cancelled")

    # Disable servos after test
    print("\n[3.7] Disabling all servos...")
    await client.post("/servo/batch/off", json={"axis_ids": ALL_AXES})
    print("  ✓ All servos disabled")

    print()
    print("=" * 70)
    print("Test 3 completed!")
    print()


async def main():
    """Main test function - runs tests one by one with user prompts."""
    print("=" * 70)
    print("REST API Angle Adjustment Test - Async Task Pattern")
    print("=" * 70)
    print()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:

        # Test 1: Angle adjustment with cancellation
        user_input = input("Run TEST 1: Angle adjustment with cancellation? (yes/no): ")
        if user_input.lower() == "yes":
            await test_angle_adjustment_with_cancellation(client)
        else:
            print("Skipping Test 1\n")

        # Test 2: Full angle adjustment to completion
        user_input = input("Run TEST 2: Full angle adjustment to completion? (yes/no): ")
        if user_input.lower() == "yes":
            await test_full_angle_adjustment(client)
        else:
            print("Skipping Test 2\n")

        # Test 3: Concurrent task rejection
        user_input = input("Run TEST 3: Concurrent task rejection? (yes/no): ")
        if user_input.lower() == "yes":
            await test_concurrent_task_rejection(client)
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
