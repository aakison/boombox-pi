import spidev
import time
import RPi.GPIO as GPIO

# Initialize GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(7, GPIO.OUT)
GPIO.output(7, GPIO.HIGH)  # Start with CS HIGH (inactive)

# Initialize SPI
spi = spidev.SpiDev()
spi.open(0, 1)  # SPI bus 0, CE1 (GPIO7)
spi.max_speed_hz = 10000
spi.mode = 0
spi.no_cs = True  # Disable automatic CS control

def read_mcp3008(channel):
    if channel < 0 or channel > 7:
        raise ValueError("Channel must be 0-7")
    # Manually toggle CS
    GPIO.output(7, GPIO.LOW)  # Activate MCP3008
    adc = spi.xfer2([1, (8 + channel) << 4, 0])  # SPI transfer
    GPIO.output(7, GPIO.HIGH)  # Deactivate MCP3008
    data = ((adc[1] & 3) << 8) + adc[2]  # Combine 10-bit result
    return data

try:
    print("Reading potentiometer on MCP3008 channel 0 (Ctrl+C to exit)...")
    while True:
        value = read_mcp3008(0)
        voltage = value * 3.3 / 1023
        print(f"ADC Value: {value}, Voltage: {voltage:.2f}V")
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\nProgram terminated by user.")
finally:
    GPIO.cleanup()  # Restore GPIO state
    spi.close()  # Close SPI connection
