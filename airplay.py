import subprocess
import time

from boombox_function import IBoomboxFunction
from announcer import Announcer

class AirPlay(IBoomboxFunction):
    """Handles starting/stopping the Shairport Sync (AirPlay) service"""

    def __init__(self):
        self.announcer = Announcer()
        self._running = False

    def start(self):
        """Start the Shairport Sync service"""
        if self._running:
            return
        try:
            subprocess.run(["sudo", "systemctl", "start", "shairport-sync.service"], check=True, capture_output=True, text=True)
            self._running = True
            print("AirPlay started")
            self.announcer.announce("AirPlay")
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

    def is_running(self):
        """Return True if AirPlay is currently active"""
        return self._running

def main():
    airplay = AirPlay()
    airplay.start()
    print("AirPlay running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping AirPlay...")
    finally:
        airplay.stop()

if __name__ == "__main__":
    main()
