"""
GPIO Handler Module
------------------
Handles GPIO pin monitoring and initialization.
"""

import threading
import time
from typing import Dict, Any

try:
    from pyA64.gpio import gpio
except ImportError:
    print("[GPIO] Warning: pyA64.gpio module not found. Running in simulation mode.")
    # Create mock gpio module for testing
    class MockGPIO:
        INPUT = 1
        PULLUP = 1
        def init(self): pass
        def setcfg(self, *args): pass
        def pullup(self, *args): pass
        def input(self, pin): return 1
    gpio = MockGPIO()

class GPIOHandler(threading.Thread):
    """Handles GPIO pin monitoring and initialization."""

    def __init__(self, config: Dict[str, Any], button_manager: Any, action_handler: Any):
        """Initialize GPIO handler with configuration."""
        super().__init__(name="GPIOHandlerThread")
        self.daemon = True
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()
        
        self._config = config
        self._button_manager = button_manager
        self._action_handler = action_handler
        
        # Extract settings
        self._poll_interval = float(self._config['settings']['poll_interval'])
        self._debounce_time = float(self._config['settings']['debounce_time'])
        
        # Map button names to GPIO pins
        self._pin_to_button = {}
        for button_name, button_config in self._config['buttons'].items():
            self._pin_to_button[button_config['value']] = button_name
        
        print("[GPIO] Handler initialized")

    def _init_gpio(self) -> bool:
        """Initialize GPIO hardware."""
        try:
            gpio.init()
            for pin in self._pin_to_button.keys():
                gpio.setcfg(pin, gpio.INPUT)
                gpio.pullup(pin, gpio.PULLUP)
                print(f"[GPIO] Configured pin {pin} as INPUT with PULLUP")
            return True
        except Exception as e:
            print(f"[GPIO] Error initializing GPIO: {e}")
            return False

    def _handle_pin_states(self) -> None:
        """Process current GPIO pin states and update button manager."""
        current_time = time.monotonic()

        # Read all configured pins
        for pin, button_name in self._pin_to_button.items():
            try:
                # Read current pin state
                current_state = gpio.input(pin)
                
                # Update button manager with new state
                # Note: LOW (0) means pressed, HIGH (1) means released
                self._button_manager.update_button_state(button_name, current_state)
                
            except Exception as e:
                print(f"[GPIO] Error reading pin {pin}: {e}")

        # Get current button states from manager
        button_state = {
            "pressed_buttons": self._button_manager.get_pressed_buttons(),
            "active_combinations": self._button_manager.get_active_combinations()
        }
        
        # Update action handler with current state
        self._action_handler.handle_button_state(button_state)

    def stop(self) -> None:
        """Signal the thread to stop and cleanup resources."""
        print("[GPIO] Stop requested")
        self._shutdown_event.set()
        
        # Clean up handlers
        if self._action_handler:
            self._action_handler.cleanup()

    def run(self) -> None:
        """Main thread loop."""
        print("[GPIO] Thread starting")
        
        if not self._init_gpio():
            print("[GPIO] Failed to initialize GPIO. Thread exiting.")
            return

        while not self._shutdown_event.is_set():
            with self._lock:
                self._handle_pin_states()
            self._shutdown_event.wait(timeout=self._poll_interval)

        print("[GPIO] Thread finished")