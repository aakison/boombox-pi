import spidev
import time
import RPi.GPIO as GPIO

CS_PIN = 5  # GPIO5, physical pin 29 - jumpered directly to MCP3008 CS, bypassing the on-board CE1 trace/R22

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(CS_PIN, GPIO.OUT, initial=GPIO.HIGH)

# Initialize SPI
spi = spidev.SpiDev()
spi.open(0, 1)  # bus/device only selects CLK/MOSI/MISO wiring; CS handled manually below
spi.max_speed_hz = 50000
spi.mode = 0
spi.no_cs = True  # kernel must not also drive CE1

def read_mcp3008(channel):
    if channel < 0 or channel > 7:
        raise ValueError("Channel must be 0-7")
    GPIO.output(CS_PIN, GPIO.LOW)
    adc = spi.xfer2([1, (8 + channel) << 4, 0])
    GPIO.output(CS_PIN, GPIO.HIGH)
    data = ((adc[1] & 3) << 8) + adc[2]  # Combine 10-bit result
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
