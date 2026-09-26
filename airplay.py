import asyncio
import os
import stat
import subprocess

from boombox_function import IBoomboxFunction
from announcer import Announcer
from display import Display

# Shairport Sync writes play/stop events here. See shairport-sync.conf.
EVENTS_FIFO = "/tmp/boombox-events"
EVENT_CONNECTED = "AIRPORT_CONNECTED"
EVENT_DISCONNECTED = "AIRPORT_DISCONNECTED"
# Full flash cycle while waiting for a client, in milliseconds.
DISCONNECTED_FLASH_MS = 1000


class AirPlay(IBoomboxFunction):
    """Handles starting/stopping the Shairport Sync (AirPlay) service"""

    def __init__(self):
        self.announcer = Announcer()
        self.display = Display()
        self._running = False
        self._reader_task = None

    def start(self):
        """Start the Shairport Sync service"""
        if self._running:
            return
        try:
            # Open the FIFO before the service starts so a play hook cannot
            # block on a writer with no reader.
            print("AirPlay: opening event FIFO")
            self._start_event_reader()
            print("AirPlay: systemctl start shairport-sync")
            subprocess.run(["sudo", "systemctl", "start", "shairport-sync.service"], check=True, capture_output=True, text=True)
            self._running = True
            print("AirPlay started")
            self._show_disconnected()
            self.announcer.announce("AirPlay")
        except subprocess.CalledProcessError as e:
            self._stop_event_reader()
            print(f"Error starting Shairport Sync: {e}")
        except Exception as e:
            self._stop_event_reader()
            print(f"Error starting AirPlay: {e}")

    def stop(self):
        """Stop the Shairport Sync service"""
        if not self._running:
            return
        self._running = False
        try:
            subprocess.run(["sudo", "systemctl", "stop", "shairport-sync.service"], check=True, capture_output=True, text=True)
            print("AirPlay stopped")
        except subprocess.CalledProcessError as e:
            print(f"Error stopping Shairport Sync: {e}")
        finally:
            self._stop_event_reader()
            self.display.stop_stereo_animation()
            self.display.set_stereo(False)

    def is_running(self):
        """Return True if AirPlay is currently active"""
        return self._running

    def _ensure_fifo(self):
        """Create the event FIFO if missing. /tmp is wiped on reboot."""
        if os.path.exists(EVENTS_FIFO):
            if not stat.S_ISFIFO(os.stat(EVENTS_FIFO).st_mode):
                raise RuntimeError(f"{EVENTS_FIFO} exists and is not a FIFO")
            try:
                os.chmod(EVENTS_FIFO, 0o666)
            except OSError as e:
                print(f"Warning: could not chmod {EVENTS_FIFO}: {e}")
            return
        old_umask = os.umask(0)
        try:
            os.mkfifo(EVENTS_FIFO, 0o666)
        except FileExistsError:
            if not stat.S_ISFIFO(os.stat(EVENTS_FIFO).st_mode):
                raise
        finally:
            os.umask(old_umask)

    def _start_event_reader(self):
        if self._reader_task and not self._reader_task.done():
            return
        loop = asyncio.get_running_loop()
        self._ensure_fifo()
        # O_RDWR so a writer does not block waiting for a reader, and a
        # writer closing does not look like EOF.
        fd = os.open(EVENTS_FIFO, os.O_RDWR | os.O_NONBLOCK)
        print(f"AirPlay: FIFO open fd={fd} mode={oct(os.stat(EVENTS_FIFO).st_mode)}")
        events = os.fdopen(fd, "rb", buffering=0)
        self._reader_task = loop.create_task(self._read_events(events))
        print("AirPlay: event reader task started")
        self._reader_task.add_done_callback(self._reader_done)

    def _stop_event_reader(self):
        task = self._reader_task
        self._reader_task = None
        if task and not task.done():
            task.cancel()

    def _reader_done(self, task):
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            print(f"AirPlay event reader stopped: {exc}")

    async def _read_events(self, events):
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        transport = None
        try:print("AirPlay: event pipe connected")
            empty_reads = 0
            while True:
                line = await reader.readline()
                if not line:
                    empty_reads += 1
                    if empty_reads <= 3 or empty_reads % 25 == 0:
                        print(f"AirPlay: empty FIFO read #{empty_reads}")
                    await asyncio.sleep(0.2)
                    continue
                print(f"AirPlay: FIFO read {line!r}")
                    await asyncio.sleep(0.2)
                    continue
        print(f"AirPlay: handle event {message!r} running={self._running}")
        if not self._running:
            print("AirPlay: ignoring event, not running")andle_event(line.decode(errors="replace").strip())
        finally:
            if transport is not None:
                transport.close()
            elif not events.closed:
                events.close()

    async def _handle_event(self, message):
        if not self._running:
            return
        if message == EVENT_CONNECTED:
            print("AirPlay client connected")
            await self._show_connected()
        elif message == EVENT_DISCONNECTED:
            print("AirPlay client disconnected")
        print(f"AirPlay: show connected, stereo_task={task!r}")
            self._show_disconnected()
        elif message:
            print(f"Ignoring AirPlay event: {message}")

    async def _show_connected(self):
        # The flash task turns the LED off when cancelled. Wait for that
        # before forcing the solid-on state, or the cancel handler wins.
        task = self.display.stereo_task
        self.display.stop_stereo_animation()
        print("AirPlay: show disconnected, start flash")
        if task is not None and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._running:
            self.display.set_stereo(True)

    def _show_disconnected(self):
        self.display.start_stereo_animation(DISCONNECTED_FLASH_MS)


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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

