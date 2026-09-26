import asyncio
import os
import random
import subprocess
from collections import deque

from boombox_function import IBoomboxFunction
from announcer import Announcer
from display import Display
from input import Input

MUSIC_DIR = "/srv/music"
STEREO_FLASH_SPEED_MS = 250  # Flash speed while scanning the MP3 library
HISTORY_SIZE = 20  # Number of recently played tracks to avoid repeating
POLL_INTERVAL_S = 1  # How often to check whether the current track has finished

FINE_TUNE_POLL_INTERVAL_S = 1 / 60  # Poll rate for the fine-tune dial (60 Hz)
FINE_TUNE_THRESHOLD = 20  # ADC delta from baseline that counts as a deliberate dial move
FINE_TUNE_SETTLE_DELAY_S = 0.25  # Let the dial stop moving before reading its resting value

class Mp3Player(IBoomboxFunction):
    """Scans /srv/music for MP3s and plays them back-to-back in random order via MPC"""

    def __init__(self):
        self.announcer = Announcer()
        self.display = Display()
        self.input = Input()
        self._running = False
        self._tracks = []
        self._history = deque(maxlen=HISTORY_SIZE)
        self._playback_task = None
        self._fine_tune_task = None
        self._current_track = None
        self._restart_requested = False
        self._track_control_event = asyncio.Event()

    def start(self):
        """Start scanning the MP3 library and begin random playback"""
        if self._running:
            return
        self._running = True
        self._playback_task = asyncio.create_task(self._run())
        self._fine_tune_task = asyncio.create_task(self._watch_fine_tune())

    def stop(self):
        """Stop playback and turn off the display"""
        if not self._running:
            return
        self._running = False
        if self._playback_task and not self._playback_task.done():
            self._playback_task.cancel()
        self._playback_task = None
        if self._fine_tune_task and not self._fine_tune_task.done():
            self._fine_tune_task.cancel()
        self._fine_tune_task = None
        try:
            subprocess.run(["mpc", "stop"], check=True, capture_output=True, text=True)
            subprocess.run(["mpc", "clear"], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Error stopping MPC playback (exit {e.returncode}): stdout={e.stdout!r} stderr={e.stderr!r}")
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")
        finally:
            self.display.stop_stereo_animation()
            self.display.set_stereo(False)
            print("MP3 Player stopped")

    def is_running(self):
        """Return True if the MP3 player is currently running"""
        return self._running

    async def _run(self):
        """Load the library (flashing the display), then play random tracks until stopped"""
        self.display.start_stereo_animation(STEREO_FLASH_SPEED_MS)
        await asyncio.to_thread(self._update_mpd_database)
        self._tracks = await asyncio.to_thread(self._scan_library)
        self.display.stop_stereo_animation()

        if not self._tracks:
            print(f"No MP3 files found under {MUSIC_DIR}")
            self.display.set_stereo(False)
            self._running = False
            return

        self.display.set_stereo(True)
        self.announcer.announce("MP3 Player")

        try:
            while self._running:
                if self._restart_requested and self._current_track is not None:
                    track = self._current_track
                else:
                    track = self._choose_track()
                    self._current_track = track
                self._restart_requested = False
                self._track_control_event.clear()
                if self._play_track(track):
                    await self._wait_for_track_to_finish()
                else:
                    await asyncio.sleep(POLL_INTERVAL_S)
        except asyncio.CancelledError:
            raise

    def _update_mpd_database(self):
        """Force MPD to rescan MUSIC_DIR so mpc add can find files that aren't already in its database"""
        try:
            subprocess.run(["mpc", "update", "--wait"], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Error updating MPD database (exit {e.returncode}): stdout={e.stdout!r} stderr={e.stderr!r}")
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")

    def _scan_library(self):
        """Recursively find all MP3 files under MUSIC_DIR, returning paths relative to it"""
        tracks = []
        for root, _dirs, files in os.walk(MUSIC_DIR):
            for name in files:
                if name.lower().endswith(".mp3"):
                    full_path = os.path.join(root, name)
                    tracks.append(os.path.relpath(full_path, MUSIC_DIR))
        print(f"Found {len(tracks)} MP3 file(s) under {MUSIC_DIR}")
        return tracks

    def _choose_track(self):
        """Pick a random track, avoiding the last HISTORY_SIZE played tracks when possible"""
        candidates = [t for t in self._tracks if t not in self._history]
        if not candidates:
            # Library is small enough that everything is in recent history - allow a repeat
            candidates = self._tracks
        track = random.choice(candidates)
        self._history.append(track)
        return track

    def _play_track(self, track):
        """Clear the MPC playlist and start playing the given track (path relative to MUSIC_DIR)"""
        try:
            subprocess.run(["mpc", "clear"], check=True, capture_output=True, text=True)
            subprocess.run(["mpc", "add", track], check=True, capture_output=True, text=True)
            subprocess.run(["mpc", "play"], check=True, capture_output=True, text=True)
            print(f"Playing: {track}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error playing {track!r} (exit {e.returncode}): stdout={e.stdout!r} stderr={e.stderr!r}")
            return False
        except FileNotFoundError:
            print("Error: MPC command not found. Please ensure MPD/MPC is installed.")
            return False

    async def _wait_for_track_to_finish(self):
        """Poll MPC status until the current track finishes, or a next/restart request interrupts it"""
        while self._running:
            try:
                await asyncio.wait_for(self._track_control_event.wait(), timeout=POLL_INTERVAL_S)
            except asyncio.TimeoutError:
                pass
            if self._track_control_event.is_set():
                return
            if not self._is_playing():
                return

    async def _watch_fine_tune(self):
        """Watch the fine-tune dial and request a track skip/restart on deliberate moves"""
        baseline = self.input.get_FineTune()
        skip_settle_delay = False
        try:
            while self._running:
                await asyncio.sleep(FINE_TUNE_POLL_INTERVAL_S)
                value = self.input.get_FineTune()
                delta = value - baseline

                if delta >= FINE_TUNE_THRESHOLD:
                    if not skip_settle_delay:
                        await asyncio.sleep(FINE_TUNE_SETTLE_DELAY_S)
                        value = self.input.get_FineTune()
                    skip_settle_delay = False
                    baseline = value
                    self._request_next_track()
                elif delta <= -FINE_TUNE_THRESHOLD:
                    await asyncio.sleep(FINE_TUNE_SETTLE_DELAY_S)
                    value = self.input.get_FineTune()
                    baseline = value
                    # Dial may be pushed against its mechanical stop - the forward move that
                    # follows is the user retrying, not a new deliberate gesture, so don't wait for it
                    skip_settle_delay = True
                    self._request_restart_track()
        except asyncio.CancelledError:
            raise

    def _request_next_track(self):
        """Interrupt playback so the player immediately moves on to a new random track"""
        self._restart_requested = False
        self._track_control_event.set()

    def _request_restart_track(self):
        """Interrupt playback so the player immediately replays the current track from the start"""
        self._restart_requested = True
        self._track_control_event.set()

    def _is_playing(self):
        """Return True if MPC reports the player is currently in the [playing] state"""
        try:
            result = subprocess.run(["mpc", "status"], check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        return "[playing]" in result.stdout

async def main():
    player = Mp3Player()
    player.start()
    print("MP3 Player running. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping MP3 Player...")
    finally:
        player.stop()

if __name__ == "__main__":
    asyncio.run(main())
