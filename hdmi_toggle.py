import subprocess
import time
import sys
import os

# Import the correct GPIO module from pyA64
# You might need to adjust the import based on how pyA64 is structured and the pin name
try:
    from pyA64.gpio import port
    from pyA64.gpio import gpio
except ImportError:
    print("Error: pyA64 library not found. Please install it (`sudo pip3 install pyA64`).")
    sys.exit(1)

# --- Configuration ---
HDMI_OUTPUT_NAME = 'HDMI-1' # Identified from xrandr output
# Find the correct pyA64 port object for your chosen GPIO pin
# Consult Olimex documentation or pyA64 examples for the correct mapping
# Example: If you use GPIO pin PL3, it might be port.PL3
BUTTON_GPIO_PIN = 32 # <--- ***CHANGE THIS to your actual pyA64 pin name***
DEBOUNCE_DELAY = 0.2 # seconds to wait for button press to settle

# --- GPIO Setup ---
try:
    gpio.init()
    # Configure the button pin as input with pull-up resistor
    # Adjust PULLUP if your wiring requires PULLDOWN or None
    gpio.setcfg(BUTTON_GPIO_PIN, gpio.INPUT)
    gpio.pullup(BUTTON_GPIO_PIN, gpio.PULLUP) # Using internal pull-up
    print(f"GPIO pin {BUTTON_GPIO_PIN} configured as input with pull-up.")
except Exception as e:
    print(f"Error setting up GPIO: {e}")
    print("Please ensure you are running with sudo and the pyA64 library is correctly installed.")
    sys.exit(1)

# --- HDMI Control Functions ---
def run_xrandr_command(args):
    """Runs an xrandr command with the DISPLAY environment variable set."""
    # Create a copy of the current environment variables
    env = os.environ.copy()
    # Set the DISPLAY environment variable to point to the local display
    env['DISPLAY'] = ':0'
    try:
        # Use a higher timeout in case xrandr is slow to respond
        result = subprocess.run(['xrandr'] + args, capture_output=True, text=True, check=True, env=env, timeout=5)
        return result.stdout
    except FileNotFoundError:
        print("Error: xrandr command not found. Is X11 installed and in the PATH?")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error running xrandr command: {' '.join(['xrandr'] + args)}\n{e}")
        print(f"Stderr: {e.stderr}")
        return None
    except subprocess.TimeoutExpired:
        print(f"Error: xrandr command timed out: {' '.join(['xrandr'] + args)}")
        return None


# def is_hdmi_on():
#     """Checks if the HDMI output is currently active using xrandr."""
#     output = run_xrandr_command([]) # Run xrandr with no arguments to get status
#     if output is not None:
#         output_lines = output.splitlines()
#         for line in output_lines:
#             if HDMI_OUTPUT_NAME in line:
#                 # Check for " connected" (with a space) to be precise
#                 return " connected" in line
#     return False

is_hdmi_on = True

def turn_off_hdmi():
    """Turns off the HDMI output using xrandr."""
    global is_hdmi_on
    print(f"Attempting to turn off {HDMI_OUTPUT_NAME}...")
    print(f"Current HDMI state before turning off: {is_hdmi_on}")
    result = run_xrandr_command(['--output', HDMI_OUTPUT_NAME, '--off'])
    if result is not None:
        print(f"{HDMI_OUTPUT_NAME} turned off.")
        is_hdmi_on = False
        print(f"HDMI state after turning off: {is_hdmi_on}")

def turn_on_hdmi():
    """Turns on the HDMI output using xrandr."""
    global is_hdmi_on
    print(f"Attempting to turn on {HDMI_OUTPUT_NAME}...")
    print(f"Current HDMI state before turning on: {is_hdmi_on}")
    result = run_xrandr_command(['--output', HDMI_OUTPUT_NAME, '--auto'])
    if result is not None:
        print(f"{HDMI_OUTPUT_NAME} turned on.")
        is_hdmi_on = True
        print(f"HDMI state after turning on: {is_hdmi_on}")

# --- Main Loop ---
print("Script started. Press the button to toggle HDMI output.")
try:
    # Initial check of button state
    last_button_state = gpio.input(BUTTON_GPIO_PIN)
    while True:
        current_button_state = gpio.input(BUTTON_GPIO_PIN)

        # Detect button press (transition from high to low if using pull-up)
        if last_button_state == gpio.HIGH and current_button_state == gpio.LOW:
            print("Button pressed!")
            time.sleep(DEBOUNCE_DELAY) # Debounce

            if is_hdmi_on:
                turn_off_hdmi()
            else:
                turn_on_hdmi()

        last_button_state = current_button_state
        time.sleep(0.01) # Small delay to reduce CPU usage

except KeyboardInterrupt:
    print("\nScript stopped by user.")
except Exception as e:
    print(f"An error occurred: {e}")
    import traceback
    traceback.print_exc()
finally:
    # Ensure GPIO cleanup is called even if an error occurs
    try:
        gpio.cleanup() # Clean up GPIO settings on exit
        print("GPIO cleanup performed.")
    except Exception as cleanup_e:
        print(f"Error during GPIO cleanup: {cleanup_e}")