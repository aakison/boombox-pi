import spidev
import smbus
import time
import RPi.GPIO as GPIO

# MCP3008 ADC Configuration
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(7, GPIO.OUT)
GPIO.output(7, GPIO.HIGH)  # Start with CS HIGH (inactive)

# Initialize SPI for MCP3008
spi = spidev.SpiDev()
spi.open(0, 1)  # SPI bus 0, CE1 (GPIO7)
spi.max_speed_hz = 10000
spi.mode = 0
spi.no_cs = True  # Disable automatic CS control

# PCF8574 I2C Configuration
I2C_ADDRESS = 0x20
bus = smbus.SMBus(1)

# Define integer ranges for the potentiometer (0-1023 from 10-bit ADC)
# You can modify these ranges as needed
POT_RANGES = [
    (0, 200),      # Range 1: 0-200
    (305, 335),    # Range 2: 201-400
    (360, 395),    # Range 3: 401-600
    (430, 468),    # Range 4: 601-800
    (801, 1023)    # Range 5: 801-1023
]

# Track current state
current_range = None
pin_state = 0xFF  # Initial state: all pins high

def read_mcp3008(channel):
    """Read ADC value from MCP3008"""
    if channel < 0 or channel > 7:
        raise ValueError("Channel must be 0-7")
    
    # Manually toggle CS
    GPIO.output(7, GPIO.LOW)  # Activate MCP3008
    adc = spi.xfer2([1, (8 + channel) << 4, 0])  # SPI transfer
    GPIO.output(7, GPIO.HIGH)  # Deactivate MCP3008
    data = ((adc[1] & 3) << 8) + adc[2]  # Combine 10-bit result
    return data

def set_i2c_pin(pin, state):
    """Set state of specific pin on PCF8574"""
    global pin_state
    if state:
        pin_state |= (1 << pin)  # Set pin high
    else:
        pin_state &= ~(1 << pin)  # Set pin low

def write_i2c_pins():
    """Write current pin state to PCF8574"""
    bus.write_byte(I2C_ADDRESS, pin_state)

def reset_i2c_pins():
    """Reset all pins to high state"""
    global pin_state
    pin_state = 0xFF
    write_i2c_pins()

def get_range_for_value(value):
    """Determine which range the ADC value falls into"""
    for i, (min_val, max_val) in enumerate(POT_RANGES):
        if min_val <= value <= max_val:
            return i
    return None

def main():
    global current_range
    
    print("Starting Raspberry Pi Tuner...")
    print("POT Ranges:")
    for i, (min_val, max_val) in enumerate(POT_RANGES):
        print(f"  Range {i+1}: {min_val}-{max_val}")
    print("Press Ctrl+C to exit\n")
    
    # Initialize I2C pins
    reset_i2c_pins()
    
    try:
        while True:
            # Read potentiometer value
            pot_value = read_mcp3008(0)
            
            # Determine current range
            new_range = get_range_for_value(pot_value)
            
            # Check for range changes
            if new_range != current_range:
                # Handle leaving previous range
                if current_range is not None:
                    print(f"Left range {current_range + 1} (ADC: {pot_value})")
                    # Turn off pin 0 when leaving any range
                    set_i2c_pin(0, True)  # Set pin 0 high (off)
                
                # Handle entering new range
                if new_range is not None:
                    print(f"Entered range {new_range + 1} (ADC: {pot_value})")
                    # Turn on pin 0 when entering any range
                    set_i2c_pin(0, False)  # Set pin 0 low (on)
                else:
                    print(f"Outside all ranges (ADC: {pot_value})")
                
                # Write the new state to I2C device
                write_i2c_pins()
                
                # Update current range
                current_range = new_range
            
            # Sleep for approximately 1/60th of a second (60 Hz)
            time.sleep(1/60)
            
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    finally:
        # Cleanup
        reset_i2c_pins()
        GPIO.cleanup()
        spi.close()
        print("Cleanup completed.")

if __name__ == "__main__":
    main()
