import threading
from typing import Optional, Dict, Any, TYPE_CHECKING
from .image_display import ImageDisplay
from .hdmi_controller import HDMIController
from .config_updater import ConfigUpdater # Added import

if TYPE_CHECKING:
    from .app import Application # Forward reference for type hinting

class ActionHandler:
    """Handles the execution of actions when buttons are pressed."""
    
    def __init__(self,
                 media_config: Dict[str, Dict[str, Any]],
                 flash_duty_cycle: float,
                 flash_duration: float,
                 scroll_text_speed: int,
                 scroll_text_font_size: int,
                 scroll_text_font_color: str,
                 scroll_text_bg_color: Optional[str],
                 app_config_path: str,
                 app_ref: 'Application'): # Added app_ref
       self._lock = threading.RLock()
       self._current_action_details: Optional[Dict[str, Any]] = None
       self._image_display_service: Optional[ImageDisplay] = None
       self._media_config = media_config
       self.flash_duty_cycle = flash_duty_cycle
       self.flash_duration = flash_duration
       self._default_scroll_speed = scroll_text_speed
       self._default_scroll_font_size = scroll_text_font_size
       self._default_scroll_font_color = scroll_text_font_color
       self._default_scroll_bg_color = scroll_text_bg_color
       self._hdmi_controller = HDMIController()
       self._app_config_path = app_config_path # Store app_config_path
       # Pass app_ref to ConfigUpdater instead of self (action_handler_ref)
       self._config_updater = ConfigUpdater(app_ref=app_ref, app_config_path=self._app_config_path)

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
            # Stop current action if one is active and different from the new one
            if self._current_action_details and self._current_action_details.get('name') != name:
                print(f"[ActionHandler] Stopping: {self._current_action_details['name']} (Mode: {self._current_action_details['mode']}) due to new action '{name}'.")
                temp_details_to_stop = self._current_action_details.copy()
                self._current_action_details = None # Clear before calling stop_current
                self.stop_current(specific_details=temp_details_to_stop)
            elif self._current_action_details and \
                 self._current_action_details.get('name') == name and \
                 self._current_action_details.get('mode') == mode and \
                 self._current_action_details.get('path') == path:
                print(f"[ActionHandler] Action {name} (Mode: {mode}, Path: {str(path)}) is already active. Re-applying.")
                # Action is identical, effects will be re-applied by subsequent logic.
            
            # Set new action details (or update if re-triggering)
            self._current_action_details = {'name': name, 'mode': mode, 'path': path}
            path_str = str(path) if path else "N/A"
            print(f"[ActionHandler] Starting/Updating action: {name} (Mode: {mode}, Path: {path_str})")

            if mode == "image_still" or mode == "image_flash":
                if self._image_display_service:
                    if path:
                        print(f"[ActionHandler] Queuing 'set_image' for ImageDisplay: Path='{path}', Mode='{mode}'")
                        self._image_display_service.set_image(image_path=path, mode=mode)
                    else:
                        print(f"[ActionHandler] Error: No path provided for image mode '{mode}'. Clearing display.")
                        self._image_display_service.clear_image()
                        self._current_action_details = None # Action failed
                else:
                    print(f"[ActionHandler] Error: ImageDisplay service not available for image mode '{mode}'.")
                    self._current_action_details = None # Action failed
            
            elif mode == "hdmi_control":
                if self._hdmi_controller:
                    self._hdmi_controller.toggle_hdmi()
                    display_text = self._hdmi_controller.get_hdmi_status_message() # Get status after toggle
                    print(f"[ActionHandler] HDMI Toggled. Status: {display_text}")
                    if self._image_display_service:
                        self._image_display_service.display_text(text=display_text)
                else:
                    print(f"[ActionHandler] Error: HDMIController not available for mode '{mode}'.")
                    if self._image_display_service: # Still display an error if possible
                        self._image_display_service.display_text(text="HDMI Ctrl Error")
                    self._current_action_details = None # Action failed

            elif mode == "load_config":
                display_text = "Starting USB update process..."
                print(f"[ActionHandler] {display_text}")
                if self._image_display_service:
                    self._image_display_service.display_text(text=display_text)
                
                # Start the USB update process via ConfigUpdater
                if self._config_updater:
                    print(f"[ActionHandler] Calling ConfigUpdater to start USB update process for action: {name}")
                    self._config_updater.start_usb_update_process()
                else:
                    # This case should ideally not happen if __init__ is correct
                    print(f"[ActionHandler] Error: ConfigUpdater not available for mode '{mode}'.")
                    if self._image_display_service:
                        self._image_display_service.display_text(text="Update Error")
                    if self._current_action_details and self._current_action_details['name'] == name : self._current_action_details = None # Action failed

            elif mode == "scroll_text":
                if self._image_display_service:
                    if path: # Path to the text file
                        print(f"[ActionHandler] Queuing 'start_scroll_text' for ImageDisplay: File='{path}', "
                              f"Speed={self._default_scroll_speed}, FontSize={self._default_scroll_font_size}, "
                              f"Color='{self._default_scroll_font_color}', BG='{self._default_scroll_bg_color}'")
                        self._image_display_service.start_scroll_text(
                            file_path=path,
                            speed=self._default_scroll_speed,
                            font_size=self._default_scroll_font_size,
                            font_color_str=self._default_scroll_font_color,
                            bg_color_str=self._default_scroll_bg_color
                        )
                    else:
                        print(f"[ActionHandler] Error: No path provided for scroll_text mode. Clearing display.")
                        self._image_display_service.clear_image() # Or display an error message
                        if self._current_action_details and self._current_action_details['name'] == name : self._current_action_details = None # Action failed
                else:
                    print(f"[ActionHandler] Error: ImageDisplay service not available for mode {mode}.")
                    self._current_action_details = None # Action failed

            else:
                # This 'else' means the mode is not one of the explicitly handled ones above.
                handled_modes = ["image_still", "image_flash", "hdmi_control", "load_config", "scroll_text"]
                if mode not in handled_modes:
                    print(f"[ActionHandler] Warning: Unknown action mode '{mode}' for action '{name}'.")
                    # Optionally clear current_action_details if the mode is truly unhandled
                    # For now, we keep _current_action_details set, as the action was "started".

    def stop_current(self, specific_details: Optional[Dict[str, Any]] = None) -> None:
        """
        Stops the currently running action, or a specific action if details are provided.
        Ensures that display elements are cleared for relevant action modes.
        """
        with self._lock:
            details_to_stop = None
            if specific_details:
                details_to_stop = specific_details
            elif self._current_action_details: # Fallback to current if no specific details
                details_to_stop = self._current_action_details

            if details_to_stop:
                action_name = details_to_stop.get('name', 'Unknown Action')
                action_mode = details_to_stop.get('mode', 'Unknown Mode')
                
                print(f"[ActionHandler] Processing stop for action: {action_name} (Mode: {action_mode})")

                # Clear display for modes that use it
                if action_mode in ["image_still", "image_flash", "hdmi_control", "load_config", "scroll_text"]: # Add "scroll_text"
                    if self._image_display_service:
                        print(f"[ActionHandler] Queuing 'clear_image' for ImageDisplay for stopped action: {action_name}")
                        self._image_display_service.clear_image()
                
                # Placeholder for stopping other types of actions (e.g., specific hardware control)

                # If stop_current was called directly (not via specific_details from execute_action),
                # and the action being stopped was indeed the _current_action_details, clear it.
                # If specific_details were provided, execute_action has already managed _current_action_details.
                if not specific_details and self._current_action_details and \
                   self._current_action_details.get('name') == action_name and \
                   self._current_action_details.get('mode') == action_mode:
                    self._current_action_details = None
            # else:
            #     print("[ActionHandler] stop_current called, but no action was active or specified to stop.")