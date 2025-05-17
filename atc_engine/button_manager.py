"""
Button Manager Module
-------------------
Handles button state tracking and management.
"""

from typing import Dict, List, Set, Optional, Tuple
import time

class ButtonState:
    """Tracks the state of a button including timing information."""
    def __init__(self, mode: str = "press"):
        self.is_pressed: bool = False
        self.is_toggled: bool = False  # For toggle mode buttons
        self.last_press_time: float = 0.0
        self.last_state: int = 1  # Default to HIGH (not pressed)
        self.was_in_combo: bool = False  # Track if button was part of a combo
        self.mode: str = mode
        self.hold_start_time: Optional[float] = None

    def update(self, state: int, current_time: float) -> None:
        """Update button state with new input."""
        if state != self.last_state:
            if state == 0:  # Button pressed
                self.is_pressed = True
                self.last_press_time = current_time
                self.hold_start_time = current_time
                if self.mode == "toggle":
                    self.is_toggled = not self.is_toggled
            else:  # Button released
                self.is_pressed = False
                self.hold_start_time = None
            self.last_state = state

    def get_hold_duration(self, current_time: float) -> float:
        """Get the current hold duration if button is being held."""
        if self.hold_start_time is None:
            return 0.0
        return current_time - self.hold_start_time

class ButtonManager:
    """Manages button states and combinations."""
    def __init__(self, config: Dict):
        self.buttons: Dict[str, ButtonState] = {}
        self.config = config
        self.active_combinations: Set[Tuple[str, ...]] = set()
        self.current_time: float = time.time()
        
        # Initialize button states
        for btn_name, btn_config in config['buttons'].items():
            self.buttons[btn_name] = ButtonState(mode=btn_config['mode'])

    def update_button_state(self, button_name: str, state: int) -> None:
        """Update the state of a single button."""
        if button_name in self.buttons:
            self.current_time = time.time()
            self.buttons[button_name].update(state, self.current_time)

    def is_button_pressed(self, button_name: str) -> bool:
        """Check if a button is currently pressed."""
        return self.buttons.get(button_name, ButtonState()).is_pressed

    def is_button_toggled(self, button_name: str) -> bool:
        """Check if a toggle mode button is currently toggled on."""
        button = self.buttons.get(button_name)
        return button.is_toggled if button and button.mode == "toggle" else False

    def get_pressed_buttons(self) -> List[str]:
        """Get a list of currently pressed button names."""
        return [name for name, state in self.buttons.items() if state.is_pressed]

    def get_active_combinations(self) -> List[Tuple[str, ...]]:
        """Get currently active button combinations."""
        combinations = []
        pressed_buttons = set(self.get_pressed_buttons())
        
        # Check media combinations
        for media_name, media_config in self.config['media'].items():
            if 'button' in media_config:
                buttons = media_config['button'] if isinstance(media_config['button'], list) else [media_config['button']]
                button_set = set(buttons)
                
                if button_set.issubset(pressed_buttons):
                    hold_time = media_config.get('hold_time', self.config['settings']['default_combo_hold_time'])
                    # Check hold time for all buttons in combination
                    if all(self.buttons[btn].get_hold_duration(self.current_time) >= hold_time for btn in button_set):
                        combinations.append(tuple(sorted(button_set)))

        # Check action combinations
        for action_name, action_config in self.config['actions'].items():
            buttons = action_config['button'] if isinstance(action_config['button'], list) else [action_config['button']]
            button_set = set(buttons)
            
            if button_set.issubset(pressed_buttons):
                hold_time = action_config.get('hold_time', self.config['settings']['default_combo_hold_time'])
                if all(self.buttons[btn].get_hold_duration(self.current_time) >= hold_time for btn in button_set):
                    combinations.append(tuple(sorted(button_set)))

        return combinations

    def get_button_hold_duration(self, button_name: str) -> float:
        """Get how long a button has been held down."""
        if button_name in self.buttons:
            return self.buttons[button_name].get_hold_duration(self.current_time)
        return 0.0

    def reset_button_states(self) -> None:
        """Reset all button states."""
        for button in self.buttons.values():
            button.is_pressed = False
            button.was_in_combo = False
            button.hold_start_time = None