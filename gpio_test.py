from pyA64.gpio import port
from pyA64.gpio import gpio
import time

gpio.init()
# Set GPIO 17 as output
# led = port.PC4
# gpio.setcfg(led, gpio.OUTPUT)
# print(gpio.getcfg(led))
# # blink GPIO 17
# while True:
#     gpio.output(led, gpio.HIGH)
#     print("PC04 HIGH")
#     time.sleep(1)
#     gpio.output(led, gpio.LOW)
#     print("PC04 LOW")
#     time.sleep(1)

# Set PE0, PE1, PE2, PE3 as input
input_pins = [32, 33, 34, 35, 36, port.PC4, port.PC7]
for pin in input_pins:
    gpio.setcfg(pin, gpio.INPUT)
    gpio.pullup(pin, gpio.PULLUP)
    print(f"GPIO {pin} set as input")
    print(f"pin{pin}: ",gpio.getcfg(pin))

while True:
    print(f"time {time.strftime('%Y-%m-%d %H:%M:%S')}")
    for pin in input_pins:
        if gpio.input(pin) == 1:
            print(f"GPIO {pin} is HIGH")
        else:
            print(f"GPIO {pin} is LOW")
    time.sleep(0.1)