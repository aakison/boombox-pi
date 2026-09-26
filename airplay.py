import asyncio
import glob
import subprocess

from boombox_function import IBoomboxFunction
from announcer import Announcer
from display import Display

ALSA_PCM_STATUS_GLOB = "/proc/asound/card*/pcm*p/sub*/status"
STEREO_FLASH_SPEED_MS = 500  # Flash speed while waiting for a device to play audio
_UNSET = object()  # Sentinel distinct from any real playback status (including None), forces the first poll to always act

class AirPlay(IBoomboxFunction):
    """Handles starting/stopping the Shairport Sync (AirPlay) service"""

    def __init__(self):
        self.announcer = Announcer()
        self.display = Display()
        self._running = False
        self._poll_task = None
        self._last_status = None

    def start(self):
        """Start the Shairport Sync service"""
        if self._running:
            return
        try:
            subprocess.run(["sudo", "systemctl", "start", "shairport-sync.service"], check=True, capture_output=True, text=True)
            self._running = True
            print("AirPlay started")
            self.announcer.announce("Apple AirPlay")
            self._start_status_polling()
        except subprocess.CalledProcessError as e:
            print(f"Error starting Shairport Sync: {e}")

    def stop(self):
        """Stop the Shairport Sync service"""
        if not self._running:
            return
        try:
            subprocess.run(["sudo", "systemctl", "stop", "shairport-sync.service"], check=True, capture_output=True, text=True)
            self._running = False
            print("AirPlay stopped")
        except subprocess.CalledProcessError as e:
            print(f"Error stopping Shairport Sync: {e}")
        finally:
            self._stop_status_polling()

    def is_running(self):
        """Return True if AirPlay is currently active"""
        return self._running

    def _start_status_polling(self):
        """Start polling ALSA PCM playback status as an independent async task"""
        if self._poll_task is None or self._poll_task.done():
            self._last_status = _UNSET
            self._poll_task = asyncio.create_task(self._poll_playback_status())

    def _stop_status_polling(self):
        """Stop polling ALSA PCM playback status and clear the stereo indicator"""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = None
        self.display.stop_stereo_animation()
        self.display.set_stereo(False)

    def _get_playback_status(self):
        """Check ALSA PCM playback substreams for one actively RUNNING, or None if all are closed/idle"""
        for path in glob.glob(ALSA_PCM_STATUS_GLOB):
            try:
                with open(path) as f:
                    content = f.read()
            except OSError:
                continue
            if content.startswith("state: RUNNING"):
                return "RUNNING"
        return None

    async def _poll_playback_status(self):
        """Poll ALSA PCM status once per second, flashing the stereo LED unless a stream is actively RUNNING"""
        try:
            while True:
                status = self._get_playback_status()
                if status != self._last_status:
                    if status == "RUNNING":
                        self.display.stop_stereo_animation()
                        self.display.set_stereo(True)
                    else:
                        self.display.start_stereo_animation(STEREO_FLASH_SPEED_MS)
                    self._last_status = status
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise

async def main():
    airplay = AirPlay()
    airplay.start()
    print("AirPlay running. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping AirPlay...")
    finally:
        airplay.stop()

if __name__ == "__main__":
    asyncio.run(main())
