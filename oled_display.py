import asyncio
import subprocess

import smbus
from PIL import Image, ImageDraw, ImageFont

MPD_HOST = "boombox"  # Hostname of the Pi running MPD; this Pi only drives the display
POLL_INTERVAL_S = 1  # How often to poll MPC for the current artist/track

I2C_BUS = 1
I2C_ADDRESS = 0x3C  # Default for these 0.91" SSD1306 clones; some boards reply on 0x3D instead

MUX_ADDRESS = 0x70  # Default TCA9548A address
MUX_CHANNEL_ARTIST = 0  # Display wired to the mux's SD0/SC0 pair
MUX_CHANNEL_TITLE = 1  # Display wired to the mux's SD1/SC1 pair

WIDTH = 128
HEIGHT = 32
PAGES = HEIGHT // 8  # SSD1306 GDDRAM is addressed in 8-pixel-tall pages

# Change these to try different installed fonts/sizes without touching any drawing code
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
# FONT_PATH = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_SIZE = 16
FONT_SIZE_LARGE = 24  # Used when the text fits on one line at this size, else falls back to FONT_SIZE

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


class I2CMultiplexer:
    """Thin wrapper around a TCA9548A that selects one downstream channel at a time on a shared bus"""

    def __init__(self, bus=I2C_BUS, address=MUX_ADDRESS):
        self.bus = smbus.SMBus(bus)
        self.address = address
        self._active_channel = None

    def is_connected(self):
        """Return True if the mux itself acknowledges on the main I2C bus"""
        try:
            self.bus.write_quick(self.address)
            return True
        except OSError as e:
            print(f"TCA9548A mux not responding at 0x{self.address:02X}: {e}")
            return False

    def select_channel(self, channel):
        """Enable only the given channel (0-7), skipping the write if it's already active"""
        if channel != self._active_channel:
            self.bus.write_byte(self.address, 1 << channel)
            self._active_channel = channel

    def read_active_channel(self):
        """Read back the mux's channel-select register, for debugging whether a select actually took"""
        try:
            return self.bus.read_byte(self.address)
        except OSError as e:
            print(f"Could not read back mux channel-select register at 0x{self.address:02X}: {e}")
            return None

    def scan_channel(self, channel):
        """Print every address that acks on the given channel, like running i2cdetect on it"""
        self.select_channel(channel)
        found = []
        for addr in range(0x03, 0x78):
            try:
                self.bus.write_quick(addr)
                found.append(addr)
            except OSError:
                pass
        addrs = ", ".join(f"0x{a:02X}" for a in found) if found else "none"
        print(f"Mux channel {channel}: devices found at {addrs}")


class OledDisplay:
    """Driver for a 0.91" 128x32 SSD1306-based I2C OLED module, reached through a TCA9548A mux channel"""

    def __init__(self, mux, channel, address=I2C_ADDRESS):
        self.mux = mux
        self.channel = channel
        self.address = address

    def is_connected(self):
        """Return True if the display acknowledges a write on the I2C bus

        Many cheap SSD1306 clones are write-only slaves that never ack a read,
        so a write_quick probe is used instead of reading a byte back.
        """
        try:
            self.mux.select_channel(self.channel)
        except OSError as e:
            print(f"Could not select mux channel {self.channel} on 0x{self.mux.address:02X}: {e}")
            return False

        try:
            self.mux.bus.write_quick(self.address)
            return True
        except OSError as e:
            print(f"OLED not responding at 0x{self.address:02X} on mux channel {self.channel}: {e}")
            self.mux.scan_channel(self.channel)
            return False

    def _write_command(self, *commands):
        """Send one or more command bytes"""
        self.mux.select_channel(self.channel)
        self.mux.bus.write_i2c_block_data(self.address, CONTROL_COMMAND, list(commands))

    def _write_data(self, data):
        """Send raw pixel data to GDDRAM, chunked to fit the I2C block size limit"""
        self.mux.select_channel(self.channel)
        for start in range(0, len(data), MAX_I2C_BLOCK):
            chunk = data[start:start + MAX_I2C_BLOCK]
            self.mux.bus.write_i2c_block_data(self.address, CONTROL_DATA, chunk)

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

    def draw_text(self, text, font_path=FONT_PATH):
        """Render text to the full frame, preferring FONT_SIZE_LARGE if it fits on one line unwrapped"""
        image = Image.new("L", (WIDTH, HEIGHT), 0)
        draw = ImageDraw.Draw(image)

        font = ImageFont.truetype(font_path, FONT_SIZE_LARGE)
        if draw.textlength(text, font=font) <= WIDTH:
            lines = [text]
        else:
            font = ImageFont.truetype(font_path, FONT_SIZE)
            lines = _wrap_text(draw, text, font, WIDTH)

        _, top, _, bottom = font.getbbox("Ay")
        line_height = bottom - top - 1  # Tighten slightly so 2 lines fit the 32px panel without clipping descenders
        y = 0
        for line in lines:
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


def _get_current_track():
    """Query MPD on MPD_HOST for the currently playing artist and track title via MPC"""
    try:
        result = subprocess.run(
            ["mpc", "-h", MPD_HOST, "current", "--format", "%artist%\t%title%"],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error querying MPC (exit {e.returncode}): stdout={e.stdout!r} stderr={e.stderr!r}")
        return "", ""
    except FileNotFoundError:
        print("Error: MPC command not found. Please ensure MPD/MPC is installed.")
        return "", ""

    line = result.stdout.strip()
    if not line:
        return "", "Nothing playing"
    artist, _, title = line.partition("\t")
    return artist, title


async def main():
    """Poll MPD on MPD_HOST once a second, showing artist on one OLED and track title on the other"""
    mux = I2CMultiplexer()
    if not mux.is_connected():
        print(f"No TCA9548A mux detected at 0x{MUX_ADDRESS:02X} on bus {I2C_BUS} - check wiring/address")
        return

    artist_display = OledDisplay(mux, MUX_CHANNEL_ARTIST)
    title_display = OledDisplay(mux, MUX_CHANNEL_TITLE)

    displays_ok = True
    for display in (artist_display, title_display):
        if not display.is_connected():
            print(f"No OLED detected on mux channel {display.channel} (address 0x{I2C_ADDRESS:02X}) "
                  "- check wiring/address and try again")
            displays_ok = False
    if not displays_ok:
        return

    for display in (artist_display, title_display):
        display.init_display()
    try:
        while True:
            artist, title = await asyncio.to_thread(_get_current_track)
            if title == "Nothing playing":
                artist_display.clear()
                title_display.clear()
            else:
                artist_display.draw_text(artist)
                title_display.draw_text(title)
            await asyncio.sleep(POLL_INTERVAL_S)
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Ctrl+C cancels the running task (raising CancelledError here), not KeyboardInterrupt directly
        print("\nProgram terminated by user.")
    finally:
        for display in (artist_display, title_display):
            display.clear()
            display.set_power(False)

if __name__ == "__main__":
    asyncio.run(main())

