import threading
from typing import Optional, Dict, Any
from .image_display import ImageDisplay

class ActionHandler:
    """Handles the execution of actions when buttons are pressed."""
    
    def __init__(self, flash_duty_cycle: float, flash_duration: float):
        self._lock = threading.Lock()
        self._current_action_details: Optional[Dict[str, Any]] = None
        self._image_display_thread: Optional[ImageDisplay] = None
        self.flash_duty_cycle = flash_duty_cycle
        self.flash_duration = flash_duration
    
    @property
    def current_action_name(self) -> Optional[str]:
        if self._current_action_details:
            return self._current_action_details['name']
        return None

    def start_services(self) -> None:
        """Starts the ImageDisplay service if not already running."""
        with self._lock:
            if self._image_display_thread is None:
                self._image_display_thread = ImageDisplay(
                    flash_duty_cycle=self.flash_duty_cycle,
                    flash_duration=self.flash_duration
                )
                self._image_display_thread.start()
                print("[ActionHandler] ImageDisplay service started.")

    def stop_services(self) -> None:
        """Stops the ImageDisplay service."""
        with self._lock:
            if self._image_display_thread is not None and self._image_display_thread.is_alive():
                self._image_display_thread.stop()
                self._image_display_thread.join(timeout=2.0)
                print("[ActionHandler] ImageDisplay service stopped.")
                self._image_display_thread = None # Clear the reference
    
    def execute_action(self, name: str, mode: str, path: Optional[str] = None) -> None:
        """Executes the specified action."""
        with self._lock:
            # Stop previous action first
            if self._current_action_details:
                # We call the full stop_current logic to ensure proper cleanup
                # This will re-acquire the lock, which is fine for reentrant locks
                # or if we release and re-acquire.
                # For simplicity, we'll rely on the fact that stop_current also locks.
                # A more robust way might be to have an internal _stop_current_action
                # that doesn't lock, but this should work for now.
                # print(f"[ActionHandler] Stopping previous action: {self._current_action_details['name']} before starting new one.")
                self.stop_current() # This will handle clearing _current_action_details

            # Now, handle the new action
            if mode == "image_still" or mode == "image_flash":
                if self._image_display_thread is None or not self._image_display_thread.is_alive():
                    # This check might be redundant if Application ensures start_services is called.
                    # However, it's a good safeguard.
                    print("[ActionHandler] ImageDisplay service was not running. Starting it now.")
                    self.start_services() # This will also acquire lock

                if self._image_display_thread: # Check again after potential start
                    if path:
                        self._image_display_thread.set_image(image_path=path, mode=mode)
                        self._current_action_details = {'name': name, 'mode': mode, 'path': path}
                        print(f"[ActionHandler] Starting: {name} (Mode: {mode}, Path: {path})")
                    else:
                        print(f"[ActionHandler] Error: No path provided for image mode {mode}")
                        if self._image_display_thread: # Ensure it exists before calling clear
                             self._image_display_thread.clear_image()
                        self._current_action_details = None # Action failed or is a clear
                else:
                    print(f"[ActionHandler] Error: ImageDisplay service could not be started for {name}.")
                    self._current_action_details = None

            else: # Other action modes
                # Placeholder for other action types
                path_str = path if path else "N/A"
                print(f"[ActionHandler] Starting: {name} (Mode: {mode}, Path: {path_str})")
                # For non-image actions, we still need to set current_action_details
                self._current_action_details = {'name': name, 'mode': mode, 'path': path}


    def stop_current(self) -> None:
        """Stops the currently running action."""
        with self._lock:
            if self._current_action_details:
                action_name = self._current_action_details['name']
                action_mode = self._current_action_details['mode']
                print(f"[ActionHandler] Stopping: {action_name} (Mode: {action_mode})")

                if action_mode == "image_still" or action_mode == "image_flash":
                    if self._image_display_thread and self._image_display_thread.is_alive():
                        self._image_display_thread.clear_image()
                
                # Placeholder for stopping other types of actions
                # e.g., if action_mode == "scroll_text": self._text_scroller.stop()

                self._current_action_details = None
            # else:
            #     print("[ActionHandler] No current action to stop.")