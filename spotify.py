import asyncio
import re
import subprocess

from boombox_function import IBoomboxFunction
from announcer import Announcer
from display import Display

MPRIS_BUS_NAME = "org.mpris.MediaPlayer2.librespot"
MPRIS_OBJECT_PATH = "/org/mpris/MediaPlayer2"
STEREO_FLASH_SPEED_MS = 500  # Flash speed while waiting for a device to play audio
_UNSET = object()  # Sentinel distinct from any real PlaybackStatus (including None), forces the first poll to always act

class Spotify(IBoomboxFunction):
    """Handles starting/stopping the Raspotify (Spotify Connect) service"""

    def __init__(self):
        self.announcer = Announcer()
        self.display = Display()
        self._running = False
        self._poll_task = None
        self._last_status = None

    def start(self):
        """Start the Raspotify service"""
        if self._running:
            return
        try:
            subprocess.run(["sudo", "systemctl", "start", "raspotify.service"], check=True, capture_output=True, text=True)
            self._running = True
            print("Spotify Connect started")
            self.announcer.announce("Spotify Connect")
            self._start_status_polling()
        except subprocess.CalledProcessError as e:
            print(f"Error starting Raspotify: {e}")

    def stop(self):
        """Stop the Raspotify service"""
        if not self._running:
            return
        try:
            subprocess.run(["sudo", "systemctl", "stop", "raspotify.service"], check=True, capture_output=True, text=True)
            self._running = False
            print("Spotify Connect stopped")
        except subprocess.CalledProcessError as e:
            print(f"Error stopping Raspotify: {e}")
        finally:
            self._stop_status_polling()

    def is_running(self):
        """Return True if Spotify Connect is currently active"""
        return self._running

    def _start_status_polling(self):
        """Start polling MPRIS PlaybackStatus as an independent async task"""
        if self._poll_task is None or self._poll_task.done():
            self._last_status = _UNSET
            self._poll_task = asyncio.create_task(self._poll_playback_status())

    def _stop_status_polling(self):
        """Stop polling MPRIS PlaybackStatus and clear the stereo indicator"""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = None
        self.display.stop_stereo_animation()
        self.display.set_stereo(False)

    def _get_playback_status(self):
        """Query MPRIS for the current PlaybackStatus, or None if unavailable (e.g. no client connected)"""
        try:
            result = subprocess.run(
                ["busctl", "get-property", MPRIS_BUS_NAME, MPRIS_OBJECT_PATH,
                 "org.mpris.MediaPlayer2.Player", "PlaybackStatus"],
                check=True, capture_output=True, text=True,
            )
            match = re.search(r'"(\w+)"', result.stdout)
            return match.group(1) if match else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    async def _poll_playback_status(self):
        """Poll MPRIS PlaybackStatus once per second, flashing the stereo LED unless actively Playing"""
        try:
            while True:
                status = self._get_playback_status()
                if status != self._last_status:
                    if status == "Playing":
                        self.display.stop_stereo_animation()
                        self.display.set_stereo(True)
                    else:
                        self.display.start_stereo_animation(STEREO_FLASH_SPEED_MS)
                    self._last_status = status
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise

async def main():
    spotify = Spotify()
    spotify.start()
    print("Spotify Connect running. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Spotify Connect...")
    finally:
        spotify.stop()

if __name__ == "__main__":
    asyncio.run(main())
