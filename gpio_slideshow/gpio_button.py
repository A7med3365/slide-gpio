"""
GPIO Button monitoring functionality.
"""
import threading
import time
from pyA64.gpio import port, gpio

# Import button-related settings
from . import config

class ButtonMonitor(threading.Thread):
    """Monitors GPIO buttons in a separate thread."""

    def __init__(self, pin_map, callback):
        super().__init__(name="ButtonThread")
        self.daemon = True
        self._pin_map = pin_map
        self._callback = callback
        self._shutdown_event = threading.Event()
        self._last_press_time = {pin: 0 for pin in pin_map} # For debouncing
        self._last_pin_state = {} # Store last known state (LOW=pressed)
        print(f"[Buttons] Initialized for pins: {list(pin_map.keys())}")

    def _init_gpio(self):
        """Initializes GPIO pins."""
        try:
            gpio.init()
            print("[Buttons] GPIO initialized.")
            for pin in self._pin_map.keys():
                gpio.setcfg(pin, gpio.INPUT)
                gpio.pullup(pin, gpio.PULLUP) # Use internal pull-up
                self._last_pin_state[pin] = gpio.input(pin) # Read initial state
                print(f"[Buttons] Configured Pin {pin} as INPUT with PULLUP. Initial state: {'HIGH (Not Pressed)' if self._last_pin_state[pin] == 1 else 'LOW (Pressed)'}")
            return True
        except Exception as e:
            print(f"[Buttons] Error initializing GPIO: {e}")
            print("[Buttons] *** Button monitoring will likely fail. ***")
            return False

    def stop(self):
        """Signals the thread to stop."""
        print("[Buttons] Stop requested.")
        self._shutdown_event.set()

    def run(self):
        """Main loop for the button monitor thread."""
        print("[Buttons] Thread started.")
        if not self._init_gpio():
             print("[Buttons] Exiting thread due to GPIO initialization failure.")
             return # Don't run loop if GPIO failed

        while not self._shutdown_event.is_set():
            current_time = time.monotonic() # Use monotonic clock for debounce timing

            for pin, folder_key in self._pin_map.items():
                try:
                    current_state = gpio.input(pin)
                except Exception as e:
                    print(f"[Buttons] Error reading pin {pin}: {e}. Skipping.")
                    continue # Skip this pin check if reading fails

                last_state = self._last_pin_state.get(pin, 1) # Default to HIGH if not seen before

                # Check for a press (transition from HIGH to LOW)
                if last_state == 1 and current_state == 0:
                    # Check debounce timer
                    if current_time - self._last_press_time.get(pin, 0) > config.DEBOUNCE_TIME:
                            print(f"[Buttons] Pin {pin} pressed! Triggering action for key: {folder_key}")
                            self._last_press_time[pin] = current_time # Update last press time
                            if self._callback:
                                try:
                                    self._callback(folder_key) # Call the registered callback
                                except Exception as e:
                                    print(f"[Buttons] Error executing callback for key {folder_key}: {e}")
                    # else:
                    #     print(f"[Buttons] Pin {pin} press detected, but within debounce period. Ignoring.")

                # Update last known state for this pin
                self._last_pin_state[pin] = current_state

            # Check for shutdown event more frequently
            self._shutdown_event.wait(timeout=config.BUTTON_POLL_INTERVAL)

        print("[Buttons] Thread finished.")