import spidev
import smbus
import time
import RPi.GPIO as GPIO

class Band:
    """Represents a tuner band with ADC range and corresponding URL"""
    def __init__(self, min_val, max_val, url, name=None):
        self.min_val = min_val
        self.max_val = max_val
        self.url = url
        self.name = name or f"{min_val}-{max_val}"
    
    def contains(self, value):
        """Check if the given ADC value falls within this band's range"""
        return self.min_val <= value <= self.max_val
    
    def __str__(self):
        return f"Band {self.name}: {self.min_val}-{self.max_val} -> {self.url}"

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

# Define bands with their ranges and URLs
BANDS = [
    Band(305, 335, "http://abm21.com.au:8000/CONTAINER92", "Band 1"),
    Band(360, 395, "http://abm21.com.au:8000/CONTAINER87", "Band 2"),
    Band(430, 468, "http://abm21.com.au:8000/CONTAINER81", "Band 3")
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

def get_band_for_value(value):
    """Determine which band the ADC value falls into"""
    for i, band in enumerate(BANDS):
        if band.contains(value):
            return i
    return None

def main():
    global current_range
    
    print("Starting Raspberry Pi Tuner...")
    print("Bands:")
    for i, band in enumerate(BANDS):
        print(f"  {band}")
    print("Press Ctrl+C to exit\n")
    
    # Initialize I2C pins
    reset_i2c_pins()
    
    try:
        while True:
            # Read potentiometer value
            pot_value = read_mcp3008(0)
            
            # Determine current band
            new_range = get_band_for_value(pot_value)
            
            # Check for band changes
            if new_range != current_range:
                # Handle leaving previous band
                if current_range is not None:
                    print(f"Left {BANDS[current_range].name} (ADC: {pot_value})")
                    # Turn off pin 0 when leaving any band
                    set_i2c_pin(0, True)  # Set pin 0 high (off)
                
                # Handle entering new band
                if new_range is not None:
                    print(f"Entered {BANDS[new_range].name} (ADC: {pot_value})")
                    print(f"URL: {BANDS[new_range].url}")
                    # Turn on pin 0 when entering any band
                    set_i2c_pin(0, False)  # Set pin 0 low (on)
                else:
                    print(f"Outside all bands (ADC: {pot_value})")
                
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
