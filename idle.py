import asyncio

from boombox_function import IBoomboxFunction
from announcer import Announcer

class Idle(IBoomboxFunction):
    """Stay inactive until another function is selected."""

    def __init__(self):
        self.announcer = Announcer()
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self.announcer.announce("Radio off, all bands")

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running

async def main():
    idle = Idle()
    idle.start()
    print("Idle running. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        print("\nStopping Idle...")
    finally:
        idle.stop()

if __name__ == "__main__":
    asyncio.run(main())