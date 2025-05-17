"""
Action Handler Module
------------------
Handles the execution of actions and media display when buttons are pressed.
"""

import threading
import subprocess
import os
from typing import Optional, Dict, Any, Set, Tuple

class ActionHandler:
    """Handles the execution of actions and media display."""
    
    def __init__(self, config: Dict[str, Any]):
        self._lock = threading.Lock()
        self._current_media: Optional[str] = None
        self._current_action: Optional[str] = None
        self._config = config
        self._active_combinations: Set[Tuple[str, ...]] = set()

    def _handle_hdmi_control(self) -> None:
        """Handle HDMI control action."""
        print("[Action] Toggle HDMI output")
        # Here we just simulate/log the action
        # In a real implementation, you would call the actual HDMI toggle code

    def _handle_load_config(self) -> None:
        """Handle config reload action."""
        print("[Action] Reload configuration")
        # Here we just simulate/log the action
        # In a real implementation, you would trigger config reload

    def _handle_media_flash(self, path: str) -> None:
        """Handle flash mode media."""
        print(f"[Media] Flash display: {path}")

    def _handle_media_still(self, path: str) -> None:
        """Handle still mode media."""
        print(f"[Media] Show still image: {path}")

    def _handle_media_slide(self, path: str) -> None:
        """Handle slide mode media."""
        print(f"[Media] Start slideshow from: {path}")

    def _handle_media_scroll_text(self, path: str) -> None:
        """Handle scroll text mode media."""
        print(f"[Media] Scroll text from: {path}")

    def handle_button_state(self, button_state: Dict[str, Any]) -> None:
        """Process button state and trigger appropriate actions/media."""
        with self._lock:
            # Get pressed buttons and active combinations
            pressed_buttons = set(button_state.get("pressed_buttons", []))
            new_combinations = set(button_state.get("active_combinations", []))

            # Check for media triggers
            for media_name, media_config in self._config["media"].items():
                buttons = media_config["button"] if isinstance(media_config["button"], list) else [media_config["button"]]
                button_set = tuple(sorted(buttons))
                
                if button_set in new_combinations:
                    self.execute_media(media_name, media_config)

            # Check for action triggers
            for action_name, action_config in self._config["actions"].items():
                buttons = action_config["button"] if isinstance(action_config["button"], list) else [action_config["button"]]
                button_set = tuple(sorted(buttons))
                
                if button_set in new_combinations:
                    self.execute_action(action_name, action_config)

            # Update active combinations
            self._active_combinations = new_combinations

            # Stop current media/action if no buttons are pressed
            if not pressed_buttons:
                self.stop_current()

    def execute_media(self, media_name: str, media_config: Dict[str, Any]) -> None:
        """Execute a media display action."""
        old_media = self._current_media
        self._current_media = media_name

        # Stop current media if different
        if old_media and old_media != media_name:
            print(f"[Media] Stopping: {old_media}")

        # Execute new media based on mode
        mode = media_config["mode"]
        path = media_config["path"]

        if mode == "flash":
            self._handle_media_flash(path)
        elif mode == "still":
            self._handle_media_still(path)
        elif mode == "slide":
            self._handle_media_slide(path)
        elif mode == "scroll_text":
            self._handle_media_scroll_text(path)
        else:
            print(f"[Media] Unknown media mode: {mode}")

    def execute_action(self, action_name: str, action_config: Dict[str, Any]) -> None:
        """Execute a system action."""
        old_action = self._current_action
        self._current_action = action_name

        # Stop current action if different
        if old_action and old_action != action_name:
            print(f"[Action] Stopping: {old_action}")

        # Execute new action based on mode
        mode = action_config["mode"]

        if mode == "hdmi_control":
            self._handle_hdmi_control()
        elif mode == "load_config":
            self._handle_load_config()
        else:
            print(f"[Action] Unknown action mode: {mode}")

    def stop_current(self) -> None:
        """Stop current media and action."""
        with self._lock:
            if self._current_media:
                print(f"[Media] Stopping: {self._current_media}")
                self._current_media = None
            
            if self._current_action:
                print(f"[Action] Stopping: {self._current_action}")
                self._current_action = None

    def cleanup(self) -> None:
        """Clean up any resources."""
        self.stop_current()