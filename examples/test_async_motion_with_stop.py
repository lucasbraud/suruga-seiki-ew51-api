"""
Test example demonstrating async motion with immediate cancellation.

This example shows how the new async architecture allows you to:
1. Enable servo on X1 axis
2. Start a long-running motion operation (X1 axis, 100um relative movement)
3. Immediately cancel it mid-flight
4. The cancellation is processed during the polling loop, stopping the axis
5. Disable servo on X1 axis

Usage:
    python examples/test_async_motion_with_stop.py

Requirements:
    - Controller must be connected to hardware
    - Make sure the 100um movement is safe for your setup
"""

import asyncio
import sys
import time
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.controller_manager import SurugaSeikiController
from app.task_manager import task_manager, OperationType
from app.tasks.motion_task import MotionTaskExecutor


async def main():
    """Main test function."""
    print("=" * 70)
    print("Async Motion with Immediate Stop - Test Example")
    print("=" * 70)
    print()

    # Initialize controller
    print("[1] Initializing controller...")
    controller = SurugaSeikiController()

    # Connect to hardware
    print("[2] Connecting to hardware...")
    success = controller.connect()

    if not success or not controller.is_connected():
        print("ERROR: Failed to connect to controller!")
        print("Make sure:")
        print("  - Hardware is powered on")
        print("  - ADS address is configured in .env or settings")
        print("  - Network connection is working")
        return

    print(f"SUCCESS: Connected to controller")
    print()

    # Check axis status
    axis_number = 1  # X1 axis
    print(f"[3] Checking axis {axis_number} (X1) status...")

    axis_status = controller.get_position(axis_number)
    if not axis_status:
        print(f"ERROR: Could not read axis {axis_number} status")
        controller.disconnect()
        return

    print(f"  Current position: {axis_status.actual_position:.2f} um")
    print(f"  Servo on: {axis_status.is_servo_on}")
    print(f"  Is moving: {axis_status.is_moving}")
    print(f"  Is error: {axis_status.is_error}")

    if axis_status.is_moving:
        print(f"WARNING: Axis {axis_number} is already moving!")
        print("Stopping axis first...")
        controller.stop_axis(axis_number)
        await asyncio.sleep(0.5)

    # Enable servo if not already on
    if not axis_status.is_servo_on:
        print(f"  Servo is OFF, enabling...")
        if controller.turn_on_servo(axis_number):
            print(f"  ✓ Servo enabled on axis {axis_number}")
            await asyncio.sleep(0.5)  # Wait for servo to stabilize
        else:
            print(f"  ERROR: Failed to enable servo on axis {axis_number}")
            controller.disconnect()
            return
    else:
        print(f"  Servo already enabled")

    print()

    # Create task for movement
    print("[4] Creating task for relative movement...")
    distance = 100.0  # 100 micrometers
    speed = 50.0  # Slow speed to give us time to see cancellation (50 um/s = 2 seconds for 100um)

    request_data = {
        "movement_type": "relative",
        "axis_number": axis_number,
        "distance": distance,
        "speed": speed,
    }

    try:
        task = task_manager.create_task(
            operation_type=OperationType.AXIS_MOVEMENT,
            request_data=request_data,
        )
        print(f"  Task created: {task.task_id}")
        print(f"  Movement: {distance:+.2f} um at {speed:.1f} um/s")
        print(f"  Estimated time: {abs(distance / speed):.2f} seconds")
        print()

        # Create executor
        executor = MotionTaskExecutor(task_manager=task_manager)

        # Start the movement in a background task
        print("[5] Starting movement in background task...")
        movement_task = asyncio.create_task(
            executor.execute(task.task_id, request_data, controller)
        )

        # Wait a very short time to ensure movement has started
        print("  Waiting 0.3 seconds for movement to start...")
        await asyncio.sleep(0.3)

        # Check if moving
        axis_status_during = controller.get_position(axis_number)
        if axis_status_during:
            print(f"  Current position: {axis_status_during.actual_position:.2f} um")
            print(f"  Is moving: {axis_status_during.is_moving}")

        # NOW CANCEL THE MOVEMENT IMMEDIATELY
        print()
        print("[6] *** CANCELLING MOVEMENT NOW ***")
        task_manager.cancel_task(task.task_id)
        print(f"  Cancellation requested for task {task.task_id}")
        print(f"  Task status: {task.status.value}")

        # Wait for the background task to complete (it should raise OperationCancelledException)
        print()
        print("[7] Waiting for movement to stop...")
        try:
            result = await movement_task
            print("  Unexpected: Movement completed without cancellation!")
            print(f"  Result: {result}")
        except Exception as e:
            print(f"  Movement was cancelled: {type(e).__name__}: {e}")

        # Give hardware time to stabilize
        await asyncio.sleep(0.5)

        # Check final position
        print()
        print("[8] Checking final state...")
        final_status = controller.get_position(axis_number)
        if final_status:
            print(f"  Initial position: {axis_status.actual_position:.2f} um")
            print(f"  Final position: {final_status.actual_position:.2f} um")
            print(f"  Actual travel: {final_status.actual_position - axis_status.actual_position:+.2f} um")
            print(f"  Requested travel: {distance:+.2f} um")
            print(f"  Is moving: {final_status.is_moving}")

            # Verify cancellation worked
            actual_travel = abs(final_status.actual_position - axis_status.actual_position)
            if actual_travel < abs(distance) * 0.9:  # Moved less than 90% of requested distance
                print()
                print("SUCCESS: Movement was stopped mid-flight!")
                print(f"  Only traveled {actual_travel:.2f} um out of {abs(distance):.2f} um requested")
            else:
                print()
                print("WARNING: Movement may have completed before cancellation took effect")

        # Check task status
        print()
        print("[9] Final task status:")
        print(f"  Task ID: {task.task_id}")
        print(f"  Status: {task.status.value}")
        print(f"  Operation: {task.operation_type.value}")
        if task.error:
            print(f"  Error: {task.error}")

    except RuntimeError as e:
        print(f"ERROR: {e}")
        print("Make sure no other task is currently running")

    except Exception as e:
        print(f"ERROR: Unexpected exception: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        print()
        print("[10] Disabling servo...")
        if controller.turn_off_servo(axis_number):
            print(f"  ✓ Servo disabled on axis {axis_number}")
        else:
            print(f"  WARNING: Failed to disable servo on axis {axis_number}")

        print()
        print("[11] Disconnecting...")
        controller.disconnect()
        print("Done!")
        print()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
