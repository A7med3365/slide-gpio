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
                if "button" not in media_config: # Ensure button key exists
                    continue
                
                buttons = media_config["button"] if isinstance(media_config["button"], list) else [media_config["button"]]
                button_set = tuple(sorted(buttons))
                
                if button_set in new_combinations:
                    # Case 1: Button for the *currently active* media is pressed again
                    if media_name == self._current_media:
                        print(f"[ActionHandler] Button for active media '{media_name}' pressed again. Returning to default.")
                        self.stop_current() # This will trigger default media display
                        # Since we are returning to default, we might not want other combinations to trigger immediately.
                        # Consider if a break or a flag is needed if multiple combinations are met.
                        # For now, let stop_current handle it and proceed.
                    # Case 2: No media is active, or the default media is active, and a new media is triggered
                    elif not self._current_media or self._current_media == self._config.get('settings', {}).get('default_media_name'):
                        self.execute_media(media_name, media_config)
                    # Case 3: A different media is active, and a new media is triggered
                    else: # self._current_media is active and is not media_name and not default
                        print(f"[ActionHandler] Switching from '{self._current_media}' to '{media_name}'.")
                        self.execute_media(media_name, media_config) # execute_media handles stopping the old one

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
        if self._current_media == media_name: # Add this check
            print(f"[Media] '{media_name}' is already active.") # Optional: log this
            return # Add this return

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
        """Stop current media and action, then display default media if configured."""
        with self._lock:
            stopped_media = False
            if self._current_media:
                print(f"[Media] Stopping: {self._current_media}")
                # Add any specific media stop logic here if needed (e.g., kill process)
                self._current_media = None
                stopped_media = True
            
            if self._current_action:
                print(f"[Action] Stopping: {self._current_action}")
                # Add any specific action stop logic here
                self._current_action = None

            # If any media was stopped or no media was active, try to show default
            if stopped_media or not self._current_media : # Ensure default shows if nothing was active too
                default_media_name = self._config.get('settings', {}).get('default_media_name')
                if default_media_name and default_media_name in self._config.get('media', {}):
                    # Avoid re-triggering if default is already what we intended to stop to.
                    # This check is now in execute_media, so direct call is fine.
                    print(f"[ActionHandler] Reverting to default media: {default_media_name}")
                    default_media_config = self._config['media'][default_media_name]
                    # Temporarily set _current_media to None to allow execute_media to run the default
                    # This is a bit of a hack; execute_media should ideally handle this better.
                    # For now, this ensures the default media actually plays.
                    # The check `if self._current_media == media_name:` in execute_media
                    # would prevent it if _current_media was just set to None and default_media_name was also None (edge case).
                    # However, default_media_name should always be a valid string.
                    # Let's assume execute_media's check is sufficient.
                    self.execute_media(default_media_name, default_media_config)
                else:
                    print("[ActionHandler] No default media configured or found to revert to.")

    def cleanup(self) -> None:
        """Clean up any resources."""
        self.stop_current()