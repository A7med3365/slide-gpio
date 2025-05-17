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
        self.was_in_combo: bool = False  # Track if button was part of a combo

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
        
        # Track combination states
        self._active_combination = None
        self._combination_start_time = 0.0
        self._held_buttons = set()
        self._default_hold_time = self._config['gpio']['settings'].get('default_combo_hold_time', 1.0)
        
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

    def _check_combinations(self, current_pressed: Set[int], current_time: float) -> Optional[dict]:
        """Check for active button combinations with hold time."""
        if not current_pressed:
            self._held_buttons.clear()
            self._combination_start_time = 0.0
            self._active_combination = None
            return None

        # Check each defined combination
        for combo in self._config['gpio']['combinations']:
            combo_pins = [int(pin) for pin in combo['buttons']]
            combo_set = set(combo_pins)
            
            # Check if exactly these buttons are pressed
            if current_pressed == combo_set:
                # New combination detected
                if self._held_buttons != combo_set:
                    self._held_buttons = combo_set.copy()
                    self._combination_start_time = current_time
                    print(f"[GPIO] Potential combination detected: {combo['name']}, holding...")
                    return None
                
                # Check if held long enough
                hold_time = float(combo.get('hold_time', self._default_hold_time))
                if current_time - self._combination_start_time >= hold_time:
                    if self._active_combination != combo:
                        print(f"[GPIO] Combination activated after {hold_time:.1f}s hold: {combo['name']}")
                        return combo
                return None
                
        # No matching combination, reset hold state
        self._held_buttons.clear()
        self._combination_start_time = 0.0
        return None

    def _handle_button_states(self) -> None:
        """Process current button states and detect combinations."""
        current_time = time.monotonic()
        currently_pressed = set()
        newly_pressed = set()

        # Check each button's current state
        for pin, state in self._button_states.items():
            try:
                current_state = gpio.input(pin)
                pin_int = int(pin)
                
                # Detect state changes
                if state.last_state != current_state:
                    # Button pressed (transition from HIGH to LOW)
                    if current_state == 0:
                        if current_time - state.last_press_time > self._debounce_time:
                            state.is_pressed = True
                            state.last_press_time = current_time
                            state.was_in_combo = False  # Reset combo state on new press
                            print(f"[GPIO] Pin {pin} pressed")
                            newly_pressed.add(pin_int)
                    # Button released (transition from LOW to HIGH)
                    else:
                        if pin_int in self._held_buttons:
                            state.was_in_combo = True
                
                # Update last known state
                state.last_state = current_state
                
                # Track currently held buttons
                if current_state == 0:
                    currently_pressed.add(pin_int)
                
            except Exception as e:
                print(f"[GPIO] Error reading pin {pin}: {e}")

        # Check for combinations
        combo = self._check_combinations(currently_pressed, current_time)
        if combo:
            # Mark all combo buttons
            for pin in [int(p) for p in combo['buttons']]:
                if pin in self._button_states:
                    self._button_states[pin].was_in_combo = True
            
            # Handle combination action
            print(f"[GPIO] Executing combination action: {combo['name']} -> {combo['path']}")
            if hasattr(self, '_action_handler'):
                self._action_handler.execute_action(combo['path'])
            self._active_combination = combo
            
        # Handle single button presses
        elif len(newly_pressed) == 1:
            pin = list(newly_pressed)[0]
            state = self._button_states.get(pin)
            
            # Only trigger if button wasn't part of a combo
            if state and not state.was_in_combo and str(pin) in self._config['gpio']['buttons']:
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