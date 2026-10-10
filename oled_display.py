import asyncio

import smbus
from PIL import Image, ImageDraw, ImageFont

I2C_BUS = 1
I2C_ADDRESS = 0x3C  # Default for these 0.91" SSD1306 clones; some boards reply on 0x3D instead

WIDTH = 128
HEIGHT = 32
PAGES = HEIGHT // 8  # SSD1306 GDDRAM is addressed in 8-pixel-tall pages

# Change these to try different installed fonts/sizes without touching any drawing code
# FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
# FONT_PATH = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_PATH = "/home/adrian/boombox-pi/terminal16.ttf"
FONT_SIZE = 16

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

    def draw_text(self, text, font_path=FONT_PATH, font_size=FONT_SIZE):
        """Render (word-wrapped) text to the full frame using a TrueType font"""
        font = ImageFont.truetype(font_path, font_size)
        image = Image.new("L", (WIDTH, HEIGHT), 0)
        draw = ImageDraw.Draw(image)

        _, top, _, bottom = font.getbbox("Ay")
        line_height = bottom - top - 1  # Tighten slightly so 2 lines fit the 32px panel without clipping descenders
        y = 0
        for line in _wrap_text(draw, text, font, WIDTH):
            draw.text((0, y), line, fill=255, font=font)
            y += line_height

        bitmap = image.convert("1", dither=Image.NONE)  # Hard threshold - no dithering on a 1-bit panel
        self._set_addressing_window()
        self._write_data(_image_to_gddram(bitmap))

    def set_power(self, on):
        """Turn the display panel on or off without touching GDDRAM contents"""
        self._write_command(0xAF if on else 0xAE)


def _wrap_text(draw, text, font, max_width):
    """Greedily wrap text into lines that fit max_width pixels, measured with the given font"""
    lines = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _image_to_gddram(image):
    """Pack a 1-bit PIL image into SSD1306 paged GDDRAM byte layout (8 vertical pixels per byte, LSB on top)"""
    pixels = image.load()
    buffer = bytearray(WIDTH * PAGES)
    for page in range(PAGES):
        for x in range(WIDTH):
            byte = 0
            for bit in range(8):
                if pixels[x, page * 8 + bit]:
                    byte |= 1 << bit
            buffer[page * WIDTH + x] = byte
    return list(buffer)


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
            display.draw_text("AC / DC")
            await asyncio.sleep(1)
            display.draw_text("You shogk me all night long")
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    finally:
        display.clear()
        display.set_power(False)

if __name__ == "__main__":
    asyncio.run(main())

