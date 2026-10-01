import asyncio

import RPi.GPIO as GPIO

from airplay import AirPlay
from idle import Idle
from input import Band, Function, Input
from mp3_player import Mp3Player
from radio import Radio
from spotify import Spotify

POLL_INTERVAL_S = 0.015
DEBOUNCE_INTERVAL_S = 0.25


def _requested_mode(function, band):
    if function is Function.TAPE:
        return "idle"
    return {
        Band.AM: "mp3_player",
        Band.SW1: "airplay",
        Band.SW2: "spotify",
        Band.FM: "radio",
    }.get(band)


async def main():
    input_device = Input()
    active_mode = None
    functions = {}
    candidate_mode = object()
    candidate_since = 0.0
    loop = asyncio.get_running_loop()

    try:
        functions = {
            "idle": Idle(),
            "mp3_player": Mp3Player(),
            "airplay": AirPlay(),
            "spotify": Spotify(),
            "radio": Radio(),
        }

        print("Boombox running. Press Ctrl+C to stop.")
        while True:
            requested_mode = _requested_mode(
                input_device.get_Function(),
                input_device.get_Band(),
            )
            now = loop.time()

            if requested_mode != candidate_mode:
                candidate_mode = requested_mode
                candidate_since = now
            elif requested_mode != active_mode and now - candidate_since >= DEBOUNCE_INTERVAL_S:
                if active_mode is not None:
                    functions[active_mode].stop()
                active_mode = requested_mode
                if active_mode is not None:
                    print(f"Starting {active_mode.replace('_', ' ')}")
                    functions[active_mode].start()

            await asyncio.sleep(POLL_INTERVAL_S)
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        print("\nStopping boombox...")
    finally:
        try:
            if active_mode is not None:
                functions[active_mode].stop()
        finally:
            try:
                input_device.cleanup()
            finally:
                GPIO.cleanup()


if __name__ == "__main__":
    asyncio.run(main())