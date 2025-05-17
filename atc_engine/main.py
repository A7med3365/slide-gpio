"""
ATC Engine - Main Module
------------------------
Handles GPIO button inputs with support for button combinations and dynamic configuration.
"""

import json
import os
import threading
import time
from typing import Dict, Set, Optional, Any

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

class ActionHandler:
    """Handles the execution of actions when buttons are pressed."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._current_action: Optional[str] = None
    
    def execute_action(self, path: str) -> None:
        """Print the action that would be executed."""
        with self._lock:
            old_action = self._current_action
            self._current_action = path
            if old_action:
                print(f"[Action] Stopping: {old_action}")
            print(f"[Action] Starting: {path}")

    def stop_current(self) -> None:
        """Print the action being stopped."""
        with self._lock:
            if self._current_action:
                print(f"[Action] Stopping: {self._current_action}")
                self._current_action = None

class ButtonState:
    """Tracks the state of a button including timing information."""
    def __init__(self):
        self.is_pressed: bool = False
        self.last_press_time: float = 0.0
        self.last_state: int = 1  # Default to HIGH (not pressed)

class GPIOMonitor(threading.Thread):
    """Monitors GPIO buttons with support for combinations."""

    def __init__(self, config_path: str):
        """Initialize GPIO monitor with configuration from JSON file."""
        super().__init__(name="GPIOMonitorThread")
        self.daemon = True
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()
        self._action_handler = ActionHandler()
        
        # Load configuration
        self._load_config(config_path)
        
        # Initialize button states
        self._button_states = {
            int(pin): ButtonState() for pin in self._config['gpio']['buttons'].keys()
        }
        
        # Track active combinations
        self._active_combination = None
        self._combination_start_time = 0
        
        print("[GPIO] Monitor initialized")

    def _load_config(self, config_path: str) -> None:
        """Load and validate configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                self._config = json.load(f)
            
            # Extract settings with defaults
            gpio_settings = self._config['gpio'].get('settings', {})
            self._debounce_time = float(gpio_settings.get('debounce_time', 0.3))
            self._poll_interval = float(gpio_settings.get('poll_interval', 0.05))
            
            print(f"[GPIO] Loaded configuration: {len(self._config['gpio']['buttons'])} buttons, "
                  f"{len(self._config['gpio']['combinations'])} combinations")
        except Exception as e:
            print(f"[GPIO] Error loading configuration: {e}")
            raise

    def _init_gpio(self) -> bool:
        """Initialize GPIO hardware."""
        try:
            gpio.init()
            for pin in self._button_states.keys():
                gpio.setcfg(pin, gpio.INPUT)
                gpio.pullup(pin, gpio.PULLUP)
                print(f"[GPIO] Configured pin {pin} as INPUT with PULLUP")
            return True
        except Exception as e:
            print(f"[GPIO] Error initializing GPIO: {e}")
            return False

    def _check_combinations(self, current_pressed: Set[int]) -> Optional[dict]:
        """Check for active button combinations."""
        if not current_pressed:
            self._active_combination = None
            return None

        # Check each defined combination
        for combo in self._config['gpio']['combinations']:
            combo_pins = [int(pin) for pin in combo['buttons']]
            # Check if exactly these buttons are pressed (no extra buttons)
            if set(current_pressed) == set(combo_pins):
                if self._active_combination != combo:
                    print(f"[GPIO] Detected combination: {combo['name']}")
                    return combo
        return None

    def _handle_button_states(self) -> None:
        """Process current button states and detect combinations."""
        current_time = time.monotonic()
        currently_pressed = set()

        # Check each button's current state
        for pin, state in self._button_states.items():
            try:
                current_state = gpio.input(pin)
                
                # Detect press (transition from HIGH to LOW)
                if state.last_state == 1 and current_state == 0:
                    if current_time - state.last_press_time > self._debounce_time:
                        state.is_pressed = True
                        state.last_press_time = current_time
                        print(f"[GPIO] Pin {pin} pressed")
                        currently_pressed.add(pin)
                
                # Update last known state
                state.last_state = current_state
                
                # Add to currently pressed if still held down
                if current_state == 0:
                    currently_pressed.add(pin)
                
            except Exception as e:
                print(f"[GPIO] Error reading pin {pin}: {e}")

        # Check for combinations
        combo = self._check_combinations(currently_pressed)
        if combo:
            # Handle combination action
            print(f"[GPIO] Executing combination action: {combo['name']} -> {combo['path']}")
            if hasattr(self, '_action_handler'):
                self._action_handler.execute_action(combo['path'])
            self._active_combination = combo
        elif len(currently_pressed) == 1:
            # Handle single button press if exactly one button is pressed
            pin = list(currently_pressed)[0]
            if str(pin) in self._config['gpio']['buttons']:
                button_config = self._config['gpio']['buttons'][str(pin)]
                print(f"[GPIO] Executing single button action: {button_config['name']} -> {button_config['path']}")
                if hasattr(self, '_action_handler'):
                    self._action_handler.execute_action(button_config['path'])

    def stop(self) -> None:
        """Signal the thread to stop and cleanup resources."""
        print("[GPIO] Stop requested")
        self._shutdown_event.set()
        
        # Clean up action handler
        if hasattr(self, '_action_handler'):
            self._action_handler.stop_current()

    def run(self):
        """Main thread loop."""
        print("[GPIO] Thread starting")
        
        if not self._init_gpio():
            print("[GPIO] Failed to initialize GPIO. Thread exiting.")
            return

        while not self._shutdown_event.is_set():
            with self._lock:
                self._handle_button_states()
            self._shutdown_event.wait(timeout=self._poll_interval)

        print("[GPIO] Thread finished")

class Application:
    """Main application class."""
    
    def __init__(self, config_path: str):
        self._config_path = config_path
        self._gpio_monitor = None
        self._action_handler = ActionHandler()
        self._shutdown_event = threading.Event()
        
    def run(self) -> None:
        """Start the application and its components."""
        print("[App] Starting application")
        
        # Start GPIO monitoring
        self._gpio_monitor = GPIOMonitor(self._config_path)
        self._gpio_monitor.start()
        
        try:
            while not self._shutdown_event.is_set():
                self._shutdown_event.wait(timeout=0.1)
        except KeyboardInterrupt:
            print("\n[App] Keyboard interrupt received")
            self.stop()
            
        print("[App] Application stopped")
    
    def stop(self) -> None:
        """Stop the application and its components."""
        print("[App] Stopping application")
        self._shutdown_event.set()
        
        if self._gpio_monitor:
            self._gpio_monitor.stop()
            self._gpio_monitor.join(timeout=2.0)

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    app = Application(config_path)
    
    try:
        app.run()
    except Exception as e:
        print(f"[App] Unhandled exception: {e}")
    finally:
        print("[App] Exiting")