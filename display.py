import smbus
import asyncio

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
            self.cylon_task = None
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
    
    def reset_cylon_leds(self):
        """Reset only cylon LEDs (pins 1-5) while preserving pin 0 state"""
        # Turn off pins 1, 2, 3, 4, 5 but preserve pin 0
        for pin in [1, 2, 3, 4, 5]:
            self.set_i2c_pin(pin, True)  # True = LED off
        self.write_i2c_pins()
    
    def show_tuner_led(self, on):
        """Turn the tuner LED (pin 0) on or off"""
        self.set_i2c_pin(0, not on)  # Invert because False = LED on
        self.write_i2c_pins()
    
    async def _cylon_pattern(self):
        """Internal async cylon pattern - runs as independent task"""
        pins = [1, 2, 5, 4, 3, 4, 5, 2]
        try:
            while True:
                for pin in pins:
                    # Reset only cylon LEDs (preserve pin 0 tuner LED)
                    self.reset_cylon_leds()
                    # Turn on current pin
                    self.set_i2c_pin(pin, False)  # False = LED on
                    self.write_i2c_pins()
                    await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            # Clean up when task is cancelled - only reset cylon LEDs
            self.reset_cylon_leds()
            print("Stopped cylon LED pattern")
            raise
    
    def start_meter_cylon(self):
        """Start the cylon LED pattern as an async task"""
        if self.cylon_task is None or self.cylon_task.done():
            self.cylon_task = asyncio.create_task(self._cylon_pattern())
            print("Started cylon LED pattern")
    
    def stop_meter_cylon(self):
        """Stop the cylon LED pattern"""
        if self.cylon_task and not self.cylon_task.done():
            self.cylon_task.cancel()
            self.cylon_task = None


async def main():
    """Run the cylon LED animation until interrupted"""
    display = Display()
    display.reset_all_leds()
    display.start_meter_cylon()
    try:
        await display.cylon_task
    except asyncio.CancelledError:
        pass
    finally:
        display.reset_all_leds()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
