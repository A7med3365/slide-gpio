import json
import threading
import time
from typing import Dict, Set, Optional, Any
from vtc_engine.action_handler import ActionHandler
from vtc_engine.button_state import ButtonState
from .config_manager import ConfigManager
from pyA64.gpio import gpio

class GPIOMonitor(threading.Thread):
    """Monitors GPIO buttons with support for combinations."""

    def __init__(self, config_manager: ConfigManager, action_handler: ActionHandler):
        """Initialize GPIO monitor with configuration from ConfigManager."""
        super().__init__(name="GPIOMonitorThread")
        self.daemon = True
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()
        self._action_handler = action_handler
        self._config_manager = config_manager

        settings = self._config_manager.get_settings()
        # self._debounce_time = float(settings.get('debounce_time', 0.3)) # Kept for reference if push buttons are used again
        self._poll_interval = float(settings.get('poll_interval', 0.05))
        self._default_hold_time = float(settings.get('default_combo_hold_time', 1.0))
        
        self._default_media_name = self._config_manager.get_default_media_name()
        if self._default_media_name:
            print(f"[GPIO] Default media name loaded: {self._default_media_name}")
        else:
            print("[GPIO] No default_media_name found in settings.")

        self._button_states: Dict[int, ButtonState] = {}
        self._pin_to_button_name: Dict[int, str] = {}
        self._button_modes: Dict[str, str] = {} # Store button modes (press/toggle)

        for btn_name, button_details in self._config_manager.get_buttons_config().items():
            pin_value = int(button_details['value'])
            self._button_states[pin_value] = ButtonState()
            self._pin_to_button_name[pin_value] = btn_name
            self._button_modes[btn_name] = button_details.get('mode', 'press') # Default to 'press' if not specified
        
        self._active_combination_info: Optional[Dict[str, Any]] = None
        self._combination_start_time: float = 0.0
        self._held_buttons_for_combo: Set[str] = set()
        
        self._combined_actions = self._config_manager.get_combined_actions()
        
        print(f"[GPIO] Monitor initialized. Buttons: {len(self._button_states)}, Combined Actions: {len(self._combined_actions)}")

    def _init_gpio(self) -> bool:
        """Initialize GPIO hardware."""
        try:
            gpio.init()
            for button_details in self._config_manager.get_buttons_config().values():
                pin = int(button_details['value'])
                gpio.setcfg(pin, gpio.INPUT)
                gpio.pullup(pin, gpio.PULLUP)
                print(f"[GPIO] Configured pin {pin} as INPUT with PULLUP")
            return True
        except Exception as e:
            print(f"[GPIO] Error initializing GPIO: {e}")
            return False

    def _check_combinations(self, current_pressed_button_names: Set[str], current_time: float) -> Optional[Dict[str, Any]]:
        """Check for active button combinations based on currently ON toggle button names and hold time."""
        # This function largely remains the same, but current_pressed_button_names is now derived from latched toggle states
        if not current_pressed_button_names:
            self._held_buttons_for_combo.clear()
            self._combination_start_time = 0.0
            # Do not clear _active_combination_info here, allow it to be cleared if the combo is no longer met
            return None

        for item in self._combined_actions:
            item_button_config = item['details'].get('button')
            if not item_button_config:
                continue

            required_button_names: Set[str]
            if isinstance(item_button_config, str):
                required_button_names = {item_button_config}
            elif isinstance(item_button_config, list):
                required_button_names = set(item_button_config)
            else:
                continue

            if len(required_button_names) <= 1: # Only consider combinations
                continue

            if current_pressed_button_names == required_button_names:
                if self._held_buttons_for_combo != required_button_names:
                    self._held_buttons_for_combo = required_button_names.copy()
                    self._combination_start_time = current_time
                    return None 

                hold_time = float(item['details'].get('hold_time', self._default_hold_time))
                if current_time - self._combination_start_time >= hold_time:
                    if not self._active_combination_info or self._active_combination_info['name'] != item['name']:
                        print(f"[GPIO] Combination '{item['name']}' activated after {hold_time:.1f}s hold.")
                        return {
                            'name': item['name'],
                            'mode': item['details']['mode'],
                            'path': item['details'].get('path'),
                            '_buttons_internal': required_button_names.copy() # Store buttons for this combo
                        }
                return None 
        
        self._held_buttons_for_combo.clear()
        self._combination_start_time = 0.0
        return None

    def _handle_button_states(self) -> None:
        """Process current button states and detect single or combination actions for toggle buttons."""
        current_time = time.monotonic()
        
        pins_toggled_on_this_cycle: Set[int] = set()
        pins_toggled_off_this_cycle: Set[int] = set()
        currently_pressed_pins: Set[int] = set() # Pins of toggle buttons currently latched ON

        for pin, state in self._button_states.items():
            button_name = self._pin_to_button_name.get(pin)
            button_mode = self._button_modes.get(button_name, 'press')

            try:
                current_pin_state = gpio.input(pin) # 0 for pressed/ON, 1 for not pressed/OFF

                if button_mode == 'toggle':
                    if state.last_state != current_pin_state: # Toggle switch was flipped
                        if current_pin_state == 0: # Switched to ON
                            print(f"[GPIO] Toggle Pin {pin} ({button_name}) toggled ON")
                            if not state.is_pressed: # Was previously OFF
                                pins_toggled_on_this_cycle.add(pin)
                            state.is_pressed = True
                        else: # Switched to OFF (current_pin_state == 1)
                            print(f"[GPIO] Toggle Pin {pin} ({button_name}) toggled OFF")
                            if state.is_pressed: # Was previously ON
                                pins_toggled_off_this_cycle.add(pin)
                            state.is_pressed = False
                        state.was_in_combo = False # Reset combo status on any toggle change
                    
                    if state.is_pressed:
                        currently_pressed_pins.add(pin)
                    state.last_state = current_pin_state

                # else: # Original push-button logic (kept for reference)
                #     # if state.last_state != current_pin_state: # State changed
                #     #     if current_pin_state == 0: # Pin pressed (transitioned to LOW)
                #     #         # Debounce for push buttons
                #     #         if current_time - state.last_press_time > self._debounce_time:
                #     #             state.is_pressed = True
                #     #             state.last_press_time = current_time
                #     #             state.was_in_combo = False # Reset combo flag on new press
                #     #             print(f"[GPIO] Pin {pin} ({button_name}) pressed")
                #     #             # For push buttons, newly_pressed_pins would be used here
                #     # else: # Pin released (transitioned to HIGH)
                #     #     state.is_pressed = False
                #     # state.last_state = current_pin_state
                #     # if current_pin_state == 0: # Pin is currently pressed (for push buttons)
                #     # currently_pressed_pins.add(pin) # This would be for push buttons
                pass # End of per-button processing

            except Exception as e:
                print(f"[GPIO] Error reading pin {pin}: {e}")

        current_pressed_button_names = {self._pin_to_button_name[pin] for pin in currently_pressed_pins if pin in self._pin_to_button_name}
        
        # 1. Check for Combinations
        combo_action_details = self._check_combinations(current_pressed_button_names, current_time)
        
        # If a new combination has just activated
        if combo_action_details and (not self._active_combination_info or self._active_combination_info['name'] != combo_action_details['name']):
            print(f"[GPIO] Executing NEW combination action: Name='{combo_action_details['name']}'")
            self._action_handler.execute_action(
                name=combo_action_details['name'],
                mode=combo_action_details['mode'],
                path=combo_action_details.get('path'),
                action_params=None # Combos typically don't have specific action_params like hdmi target_state
            )
            self._active_combination_info = combo_action_details
            # Mark involved buttons as being part of this active combo
            for pin_in_combo_name in combo_action_details.get('_buttons_internal', set()):
                for pin_val, btn_name_lookup in self._pin_to_button_name.items():
                    if btn_name_lookup == pin_in_combo_name:
                        if pin_val in self._button_states:
                            self._button_states[pin_val].was_in_combo = True
            return # Prioritize combo activation

        # If an existing combination is no longer met
        if self._active_combination_info and not combo_action_details:
            # Check if the specific buttons for the active combo are still pressed
            active_combo_buttons = self._active_combination_info.get('_buttons_internal', set())
            if not active_combo_buttons.issubset(current_pressed_button_names):
                print(f"[GPIO] Active combination '{self._active_combination_info['name']}' NO LONGER MET. Reverting to default.")
                self._active_combination_info = None
                if self._default_media_name:
                    default_media_details = self._config_manager.get_media_config().get(self._default_media_name)
                    if default_media_details:
                        self._action_handler.execute_action(
                            name=self._default_media_name,
                            mode=default_media_details['mode'],
                            path=default_media_details.get('path'),
                            action_params=None
                        )
                    else: self._action_handler.stop_current() # Fallback
                else: self._action_handler.stop_current() # Fallback
                return # Combo state changed, re-evaluate next cycle

        # 2. Handle Single Button Toggles (if no combo was just activated or deactivated)
        # Handle toggling ON
        for pin_on in pins_toggled_on_this_cycle:
            button_on_name = self._pin_to_button_name.get(pin_on)
            if not button_on_name or self._button_modes.get(button_on_name) != 'toggle':
                continue

            # Ensure this button is not part of an ALREADY active combination
            if self._active_combination_info and button_on_name in self._active_combination_info.get('_buttons_internal', set()):
                continue # Part of an active combo, don't trigger single action

            # Check if this ON toggle should trigger a single action
            # A single action is triggered if this is the only button ON, or if it's configured for single action
            # and not overridden by a current combination.
            
            # Find the action for this single button
            action_to_trigger: Optional[Dict[str, Any]] = None
            for item in self._combined_actions:
                item_button_config = item['details'].get('button')
                if isinstance(item_button_config, str) and item_button_config == button_on_name:
                    # Ensure it's truly a single button action (not a misconfigured combo)
                    is_single_def = True
                    if isinstance(self._config_manager.get_media_config().get(item['name'], {}).get('button'), list) or \
                       isinstance(self._config_manager.get_actions_config().get(item['name'], {}).get('button'), list):
                        if len(item_button_config) > 1: is_single_def = False
                    
                    if is_single_def:
                        action_to_trigger = item
                        break
            
            if action_to_trigger:
                # If another single action is active by a different button, stop it.
                # If a combo is active, this path shouldn't be hit due to earlier return/checks.
                current_ah_action_name = self._action_handler.current_action_name
                if current_ah_action_name and current_ah_action_name != action_to_trigger['name'] and not self._active_combination_info:
                     print(f"[GPIO] Different single action '{current_ah_action_name}' was active. Stopping it.")
                     # Reverting to default implicitly stops the old one if it's not the default.
                     # Or, explicitly stop then execute. For now, execute_action handles stopping previous.
  
                action_params_for_on_toggle = None
                if action_to_trigger['details']['mode'] == 'hdmi_control':
                    action_params_for_on_toggle = {'target_state': 'off'} # Button ON -> Screen OFF
                    print(f"[GPIO] HDMI control: Button '{button_on_name}' ON, setting screen OFF.")
                
                print(f"[GPIO] Executing single toggle-ON action: Name='{action_to_trigger['name']}', Params: {action_params_for_on_toggle}")
                self._action_handler.execute_action(
                    name=action_to_trigger['name'],
                    mode=action_to_trigger['details']['mode'],
                    path=action_to_trigger['details'].get('path'),
                    action_params=action_params_for_on_toggle
                )
                # Clear active combo if a single action overrides
                if self._active_combination_info and action_to_trigger['name'] != self._active_combination_info['name']:
                    self._active_combination_info = None
                return # Processed one toggle ON event

        # Handle toggling OFF
        for pin_off in pins_toggled_off_this_cycle:
            button_off_name = self._pin_to_button_name.get(pin_off)
            if not button_off_name or self._button_modes.get(button_off_name) != 'toggle':
                continue

            # Check if this button_off_name is specifically for 'hdmi_control'
            hdmi_action_details_for_off_toggle: Optional[Dict[str, Any]] = None
            for item in self._combined_actions:
                if item['details'].get('button') == button_off_name and item['details']['mode'] == 'hdmi_control':
                    hdmi_action_details_for_off_toggle = item
                    break
            
            if hdmi_action_details_for_off_toggle:
                action_params_for_off_toggle = {'target_state': 'on'} # Button OFF -> Screen ON
                print(f"[GPIO] HDMI control: Button '{button_off_name}' OFF, setting screen ON.")
                self._action_handler.execute_action(
                    name=hdmi_action_details_for_off_toggle['name'],
                    mode=hdmi_action_details_for_off_toggle['details']['mode'],
                    path=hdmi_action_details_for_off_toggle['details'].get('path'),
                    action_params=action_params_for_off_toggle
                )
                return # Processed HDMI toggle OFF event

            # Original logic for other buttons toggling OFF (reverting to default)
            current_ah_action_name = self._action_handler.current_action_name
            # Ensure we are not dealing with hdmi_control here again, as it's handled above.
            if current_ah_action_name and not self._active_combination_info:
                is_single_action_match = False
                for item in self._combined_actions:
                    if item['name'] == current_ah_action_name and item['details'].get('button') == button_off_name:
                        # Make sure this is NOT the hdmi_control action we just handled
                        if item['details']['mode'] != 'hdmi_control':
                            is_single_action_match = True
                        break
                
                if is_single_action_match:
                    print(f"[GPIO] Single action button '{button_off_name}' (not HDMI) toggled OFF. Reverting to default.")
                    if self._default_media_name:
                        default_media_details = self._config_manager.get_media_config().get(self._default_media_name)
                        if default_media_details:
                            self._action_handler.execute_action(
                                name=self._default_media_name,
                                mode=default_media_details['mode'],
                                path=default_media_details.get('path'),
                                action_params=None
                            )
                        else: self._action_handler.stop_current() # Fallback
                    else: self._action_handler.stop_current() # Fallback
                    return # Processed one toggle OFF event

        # If no buttons are ON, and an action (single or combo) was active, revert to default.
        if not currently_pressed_pins:
            action_was_active = self._action_handler.current_action_name and self._action_handler.current_action_name != self._default_media_name
            combo_was_active = self._active_combination_info is not None

            if action_was_active or combo_was_active:
                print("[GPIO] All toggle buttons are OFF. Reverting to default media.")
                self._active_combination_info = None # Clear any active combo
                if self._default_media_name:
                    default_media_details = self._config_manager.get_media_config().get(self._default_media_name)
                    if default_media_details:
                        # Check if default is already active to prevent loop
                        if self._action_handler.current_action_name != self._default_media_name:
                            self._action_handler.execute_action(
                                name=self._default_media_name,
                                mode=default_media_details['mode'],
                                path=default_media_details.get('path'),
                                action_params=None
                            )
                    else: self._action_handler.stop_current() # Fallback
                else: self._action_handler.stop_current() # Fallback


    def stop(self) -> None:
        """Signal the thread to stop and cleanup resources."""
        print("[GPIO] Stop requested")
        self._shutdown_event.set()
        # self._action_handler.stop_current() # stop_current is called by App.stop

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