import json
import threading
import time
from typing import Dict, Set, Optional, Any # Retained Dict for consistency with original, though GPIOMonitor itself might not use it directly.
from atc_engine.action_handler import ActionHandler
from atc_engine.button_state import ButtonState

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
        def input(self, pin): return 1 # Default to not pressed (high for pull-up)
    gpio = MockGPIO()

class GPIOMonitor(threading.Thread):
    """Monitors GPIO buttons with support for combinations."""

    def __init__(self, config_path: str, action_handler: ActionHandler):
        """Initialize GPIO monitor with configuration from JSON file."""
        super().__init__(name="GPIOMonitorThread")
        self.daemon = True
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()
        self._action_handler = action_handler # ActionHandler instance
        
        # Load configuration
        self._load_config(config_path)
        
        # Initialize button states
        self._button_states: Dict[int, ButtonState] = {
            int(pin): ButtonState() for pin in self._config['gpio']['buttons'].keys()
        }
        
        # Track combination states
        self._active_combination: Optional[Dict[str, Any]] = None
        self._combination_start_time: float = 0.0
        self._held_buttons: Set[int] = set()
        self._default_hold_time: float = self._config['gpio']['settings'].get('default_combo_hold_time', 1.0)
        
        print("[GPIO] Monitor initialized")

    def _load_config(self, config_path: str) -> None:
        """Load and validate configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                self._config = json.load(f)
            
            # Extract settings with defaults
            gpio_settings = self._config['gpio'].get('settings', {})
            self._debounce_time: float = float(gpio_settings.get('debounce_time', 0.3))
            self._poll_interval: float = float(gpio_settings.get('poll_interval', 0.05))
            
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

    def _check_combinations(self, current_pressed: Set[int], current_time: float) -> Optional[Dict[str, Any]]:
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
            
            if current_pressed == combo_set:
                if self._held_buttons != combo_set:
                    self._held_buttons = combo_set.copy()
                    self._combination_start_time = current_time
                    print(f"[GPIO] Potential combination detected: {combo['name']}, holding...")
                    return None # Indicate potential combo, but not yet active
                
                hold_time = float(combo.get('hold_time', self._default_hold_time))
                if current_time - self._combination_start_time >= hold_time:
                    if self._active_combination != combo: # Activate only once per hold
                        print(f"[GPIO] Combination activated after {hold_time:.1f}s hold: {combo['name']}")
                        return combo
                return None # Still holding, or already activated this hold period
                
        # If no current combination matches, or current_pressed doesn't match any combo_set
        self._held_buttons.clear()
        self._combination_start_time = 0.0
        # self._active_combination = None # Reset active_combination only if no combo is pressed
        return None

    def _handle_button_states(self) -> None:
        """Process current button states and detect combinations."""
        current_time = time.monotonic()
        currently_pressed: Set[int] = set()
        newly_pressed: Set[int] = set()

        for pin, state in self._button_states.items():
            try:
                current_state = gpio.input(pin) # 0 for pressed, 1 for not pressed (PULLUP)
                pin_int = int(pin)
                
                if state.last_state != current_state: # State changed
                    if current_state == 0: # Pin pressed
                        if current_time - state.last_press_time > self._debounce_time:
                            state.is_pressed = True
                            state.last_press_time = current_time
                            state.was_in_combo = False # Reset combo flag on new press
                            print(f"[GPIO] Pin {pin_int} pressed")
                            newly_pressed.add(pin_int)
                    else: # Pin released
                        state.is_pressed = False
                        # If a button is released, and it was part of _held_buttons, it might break a combo
                        if pin_int in self._held_buttons:
                            # This logic is tricky; _check_combinations handles most of it.
                            # Consider if _active_combination should be reset if a constituent button is released.
                            pass
                
                state.last_state = current_state
                
                if current_state == 0: # Pin is currently pressed
                    currently_pressed.add(pin_int)
                
            except Exception as e:
                print(f"[GPIO] Error reading pin {pin}: {e}")

        # Check for combinations first
        active_combo_details = self._check_combinations(currently_pressed, current_time)
        
        if active_combo_details:
            # Mark all buttons in the activated combo as 'was_in_combo'
            for pin_val in [int(p) for p in active_combo_details['buttons']]:
                if pin_val in self._button_states:
                    self._button_states[pin_val].was_in_combo = True
            
            print(f"[GPIO] Executing combination action: {active_combo_details['name']} -> {active_combo_details['path']}")
            self._action_handler.execute_action(active_combo_details['path'])
            self._active_combination = active_combo_details # Store the activated combination
            # Clear newly_pressed to prevent single action if part of combo
            newly_pressed.clear() 
            
        elif not currently_pressed: # No buttons are pressed, reset active combination
             self._active_combination = None

        # Handle single button presses only if no combination was activated in this cycle
        # And only if there are newly pressed buttons not part of an ongoing combo check
        if not active_combo_details and newly_pressed:
            for pin_val_pressed in list(newly_pressed): # Iterate over a copy
                state = self._button_states.get(pin_val_pressed)
                # Ensure it's a single button press, not part of a forming or just-fired combo
                if state and not state.was_in_combo and str(pin_val_pressed) in self._config['gpio']['buttons']:
                    # Check if this single button is currently the only one pressed
                    if len(currently_pressed) == 1 and pin_val_pressed in currently_pressed:
                        button_config = self._config['gpio']['buttons'][str(pin_val_pressed)]
                        print(f"[GPIO] Executing single button action: {button_config['name']} -> {button_config['path']}")
                        self._action_handler.execute_action(button_config['path'])
                        # Once action is taken, mark it to avoid re-triggering if held (optional)
                        # Or rely on debounce and state.was_in_combo for subsequent checks.

    def stop(self) -> None:
        """Signal the thread to stop and cleanup resources."""
        print("[GPIO] Stop requested")
        self._shutdown_event.set()
        self._action_handler.stop_current() # Ensure action handler also stops

    def run(self):
        """Main thread loop."""
        print("[GPIO] Thread starting")
        
        if not self._init_gpio():
            print("[GPIO] Failed to initialize GPIO. Thread exiting.")
            return

        while not self._shutdown_event.is_set():
            with self._lock: # Ensure thread-safe access to shared state
                self._handle_button_states()
            # Use wait with timeout for polling interval
            self._shutdown_event.wait(timeout=self._poll_interval)

        print("[GPIO] Thread finished")