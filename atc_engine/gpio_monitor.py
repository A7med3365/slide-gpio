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
        self._config: Dict[str, Any] = {} # Will be populated by _load_config
        self._load_config(config_path)

        # Load default media name from config
        self._default_media_name: Optional[str] = self._config.get('settings', {}).get('default_media_name')
        if self._default_media_name:
            print(f"[GPIO] Default media name loaded: {self._default_media_name}")
        else:
            print("[GPIO] No default_media_name found in settings.")
        
        # Initialize button states and pin-to-name mapping
        self._button_states: Dict[int, ButtonState] = {}
        self._pin_to_button_name: Dict[int, str] = {}
        for btn_name, button_details in self._config.get('buttons', {}).items():
            pin_value = int(button_details['value'])
            self._button_states[pin_value] = ButtonState()
            self._pin_to_button_name[pin_value] = btn_name
        
        # Track combination states
        self._active_combination_info: Optional[Dict[str, Any]] = None # Stores name, mode, path of active combo
        self._combination_start_time: float = 0.0
        self._held_buttons_for_combo: Set[str] = set() # Stores button names for current potential combo
        self._default_hold_time: float = self._config.get('settings', {}).get('default_combo_hold_time', 1.0)

        # Prepare combined actions list
        self._combined_actions: list[Dict[str, Any]] = []
        for action_type, actions_dict in [("media", self._config.get('media', {})),
                                          ("action", self._config.get('actions', {}))]:
            for name, details in actions_dict.items():
                self._combined_actions.append({
                    'name': name,
                    'details': details,
                    'type': action_type
                })
        
        print(f"[GPIO] Monitor initialized. Buttons: {len(self._button_states)}, Combined Actions: {len(self._combined_actions)}")

    def _load_config(self, config_path: str) -> None:
        """Load and validate configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                self._config = json.load(f) # Store entire config
            
            # Extract settings with defaults
            settings = self._config.get('settings', {})
            self._debounce_time: float = float(settings.get('debounce_time', 0.3))
            self._poll_interval: float = float(settings.get('poll_interval', 0.05))
            # self._default_hold_time is now set in __init__
            
            print(f"[GPIO] Loaded configuration from {config_path}")
        except Exception as e:
            print(f"[GPIO] Error loading configuration from {config_path}: {e}")
            raise

    def _init_gpio(self) -> bool:
        """Initialize GPIO hardware."""
        try:
            gpio.init()
            for button_details in self._config.get('buttons', {}).values():
                pin = int(button_details['value'])
                gpio.setcfg(pin, gpio.INPUT)
                gpio.pullup(pin, gpio.PULLUP)
                print(f"[GPIO] Configured pin {pin} as INPUT with PULLUP")
            return True
        except Exception as e:
            print(f"[GPIO] Error initializing GPIO: {e}")
            return False

    def _check_combinations(self, current_pressed_pins: Set[int], current_time: float) -> Optional[Dict[str, Any]]:
        """Check for active button combinations based on button names and hold time."""
        if not current_pressed_pins:
            self._held_buttons_for_combo.clear()
            self._combination_start_time = 0.0
            self._active_combination_info = None
            return None

        current_pressed_button_names = {self._pin_to_button_name[pin] for pin in current_pressed_pins if pin in self._pin_to_button_name}

        for item in self._combined_actions:
            item_button_config = item['details'].get('button')
            if not item_button_config: # Skip if no button defined for this action/media
                continue

            # Normalize item_button_config to a set of button names
            required_button_names: Set[str]
            if isinstance(item_button_config, str):
                required_button_names = {item_button_config}
            elif isinstance(item_button_config, list):
                required_button_names = set(item_button_config)
            else:
                continue # Invalid button config for this item

            # Only consider items that are combinations (more than one button)
            if len(required_button_names) <= 1:
                continue

            if current_pressed_button_names == required_button_names:
                if self._held_buttons_for_combo != required_button_names:
                    self._held_buttons_for_combo = required_button_names.copy()
                    self._combination_start_time = current_time
                    # print(f"[GPIO] Potential combination for '{item['name']}' detected, holding...")
                    return None # Indicate potential combo, but not yet active

                hold_time = float(item['details'].get('hold_time', self._default_hold_time))
                if current_time - self._combination_start_time >= hold_time:
                    # Activate only once per hold by checking against _active_combination_info
                    # To prevent re-triggering, we compare the 'name' of the item.
                    if not self._active_combination_info or self._active_combination_info['name'] != item['name']:
                        print(f"[GPIO] Combination '{item['name']}' activated after {hold_time:.1f}s hold.")
                        return {
                            'name': item['name'],
                            'mode': item['details']['mode'],
                            'path': item['details'].get('path')
                        }
                return None # Still holding, or already activated this hold period for this specific combo name
        
        # If no current combination matches, or current_pressed_button_names doesn't match any combo_set
        self._held_buttons_for_combo.clear()
        self._combination_start_time = 0.0
        # self._active_combination_info = None # Reset only if no combo is pressed or matched
        return None

    def _handle_button_states(self) -> None:
        """Process current button states and detect single or combination actions."""
        current_time = time.monotonic()
        currently_pressed_pins: Set[int] = set()
        newly_pressed_pins: Set[int] = set()

        for pin, state in self._button_states.items():
            try:
                # Assuming gpio.input(pin) returns 0 for pressed (LOW) and 1 for not pressed (HIGH due to PULLUP)
                current_pin_state = gpio.input(pin)
                
                if state.last_state != current_pin_state: # State changed
                    if current_pin_state == 0: # Pin pressed (transitioned to LOW)
                        if current_time - state.last_press_time > self._debounce_time:
                            state.is_pressed = True
                            state.last_press_time = current_time
                            state.was_in_combo = False # Reset combo flag on new press
                            print(f"[GPIO] Pin {pin} ({self._pin_to_button_name.get(pin, 'Unknown')}) pressed")
                            newly_pressed_pins.add(pin)
                    else: # Pin released (transitioned to HIGH)
                        state.is_pressed = False
                        # If a button is released, and it was part of _held_buttons_for_combo, it might break a combo.
                        # _check_combinations will handle this by not finding a match.
                        # Also, if an active combo was triggered by this button, releasing it should clear _active_combination_info
                        button_name_released = self._pin_to_button_name.get(pin)
                        if self._active_combination_info and button_name_released and \
                           (isinstance(self._active_combination_info.get('_buttons_internal', set()), set) and \
                            button_name_released in self._active_combination_info['_buttons_internal']):
                            print(f"[GPIO] Button {button_name_released} from active combo '{self._active_combination_info['name']}' released. Clearing active combo.")
                            self._active_combination_info = None # Clear active combo if one of its buttons is released
                
                state.last_state = current_pin_state
                
                if current_pin_state == 0: # Pin is currently pressed
                    currently_pressed_pins.add(pin)
                
            except Exception as e:
                print(f"[GPIO] Error reading pin {pin}: {e}")

        # Check for combinations first
        combo_action_details = self._check_combinations(currently_pressed_pins, current_time)
        
        if combo_action_details:
            # Mark all buttons involved in the activated combo as 'was_in_combo'
            # The 'button' field in item['details'] can be a string or list of button names
            combo_buttons_config = None
            for item in self._combined_actions: # Find the original item to get its button config
                if item['name'] == combo_action_details['name']:
                    combo_buttons_config = item['details'].get('button')
                    break
            
            if combo_buttons_config:
                involved_button_names = set()
                if isinstance(combo_buttons_config, str):
                    involved_button_names = {combo_buttons_config}
                elif isinstance(combo_buttons_config, list):
                    involved_button_names = set(combo_buttons_config)

                for pin, btn_name in self._pin_to_button_name.items():
                    if btn_name in involved_button_names and pin in self._button_states:
                        self._button_states[pin].was_in_combo = True
            
            print(f"[GPIO] Executing combination action: Name='{combo_action_details['name']}', Mode='{combo_action_details['mode']}', Path='{combo_action_details.get('path')}'")
            self._action_handler.execute_action(
                name=combo_action_details['name'],
                mode=combo_action_details['mode'],
                path=combo_action_details.get('path')
            )
            self._active_combination_info = combo_action_details # Store the activated combination details
            # Add involved button names to _active_combination_info for release check
            self._active_combination_info['_buttons_internal'] = involved_button_names if combo_buttons_config else set()

            newly_pressed_pins.clear() # Prevent single action if part of combo
            
        elif not currently_pressed_pins: # No buttons are pressed, reset active combination info
             self._active_combination_info = None

        # Handle single button presses only if no combination was activated in this cycle
        if not combo_action_details and newly_pressed_pins:
            for pressed_pin in list(newly_pressed_pins): # Iterate over a copy
                state = self._button_states.get(pressed_pin)
                button_name = self._pin_to_button_name.get(pressed_pin)
                
                # Ensure it's a single button press, not part of a forming or just-fired combo,
                # and only one button is currently physically pressed.
                if state and not state.was_in_combo and button_name and len(currently_pressed_pins) == 1 and pressed_pin in currently_pressed_pins:
                    # Find the action for this single button
                    action_item_name_to_trigger: Optional[str] = None
                    action_item_details_to_trigger: Optional[Dict[str, Any]] = None

                    for item in self._combined_actions:
                        item_button_config = item['details'].get('button')
                        # Ensure it's a single button action definition
                        if isinstance(item_button_config, str) and item_button_config == button_name:
                            # Check if it's not actually a multi-button item misconfigured as string
                            # (though config validation should ideally catch this)
                            if isinstance(item['details'].get('button'), list) and len(item['details']['button']) > 1:
                                continue # Skip this item, it's for a combo

                            action_item_name_to_trigger = item['name']
                            action_item_details_to_trigger = item['details']
                            break # Found the corresponding action for the single button press
                    
                    if action_item_name_to_trigger and action_item_details_to_trigger:
                        current_active_action_name = self._action_handler.current_action_name
                        
                        # New Logic: Check if this button press corresponds to the currently active media item
                        if action_item_name_to_trigger == current_active_action_name:
                            print(f"[GPIO] Single press on active action button '{button_name}' ({action_item_name_to_trigger}).")
                            if self._default_media_name:
                                default_media_details = self._config.get('media', {}).get(self._default_media_name)
                                if default_media_details:
                                    print(f"[GPIO] Re-press of active action '{action_item_name_to_trigger}'. Returning to home: '{self._default_media_name}'")
                                    self._action_handler.execute_action(
                                        name=self._default_media_name,
                                        mode=default_media_details['mode'],
                                        path=default_media_details.get('path')
                                    )
                                else:
                                    print(f"[GPIO] Default media '{self._default_media_name}' not found in config. Stopping current action.")
                                    self._action_handler.stop_current()
                            else:
                                print("[GPIO] No default_media_name defined. Stopping current action.")
                                self._action_handler.stop_current()
                            # Mark as handled for this press cycle
                            # state.was_in_combo = True # Or a new flag
                            break # Processed this pin, move to next _handle_button_states cycle
                        else:
                            # Original behavior: trigger the action associated with this single button
                            print(f"[GPIO] Executing single action: Name='{action_item_name_to_trigger}', Mode='{action_item_details_to_trigger['mode']}', Path='{action_item_details_to_trigger.get('path')}'")
                            self._action_handler.execute_action(
                                name=action_item_name_to_trigger,
                                mode=action_item_details_to_trigger['mode'],
                                path=action_item_details_to_trigger.get('path')
                            )
                            # Mark as handled for this press cycle
                            # state.was_in_combo = True # Or a new flag
                            break # Found and executed action for this single button

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