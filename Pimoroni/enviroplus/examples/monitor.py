#!/usr/bin/env python3

import colorsys
import sys
import time

import st7735

try:
    # Transitional fix for breaking change in LTR559
    from ltr559 import LTR559
    ltr559 = LTR559()
except ImportError:
    import ltr559

import logging
from subprocess import PIPE, Popen

from bme280 import BME280
from fonts.ttf import RobotoMedium as UserFont
from PIL import Image, ImageDraw, ImageFont
from pms5003 import PMS5003
from pms5003 import ReadTimeoutError as pmsReadTimeoutError
from pms5003 import SerialTimeoutError

from enviroplus import gas

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S")

logging.info("""combined.py - Displays readings from all of Enviro plus' sensors

Press Ctrl+C to exit!

""")

def setup_sensors():
    global bme280, pms5003
    # BME280 temperature/pressure/humidity sensor
    bme280 = BME280()
    # PMS5003 particulate sensor
    pms5003 = PMS5003()
    time.sleep(1.0)

def setup_display():
    global st7735, WIDTH, HEIGHT, img, draw, font, smallfont, x_offset, y_offset, top_pos
    # Create ST7735 LCD display class
    st7735 = st7735.ST7735(
        port=0,
        cs=1,
        dc="GPIO9",
        backlight="GPIO12",
        rotation=270,
        spi_speed_hz=10000000
    )
    # Initialize display
    st7735.begin()
    WIDTH = st7735.width
    HEIGHT = st7735.height
    # Set up canvas and font
    img = Image.new("RGB", (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_size_small = 10
    font_size_large = 20
    font = ImageFont.truetype(UserFont, font_size_large)
    smallfont = ImageFont.truetype(UserFont, font_size_small)
    x_offset = 2
    y_offset = 2
    # The position of the top bar
    top_pos = 25

def setup_variables():
    global variables, units, limits, palette, values
    # Create a values dict to store the data
    variables = [
        "temperature", "pressure", "humidity", "light",
        "oxidised", "reduced", "nh3", "pm1", "pm25", "pm10"
    ]
    units = [
        "C", "hPa", "%", "Lux", "kO", "kO", "kO",
        "ug/m3", "ug/m3", "ug/m3"
    ]
    # Define your own warning limits
    limits = [
        [4, 18, 28, 35],
        [250, 650, 1013.25, 1015],
        [20, 30, 60, 70],
        [-1, -1, 30000, 100000],
        [-1, -1, 40, 50],
        [-1, -1, 450, 550],
        [-1, -1, 200, 300],
        [-1, -1, 50, 100],
        [-1, -1, 50, 100],
        [-1, -1, 50, 100]
    ]
    # RGB palette for values on the combined screen
    palette = [
        (0, 0, 255),    # Dangerously Low
        (0, 255, 255),  # Low
        (0, 255, 0),    # Normal
        (255, 255, 0),  # High
        (255, 0, 0)     # Dangerously High
    ]
    values = {}

def setup_state():
    global mode, last_page, delay, cpu_temps, factor
    # Initialize mode and timing variables
    mode = 0
    last_page = time.time()
    delay = 0.5
    # Initialize CPU temperature smoothing
    cpu_temps = [0.0] * 5
    factor = 2.25

def setup():
    setup_sensors()
    setup_display()
    setup_variables()
    setup_state()


# Displays data and text on the 0.96" LCD
def display_text(variable, data, unit):
    # Maintain length of list
    values[variable] = values[variable][1:] + [data]
    # Scale the values for the variable between 0 and 1
    vmin = min(values[variable])
    vmax = max(values[variable])
    colours = [(v - vmin + 1) / (vmax - vmin + 1) for v in values[variable]]
    # Format the variable name and value
    message = f"{variable[:4]}: {data:.1f} {unit}"
    logging.info(message)
    draw.rectangle((0, 0, WIDTH, HEIGHT), (255, 255, 255))
    for i in range(len(colours)):
        # Convert the values to colours from red to blue
        colour = (1.0 - colours[i]) * 0.6
        r, g, b = [int(x * 255.0) for x in colorsys.hsv_to_rgb(colour, 1.0, 1.0)]
        # Draw a 1-pixel wide rectangle of colour
        draw.rectangle((i, top_pos, i + 1, HEIGHT), (r, g, b))
        # Draw a line graph in black
        line_y = HEIGHT - (top_pos + (colours[i] * (HEIGHT - top_pos))) + top_pos
        draw.rectangle((i, line_y, i + 1, line_y + 1), (0, 0, 0))
    # Write the text at the top in black
    draw.text((0, 0), message, font=font, fill=(0, 0, 0))
    st7735.display(img)


# Saves the data to be used in the graphs later and prints to the log
def save_data(idx, data):
    variable = variables[idx]
    # Maintain length of list
    values[variable] = values[variable][1:] + [data]
    unit = units[idx]
    message = f"{variable[:4]}: {data:.1f} {unit}"
    logging.info(message)


# Displays all the text on the 0.96" LCD
def display_everything():
    draw.rectangle((0, 0, WIDTH, HEIGHT), (0, 0, 0))
    column_count = 2
    row_count = (len(variables) / column_count)
    for i in range(len(variables)):
        variable = variables[i]
        data_value = values[variable][-1]
        unit = units[i]
        x = x_offset + ((WIDTH // column_count) * (i // row_count))
        y = y_offset + ((HEIGHT / row_count) * (i % row_count))
        message = f"{variable[:4]}: {data_value:.1f} {unit}"
        lim = limits[i]
        rgb = palette[0]
        for j in range(len(lim)):
            if data_value > lim[j]:
                rgb = palette[j + 1]
        draw.text((x, y), message, font=smallfont, fill=rgb)
    st7735.display(img)


# Get the temperature of the CPU for compensation
def get_cpu_temperature():
    process = Popen(["vcgencmd", "measure_temp"], stdout=PIPE, universal_newlines=True)
    output, _error = process.communicate()
    return float(output[output.index("=") + 1:output.rindex("'")])

def handle_temperature_mode():
    unit = "°C"
    cpu_temp = get_cpu_temperature()
    # Smooth out with some averaging to decrease jitter
    cpu_temps = cpu_temps[1:] + [cpu_temp]
    avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
    raw_temp = bme280.get_temperature()
    data = raw_temp - ((avg_cpu_temp - raw_temp) / factor)
    display_text(variables[0], data, unit)

def handle_pressure_mode():
    unit = "hPa"
    data = bme280.get_pressure()
    display_text(variables[1], data, unit)

def handle_humidity_mode():
    unit = "%"
    data = bme280.get_humidity()
    display_text(variables[2], data, unit)

def handle_light_mode():
    unit = "Lux"
    if proximity < 10:
        data = ltr559.get_lux()
    else:
        data = 1
    display_text(variables[3], data, unit)

def handle_oxidised_mode():
    unit = "kO"
    data = gas.read_all()
    data = data.oxidising / 1000
    display_text(variables[4], data, unit)

def handle_reduced_mode():
    unit = "kO"
    data = gas.read_all()
    data = data.reducing / 1000
    display_text(variables[5], data, unit)

def handle_nh3_mode():
    unit = "kO"
    data = gas.read_all()
    data = data.nh3 / 1000
    display_text(variables[6], data, unit)

def handle_pm1_mode():
    unit = "ug/m3"
    try:
        data = pms5003.read()
    except (SerialTimeoutError, pmsReadTimeoutError):
        logging.warning("Failed to read PMS5003")
    else:
        data = float(data.pm_ug_per_m3(1.0))
        display_text(variables[7], data, unit)

def handle_pm25_mode():
    unit = "ug/m3"
    try:
        data = pms5003.read()
    except (SerialTimeoutError, pmsReadTimeoutError):
        logging.warning("Failed to read PMS5003")
    else:
        data = float(data.pm_ug_per_m3(2.5))
        display_text(variables[8], data, unit)

def handle_pm10_mode():
    unit = "ug/m3"
    try:
        data = pms5003.read()
    except (SerialTimeoutError, pmsReadTimeoutError):
        logging.warning("Failed to read PMS5003")
    else:
        data = float(data.pm_ug_per_m3(10))
        display_text(variables[9], data, unit)

def handle_display_everything_mode():
    cpu_temp = get_cpu_temperature()
    # Smooth out with some averaging to decrease jitter
    cpu_temps = cpu_temps[1:] + [cpu_temp]
    avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
    raw_temp = bme280.get_temperature()
    raw_data = raw_temp - ((avg_cpu_temp - raw_temp) / factor)
    save_data(0, raw_data)
    display_everything()
    raw_data = bme280.get_pressure()
    save_data(1, raw_data)
    display_everything()
    raw_data = bme280.get_humidity()
    save_data(2, raw_data)
    if proximity < 10:
        raw_data = ltr559.get_lux()
    else:
        raw_data = 1
    save_data(3, raw_data)
    display_everything()
    gas_data = gas.read_all()
    save_data(4, gas_data.oxidising / 1000)
    save_data(5, gas_data.reducing / 1000)
    save_data(6, gas_data.nh3 / 1000)
    display_everything()
    pms_data = None
    try:
        pms_data = pms5003.read()
    except (SerialTimeoutError, pmsReadTimeoutError):
        logging.warning("Failed to read PMS5003")
    else:
        save_data(7, float(pms_data.pm_ug_per_m3(1.0)))
        save_data(8, float(pms_data.pm_ug_per_m3(2.5)))
        save_data(9, float(pms_data.pm_ug_per_m3(10)))
        display_everything()

def main_loop ():
    global mode, last_page, delay
    global proximity, lux
    global screen_on, dimmed, light_off_time, light_on_time
    global dim_delay, off_delay, on_delay
    
    screen_on = True
    dimmed = False
    light_off_time = None
    light_on_time = None
    dim_delay = 2      # seconds to wait before dimming
    off_delay = 4      # seconds to wait before turning off after dim
    on_delay = 3       # seconds of light before turning back on

    try:
        while True:
            
            proximity = ltr559.get_proximity()
            lux = ltr559.get_lux()

            now = time.time()

            if lux <= 0:
                if screen_on and not dimmed:
                    if light_off_time is None:
                        light_off_time = now
                    elif now - light_off_time > dim_delay:
                        st7735.set_backlight(0.2)  # Dim the screen
                        dimmed = True
                elif dimmed:
                    if now - light_off_time > (dim_delay + off_delay):
                        st7735.set_backlight(0)  # Turn off the screen
                        screen_on = False
                        dimmed = False
                        light_off_time = None
                light_on_time = None
            else:
                if not screen_on:
                    if light_on_time is None:
                        light_on_time = now
                    elif now - light_on_time > on_delay:
                        st7735.set_backlight(1)  # Turn on the screen
                        screen_on = True
                        light_on_time = None
                elif dimmed:
                    st7735.set_backlight(1)  # Restore brightness
                    dimmed = False
                    light_off_time = None
                else:
                    light_off_time = None
                # Reset light_off_time if light is back

            # If the proximity crosses the threshold, toggle the mode
            if proximity > 1500 and time.time() - last_page > delay:
                mode += 1
                mode %= (len(variables) + 1)
                last_page = time.time()

            # Call the appropriate function based on the mode
            match mode:

                case 10:
                    handle_display_everything_mode()
                case 0:
                    handle_temperature_mode()
                case 1:
                    handle_pressure_mode()
                case 2:
                    handle_humidity_mode()
                case 3:
                    handle_light_mode()
                case 4:
                    handle_oxidised_mode()
                case 5:
                    handle_reduced_mode()
                case 6:
                    handle_nh3_mode()
                case 7:
                    handle_pm1_mode()
                case 8:
                    handle_pm25_mode()
                case 9:
                    handle_pm10_mode()
        

    except KeyboardInterrupt:
        sys.exit(0)


def main():
    setup()
    main_loop()


if __name__ == "__main__":
    main()

