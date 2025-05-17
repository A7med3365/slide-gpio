import threading
from typing import Optional, Dict, Any
from .image_display import ImageDisplay

class ActionHandler:
    """Handles the execution of actions when buttons are pressed."""
    
    def __init__(self, media_config: Dict[str, Dict[str, Any]], flash_duty_cycle: float, flash_duration: float):
        self._lock = threading.RLock()
        self._current_action_details: Optional[Dict[str, Any]] = None
        self._image_display_service: Optional[ImageDisplay] = None
        self._media_config = media_config
        self.flash_duty_cycle = flash_duty_cycle
        self.flash_duration = flash_duration
    
    @property
    def current_action_name(self) -> Optional[str]:
        if self._current_action_details:
            return self._current_action_details['name']
        return None

    def start_services(self) -> None:
        """Instantiates the ImageDisplay service if it doesn't exist."""
        with self._lock:
            if self._image_display_service is None:
                self._image_display_service = ImageDisplay(
                    media_config=self._media_config,
                    flash_duty_cycle=self.flash_duty_cycle,
                    flash_duration=self.flash_duration
                )
                print("[ActionHandler] ImageDisplay service instance created.")

    @property
    def image_display_service(self) -> Optional[ImageDisplay]:
        return self._image_display_service

    def stop_services(self) -> None:
        """Requests the ImageDisplay service to stop."""
        with self._lock:
            if self._image_display_service is not None:
                print("[ActionHandler] Requesting ImageDisplay service to stop...")
                self._image_display_service.stop_display() # This queues the 'stop' command
                self._image_display_service = None # Clear the reference
    
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
                if self._image_display_service is None:
                    # This should ideally not happen if start_services was called by Application
                    print("[ActionHandler] Error: ImageDisplay service not initialized. Cannot execute image action.")
                    self._current_action_details = None
                    return # Cannot proceed

                # Ensure _image_display_service exists (it should have been created by start_services)
                if path:
                    print(f"[ActionHandler] Queuing 'set_image' for ImageDisplay: Path='{path}', Mode='{mode}'")
                    self._image_display_service.set_image(image_path=path, mode=mode)
                    self._current_action_details = {'name': name, 'mode': mode, 'path': path}
                    # print(f"[ActionHandler] Queued image: {name} (Mode: {mode}, Path: {path})") # Original log, commented out or removed
                else: # No path, means clear the display for this action
                    print(f"[ActionHandler] Clearing image display for action: {name} (Mode: {mode})")
                    self._image_display_service.clear_image()
                    # Setting details even for a clear, as it's an explicit action
                    self._current_action_details = {'name': name, 'mode': mode, 'path': None}

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
                    if self._image_display_service:
                        print(f"[ActionHandler] Queuing 'clear_image' for ImageDisplay for stopped action: {self._current_action_details['name']}")
                        self._image_display_service.clear_image()
                
                # Placeholder for stopping other types of actions
                # e.g., if action_mode == "scroll_text": self._text_scroller.stop()

                self._current_action_details = None
            # else:
            #     print("[ActionHandler] No current action to stop.")