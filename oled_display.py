import asyncio

import smbus

I2C_BUS = 1
I2C_ADDRESS = 0x3C  # Default for these 0.91" SSD1306 clones; some boards reply on 0x3D instead

WIDTH = 128
HEIGHT = 32
PAGES = HEIGHT // 8  # SSD1306 GDDRAM is addressed in 8-pixel-tall pages

CONTROL_COMMAND = 0x00
CONTROL_DATA = 0x40
MAX_I2C_BLOCK = 32  # smbus write_i2c_block_data payload limit, so writes are sent in chunks

# Standard SSD1306 startup sequence for a 128x32 panel
INIT_SEQUENCE = [
    0xAE,              # Display off
    0xD5, 0x80,        # Set display clock divide ratio/oscillator frequency
    0xA8, HEIGHT - 1,  # Set multiplex ratio
    0xD3, 0x00,        # Set display offset
    0x40,              # Set display start line = 0
    0x8D, 0x14,        # Enable charge pump
    0x20, 0x00,        # Memory addressing mode = horizontal
    0xA1,              # Segment remap (column 127 mapped to SEG0)
    0xC8,              # COM output scan direction, remapped
    0xDA, 0x02,        # COM pins hardware configuration
    0x81, 0x8F,        # Set contrast
    0xD9, 0xF1,        # Set pre-charge period
    0xDB, 0x40,        # Set VCOMH deselect level
    0xA4,              # Resume to RAM content display
    0xA6,              # Normal (not inverted) display
    0xAF,              # Display on
]


class OledDisplay:
    """Singleton class driving a 0.91" 128x32 SSD1306-based I2C OLED module"""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(OledDisplay, cls).__new__(cls)
        return cls._instance

    def __init__(self, bus=I2C_BUS, address=I2C_ADDRESS):
        if not OledDisplay._initialized:
            self.bus = smbus.SMBus(bus)
            self.address = address
            OledDisplay._initialized = True

    def is_connected(self):
        """Return True if the display acknowledges on the I2C bus, for a basic wiring/address check"""
        try:
            self.bus.read_byte(self.address)
            return True
        except OSError as e:
            print(f"OLED not responding at 0x{self.address:02X}: {e}")
            return False

    def _write_command(self, *commands):
        """Send one or more command bytes"""
        self.bus.write_i2c_block_data(self.address, CONTROL_COMMAND, list(commands))

    def _write_data(self, data):
        """Send raw pixel data to GDDRAM, chunked to fit the I2C block size limit"""
        for start in range(0, len(data), MAX_I2C_BLOCK):
            chunk = data[start:start + MAX_I2C_BLOCK]
            self.bus.write_i2c_block_data(self.address, CONTROL_DATA, chunk)

    def init_display(self):
        """Run the SSD1306 startup sequence and blank the screen"""
        self._write_command(*INIT_SEQUENCE)
        self.clear()
        print("OLED display initialised")

    def _set_addressing_window(self):
        """Point GDDRAM writes at the full 128x32 frame"""
        self._write_command(0x21, 0, WIDTH - 1)  # Column address range
        self._write_command(0x22, 0, PAGES - 1)  # Page address range

    def fill(self, on):
        """Turn every pixel on the panel on or off, useful as a simple connectivity test"""
        self._set_addressing_window()
        pattern = 0xFF if on else 0x00
        self._write_data([pattern] * (WIDTH * PAGES))

    def clear(self):
        """Turn off every pixel"""
        self.fill(False)

    def set_power(self, on):
        """Turn the display panel on or off without touching GDDRAM contents"""
        self._write_command(0xAF if on else 0xAE)


async def main():
    """Blink the whole screen on and off every 500ms to prove out I2C wiring and addressing"""
    display = OledDisplay()
    if not display.is_connected():
        print(f"No OLED detected at 0x{I2C_ADDRESS:02X} - check wiring/address and try again")
        return

    display.init_display()
    try:
        state = True
        while True:
            display.fill(state)
            state = not state
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    finally:
        display.clear()
        display.set_power(False)

if __name__ == "__main__":
    asyncio.run(main())
