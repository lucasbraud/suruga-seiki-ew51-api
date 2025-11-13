"""
Simple test demonstrating async motion cancellation without task framework.

This is a minimal example showing the core async functionality:
1. Enable servo on X1 axis
2. Start a relative movement on X1 axis
3. Cancel it immediately using asyncio.Event
4. Verify the axis stopped mid-flight
5. Disable servo on X1 axis

This example uses the controller's async methods directly without the
full task management system.

Usage:
    python examples/test_simple_async_motion_stop.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.controller_manager import SurugaSeikiController


async def main():
    """Main test function."""
    print("=" * 70)
    print("Simple Async Motion with Cancellation - Direct Test")
    print("=" * 70)
    print()

    # Initialize and connect
    print("[1] Connecting to controller...")
    controller = SurugaSeikiController()

    if not controller.connect() or not controller.is_connected():
        print("ERROR: Failed to connect to controller!")
        print("Make sure:")
        print("  - Hardware is powered on")
        print("  - ADS address is configured in .env or settings")
        print("  - Network connection is working")
        return

    print("SUCCESS: Connected")
    print()

    # Configuration
    axis_number = 1  # X1
    distance = 100.0  # micrometers
    speed = 50.0  # um/s (slow speed = 2 seconds for 100um)

    # Check initial state
    print(f"[2] Checking axis {axis_number} (X1) initial state...")
    initial_status = controller.get_position(axis_number)

    if not initial_status:
        print("ERROR: Cannot read axis status")
        controller.disconnect()
        return

    print(f"  Position: {initial_status.actual_position:.2f} um")
    print(f"  Servo on: {initial_status.is_servo_on}")

    if initial_status.is_moving:
        print("  WARNING: Already moving, stopping...")
        controller.stop_axis(axis_number)
        await asyncio.sleep(0.5)

    # Enable servo if not already on
    if not initial_status.is_servo_on:
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

    initial_position = initial_status.actual_position
    print()

    # Create cancellation event
    print(f"[3] Starting movement: {distance:+.2f} um at {speed:.1f} um/s")
    print(f"  Estimated duration: {abs(distance/speed):.2f} seconds")

    cancellation_event = asyncio.Event()
    progress_updates = []

    def progress_callback(progress_data):
        """Capture progress updates."""
        progress_updates.append(progress_data)
        if "message" in progress_data:
            print(f"  Progress: {progress_data['message']}")

    # Start movement as background task
    print("  Starting background movement...")
    movement_task = asyncio.create_task(
        controller.move_relative_async(
            axis_number=axis_number,
            distance=distance,
            speed=speed,
            cancellation_event=cancellation_event,
            progress_callback=progress_callback,
        )
    )

    # Wait briefly to ensure movement started
    print("  Waiting 0.3 seconds...")
    await asyncio.sleep(0.3)

    # Check if moving
    mid_status = controller.get_position(axis_number)
    if mid_status:
        print(f"  Position now: {mid_status.actual_position:.2f} um (moved {mid_status.actual_position - initial_position:+.2f} um)")
        print(f"  Is moving: {mid_status.is_moving}")

    # CANCEL IT NOW!
    print()
    print("[4] *** CANCELLING MOVEMENT ***")
    cancellation_event.set()

    # Wait for movement task to finish
    try:
        result = await movement_task
        print("  WARNING: Movement completed without cancellation")
        print(f"  Result: {result}")
    except Exception as e:
        print(f"  Cancelled successfully: {e}")

    # Wait for axis to stabilize
    await asyncio.sleep(0.5)

    # Check final state
    print()
    print("[5] Results:")
    final_status = controller.get_position(axis_number)

    if final_status:
        actual_distance = final_status.actual_position - initial_position

        print(f"  Initial position: {initial_position:.2f} um")
        print(f"  Final position: {final_status.actual_position:.2f} um")
        print(f"  Requested distance: {distance:+.2f} um")
        print(f"  Actual distance: {actual_distance:+.2f} um")
        print(f"  Stopped at: {abs(actual_distance) / abs(distance) * 100:.1f}% of target")
        print()

        if abs(actual_distance) < abs(distance) * 0.9:
            print("✓ SUCCESS: Movement stopped mid-flight!")
            print(f"  Axis stopped after only {abs(actual_distance):.2f} um")
        else:
            print("⚠ WARNING: Movement may have completed before cancel")

    # Show progress updates captured
    print()
    print(f"[6] Progress updates received: {len(progress_updates)}")
    for i, update in enumerate(progress_updates, 1):
        if "progress_percent" in update:
            print(f"  Update {i}: {update.get('progress_percent', 0)}% - {update.get('current_position', 'N/A')} um")

    # Cleanup
    print()
    print("[7] Disabling servo...")
    if controller.turn_off_servo(axis_number):
        print(f"  ✓ Servo disabled on axis {axis_number}")
    else:
        print(f"  WARNING: Failed to disable servo on axis {axis_number}")

    print()
    print("[8] Disconnecting...")
    controller.disconnect()
    print("Done!")
    print()


if __name__ == "__main__":
    asyncio.run(main())
