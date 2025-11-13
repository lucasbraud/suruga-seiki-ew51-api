"""
Test example demonstrating relative and absolute motion with async.

This example shows:
1. Enable servo on X1 axis
2. Record initial position
3. Move relative +100 um
4. Move absolute back to initial position
5. Verify we're back at the start position
6. Disable servo

Usage:
    python examples/test_relative_then_absolute.py
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
    print("Relative + Absolute Movement Test")
    print("=" * 70)
    print()

    # Initialize and connect
    print("[1] Connecting to controller...")
    controller = SurugaSeikiController()

    if not controller.connect() or not controller.is_connected():
        print("ERROR: Failed to connect to controller!")
        return

    print("SUCCESS: Connected")
    print()

    # Configuration
    axis_number = 1  # X1
    relative_distance = 100.0  # micrometers to move
    speed = 100.0  # um/s

    try:
        # Check initial state
        print(f"[2] Checking axis {axis_number} (X1) initial state...")
        initial_status = controller.get_position(axis_number)

        if not initial_status:
            print("ERROR: Cannot read axis status")
            return

        print(f"  Position: {initial_status.actual_position:.2f} um")
        print(f"  Servo on: {initial_status.is_servo_on}")

        # Enable servo if needed
        if not initial_status.is_servo_on:
            print(f"  Servo is OFF, enabling...")
            if controller.turn_on_servo(axis_number):
                print(f"  ✓ Servo enabled on axis {axis_number}")
                await asyncio.sleep(0.5)
            else:
                print(f"  ERROR: Failed to enable servo")
                return
        else:
            print(f"  Servo already enabled")

        # Record initial position
        initial_position = initial_status.actual_position
        print(f"\n  📍 Initial position recorded: {initial_position:.2f} um")
        print()

        # ========== MOVE 1: Relative Movement ==========
        print(f"[3] Moving RELATIVE: {relative_distance:+.2f} um at {speed:.1f} um/s")

        # Progress tracking for relative movement
        relative_updates = []

        def relative_progress(data):
            relative_updates.append(data)
            if "current_position" in data and data.get("progress_percent") is not None:
                print(f"    Progress: {data['progress_percent']}% - Position: {data['current_position']:.2f} um")

        # Execute relative movement
        try:
            result = await controller.move_relative_async(
                axis_number=axis_number,
                distance=relative_distance,
                speed=speed,
                cancellation_event=None,  # No cancellation for this move
                progress_callback=relative_progress,
            )

            print(f"  ✓ Relative movement completed")
            print(f"    Target position: {initial_position + relative_distance:.2f} um")
            print(f"    Final position: {result['final_position']:.2f} um")
            print(f"    Execution time: {result['execution_time']:.2f}s")

            after_relative_position = result['final_position']

        except Exception as e:
            print(f"  ✗ Relative movement failed: {e}")
            return

        print()

        # ========== MOVE 2: Absolute Movement (Back to Start) ==========
        print(f"[4] Moving ABSOLUTE back to initial position: {initial_position:.2f} um")

        # Progress tracking for absolute movement
        absolute_updates = []

        def absolute_progress(data):
            absolute_updates.append(data)
            if "current_position" in data and data.get("progress_percent") is not None:
                print(f"    Progress: {data['progress_percent']}% - Position: {data['current_position']:.2f} um")

        # Execute absolute movement back to start
        try:
            result = await controller.move_absolute_async(
                axis_number=axis_number,
                position=initial_position,
                speed=speed,
                cancellation_event=None,  # No cancellation for this move
                progress_callback=absolute_progress,
            )

            print(f"  ✓ Absolute movement completed")
            print(f"    Target position: {initial_position:.2f} um")
            print(f"    Final position: {result['final_position']:.2f} um")
            print(f"    Execution time: {result['execution_time']:.2f}s")

            final_position = result['final_position']

        except Exception as e:
            print(f"  ✗ Absolute movement failed: {e}")
            return

        print()

        # ========== VERIFICATION ==========
        print("[5] Verification:")

        # Check if we're back at the start
        position_error = abs(final_position - initial_position)

        print(f"  Initial position:  {initial_position:.2f} um")
        print(f"  After relative:    {after_relative_position:.2f} um (moved {after_relative_position - initial_position:+.2f} um)")
        print(f"  After absolute:    {final_position:.2f} um")
        print(f"  Position error:    {position_error:.2f} um")
        print()

        if position_error < 1.0:  # Within 1 micrometer
            print("  ✓ SUCCESS: Returned to initial position!")
            print(f"    Accuracy: {position_error:.3f} um")
        else:
            print(f"  ⚠ WARNING: Position error is {position_error:.2f} um")

        print()

        # ========== STATISTICS ==========
        print("[6] Movement Statistics:")
        print(f"  Relative movement:")
        print(f"    - Progress updates: {len([u for u in relative_updates if 'progress_percent' in u])}")
        print(f"  Absolute movement:")
        print(f"    - Progress updates: {len([u for u in absolute_updates if 'progress_percent' in u])}")

    finally:
        # Cleanup
        print()
        print("[7] Disabling servo...")
        if controller.turn_off_servo(axis_number):
            print(f"  ✓ Servo disabled on axis {axis_number}")
        else:
            print(f"  WARNING: Failed to disable servo")

        print()
        print("[8] Disconnecting...")
        controller.disconnect()
        print("Done!")
        print()


if __name__ == "__main__":
    asyncio.run(main())
