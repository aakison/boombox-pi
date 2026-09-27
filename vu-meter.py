import asyncio
import audioop
import math
import subprocess

from boombox_function import IBoomboxFunction
from display import Display

# Capture side of the snd-aloop tap that duplicates the shared mixer (see
# asound.conf's dup_out and aloop.conf).
DEVICE = "hw:Loopback,1"
SAMPLE_RATE = 44100
CHANNELS = 2
SAMPLE_WIDTH = 2  # bytes per sample, matches asound.conf's S16_LE

UPDATE_HZ = 30
FRAMES_PER_CHUNK = SAMPLE_RATE // UPDATE_HZ
CHUNK_BYTES = FRAMES_PER_CHUNK * CHANNELS * SAMPLE_WIDTH

MAX_LEVEL = 5  # number of lit LEDs; Display.set_sound_level accepts 0-5
MIN_DBFS = -50.0  # silence floor, matches asound.conf's softvol min_dB
MAX_DBFS = 0.0
ATTACK = 0.6  # fraction of the gap closed per update while rising (fast)
DECAY = 0.05  # fraction of the gap closed per update while falling (slow)

class VUMeter(IBoomboxFunction):
    """Drives the 5-LED bar graph from the shared audio mixer via the ALSA loopback tap"""

    def __init__(self):
        self.display = Display()
        self._running = False
        self._process = None
        self._meter_task = None
        self._smoothed_dbfs = MIN_DBFS

    def start(self):
        """Start capturing from the loopback device and updating the LED bar graph"""
        if self._running:
            return
        try:
            self._process = subprocess.Popen(
                ["arecord", "-D", DEVICE, "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS), "-t", "raw"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("Error: arecord command not found. Please ensure alsa-utils is installed.")
            return
        self._running = True
        self._smoothed_dbfs = MIN_DBFS
        self._meter_task = asyncio.create_task(self._run())
        print("VU meter started")

    def stop(self):
        """Stop capturing and clear the LED bar graph"""
        if not self._running:
            return
        self._running = False
        if self._process is not None:
            self._process.kill()  # unblocks the background read so _run can exit
            self._process.wait()
            self._process = None
        if self._meter_task and not self._meter_task.done():
            self._meter_task.cancel()
        self._meter_task = None
        self.display.set_sound_level(0)
        print("VU meter stopped")

    def is_running(self):
        """Return True if the VU meter is currently running"""
        return self._running

    async def _run(self):
        """Read PCM chunks from the loopback tap and update the LEDs at UPDATE_HZ until stopped"""
        try:
            while self._running:
                chunk = await asyncio.to_thread(self._read_chunk)
                if chunk is None:
                    break
                self.display.set_sound_level(self._chunk_to_level(chunk))
        except asyncio.CancelledError:
            raise

    def _read_chunk(self):
        """Block until CHUNK_BYTES of raw PCM are available, or return None on EOF"""
        buf = bytearray()
        while len(buf) < CHUNK_BYTES:
            data = self._process.stdout.read(CHUNK_BYTES - len(buf))
            if not data:
                return None
            buf.extend(data)
        return bytes(buf)

    def _chunk_to_level(self, chunk):
        """Map one PCM chunk to a 0-5 LED level with fast-attack/slow-decay ballistics"""
        rms = audioop.rms(chunk, SAMPLE_WIDTH)
        dbfs = 20 * math.log10(rms / 32768) if rms > 0 else MIN_DBFS
        dbfs = max(MIN_DBFS, min(MAX_DBFS, dbfs))

        rate = ATTACK if dbfs > self._smoothed_dbfs else DECAY
        self._smoothed_dbfs += (dbfs - self._smoothed_dbfs) * rate

        fraction = (self._smoothed_dbfs - MIN_DBFS) / (MAX_DBFS - MIN_DBFS)
        return round(fraction * MAX_LEVEL)


async def main():
    """Run the VU meter standalone; play audio via `mpc play` or `speaker-test` to see it react"""
    vu_meter = VUMeter()
    vu_meter.start()
    print("VU meter running. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping VU meter...")
    finally:
        vu_meter.stop()

if __name__ == "__main__":
    asyncio.run(main())
