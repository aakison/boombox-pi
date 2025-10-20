import spidev, time, RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(7, GPIO.OUT)
GPIO.output(7, GPIO.HIGH)
spi = spidev.SpiDev()
spi.open(0, 1)
spi.max_speed_hz = 50000
spi.mode = 0
spi.no_cs = True
def read_mcp3008(channel):
    GPIO.output(7, GPIO.LOW)
    adc = spi.xfer2([1, (8 + channel) << 4, 0])
    GPIO.output(7, GPIO.HIGH)
    return ((adc[1] & 3) << 8) + adc[2]
try:
    while True:
        print(f"ADC: {read_mcp3008(0)}")
        time.sleep(0.5)
except KeyboardInterrupt:
    GPIO.cleanup()
    spi.close()

