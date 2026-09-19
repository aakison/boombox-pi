import spidev
import time

# Initialize SPI
spi = spidev.SpiDev()
spi.open(0, 1)  # SPI bus 0, CE1 (GPIO7) - CS handled by hardware
spi.max_speed_hz = 1350000  # MCP3008 rated speed at 3.3V; 10kHz left long glitch windows
spi.mode = 0

def read_mcp3008(channel):
    if channel < 0 or channel > 7:
        raise ValueError("Channel must be 0-7")
    cmd = [1, (8 + channel) << 4, 0]
    spi.xfer2(cmd)  # priming transfer: discard result, absorbs first-clock-edge misalignment
    adc = spi.xfer2(cmd)  # real transfer
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
    spi.close()  # Close SPI connection
