"""
Configuration settings for the GPIO Slideshow application.
"""
import os

# Button Pin Configuration
# Maps physical GPIO pins to folder keys (indices)
PIN_TO_FOLDER_KEY_MAP = {
    32: 0,  # Button 1
    33: 1,  # Button 2
    34: 2,  # Button 3
    35: 3,  # Button 4
    # Add pins for buttons 5 and 6 if needed:
    # 36: 4,  # Button 5
    # 37: 5,  # Button 6
}

# Image Path Configuration
BASE_IMAGE_PATH = "/home/olimex/Documents/slide/gpio_slideshow/image_sets"

# Map folder keys to actual folder paths
FOLDER_MAP = {
    0: os.path.join(BASE_IMAGE_PATH, "set0"),
    1: os.path.join(BASE_IMAGE_PATH, "set1"),
    2: os.path.join(BASE_IMAGE_PATH, "set2"),
    3: os.path.join(BASE_IMAGE_PATH, "set3"),
    # Add entries for additional sets if needed:
    # 4: os.path.join(BASE_IMAGE_PATH, "set4"),
    # 5: os.path.join(BASE_IMAGE_PATH, "set5"),
}

# Slideshow Settings
SLIDESHOW_DELAY_SECONDS = 1  # Delay between images in slideshow mode
INITIAL_FOLDER_KEY = 0       # Which folder key to start with

# Button Settings
BUTTON_POLL_INTERVAL = 0.05  # How often to check button state (seconds)
DEBOUNCE_TIME = 0.3         # Ignore button changes for this duration after a press (seconds)