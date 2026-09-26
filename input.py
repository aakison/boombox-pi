import spidev
import time
from enum import Enum
import RPi.GPIO as GPIO

# Hardware pin constants
FUNCTION_PIN = 17       # Function switch: HIGH = RADIO, LOW = TAPE
BAND_AM_PIN = 18        # Band switch position: AM
BAND_FM_PIN = 25        # Band switch position: FM
BAND_SW1_PIN = 23       # Band switch position: SW1
BAND_SW2_PIN = 24       # Band switch position: SW2
BEAT_CANCEL_PIN = 4     # Beat cancel switch: HIGH = enabled

TUNER_CHANNEL = 0       # POT1 on MCP3008 channel 0
FINE_TUNE_CHANNEL = 1   # POT2 on MCP3008 channel 1


class Function(Enum):
    TAPE = "TAPE"
    RADIO = "RADIO"


class Band(Enum):
    AM = "AM"
    FM = "FM"
    SW1 = "SW1"
    SW2 = "SW2"


class Input:
    """Singleton class exposing all switch and potentiometer inputs."""
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Input, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not Input._initialized:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)

            for pin in (FUNCTION_PIN, BAND_AM_PIN, BAND_FM_PIN, BAND_SW1_PIN, BAND_SW2_PIN, BEAT_CANCEL_PIN):
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

            # MCP3008 ADC for potentiometers, hardware chip select on SPI0 CE1 (GPIO7) - never claim GPIO7 directly
            self.spi = spidev.SpiDev()
            self.spi.open(0, 1)
            self.spi.max_speed_hz = 1350000  # MCP3008 rated speed at 3.3V
            self.spi.mode = 0

            Input._initialized = True

    def _read_mcp3008(self, channel):
        """Read raw ADC value from MCP3008"""
        if channel < 0 or channel > 7:
            raise ValueError("Channel must be 0-7")
        adc = self.spi.xfer2([1, (8 + channel) << 4, 0])
        return ((adc[1] & 3) << 8) + adc[2]  # Combine 10-bit result

    def get_Function(self):
        """Return the current Function switch position"""
        return Function.RADIO if GPIO.input(FUNCTION_PIN) == GPIO.HIGH else Function.TAPE

    def get_Band(self):
        """Return the current Band switch position, or None if no position is active"""
        if GPIO.input(BAND_AM_PIN) == GPIO.HIGH:
            return Band.AM
        if GPIO.input(BAND_FM_PIN) == GPIO.HIGH:
            return Band.FM
        if GPIO.input(BAND_SW1_PIN) == GPIO.HIGH:
            return Band.SW1
        if GPIO.input(BAND_SW2_PIN) == GPIO.HIGH:
            return Band.SW2
        return None

    def get_Tuner(self):
        """Return the Tuner potentiometer (POT1) value, 0-1023"""
        return self._read_mcp3008(TUNER_CHANNEL)

    def get_FineTune(self):
        """Return the Fine Tune potentiometer (POT2) value, 0-1023"""
        return self._read_mcp3008(FINE_TUNE_CHANNEL)

    def get_BeatCancel(self):
        """Return whether the Beat Cancel switch is enabled"""
        return GPIO.input(BEAT_CANCEL_PIN) == GPIO.HIGH

    def cleanup(self):
        """Clean up SPI resources"""
        self.spi.close()
        # Note: GPIO.cleanup() is called in main() to clean up all GPIO pins


def main():
    input_device = Input()

    print("Reading inputs (Ctrl+C to exit)...")
    try:
        while True:
            function = input_device.get_Function()
            band = input_device.get_Band()
            tuner = input_device.get_Tuner()
            fine_tune = input_device.get_FineTune()
            beat_cancel = input_device.get_BeatCancel()

            band_label = band.value if band else "NONE"
            print(f"Function: {function.value:<5} | Band: {band_label:<4} | "
                  f"Tuner: {tuner:4d} | FineTune: {fine_tune:4d} | BeatCancel: {beat_cancel}")

            time.sleep(1)  # Update every second
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    finally:
        input_device.cleanup()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
