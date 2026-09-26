import spidev
import time
import subprocess
import asyncio
import RPi.GPIO as GPIO

from display import Display

# Hardware pin constants
TUNER_SWITCH_PIN = 17  # GPIO pin 17 used as on/off switch (HIGH=off, LOW=on)
SPOTIFY_SWITCH_PIN = 23  # GPIO pin 23 used to toggle Spotify Connect (HIGH=on, LOW=off)

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
            # Initialize GPIO for tuner switch
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(TUNER_SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_OFF)  # Switch input, external 10K pull-down
            GPIO.setup(SPOTIFY_SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # Spotify switch, pull-down
            
            # Initialize SPI for MCP3008, using hardware chip select (CE1 on GPIO7)
            self.spi = spidev.SpiDev()
            self.spi.open(0, 1)  # SPI bus 0, CE1 (GPIO7)
            self.spi.max_speed_hz = 1350000  # MCP3008 rated speed at 3.3V
            self.spi.mode = 0
            Tuner._initialized = True
    
    def read_mcp3008(self, channel):
        """Read ADC value from MCP3008"""
        if channel < 0 or channel > 7:
            raise ValueError("Channel must be 0-7")
        
        adc = self.spi.xfer2([1, (8 + channel) << 4, 0])  # SPI transfer
        data = ((adc[1] & 3) << 8) + adc[2]  # Combine 10-bit result
        return data
    
    async def read_mcp3008_smooth(self, channel, samples=15):
        """Read smoothed ADC value from MCP3008 averaged over multiple samples"""
        if samples <= 0:
            raise ValueError("Samples must be greater than 0")
        
        total = 0
        for _ in range(samples):
            total += self.read_mcp3008(channel)
            # Small delay between samples to allow for settling
            await asyncio.sleep(0.001)  # 1ms delay
        
        return total // samples  # Return integer average
    
    def is_on(self):
        """Check if the tuner is currently on by reading the switch pin"""
        # LOW = on, HIGH = off
        return GPIO.input(TUNER_SWITCH_PIN) == GPIO.LOW
    
    async def get_band(self):
        """Get the current band based on smoothed ADC reading"""
        # If tuner is off, return None regardless of potentiometer position
        if not self.is_on():
            return None, 0  # Return None for band and 0 for ADC value
        
        pot_value = await self.read_mcp3008_smooth(0)
        
        for i, band in enumerate(BANDS):
            if band.contains(pot_value):
                return i, pot_value  # Return band index and ADC value
        
        return None, pot_value  # Return None if outside all bands
    
    
    def cleanup(self):
        """Clean up SPI resources and GPIO"""
        self.spi.close()
        # Note: GPIO.cleanup() is called in main() to clean up all GPIO pins

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
    
    def play(self, band, adc_value):
        """Called when entering a band"""
        print(f"Entered {band.name} (ADC: {adc_value})")
        print(f"URL: {band.url}")
        
        # Execute MPC commands to add and play the URL
        try:
            # Turn on tuner LED when entering any band
            self.display.show_tuner_led(True)
            # Add the URL to MPC playlist
            add_result = subprocess.run(["mpc", "add", band.url], check=True, capture_output=True, text=True)
            print(f"Added {band.url} to playlist: {add_result.stdout.strip() or '(no output)'}")
            
            # Start playing
            play_result = subprocess.run(["mpc", "play"], check=True, capture_output=True, text=True)
            print(f"Started playback: {play_result.stdout.strip() or '(no output)'}")
            
            # Announce the band name only after successful playback start
            self.announce(band.name)
            
        except subprocess.CalledProcessError as e:
            print(f"Error executing MPC command (exit {e.returncode}): stdout={e.stdout!r} stderr={e.stderr!r}")
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")
       
   
    def stop(self, band, adc_value):
        """Called when leaving a band"""
        print(f"Left {band.name} (ADC: {adc_value})")
        
        # Execute MPC command to clear playlist
        try:
            clear_result = subprocess.run(["mpc", "clear"], check=True, capture_output=True, text=True)
            print(f"Cleared playlist: {clear_result.stdout.strip() or '(no output)'}")
        except subprocess.CalledProcessError as e:
            print(f"Error executing MPC clear command (exit {e.returncode}): stdout={e.stdout!r} stderr={e.stderr!r}")
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")
        
        # Turn off tuner LED when leaving any band
        self.display.show_tuner_led(False)
    
    def announce(self, text):
        """Announce text using espeak and aplay (non-blocking)"""
        try:
            # Use bash & to run in background, making it non-blocking
            command = f'espeak "{text}" --stdout | aplay -D plug:espeak &'
            result = subprocess.run(command, shell=True, check=False, capture_output=True, text=True)  # Don't check return code for background process
            print(f"Announcing: {text} (exit {result.returncode}, stderr={result.stderr.strip() or '(none)'})")
        except FileNotFoundError:
            print("Error: espeak or aplay command not found. Please ensure they are installed.")

# GPIO configuration is now handled by individual classes

# Define bands with their ranges and URLs
BANDS = [
    Band(181, 215, "http://abm21.com.au:8000/CONTAINER81", "Band 1"),
    Band(235, 270, "http://abm21.com.au:8000/CONTAINER92", "Band 3"),
    Band(305, 335, "http://abm21.com.au:8000/CONTAINER86", "Radio Sydney, 80s Pop Charts"),
    Band(360, 395, "http://abm21.com.au:8000/CONTAINER87", "Radio Sydney, 80s Alternative"),
    Band(430, 468, "http://abm21.com.au:8000/CONTAINER90", "Radio Sydney, 90s Pop Charts"),
    Band(483, 548, "http://abm21.com.au:8000/CONTAINER91", "Radio Sydney, 90s Alternative"),
    Band(568, 624, "https://stream.revma.ihrhls.com/zc397", "93.3 K.T.C.L. Denver (K-Tickle)"),
    Band(644, 700, "https://live-radio01.mediahubaustralia.com/2TJW/mp3/", "Triple J Sydney"),
    Band(720, 776, "https://live.amperwave.net/direct/audacy-kroqfmaac-imc", "K.R.O.Q. Los Angeles (K-Rock)")
]

# Initialize singleton instances
tuner = Tuner()
display = Display()
dj = DeeJay()

# Track current state
current_band = None
spotify_active = False

def set_spotify(on):
    """Start or stop the Raspotify service"""
    global spotify_active
    if on and not spotify_active:
        try:
            subprocess.run(["sudo", "systemctl", "start", "raspotify.service"], check=True, capture_output=True, text=True)
            spotify_active = True
            print("Spotify Connect started")
            dj.announce("Spotify Connect")
        except subprocess.CalledProcessError as e:
            print(f"Error starting Raspotify: {e}")
    elif not on and spotify_active:
        try:
            subprocess.run(["sudo", "systemctl", "stop", "raspotify.service"], check=True, capture_output=True, text=True)
            spotify_active = False
            print("Spotify Connect stopped")
        except subprocess.CalledProcessError as e:
            print(f"Error stopping Raspotify: {e}")

async def main():
    global current_band
    
    print("Starting Raspberry Pi Tuner...")
    print("Bands:")
    for i, band in enumerate(BANDS):
        print(f"  {band}")
    print("Press Ctrl+C to exit\n")
    
    # Initialize LEDs
    display.reset_all_leds()
    
    display.start_meter_cylon()

    try:
        while True:
            # Get current band from tuner
            new_band, adc_value = await tuner.get_band()
            
            # Check for band changes
            if new_band != current_band:
                # Handle leaving previous band
                if current_band is not None:
                    dj.stop(BANDS[current_band], adc_value)
                
                # Handle entering new band
                if new_band is not None:
                    dj.play(BANDS[new_band], adc_value)
                else:
                    print(f"Outside all bands (ADC: {adc_value})")
                
                # Update current band
                current_band = new_band
            
            # Check Spotify switch (pin 23)
            spotify_pin = GPIO.input(SPOTIFY_SWITCH_PIN)
            set_spotify(spotify_pin == GPIO.HIGH)

            # Sleep for approximately 1/60th of a second (60 Hz)
            await asyncio.sleep(1/60)
            
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    finally:
        # Cleanup
        display.reset_all_leds()
        tuner.cleanup()
        GPIO.cleanup()
        print("Cleanup completed.")

if __name__ == "__main__":
    asyncio.run(main())
