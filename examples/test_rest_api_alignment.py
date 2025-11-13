"""
Test REST API optical alignment endpoints with async task management.

This example demonstrates the full async REST API workflow for optical alignment:
1. POST /alignment/flat/execute or /alignment/focus/execute - Returns 202 + task_id
2. GET /alignment/status/{task_id} - Poll for progress
3. POST /alignment/stop/{task_id} - Cancel if needed
4. Verify task completion

Requirements:
    - FastAPI server running: fastapi dev app/main.py
    - httpx installed: pip install httpx

Usage:
    python examples/test_rest_api_alignment.py
"""

import asyncio
import httpx


BASE_URL = "http://localhost:8000"


async def main():
    """Main test function."""
    print("=" * 70)
    print("REST API Optical Alignment Test - Async Task Pattern")
    print("=" * 70)
    print()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180.0) as client:  # 3 min timeout

        # ========== TEST 1: Flat Alignment with Cancellation ==========
        print("[TEST 1] Flat alignment with early cancellation")
        print("-" * 70)

        # Start flat alignment
        print("\n[1] Starting flat (2D) alignment...")
        response = await client.post(
            "/alignment/flat/execute",
            json={
                "mainStageNumberX": 1,
                "mainStageNumberY": 2,
                "subStageNumberXY": 3,
                "subAngleX": 0.0,
                "subAngleY": 0.0,
                "pmCh": 1,
                "analogCh": 0,
                "wavelength": 1550,
                "pmAutoRangeUpOn": True,
                "pmInitRangeSettingOn": False,
                "pmInitRange": -10,
                "fieldSearchThreshold": 0.3,
                "peakSearchThreshold": 0.7,
                "searchRangeX": 100.0,
                "searchRangeY": 100.0,
                "fieldSearchPitchX": 10.0,
                "fieldSearchPitchY": 10.0,
                "fieldSearchFirstPitchX": 20.0,
                "fieldSearchSpeedX": 100.0,
                "fieldSearchSpeedY": 100.0,
                "peakSearchSpeedX": 50.0,
                "peakSearchSpeedY": 50.0,
                "smoothingRangeX": 5.0,
                "smoothingRangeY": 5.0,
                "centroidThresholdX": 0.9,
                "centroidThresholdY": 0.9,
                "convergentRangeX": 2.0,
                "convergentRangeY": 2.0,
                "comparisonCount": 3,
                "maxRepeatCount": 5
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

        # Wait for it to start
        print("\n[2] Waiting 3 seconds for alignment to start...")
        await asyncio.sleep(3.0)

        # Check status
        print(f"\n[3] Checking task status...")
        status_response = await client.get(f"/alignment/status/{task_id}")
        status_data = status_response.json()

        print(f"  Task ID: {status_data['task_id']}")
        print(f"  Status: {status_data['status']}")
        if status_data.get('progress'):
            print(f"  Progress: {status_data['progress']}")

        # Cancel the alignment
        print(f"\n[4] Cancelling alignment...")
        cancel_response = await client.post(f"/alignment/stop/{task_id}")
        cancel_data = cancel_response.json()

        print(f"  Success: {cancel_data['success']}")
        print(f"  Message: {cancel_data['message']}")

        # Wait for cancellation to take effect
        await asyncio.sleep(2.0)

        # Check final status
        print(f"\n[5] Checking final status...")
        final_status = await client.get(f"/alignment/status/{task_id}")
        final_data = final_status.json()

        print(f"  Status: {final_data['status']}")
        if final_data.get('error'):
            print(f"  Error: {final_data['error']}")

        if final_data['status'] == 'cancelled':
            print("  ✓ Alignment successfully cancelled!")
        else:
            print(f"  ⚠ Unexpected status: {final_data['status']}")

        print()
        print("=" * 70)

        # ========== TEST 2: Focus Alignment to Completion ==========
        print("[TEST 2] Focus (3D) alignment - CAUTION: Full run")
        print("-" * 70)
        print("\n⚠ WARNING: This test will run a FULL focus alignment sequence.")
        print("   This can take 1-3 minutes and will move X, Y, and Z axes.")
        print("   Make sure the stage is ready and there's adequate clearance.")
        print()

        # Ask user if they want to continue
        user_input = input("Do you want to run the full focus alignment test? (yes/no): ")
        if user_input.lower() != "yes":
            print("  Skipping full alignment test.")
            print()
            print("=" * 70)
            print("Test 1 completed!")
            print()
            return

        # Start focus alignment
        print(f"\n[1] Starting full focus (3D) alignment (zMode=Linear)...")
        response = await client.post(
            "/alignment/focus/execute",
            json={
                "zMode": "Linear",
                "mainStageNumberX": 1,
                "mainStageNumberY": 2,
                "subStageNumberXY": 3,
                "subAngleX": 0.0,
                "subAngleY": 0.0,
                "pmCh": 1,
                "analogCh": 0,
                "wavelength": 1550,
                "pmAutoRangeUpOn": True,
                "pmInitRangeSettingOn": False,
                "pmInitRange": -10,
                "fieldSearchThreshold": 0.3,
                "peakSearchThreshold": 0.7,
                "searchRangeX": 100.0,
                "searchRangeY": 100.0,
                "fieldSearchPitchX": 10.0,
                "fieldSearchPitchY": 10.0,
                "fieldSearchFirstPitchX": 20.0,
                "fieldSearchSpeedX": 100.0,
                "fieldSearchSpeedY": 100.0,
                "peakSearchSpeedX": 50.0,
                "peakSearchSpeedY": 50.0,
                "smoothingRangeX": 5.0,
                "smoothingRangeY": 5.0,
                "centroidThresholdX": 0.9,
                "centroidThresholdY": 0.9,
                "convergentRangeX": 2.0,
                "convergentRangeY": 2.0,
                "comparisonCount": 3,
                "maxRepeatCount": 5
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
        print(f"\n[2] Polling for completion (may take 1-3 minutes)...")
        completed = False
        poll_count = 0

        while not completed and poll_count < 360:  # Max 360 polls (3 minutes)
            await asyncio.sleep(0.5)  # Poll every 500ms
            poll_count += 1

            status_response = await client.get(f"/alignment/status/{task_id}")
            status_data = status_response.json()

            status = status_data['status']
            progress = status_data.get('progress', {})

            # Show progress
            if progress:
                phase = progress.get('phase', '?')
                phase_desc = progress.get('phase_description', '')
                elapsed = progress.get('elapsed_time', 0)
                print(f"  Poll #{poll_count}: Status={status}, Phase={phase}, Elapsed={elapsed:.1f}s")
                if phase_desc:
                    print(f"    {phase_desc}")
            else:
                print(f"  Poll #{poll_count}: Status={status}")

            if status in ['completed', 'failed', 'cancelled']:
                completed = True

        # Check final result
        print(f"\n[3] Final result:")
        if status_data['status'] == 'completed':
            result = status_data.get('result', {})
            print(f"  ✓ Focus alignment completed successfully!")
            print(f"    Initial power: {result.get('initial_power', '?'):.3f} dBm")
            print(f"    Final power: {result.get('final_power', '?'):.3f} dBm")
            print(f"    Power improvement: {result.get('power_improvement', '?'):+.3f} dB")
            print(f"    Peak X: {result.get('peak_position_x', '?'):.2f} um")
            print(f"    Peak Y: {result.get('peak_position_y', '?'):.2f} um")
            print(f"    Peak Z: {result.get('peak_position_z', '?'):.2f} um")
            print(f"    Execution time: {result.get('execution_time', '?'):.2f}s")
        else:
            print(f"  ✗ Alignment {status_data['status']}")
            if status_data.get('error'):
                print(f"    Error: {status_data['error']}")

        print()
        print("=" * 70)

        # ========== TEST 3: Concurrent Task Rejection ==========
        print("[TEST 3] Concurrent task rejection (only one at a time)")
        print("-" * 70)

        # Start first alignment
        print("\n[1] Starting first alignment...")
        response1 = await client.post(
            "/alignment/flat/execute",
            json={
                "mainStageNumberX": 1,
                "mainStageNumberY": 2,
                "subStageNumberXY": 3,
                "subAngleX": 0.0,
                "subAngleY": 0.0,
                "pmCh": 1,
                "analogCh": 0,
                "wavelength": 1550,
                "pmAutoRangeUpOn": True,
                "pmInitRangeSettingOn": False,
                "pmInitRange": -10,
                "fieldSearchThreshold": 0.3,
                "peakSearchThreshold": 0.7,
                "searchRangeX": 100.0,
                "searchRangeY": 100.0,
                "fieldSearchPitchX": 10.0,
                "fieldSearchPitchY": 10.0,
                "fieldSearchFirstPitchX": 20.0,
                "fieldSearchSpeedX": 100.0,
                "fieldSearchSpeedY": 100.0,
                "peakSearchSpeedX": 50.0,
                "peakSearchSpeedY": 50.0,
                "smoothingRangeX": 5.0,
                "smoothingRangeY": 5.0,
                "centroidThresholdX": 0.9,
                "centroidThresholdY": 0.9,
                "convergentRangeX": 2.0,
                "convergentRangeY": 2.0,
                "comparisonCount": 3,
                "maxRepeatCount": 5
            }
        )

        if response1.status_code == 202:
            task1_id = response1.json()["task_id"]
            print(f"  ✓ First task created: {task1_id}")
        else:
            print(f"  ✗ Failed: {response1.json()}")
            return

        # Try to start second alignment immediately
        print("\n[2] Trying to start second alignment (should fail)...")
        response2 = await client.post(
            "/alignment/focus/execute",
            json={
                "zMode": "Linear",
                "mainStageNumberX": 1,
                "mainStageNumberY": 2,
                "subStageNumberXY": 3,
                "subAngleX": 0.0,
                "subAngleY": 0.0,
                "pmCh": 1,
                "analogCh": 0,
                "wavelength": 1550,
                "pmAutoRangeUpOn": True,
                "pmInitRangeSettingOn": False,
                "pmInitRange": -10,
                "fieldSearchThreshold": 0.3,
                "peakSearchThreshold": 0.7,
                "searchRangeX": 100.0,
                "searchRangeY": 100.0,
                "fieldSearchPitchX": 10.0,
                "fieldSearchPitchY": 10.0,
                "fieldSearchFirstPitchX": 20.0,
                "fieldSearchSpeedX": 100.0,
                "fieldSearchSpeedY": 100.0,
                "peakSearchSpeedX": 50.0,
                "peakSearchSpeedY": 50.0,
                "smoothingRangeX": 5.0,
                "smoothingRangeY": 5.0,
                "centroidThresholdX": 0.9,
                "centroidThresholdY": 0.9,
                "convergentRangeX": 2.0,
                "convergentRangeY": 2.0,
                "comparisonCount": 3,
                "maxRepeatCount": 5
            }
        )

        if response2.status_code == 409:
            print(f"  ✓ Correctly rejected with 409 Conflict")
            print(f"    Message: {response2.json()['detail']}")
        else:
            print(f"  ⚠ Unexpected status: {response2.status_code}")

        # Cancel first task
        print(f"\n[3] Cancelling first task...")
        await client.post(f"/alignment/stop/{task1_id}")
        await asyncio.sleep(1.0)
        print("  ✓ First task cancelled")

        print()
        print("=" * 70)
        print("All tests completed!")
        print()


if __name__ == "__main__":
    print()
    print("Make sure FastAPI server is running:")
    print("  fastapi dev app/main.py")
    print()
    input("Press Enter to continue...")
    print()

    asyncio.run(main())
