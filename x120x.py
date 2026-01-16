#!/usr/bin/python3
# This file was derived from  merged-trixie.py
# which is part of https://github.com/suptronics/x120x

import os
import sys
import struct
import time
import subprocess
from subprocess import call
import smbus2
import gpiod

sys.path.append("/home/embed/send-email")
import send_email


# User-configurable variables
SHUTDOWN_THRESHOLD = 3  # Number of consecutive failures required for shutdown
SLEEP_TIME = 60  # Time in seconds to wait between failure checks
MONITOR_INTERVAL = 3  # Seconds between monitoring checks
VOLTAGE_CRITICAL = 3.2  # shutdown initiation threshold
CAPACITY_CRITICAL = 10  # shutdown initiation threshold
OUTPUT_LIMIT = 5000


def find_host():
    """Find the name of the current host for reporting purposes"""
    try:
        response = subprocess.check_output("hostname", shell=True, text=True)
        response = response.replace("\n", "")
        response = response.lower()
    except:
        return "unknown host"

    return response


def notify(message):
    """Take a message from the queue and attempt to send it via email"""
    hostname = find_host() + " has had a power supply event"
    return send_email.message_using_config(hostname, message, "", "/etc/email.config")


def act_on_first_item(objects, action):
    """Apply action to the first item on the list. If this succeeds, remove the item"""

    # No items, don't bother

    if objects == []:
        return []
    # This must then succeed since objects != []

    first = objects[0]

    # As must this

    if action(first):
        first = objects.pop(0)

    return objects


def readVoltage(bus, address):
    """i2c magic to read voltage"""
    try:
        read = bus.read_word_data(address, 2)
        swapped = struct.unpack("<H", struct.pack(">H", read))[0]
        voltage = swapped * 1.25 / 1000 / 16
        return voltage
    except Exception as err:
        print("read voltage:", err)
        return 0


def readCapacity(bus, address):
    """i2c magic to read battery capacity"""
    try:
        read = bus.read_word_data(address, 4)
        swapped = struct.unpack("<H", struct.pack(">H", read))[0]
        capacity = swapped / 256
        return capacity
    except Exception as err:
        print("read capacity :", err)
        return 0


def get_battery_status(voltage):
    """Text descriptions of battery voltage state"""
    if 3.87 <= voltage:  # Remove upper bound
        return "Full"
    elif 3.7 <= voltage < 3.87:
        return "High"
    elif 3.55 <= voltage < 3.7:
        return "Medium"
    elif 3.4 <= voltage < 3.55:
        return "Low"
    elif voltage < 3.4:
        return "Critical"
    else:
        print("Unknown voltage:", voltage)
        return "Unknown"


def main():
    # Ensure only one instance of the script is running
    # The service file has a ExecStopPost action to remove this file

    try:
        pid = str(os.getpid())
        pidfile = "/tmp/X120x.pid"
        if os.path.isfile(pidfile):
            print("ERROR:clashing pid file")
            sys.exit(1)
        else:
            with open(pidfile, "w") as f:
                f.write(pid)

    except Exception as err:
        print(err)
        sys.exit(2)

    print("PID file created")

    try:
        # Initialize I2C bus
        bus = smbus2.SMBus(1)
        address = 0x36

        print("I2C bus initialised ")

        # Initialize GPIO
        PLD_PIN = 6
        request = gpiod.request_lines(
            "/dev/gpiochip0",
            consumer="PLD",
            config={PLD_PIN: gpiod.LineSettings(direction=gpiod.line.Direction.INPUT)},
        )

        print("GPIO initialised")

        failure_counter = 0
        shutdown_reason = []

        # Initialise value of ac_power_state

        values = request.get_values()
        ac_power_state = values[PLD_PIN] if isinstance(values, dict) else values[0]

        output_count = 0  # Used to limit output
        messages = []  # Used to queue messages

        print("Start control loop")

        while True:
            # If we have messages, attempt to send them
            act_on_first_item(messages, notify)
            # Read GPIO value
            values = request.get_values()
            ac_power_last_cycle = ac_power_state
            ac_power_state = values[PLD_PIN] if isinstance(values, dict) else values[0]

            # Read battery information
            voltage = readVoltage(bus, address)
            battery_status = get_battery_status(voltage)
            capacity = readCapacity(bus, address)

            if ac_power_state != ac_power_last_cycle:
                message = f"Change of power status: Battery: {capacity:.1f}% ({battery_status}), Voltage: {voltage:.2f}V, AC Power: {'Plugged in' if ac_power_state == gpiod.line.Value.ACTIVE else 'Unplugged'}"
                # Queue message
                messages.append(message)
                print(message)  # Update local log
            # Display current status

            if OUTPUT_LIMIT < output_count:
                output_count = 0

            if output_count == 0:
                print(
                    f"Battery: {capacity:.1f}% ({battery_status}), Voltage: {voltage:.2f}V, AC Power: {'Plugged in' if ac_power_state == gpiod.line.Value.ACTIVE else 'Unplugged'}"
                )

            output_count += 1

            # Check conditions

            current_failures = 0

            if capacity < CAPACITY_CRITICAL:
                current_failures += 1

            if voltage < VOLTAGE_CRITICAL:
                current_failures += 1

            # Update failure counter

            if current_failures > 0:
                failure_counter += 1
            else:
                failure_counter = 0

            # Check if shutdown threshold reached

            if failure_counter >= SHUTDOWN_THRESHOLD:
                shutdown_reason = []

                if capacity < CAPACITY_CRITICAL:
                    shutdown_reason.append("critical battery level")

                if voltage < VOLTAGE_CRITICAL:
                    shutdown_reason.append("critical battery voltage")

                # Don't shutdown if AC power is on, because restart will never occur

                if ac_power_state != gpiod.line.Value.ACTIVE:
                    shutdown_reason.append("AC power loss")
                    reason_text = " and ".join(shutdown_reason)
                    print(
                        f"Critical condition met due to {reason_text}. Initiating shutdown."
                    )

                    #  shutdown with last instant check we are not on AC power

                    values = request.get_values()
                    ac_power_state = (
                        values[PLD_PIN] if isinstance(values, dict) else values[0]
                    )
                    if ac_power_state != gpiod.line.Value.ACTIVE:
                        call("sudo nohup shutdown -h now", shell=True)
                    break
            # Wait for next monitoring interval
            time.sleep(MONITOR_INTERVAL)

    except KeyboardInterrupt:
        pass

    except Exception as err:
        print(err)
        pass

    finally:
        # Cleanup
        try:
            if "request" in locals():
                request.release()
        except Exception as err:
            print(err)

        try:
            if "bus" in locals():
                bus.close()
        except:
            pass

        if os.path.isfile(pidfile):
            os.unlink(pidfile)

    print("Exit")


if __name__ == "__main__":
    main()
