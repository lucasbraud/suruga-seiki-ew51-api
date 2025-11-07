#!/usr/bin/env python3
"""
Manual Control Script for Suruga Seiki EW51 Probe Station
Terminal-based interface for testing and debugging the probe station hardware
"""
import sys
import time
from pathlib import Path

# Add parent directory to path to import from instruments
sys.path.insert(0, str(Path(__file__).parent.parent / "instruments" / "suruga_seiki_ew51" / "daemon" / "app"))

from controller_manager import SurugaSeikiController, AlignmentMode
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ManualController:
    """Interactive manual controller for probe station"""

    def __init__(self, ads_address: str = "5.146.68.190.1.1"):
        self.controller = SurugaSeikiController(ads_address)
        self.running = False

    def connect(self) -> bool:
        """Connect to the probe station"""
        print("\n" + "=" * 60)
        print("Connecting to Suruga Seiki EW51 Probe Station...")
        print(f"ADS Address: {self.controller.ads_address}")
        print("=" * 60)

        success = self.controller.connect()

        if success:
            print("\n Connection successful!")
            is_error, error_msg = self.controller.check_error()
            if is_error:
                print(f"  System has errors: {error_msg}")
            else:
                print(" System status: OK")
        else:
            print("\n Connection failed!")

        return success

    def disconnect(self):
        """Disconnect from the probe station"""
        print("\nDisconnecting from probe station...")
        self.controller.disconnect()
        print(" Disconnected")

    def show_menu(self):
        """Display main menu"""
        print("\n" + "=" * 60)
        print("MANUAL CONTROL - Suruga Seiki EW51 Probe Station")
        print("=" * 60)
        print("\nConnection:")
        print("  1. Show system status")
        print("  2. Show all axis positions")
        print("\nServo Control:")
        print("  3. Turn on servo")
        print("  4. Turn off servo")
        print("  5. Turn on all servos")
        print("  6. Turn off all servos")
        print("\nMotion Control:")
        print("  7. Move absolute")
        print("  8. Move relative")
        print("  9. Stop axis")
        print("  10. Emergency stop all axes")
        print("\n2D/3D Motion:")
        print("  11. 2D interpolation move")
        print("  12. 3D interpolation move")
        print("\nAlignment:")
        print("  13. Run flat alignment")
        print("  14. Run focus alignment")
        print("  15. Run single alignment")
        print("\nProfile Measurement:")
        print("  16. Measure profile scan")
        print("\nI/O Control:")
        print("  17. Set digital output")
        print("  18. Read digital input")
        print("  19. Set analog output")
        print("  20. Read analog input")
        print("\nUtility:")
        print("  21. Monitor positions (real-time)")
        print("  0. Exit")
        print("=" * 60)

    def get_axis_number(self, prompt: str = "Enter axis number (1-12): ") -> int:
        """Get and validate axis number from user"""
        while True:
            try:
                axis = int(input(prompt))
                if 1 <= axis <= 12:
                    return axis
                print("Invalid axis number. Must be between 1 and 12.")
            except ValueError:
                print("Invalid input. Please enter a number.")

    def show_system_status(self):
        """Display system status"""
        print("\n" + "-" * 60)
        print("SYSTEM STATUS")
        print("-" * 60)
        print(f"Connected: {self.controller.is_connected()}")

        is_error, error_msg = self.controller.check_error()
        print(f"Has Error: {is_error}")
        if is_error:
            print(f"Error Message: {error_msg}")
        print("-" * 60)

    def show_all_positions(self):
        """Display positions for all axes"""
        print("\n" + "-" * 80)
        print("ALL AXIS POSITIONS")
        print("-" * 80)
        print(f"{'Axis':<6} {'Actual Pos':<15} {'Command Pos':<15} {'Moving':<8} {'Servo':<8} {'Error':<6}")
        print("-" * 80)

        positions = self.controller.get_all_positions()

        for axis_num in sorted(positions.keys()):
            pos = positions[axis_num]
            print(f"{pos.axis_number:<6} "
                  f"{pos.actual_position:<15.2f} "
                  f"{pos.command_position:<15.2f} "
                  f"{'Yes' if pos.is_moving else 'No':<8} "
                  f"{'On' if pos.is_servo_on else 'Off':<8} "
                  f"{'Yes' if pos.is_error else 'No':<6}")

        print("-" * 80)

    def turn_on_servo(self):
        """Turn on servo for an axis"""
        axis = self.get_axis_number()
        success = self.controller.turn_on_servo(axis)
        print(f"{'' if success else ''} Servo {'turned on' if success else 'failed'} for axis {axis}")

    def turn_off_servo(self):
        """Turn off servo for an axis"""
        axis = self.get_axis_number()
        success = self.controller.turn_off_servo(axis)
        print(f"{'' if success else ''} Servo {'turned off' if success else 'failed'} for axis {axis}")

    def turn_on_all_servos(self):
        """Turn on servos for all axes"""
        print("\nTurning on all servos...")
        for axis in range(1, 13):
            success = self.controller.turn_on_servo(axis)
            print(f"  Axis {axis:2d}: {'' if success else ''}")

    def turn_off_all_servos(self):
        """Turn off servos for all axes"""
        print("\nTurning off all servos...")
        for axis in range(1, 13):
            success = self.controller.turn_off_servo(axis)
            print(f"  Axis {axis:2d}: {'' if success else ''}")

    def move_absolute(self):
        """Move axis to absolute position"""
        axis = self.get_axis_number()
        position = float(input("Enter target position (um): "))
        speed = float(input("Enter speed (um/s) [default 1000]: ") or "1000")

        success = self.controller.move_absolute(axis, position, speed)
        print(f"{'' if success else ''} Move command {'sent' if success else 'failed'}")

        if success:
            print("Waiting for movement to complete...")
            self.controller.wait_for_axis_stop(axis)
            pos = self.controller.get_position(axis)
            if pos:
                print(f" Movement complete. Position: {pos.actual_position:.2f} um")

    def move_relative(self):
        """Move axis relative to current position"""
        axis = self.get_axis_number()
        distance = float(input("Enter relative distance (um): "))
        speed = float(input("Enter speed (um/s) [default 1000]: ") or "1000")

        success = self.controller.move_relative(axis, distance, speed)
        print(f"{'' if success else ''} Move command {'sent' if success else 'failed'}")

        if success:
            print("Waiting for movement to complete...")
            self.controller.wait_for_axis_stop(axis)
            pos = self.controller.get_position(axis)
            if pos:
                print(f" Movement complete. Position: {pos.actual_position:.2f} um")

    def stop_axis(self):
        """Stop movement of an axis"""
        axis = self.get_axis_number()
        success = self.controller.stop_axis(axis)
        print(f"{'' if success else ''} Stop command {'sent' if success else 'failed'}")

    def emergency_stop(self):
        """Emergency stop all axes"""
        confirm = input("  Emergency stop ALL axes? (yes/no): ")
        if confirm.lower() == "yes":
            success = self.controller.emergency_stop()
            print(f"{'' if success else ''} Emergency stop {'executed' if success else 'failed'}")

    def move_2d(self):
        """Execute 2D interpolation move"""
        print("\n2D Interpolation Move")
        axis1 = self.get_axis_number("Enter first axis number (1-12): ")
        axis2 = self.get_axis_number("Enter second axis number (1-12): ")
        x = float(input("Enter X position (um): "))
        y = float(input("Enter Y position (um): "))
        speed = float(input("Enter speed (um/s) [default 1000]: ") or "1000")
        angle = float(input("Enter angle offset (deg) [default 0]: ") or "0")

        success = self.controller.move_2d_absolute(axis1, axis2, x, y, speed, angle)
        print(f"{'' if success else ''} 2D move command {'sent' if success else 'failed'}")

    def move_3d(self):
        """Execute 3D interpolation move"""
        print("\n3D Interpolation Move")
        axis1 = self.get_axis_number("Enter first axis number (1-12): ")
        axis2 = self.get_axis_number("Enter second axis number (1-12): ")
        axis3 = self.get_axis_number("Enter third axis number (1-12): ")
        x = float(input("Enter X position (um): "))
        y = float(input("Enter Y position (um): "))
        z = float(input("Enter Z position (um): "))
        speed = float(input("Enter speed (um/s) [default 1000]: ") or "1000")

        success = self.controller.move_3d_absolute(axis1, axis2, axis3, x, y, z, speed)
        print(f"{'' if success else ''} 3D move command {'sent' if success else 'failed'}")

    def run_flat_alignment(self):
        """Run flat alignment routine"""
        print("\nFlat Alignment Configuration")
        monitor_axis = self.get_axis_number("Enter monitor axis (1-12): ")
        scan_axis_1 = self.get_axis_number("Enter scan axis 1 (1-12): ")
        scan_axis_2 = self.get_axis_number("Enter scan axis 2 (1-12): ")
        scan_range = float(input("Enter scan range (um) [default 1000]: ") or "1000")
        scan_speed = float(input("Enter scan speed (um/s) [default 100]: ") or "100")

        print("\nExecuting flat alignment...")
        result = self.controller.run_alignment(
            mode=AlignmentMode.FLAT,
            monitor_axis=monitor_axis,
            scan_axis_1=scan_axis_1,
            scan_axis_2=scan_axis_2,
            scan_range_1=scan_range,
            scan_range_2=scan_range,
            scan_speed=scan_speed
        )

        if result:
            print(f"\n{'' if result.success else ''} Alignment {'completed' if result.success else 'failed'}")
            print(f"Peak Value: {result.peak_value:.4f}")
            print(f"Peak Position: ({result.peak_position_x:.2f}, {result.peak_position_y:.2f}) um")
            print(f"Execution Time: {result.execution_time:.2f} s")
            if result.profile_data:
                print(f"Profile Data Points: {len(result.profile_data)}")
        else:
            print(" Alignment failed")

    def run_focus_alignment(self):
        """Run focus alignment routine"""
        print("\nFocus Alignment Configuration")
        monitor_axis = self.get_axis_number("Enter monitor axis (1-12): ")
        scan_axis = self.get_axis_number("Enter scan axis (Z) (1-12): ")
        scan_range = float(input("Enter scan range (um) [default 1000]: ") or "1000")
        scan_speed = float(input("Enter scan speed (um/s) [default 100]: ") or "100")

        print("\nExecuting focus alignment...")
        result = self.controller.run_alignment(
            mode=AlignmentMode.FOCUS,
            monitor_axis=monitor_axis,
            scan_axis_1=scan_axis,
            scan_range_1=scan_range,
            scan_speed=scan_speed
        )

        if result:
            print(f"\n{'' if result.success else ''} Alignment {'completed' if result.success else 'failed'}")
            print(f"Peak Value: {result.peak_value:.4f}")
            print(f"Peak Position Z: {result.peak_position_z:.2f} um" if result.peak_position_z else "N/A")
            print(f"Execution Time: {result.execution_time:.2f} s")
        else:
            print(" Alignment failed")

    def run_single_alignment(self):
        """Run single alignment routine"""
        print("\nSingle Alignment Configuration")
        monitor_axis = self.get_axis_number("Enter monitor axis (1-12): ")
        scan_axis = self.get_axis_number("Enter scan axis (1-12): ")
        scan_range = float(input("Enter scan range (um) [default 1000]: ") or "1000")
        scan_speed = float(input("Enter scan speed (um/s) [default 100]: ") or "100")

        print("\nExecuting single alignment...")
        result = self.controller.run_alignment(
            mode=AlignmentMode.SINGLE,
            monitor_axis=monitor_axis,
            scan_axis_1=scan_axis,
            scan_range_1=scan_range,
            scan_speed=scan_speed
        )

        if result:
            print(f"\n{'' if result.success else ''} Alignment {'completed' if result.success else 'failed'}")
            print(f"Peak Value: {result.peak_value:.4f}")
            print(f"Peak Position: {result.peak_position_x:.2f} um")
            print(f"Execution Time: {result.execution_time:.2f} s")
        else:
            print(" Alignment failed")

    def measure_profile(self):
        """Measure profile scan"""
        print("\nProfile Measurement Configuration")
        scan_axis = self.get_axis_number("Enter scan axis (1-12): ")
        monitor_axis = self.get_axis_number("Enter monitor axis (1-12): ")
        start_pos = float(input("Enter start position (um): "))
        end_pos = float(input("Enter end position (um): "))
        scan_speed = float(input("Enter scan speed (um/s) [default 100]: ") or "100")
        sampling = float(input("Enter sampling interval (um) [default 10]: ") or "10")

        print("\nExecuting profile measurement...")
        profile_data = self.controller.measure_profile(
            scan_axis=scan_axis,
            monitor_axis=monitor_axis,
            start_position=start_pos,
            end_position=end_pos,
            scan_speed=scan_speed,
            sampling_interval=sampling
        )

        if profile_data:
            print(f" Profile measurement completed")
            print(f"Data Points: {len(profile_data)}")
            print("\nFirst 5 data points:")
            for i, (pos, val) in enumerate(profile_data[:5]):
                print(f"  {i+1}. Position: {pos:.2f} um, Value: {val:.4f}")
            if len(profile_data) > 5:
                print("  ...")
        else:
            print(" Profile measurement failed")

    def set_digital_output(self):
        """Set digital output"""
        channel = int(input("Enter digital output channel: "))
        value = input("Enter value (high/low): ").lower() == "high"
        success = self.controller.set_digital_output(channel, value)
        print(f"{'' if success else ''} Digital output {'set' if success else 'failed'}")

    def read_digital_input(self):
        """Read digital input"""
        channel = int(input("Enter digital input channel: "))
        value = self.controller.get_digital_input(channel)
        if value is not None:
            print(f" Digital input {channel}: {'HIGH' if value else 'LOW'}")
        else:
            print(" Failed to read digital input")

    def set_analog_output(self):
        """Set analog output"""
        channel = int(input("Enter analog output channel: "))
        voltage = float(input("Enter voltage (V): "))
        success = self.controller.set_analog_output(channel, voltage)
        print(f"{'' if success else ''} Analog output {'set' if success else 'failed'}")

    def read_analog_input(self):
        """Read analog input"""
        channel = int(input("Enter analog input channel: "))
        voltage = self.controller.get_analog_input(channel)
        if voltage is not None:
            print(f" Analog input {channel}: {voltage:.4f} V")
        else:
            print(" Failed to read analog input")

    def monitor_positions(self):
        """Real-time position monitoring"""
        print("\nReal-time Position Monitor (Press Ctrl+C to stop)")
        print("-" * 80)

        try:
            while True:
                positions = self.controller.get_all_positions()

                # Clear screen (simple approach)
                print("\033[H\033[J", end="")

                print("=" * 80)
                print(f"{'Axis':<6} {'Actual Pos':<15} {'Moving':<8} {'Servo':<8} {'Error':<6}")
                print("=" * 80)

                for axis_num in sorted(positions.keys()):
                    pos = positions[axis_num]
                    print(f"{pos.axis_number:<6} "
                          f"{pos.actual_position:<15.2f} "
                          f"{'Yes' if pos.is_moving else 'No':<8} "
                          f"{'On' if pos.is_servo_on else 'Off':<8} "
                          f"{'Yes' if pos.is_error else 'No':<6}")

                print("=" * 80)
                print("Press Ctrl+C to stop monitoring")

                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped")

    def run(self):
        """Main control loop"""
        if not self.connect():
            print("\nFailed to connect. Exiting.")
            return

        self.running = True

        try:
            while self.running:
                self.show_menu()

                try:
                    choice = input("\nEnter choice: ").strip()

                    if choice == "0":
                        self.running = False
                    elif choice == "1":
                        self.show_system_status()
                    elif choice == "2":
                        self.show_all_positions()
                    elif choice == "3":
                        self.turn_on_servo()
                    elif choice == "4":
                        self.turn_off_servo()
                    elif choice == "5":
                        self.turn_on_all_servos()
                    elif choice == "6":
                        self.turn_off_all_servos()
                    elif choice == "7":
                        self.move_absolute()
                    elif choice == "8":
                        self.move_relative()
                    elif choice == "9":
                        self.stop_axis()
                    elif choice == "10":
                        self.emergency_stop()
                    elif choice == "11":
                        self.move_2d()
                    elif choice == "12":
                        self.move_3d()
                    elif choice == "13":
                        self.run_flat_alignment()
                    elif choice == "14":
                        self.run_focus_alignment()
                    elif choice == "15":
                        self.run_single_alignment()
                    elif choice == "16":
                        self.measure_profile()
                    elif choice == "17":
                        self.set_digital_output()
                    elif choice == "18":
                        self.read_digital_input()
                    elif choice == "19":
                        self.set_analog_output()
                    elif choice == "20":
                        self.read_analog_input()
                    elif choice == "21":
                        self.monitor_positions()
                    else:
                        print("Invalid choice. Please try again.")

                except KeyboardInterrupt:
                    print("\n\nInterrupted by user")
                    continue
                except Exception as e:
                    print(f"\n Error: {e}")
                    logger.exception("Error in manual control")

        finally:
            self.disconnect()
            print("\nThank you for using Manual Control!")


def main():
    """Main entry point"""
    print("\n" + "=" * 60)
    print("Suruga Seiki EW51 Probe Station - Manual Control")
    print("=" * 60)

    # Allow custom ADS address
    ads_address = input("\nEnter ADS address [default: 5.146.68.190.1.1]: ").strip()
    if not ads_address:
        ads_address = "5.146.68.190.1.1"

    controller = ManualController(ads_address)
    controller.run()


if __name__ == "__main__":
    main()
