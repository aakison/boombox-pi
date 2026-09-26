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
            self.stereo_task = None
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
    
    def set_sound_level(self, level):
        """Light up the sound meter LEDs (pins 1-5) as a bar graph, 0-5 lit"""
        if not 0 <= level <= 5:
            raise ValueError("level must be between 0 and 5")
        for i, pin in enumerate([1, 2, 3, 4, 5], start=1):
            self.set_i2c_pin(pin, i > level)  # LED on while its position is within the level
        self.write_i2c_pins()
    
    def set_stereo(self, on):
        """Turn the stereo LED (pin 0) on or off"""
        self.set_i2c_pin(0, not on)  # pin state is inverted: low = LED on
        self.write_i2c_pins()
    
    async def _cylon_pattern(self):
        """Internal async cylon pattern - runs as independent task"""
        pins = [1, 2, 5, 4, 3, 4, 5, 2]
        try:
            while True:
                for pin in pins:
                    # Reset only cylon LEDs (preserve pin 0 stereo LED)
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
    
    def start_cylon_animation(self):
        """Start the cylon LED pattern as an independent async task"""
        if self.cylon_task is None or self.cylon_task.done():
            self.cylon_task = asyncio.create_task(self._cylon_pattern())
            print("Started cylon LED pattern")
    
    def stop_cylon_animation(self):
        """Stop the cylon LED pattern"""
        if self.cylon_task and not self.cylon_task.done():
            self.cylon_task.cancel()
            self.cylon_task = None
    
    async def _stereo_flash_pattern(self, speed):
        """Internal async stereo LED flash pattern - runs as independent task"""
        half_cycle = (speed / 1000) / 2
        try:
            while True:
                self.set_stereo(True)
                await asyncio.sleep(half_cycle)
                self.set_stereo(False)
                await asyncio.sleep(half_cycle)
        except asyncio.CancelledError:
            self.set_stereo(False)
            print("Stopped stereo LED animation")
            raise
    
    def start_stereo_animation(self, speed):
        """Start flashing the stereo LED as an independent async task, speed in ms per cycle"""
        if self.stereo_task is None or self.stereo_task.done():
            self.stereo_task = asyncio.create_task(self._stereo_flash_pattern(speed))
            print("Started stereo LED animation")
    
    def stop_stereo_animation(self):
        """Stop flashing the stereo LED"""
        if self.stereo_task and not self.stereo_task.done():
            self.stereo_task.cancel()
            self.stereo_task = None


async def main():
    """Run the cylon and stereo flash animations together until interrupted"""
    display = Display()
    display.reset_all_leds()
    display.start_cylon_animation()
    display.start_stereo_animation(500)
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    finally:
        display.stop_cylon_animation()
        display.stop_stereo_animation()
        display.reset_all_leds()

if __name__ == "__main__":
    asyncio.run(main())
