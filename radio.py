import asyncio
import subprocess

from boombox_function import IBoomboxFunction
from announcer import Announcer
from display import Display
from input import Input

TUNER_SAMPLES = 15  # Number of ADC samples averaged per tuner reading
TUNER_POLL_INTERVAL_S = 1 / 60  # 60 Hz poll rate for the tuner dial

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

# Define bands with their ranges and URLs
BANDS = [
    Band(181, 215, "http://abm21.com.au:8000/CONTAINER81", "Band 1"),
    Band(235, 270, "http://abm21.com.au:8000/CONTAINER92", "Band 3"),
    Band(305, 335, "http://abm21.com.au:8000/CONTAINER86", "Radio Sydney, 80s Pop Charts"),
    Band(360, 395, "http://abm21.com.au:8000/CONTAINER87", "Radio Sydney, 80s Alternative"),
    Band(430, 468, "http://abm21.com.au:8000/CONTAINER90", "Radio Sydney, 90s Pop Charts"),
    Band(483, 548, "http://abm21.com.au:8000/CONTAINER91", "Radio Sydney, 90s Alternative"),
    Band(568, 624, "https://stream.revma.ihrhls.com/zc397", "93.3 K.T.C.L. Denver (K-Tickle)"),
    Band(644, 700, "https://mediaserviceslive.akamaized.net/hls/live/2038315/doublejnsw/index.m3u8", "Double J"),
    Band(720, 776, "https://live.amperwave.net/direct/audacy-kroqfmaac-imc", "K.R.O.Q. Los Angeles (K-Rock)")
]

class Radio(IBoomboxFunction):
    """Tunes to a band based on the tuner dial and streams its URL via MPC"""

    def __init__(self):
        self.input = Input()
        self.announcer = Announcer()
        self.display = Display()
        self._running = False
        self._poll_task = None
        self._current_band = None

    def start(self):
        """Start polling the tuner dial and playing whichever band it lands on"""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._run())
        print("Radio started")

    def stop(self):
        """Stop polling and leave the current band if one is active"""
        if not self._running:
            return
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = None
        if self._current_band is not None:
            self._leave_band(BANDS[self._current_band], 0)
            self._current_band = None
        print("Radio stopped")

    def is_running(self):
        """Return True if the radio is currently polling/playing"""
        return self._running

    async def _run(self):
        """Poll the tuner dial and react to band changes until stopped"""
        try:
            while self._running:
                new_band, adc_value = await self._get_band()

                if new_band != self._current_band:
                    if self._current_band is not None:
                        self._leave_band(BANDS[self._current_band], adc_value)

                    if new_band is not None:
                        self._enter_band(BANDS[new_band], adc_value)
                    else:
                        print(f"Outside all bands (ADC: {adc_value})")

                    self._current_band = new_band

                await asyncio.sleep(TUNER_POLL_INTERVAL_S)
        except asyncio.CancelledError:
            raise

    async def _get_band(self):
        """Get the current band based on a smoothed tuner dial reading"""
        pot_value = await self._read_tuner_smooth()

        for i, band in enumerate(BANDS):
            if band.contains(pot_value):
                return i, pot_value

        return None, pot_value

    async def _read_tuner_smooth(self, samples=TUNER_SAMPLES):
        """Read the tuner dial averaged over multiple samples to reduce noise"""
        total = 0
        for _ in range(samples):
            total += self.input.get_Tuner()
            await asyncio.sleep(0.001)
        return total // samples

    def _enter_band(self, band, adc_value):
        """Borrowed from DeeJay.play: called when entering a band"""
        print(f"Entered {band.name} (ADC: {adc_value})")
        print(f"URL: {band.url}")

        try:
            # Turn on stereo LED when entering any band
            self.display.set_stereo(True)
            # Add the URL to MPC playlist
            add_result = subprocess.run(["mpc", "add", band.url], check=True, capture_output=True, text=True)
            print(f"Added {band.url} to playlist: {add_result.stdout.strip() or '(no output)'}")

            # Start playing
            play_result = subprocess.run(["mpc", "play"], check=True, capture_output=True, text=True)
            print(f"Started playback: {play_result.stdout.strip() or '(no output)'}")

            # Announce the band name only after successful playback start
            self.announcer.announce(band.name)

        except subprocess.CalledProcessError as e:
            print(f"Error executing MPC command (exit {e.returncode}): stdout={e.stdout!r} stderr={e.stderr!r}")
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")

    def _leave_band(self, band, adc_value):
        """Borrowed from DeeJay.stop: called when leaving a band"""
        print(f"Left {band.name} (ADC: {adc_value})")

        try:
            clear_result = subprocess.run(["mpc", "clear"], check=True, capture_output=True, text=True)
            print(f"Cleared playlist: {clear_result.stdout.strip() or '(no output)'}")
        except subprocess.CalledProcessError as e:
            print(f"Error executing MPC clear command (exit {e.returncode}): stdout={e.stdout!r} stderr={e.stderr!r}")
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")

        # Turn off stereo LED when leaving any band
        self.display.set_stereo(False)

async def main():
    radio = Radio()
    radio.start()
    print("Radio running. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Radio...")
    finally:
        radio.stop()

if __name__ == "__main__":
    asyncio.run(main())
