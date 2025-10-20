import spidev
import smbus
import time
import subprocess
import RPi.GPIO as GPIO

# Hardware pin constants
MCP3008_CS_PIN = 7  # GPIO pin 7 used as Chip Select for MCP3008 ADC

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

class Tuner:
    """Singleton class to handle SPI interface to MCP3008 and band detection"""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Tuner, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not Tuner._initialized:
            # Initialize GPIO for MCP3008 chip select
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(MCP3008_CS_PIN, GPIO.OUT)
            GPIO.output(MCP3008_CS_PIN, GPIO.HIGH)  # Start with CS HIGH (inactive)
            
            # Initialize SPI for MCP3008
            self.spi = spidev.SpiDev()
            self.spi.open(0, 1)  # SPI bus 0, CE1 (GPIO7)
            self.spi.max_speed_hz = 10000
            self.spi.mode = 0
            self.spi.no_cs = True  # Disable automatic CS control
            Tuner._initialized = True
    
    def read_mcp3008(self, channel):
        """Read ADC value from MCP3008"""
        if channel < 0 or channel > 7:
            raise ValueError("Channel must be 0-7")
        
        # Manually toggle chip select
        GPIO.output(MCP3008_CS_PIN, GPIO.LOW)  # Activate MCP3008
        adc = self.spi.xfer2([1, (8 + channel) << 4, 0])  # SPI transfer
        GPIO.output(MCP3008_CS_PIN, GPIO.HIGH)  # Deactivate MCP3008
        data = ((adc[1] & 3) << 8) + adc[2]  # Combine 10-bit result
        return data
    
    def read_mcp3008_smooth(self, channel, samples=15):
        """Read smoothed ADC value from MCP3008 averaged over multiple samples"""
        if samples <= 0:
            raise ValueError("Samples must be greater than 0")
        
        total = 0
        for _ in range(samples):
            total += self.read_mcp3008(channel)
            # Small delay between samples to allow for settling
            time.sleep(0.001)  # 1ms delay
        
        return total // samples  # Return integer average
    
    def get_band(self):
        """Get the current band based on smoothed ADC reading"""
        pot_value = self.read_mcp3008_smooth(0)
        
        for i, band in enumerate(BANDS):
            if band.contains(pot_value):
                return i, pot_value  # Return band index and ADC value
        
        return None, pot_value  # Return None if outside all bands
    
    def cleanup(self):
        """Clean up SPI resources and GPIO"""
        self.spi.close()
        # Note: GPIO.cleanup() is called in main() to clean up all GPIO pins

class Display:
    """Singleton class to control 6 LEDs on I2C interface"""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Display, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not Display._initialized:
            self.pin_state = 0xFF  # Initial state: all pins high (LEDs off)
            self.bus = smbus.SMBus(1)
            self.i2c_address = 0x20
            Display._initialized = True
    
    def set_i2c_pin(self, pin, state):
        """Set state of specific pin on PCF8574"""
        if state:
            self.pin_state |= (1 << pin)  # Set pin high (LED off)
        else:
            self.pin_state &= ~(1 << pin)  # Set pin low (LED on)
    
    def write_i2c_pins(self):
        """Write current pin state to PCF8574"""
        self.bus.write_byte(self.i2c_address, self.pin_state)
    
    def reset_all_leds(self):
        """Reset all LEDs to off state"""
        self.pin_state = 0xFF
        self.write_i2c_pins()
    
    def ShowTunerLed(self, on):
        """Turn the tuner LED (pin 0) on or off"""
        self.set_i2c_pin(0, not on)  # Invert because False = LED on
        self.write_i2c_pins()

class DeeJay:
    """Singleton class to handle band transitions"""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeeJay, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not DeeJay._initialized:
            self.display = Display()
            DeeJay._initialized = True
    
    def Play(self, band, adc_value):
        """Called when entering a band"""
        print(f"Entered {band.name} (ADC: {adc_value})")
        print(f"URL: {band.url}")
        
        # Execute MPC commands to add and play the URL
        try:
            # Add the URL to MPC playlist
            subprocess.run(["mpc", "add", band.url], check=True, capture_output=True, text=True)
            print(f"Added {band.url} to playlist")
            
            # Start playing
            subprocess.run(["mpc", "play"], check=True, capture_output=True, text=True)
            print("Started playback")
            
        except subprocess.CalledProcessError as e:
            print(f"Error executing MPC command: {e}")
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")
        
        # Turn on tuner LED when entering any band
        self.display.ShowTunerLed(True)
    
    def Stop(self, band, adc_value):
        """Called when leaving a band"""
        print(f"Left {band.name} (ADC: {adc_value})")
        
        # Execute MPC command to clear playlist
        try:
            subprocess.run(["mpc", "clear"], check=True, capture_output=True, text=True)
            print("Cleared playlist")
        except subprocess.CalledProcessError as e:
            print(f"Error executing MPC clear command: {e}")
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")
        
        # Turn off tuner LED when leaving any band
        self.display.ShowTunerLed(False)

# GPIO configuration is now handled by individual classes

# Define bands with their ranges and URLs
BANDS = [
    Band(305, 335, "http://abm21.com.au:8000/CONTAINER92", "Band 1"),
    Band(360, 395, "http://abm21.com.au:8000/CONTAINER87", "Band 2"),
    Band(430, 468, "http://abm21.com.au:8000/CONTAINER81", "Band 3")
]

# Initialize singleton instances
tuner = Tuner()
display = Display()
dj = DeeJay()

# Track current state
current_band = None

def main():
    global current_band
    
    print("Starting Raspberry Pi Tuner...")
    print("Bands:")
    for i, band in enumerate(BANDS):
        print(f"  {band}")
    print("Press Ctrl+C to exit\n")
    
    # Initialize LEDs
    display.reset_all_leds()
    
    try:
        while True:
            # Get current band from tuner
            new_band, adc_value = tuner.get_band()
            
            # Check for band changes
            if new_band != current_band:
                # Handle leaving previous band
                if current_band is not None:
                    dj.Stop(BANDS[current_band], adc_value)
                
                # Handle entering new band
                if new_band is not None:
                    dj.Play(BANDS[new_band], adc_value)
                else:
                    print(f"Outside all bands (ADC: {adc_value})")
                
                # Update current band
                current_band = new_band
            
            # Sleep for approximately 1/60th of a second (60 Hz)
            time.sleep(1/60)
            
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    finally:
        # Cleanup
        display.reset_all_leds()
        tuner.cleanup()
        GPIO.cleanup()
        print("Cleanup completed.")

if __name__ == "__main__":
    main()
