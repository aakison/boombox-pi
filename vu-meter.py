import asyncio
import os
import subprocess

import numpy as np

from boombox_function import IBoomboxFunction
from display import Display

# These must match the "VU Meter" fifo audio_output in mpd.conf
MPD_OUTPUT_NAME = "VU Meter"
FIFO_PATH = "/var/lib/mpd/vu.fifo"
SAMPLE_RATE = 44100
BYTES_PER_SAMPLE = 2  # 16-bit mono

ANALYSIS_RATE_HZ = 30
ANALYSIS_PERIOD_S = 1 / ANALYSIS_RATE_HZ
WINDOW_BYTES = (SAMPLE_RATE // ANALYSIS_RATE_HZ) * BYTES_PER_SAMPLE  # One tick's worth of audio
READ_CHUNK_BYTES = 65536  # Linux default pipe buffer size

LEVEL_THRESHOLDS_DB = [-30, -26, -21, -15, -9]  # RMS dBFS needed to light LEDs 1..5
DECAY_DB_PER_S = 40  # Slow fall so the bar doesn't flicker between ticks
FLOOR_DB = -90.0
FIFO_RETRY_S = 1

class VUMeter(IBoomboxFunction):
    """Shows the MPD output level on the 5 sound-level LEDs, read from MPD's fifo output"""

    def __init__(self):
        self.display = Display()
        self._running = False
        self._task = None
        self._fd = None
        self._carry = b""
        self._level_db = FLOOR_DB
        self._level = 0

    def start(self):
        """Enable MPD's fifo output and start analysing it"""
        if self._running:
            return
        self._running = True
        self._level_db = FLOOR_DB
        self._level = 0
        self.display.set_sound_level(0)
        self._set_mpd_output(True)
        self._task = asyncio.create_task(self._run())
        print("VU Meter started")

    def stop(self):
        """Stop analysing, disable MPD's fifo output and clear the LEDs"""
        if not self._running:
            return
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._close_fifo()
        self._set_mpd_output(False)
        self.display.set_sound_level(0)
        print("VU Meter stopped")

    def is_running(self):
        """Return True if the VU meter is currently running"""
        return self._running

    async def _run(self):
        """Analyse the latest audio at a fixed 30 Hz until stopped"""
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while self._running:
            if self._fd is None and not self._open_fifo():
                await asyncio.sleep(FIFO_RETRY_S)
                next_tick = loop.time()
                continue

            self._update_level(self._read_latest_window())

            next_tick += ANALYSIS_PERIOD_S
            delay = next_tick - loop.time()
            if delay < 0:
                # Fell behind - resync rather than bursting to catch up
                next_tick = loop.time()
                delay = 0
            await asyncio.sleep(delay)

    def _open_fifo(self):
        """Open the FIFO non-blocking, returning False if MPD hasn't created it"""
        try:
            self._fd = os.open(FIFO_PATH, os.O_RDONLY | os.O_NONBLOCK)
        except FileNotFoundError:
            print(f"Waiting for {FIFO_PATH} - is the '{MPD_OUTPUT_NAME}' output in /etc/mpd.conf?")
            return False
        self._carry = b""
        return True

    def _close_fifo(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self._carry = b""

    def _read_latest_window(self):
        """Drain the FIFO and return the most recent tick of samples, or None if no audio arrived"""
        data = self._carry
        while True:
            try:
                chunk = os.read(self._fd, READ_CHUNK_BYTES)
            except BlockingIOError:
                break
            if not chunk:
                # MPD closed its write end (e.g. restarted) - reopen on a later tick
                self._close_fifo()
                data = b""
                break
            data += chunk

        # Keep any trailing odd byte so samples stay aligned across reads
        usable = len(data) - (len(data) % BYTES_PER_SAMPLE)
        if self._fd is not None:
            self._carry = data[usable:]
        if usable == 0:
            return None
        return np.frombuffer(data[max(0, usable - WINDOW_BYTES):usable], dtype="<i2")

    def _update_level(self, samples):
        """Convert samples to RMS dBFS with instant attack and slow decay, and update the LEDs on change"""
        measured_db = FLOOR_DB
        if samples is not None:
            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
            if rms > 0:
                measured_db = 20 * np.log10(rms / 32768)

        decayed_db = self._level_db - DECAY_DB_PER_S * ANALYSIS_PERIOD_S
        self._level_db = max(measured_db, decayed_db, FLOOR_DB)

        level = sum(self._level_db >= threshold for threshold in LEVEL_THRESHOLDS_DB)
        if level != self._level:
            self._level = level
            self.display.set_sound_level(level)

    def _set_mpd_output(self, enabled):
        command = "enable" if enabled else "disable"
        try:
            subprocess.run(["mpc", command, MPD_OUTPUT_NAME], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running 'mpc {command} {MPD_OUTPUT_NAME}' (exit {e.returncode}): stdout={e.stdout!r} stderr={e.stderr!r}")
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")

async def main():
    meter = VUMeter()
    meter.start()
    print("VU Meter running - play something with mpc. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping VU Meter...")
    finally:
        meter.stop()

if __name__ == "__main__":
    asyncio.run(main())
