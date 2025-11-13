"""
Test REST API motion endpoints with async task management.

This example demonstrates the full async REST API workflow:
1. POST /move/relative - Returns 202 + task_id
2. GET /move/status/{task_id} - Poll for progress
3. POST /move/stop/{task_id} - Cancel if needed
4. Verify task completion

Requirements:
    - FastAPI server running: fastapi dev app/main.py
    - httpx installed: pip install httpx

Usage:
    python examples/test_rest_api_motion.py
"""

import asyncio
import httpx
import time
from typing import Optional


BASE_URL = "http://localhost:8000"


async def main():
    """Main test function."""
    print("=" * 70)
    print("REST API Motion Control Test - Async Task Pattern")
    print("=" * 70)
    print()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:

        # ========== SETUP: Enable Servo ==========
        print("[SETUP] Enabling servo on axis 1 (X1)...")
        servo_response = await client.post(
            "/servo/on",
            json={"axis_id": 1}
        )

        if servo_response.status_code == 200:
            print(f"  ✓ Servo enabled on axis 1")
        else:
            print(f"  ✗ Failed to enable servo: {servo_response.json()}")
            return

        # Wait for servo to stabilize
        await asyncio.sleep(0.5)
        print()

        try:
            # ========== TEST 1: Relative Movement with Cancellation ==========
            print("[TEST 1] Relative movement with cancellation")
            print("-" * 70)

            # Start relative movement
            print("\n[1] Starting relative movement: +100 um on axis 1...")
            response = await client.post(
                "/move/relative",
                json={
                    "axis_id": 1,
                    "distance": 100.0,
                    "speed": 50.0  # Slow speed to allow cancellation
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
                return

            # Wait a bit
            print("\n[2] Waiting 0.5 seconds...")
            await asyncio.sleep(0.5)

            # Check status
            print(f"\n[3] Checking task status...")
            status_response = await client.get(f"/move/status/{task_id}")
            status_data = status_response.json()

            print(f"  Task ID: {status_data['task_id']}")
            print(f"  Status: {status_data['status']}")
            print(f"  Progress: {status_data.get('progress', {})}")

            # Cancel the movement
            print(f"\n[4] Cancelling movement...")
            cancel_response = await client.post(f"/move/stop/{task_id}")
            cancel_data = cancel_response.json()

            print(f"  Success: {cancel_data['success']}")
            print(f"  Message: {cancel_data['message']}")

            # Wait for cancellation to take effect
            await asyncio.sleep(1.0)

            # Check final status
            print(f"\n[5] Checking final status...")
            final_status = await client.get(f"/move/status/{task_id}")
            final_data = final_status.json()

            print(f"  Status: {final_data['status']}")
            if final_data.get('error'):
                print(f"  Error: {final_data['error']}")

            if final_data['status'] == 'cancelled':
                print("  ✓ Movement successfully cancelled!")
            else:
                print(f"  ⚠ Unexpected status: {final_data['status']}")

            print()
            print("=" * 70)

            # ========== TEST 2: Absolute Movement to Completion ==========
            print("[TEST 2] Absolute movement to completion")
            print("-" * 70)

            # Get current position first
            print("\n[1] Getting current position...")
            pos_response = await client.get("/position/1")
            current_pos = pos_response.json()["actual_position"]
            print(f"  Current position: {current_pos:.2f} um")

            # Calculate target (move back 50um from current)
            target_pos = current_pos - 50.0
            print(f"  Target position: {target_pos:.2f} um")

            # Start absolute movement
            print(f"\n[2] Starting absolute movement to {target_pos:.2f} um...")
            response = await client.post(
                "/move/absolute",
                json={
                    "axis_id": 1,
                    "position": target_pos,
                    "speed": 100.0
                }
            )

            if response.status_code == 202:
                data = response.json()
                task_id = data["task_id"]
                print(f"  ✓ Task created: {task_id}")
            else:
                print(f"  ✗ Failed: {response.json()}")
                return

            # Poll for completion
            print(f"\n[3] Polling for completion...")
            completed = False
            poll_count = 0

            while not completed and poll_count < 30:  # Max 30 polls
                await asyncio.sleep(0.3)  # Poll every 300ms
                poll_count += 1

                status_response = await client.get(f"/move/status/{task_id}")
                status_data = status_response.json()

                status = status_data['status']
                progress = status_data.get('progress', {})

                # Show progress
                if 'current_position' in progress:
                    print(f"  Poll #{poll_count}: Status={status}, "
                          f"Progress={progress.get('progress_percent', '?')}%, "
                          f"Position={progress.get('current_position', '?'):.2f} um")
                else:
                    print(f"  Poll #{poll_count}: Status={status}")

                if status in ['completed', 'failed', 'cancelled']:
                    completed = True

            # Check final result
            print(f"\n[4] Final result:")
            if status_data['status'] == 'completed':
                result = status_data.get('result', {})
                print(f"  ✓ Movement completed successfully!")
                print(f"    Target: {result.get('target_position', '?'):.2f} um")
                print(f"    Final: {result.get('final_position', '?'):.2f} um")
                print(f"    Execution time: {result.get('execution_time', '?'):.2f}s")
            else:
                print(f"  ✗ Movement {status_data['status']}")
                if status_data.get('error'):
                    print(f"    Error: {status_data['error']}")

            print()
            print("=" * 70)

            # ========== TEST 3: Concurrent Task Rejection ==========
            print("[TEST 3] Concurrent task rejection (only one at a time)")
            print("-" * 70)

            # Start first movement
            print("\n[1] Starting first movement...")
            response1 = await client.post(
                "/move/relative",
                json={"axis_id": 1, "distance": 50.0, "speed": 50.0}
            )

            if response1.status_code == 202:
                task1_id = response1.json()["task_id"]
                print(f"  ✓ First task created: {task1_id}")
            else:
                print(f"  ✗ Failed: {response1.json()}")
                return

            # Try to start second movement immediately
            print("\n[2] Trying to start second movement (should fail)...")
            response2 = await client.post(
                "/move/relative",
                json={"axis_id": 1, "distance": 30.0, "speed": 50.0}
            )

            if response2.status_code == 409:
                print(f"  ✓ Correctly rejected with 409 Conflict")
                print(f"    Message: {response2.json()['detail']}")
            else:
                print(f"  ⚠ Unexpected status: {response2.status_code}")

            # Cancel first task
            print(f"\n[3] Cancelling first task...")
            await client.post(f"/move/stop/{task1_id}")
            await asyncio.sleep(0.5)
            print("  ✓ First task cancelled")

            # Now second movement should work
            print("\n[4] Trying second movement again (should work)...")
            response3 = await client.post(
                "/move/relative",
                json={"axis_id": 1, "distance": 30.0, "speed": 100.0}
            )

            if response3.status_code == 202:
                task3_id = response3.json()["task_id"]
                print(f"  ✓ Second task created: {task3_id}")

                # Let it complete
                await asyncio.sleep(0.5)
                await client.post(f"/move/stop/{task3_id}")
            else:
                print(f"  ✗ Failed: {response3.json()}")

            print()
            print("=" * 70)
            print("All tests completed!")
            print()

        finally:
            # ========== CLEANUP: Disable Servo ==========
            print()
            print("[CLEANUP] Disabling servo on axis 1...")
            servo_response = await client.post(
                "/servo/off",
                json={"axis_id": 1}
            )

            if servo_response.status_code == 200:
                print(f"  ✓ Servo disabled on axis 1")
            else:
                print(f"  ⚠ Failed to disable servo: {servo_response.json()}")

            print()


if __name__ == "__main__":
    print()
    print("Make sure FastAPI server is running:")
    print("  fastapi dev app/main.py")
    print()
    input("Press Enter to continue...")
    print()

    asyncio.run(main())
