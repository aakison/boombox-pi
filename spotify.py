import subprocess
import time

from boombox_function import IBoomboxFunction
from announcer import Announcer

class Spotify(IBoomboxFunction):
    """Handles starting/stopping the Raspotify (Spotify Connect) service"""

    def __init__(self):
        self.announcer = Announcer()
        self._running = False

    def start(self):
        """Start the Raspotify service"""
        if self._running:
            return
        try:
            subprocess.run(["sudo", "systemctl", "start", "raspotify.service"], check=True, capture_output=True, text=True)
            self._running = True
            print("Spotify Connect started")
            self.announcer.announce("Spotify Connect")
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

    def is_running(self):
        """Return True if Spotify Connect is currently active"""
        return self._running

def main():
    spotify = Spotify()
    spotify.start()
    print("Spotify Connect running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Spotify Connect...")
    finally:
        spotify.stop()

if __name__ == "__main__":
    main()
