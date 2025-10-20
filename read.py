import RPi.GPIO as GPIO
import time

# Set GPIO mode to BCM
GPIO.setmode(GPIO.BCM)

# Define input pins
input_pins = [4, 17, 27, 22, 18, 23, 24, 25, 19, 26, 16, 12]

# Setup pins as inputs with pull-down resistors
for pin in input_pins:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

try:
    print("Reading GPIO pins " + ", ".join(map(str, input_pins)) + " (Ctrl+C to exit)...")
    while True:
        # Read all pin states
        states = {pin: GPIO.input(pin) for pin in input_pins}
        # Print states (1 = high, 0 = low)
        print(", ".join(map(lambda x: f"{x}: {states[x]}", input_pins)))
        time.sleep(1)  # Update every second
except KeyboardInterrupt:
    print("\nProgram terminated by user.")
finally:
    GPIO.cleanup()  # Reset GPIO settings

