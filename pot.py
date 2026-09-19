import spidev
import time
import RPi.GPIO as GPIO

CS_PIN = 1  # BCM GPIO1 (physical pin 28) - this board's CS trace, not a hardware SPI CE pin

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(CS_PIN, GPIO.OUT, initial=GPIO.HIGH)

# Initialize SPI
spi = spidev.SpiDev()
spi.open(0, 0)  # SPI bus 0; CS handled manually on GPIO1, hardware CE0/CE1 unused
spi.max_speed_hz = 1350000  # MCP3008 rated speed at 3.3V; 10kHz left long glitch windows
spi.mode = 0
spi.no_cs = True  # kernel must not also drive CE0

def read_mcp3008(channel):
    if channel < 0 or channel > 7:
        raise ValueError("Channel must be 0-7")
    cmd = [1, (8 + channel) << 4, 0]
    GPIO.output(CS_PIN, GPIO.LOW)
    adc = spi.xfer2(cmd)
    GPIO.output(CS_PIN, GPIO.HIGH)
    data = ((adc[1] & 3) << 8) + adc[2]  # Combine 10-bit result
    if data == 0:
        print(f"  [diag] channel {channel} raw bytes: {adc}")
    return data

try:
    print("Reading potentiometers on MCP3008 channels 0 and 1 (Ctrl+C to exit)...")
    while True:
        value0 = read_mcp3008(0)
        voltage0 = value0 * 3.3 / 1023
        value1 = read_mcp3008(1)
        voltage1 = value1 * 3.3 / 1023
        print(f"CH0 - ADC Value: {value0}, Voltage: {voltage0:.2f}V | "
              f"CH1 - ADC Value: {value1}, Voltage: {voltage1:.2f}V")
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\nProgram terminated by user.")
finally:
    GPIO.cleanup()
    spi.close()  # Close SPI connection
