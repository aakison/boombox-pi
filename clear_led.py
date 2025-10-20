import smbus
import time

# PCF8574 I2C address (default 0x20)
ADDRESS = 0x20

# Initialize I2C bus
bus = smbus.SMBus(1)

# Initial state: pins 7-8 high (0xC0 = 11000000)
pin_state = 0xFF

def reset_pins():
    global pin_state
    pin_state = 0xFF

def set_pin(pin, state):
    global pin_state
    if state:
        pin_state |= (1 << pin)  # Set pin high
    else:
        pin_state &= ~(1 << pin)  # Set pin low

def write_pins():
    bus.write_byte(ADDRESS, pin_state)

# Custom pin order: 0, 1, 4, 5, 2, 3
pins = [1, 2, 5, 4, 3, 4, 5, 2]

for pin in pins:
    reset_pins()
    write_pins()
