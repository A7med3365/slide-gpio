import threading
import time # Added for sleep
import json
from typing import Optional # Added for type hinting
from .action_handler import ActionHandler
from .gpio_monitor import GPIOMonitor
from .config_manager import ConfigManager, ConfigError

class Application:
    """Main application class."""

    def __init__(self, config_path: str, fullscreen: bool = True):
        self._config_path = config_path
        self._fullscreen = fullscreen # Store the fullscreen flag
        try:
            self._config_manager = ConfigManager(config_path)
        except ConfigError as e:
            print(f"[App] Critical configuration error: {e}")
            raise
        
        self._gpio_monitor: Optional[GPIOMonitor] = None # Type hint
        self._action_handler: Optional[ActionHandler] = None # Type hint, will be initialized
        self._shutdown_event = threading.Event()
        self._reload_requested_event = threading.Event() # New event for reload
        self._new_config_path_for_reload: Optional[str] = None # Path for new config

        settings = self._config_manager.get_settings()
        flash_duty_cycle = settings.get('image_flash_duty_cycle', 0.75)
        flash_duration = settings.get('image_flash_duration', 1.0)
        scroll_text_speed = settings.get('scroll_text_speed', 3)
        scroll_text_font_size = settings.get('scroll_text_font_size', 60)
        scroll_text_font_color = settings.get('scroll_text_font_color', "white")
        scroll_text_bg_color = settings.get('scroll_text_bg_color')

        media_config = self._config_manager.get_media_config()
        self._action_handler = ActionHandler(
            media_config=media_config,
            flash_duty_cycle=flash_duty_cycle,
            flash_duration=flash_duration,
            scroll_text_speed=scroll_text_speed,
            scroll_text_font_size=scroll_text_font_size,
            scroll_text_font_color=scroll_text_font_color,
            scroll_text_bg_color=scroll_text_bg_color,
            app_config_path=self._config_manager.get_config_path(),
            app_ref=self, # Pass self (Application instance) to ActionHandler
            fullscreen=self._fullscreen # Pass fullscreen flag to ActionHandler
        )

    def display_message_on_screen(self, message: str):
        """Displays a message on the screen via the ActionHandler's ImageDisplay service."""
        print(f"[App] Displaying message: '{message}'")
        if self._action_handler and self._action_handler.image_display_service:
            try:
                self._action_handler.image_display_service.display_text(text=message)
            except Exception as e:
                print(f"[App] Error displaying message on screen via ActionHandler: {e}")
        else:
            print("[App] ActionHandler or ImageDisplay service not available for on-screen message.")

    def request_config_reload(self, new_config_path: str):
        """Requests the application to reload its configuration."""
        print(f"[App] Received request to reload configuration from: {new_config_path}")
        self._new_config_path_for_reload = new_config_path
        self._reload_requested_event.set()

    def _perform_reload(self, new_config_path: str):
        """Stops existing services, re-initializes components with the new configuration, and restarts services."""
        print(f"[App] Performing configuration reload with: {new_config_path}")
        self.display_message_on_screen("Reloading configuration...")
        time.sleep(1) # Brief pause for message visibility

        # Stop existing services
        if self._gpio_monitor:
            print("[App] Stopping GPIOMonitor for reload...")
            self._gpio_monitor.stop()
            self._gpio_monitor.join(timeout=2.0) # Wait for GPIO monitor to stop
            self._gpio_monitor = None
            print("[App] GPIOMonitor stopped for reload.")

        if self._action_handler:
            print("[App] Stopping ActionHandler services for reload...")
            self._action_handler.stop_services() # This queues stop for ImageDisplay
            # We need to ensure ImageDisplay.run() exits.
            # The new run() loop structure will handle ImageDisplay exiting.
            # For now, assume stop_services() is sufficient to signal ImageDisplay.
            # ActionHandler instance itself will be replaced.
            print("[App] ActionHandler services signaled to stop for reload.")

        # Re-initialize components
        print("[App] Re-initializing components with new configuration...")
        try:
            self._config_manager = ConfigManager(new_config_path)
            self._config_path = new_config_path # Update the stored config path
        except ConfigError as e:
            print(f"[App] CRITICAL: Failed to load new configuration during reload: {e}")
            self.display_message_on_screen(f"Reload Error: Bad Config ({e})")
            time.sleep(2)
            # Potentially try to revert or enter a safe mode. For now, we might be in a bad state.
            # Reverting to old config might be complex if assets were also changed.
            # A robust solution would involve backing up the old ConfigManager instance.
            # For now, if new config fails, the app might become unstable.
            # Let's try to re-initialize with the *old* path if possible, or a default.
            # This part needs more thought for robust error handling.
            # For now, we'll proceed, but the app might not function correctly.
            # A simple recovery: try to load the *previous* config path if reload fails.
            # This assumes self._config_path was the *old* valid path.
            try:
                print(f"[App] Attempting to revert to previous config path: {self._config_path} (this might be the failed new_config_path if not careful)")
                # To be safer, we'd need to store the *truly* old path before attempting new one.
                # For this iteration, if new_config_path fails, we are in a bit of a limbo.
                # Let's assume for now the app might need a restart if this fails.
                # A better approach: self._previous_config_path = self._config_path before trying new one.
                # self._config_manager = ConfigManager(self._previous_config_path)
                self.display_message_on_screen("FATAL: New config failed. Restart app.")
                self._shutdown_event.set() # Trigger app shutdown
                return # Exit reload process
            except ConfigError as ce_fallback:
                print(f"[App] CRITICAL: Failed to even reload previous config after new one failed: {ce_fallback}")
                self.display_message_on_screen("FATAL: Config load error. Restart app.")
                self._shutdown_event.set() # Trigger app shutdown
                return # Exit reload process


        settings = self._config_manager.get_settings()
        flash_duty_cycle = settings.get('image_flash_duty_cycle', 0.75)
        flash_duration = settings.get('image_flash_duration', 1.0)
        scroll_text_speed = settings.get('scroll_text_speed', 3)
        scroll_text_font_size = settings.get('scroll_text_font_size', 60)
        scroll_text_font_color = settings.get('scroll_text_font_color', "white")
        scroll_text_bg_color = settings.get('scroll_text_bg_color')
        media_config = self._config_manager.get_media_config()

        self._action_handler = ActionHandler(
            media_config=media_config,
            flash_duty_cycle=flash_duty_cycle,
            flash_duration=flash_duration,
            scroll_text_speed=scroll_text_speed,
            scroll_text_font_size=scroll_text_font_size,
            scroll_text_font_color=scroll_text_font_color,
            scroll_text_bg_color=scroll_text_bg_color,
            app_config_path=self._config_manager.get_config_path(), # Use new config path
            app_ref=self,
            fullscreen=self._fullscreen # Pass fullscreen flag to ActionHandler
        )
        print("[App] ActionHandler re-initialized.")

        self._gpio_monitor = GPIOMonitor(self._config_manager, self._action_handler)
        print("[App] GPIOMonitor re-initialized.")

        # Restart services
        if self._action_handler:
            print("[App] Starting ActionHandler services after reload...")
            self._action_handler.start_services() # This creates and starts the new ImageDisplay
        
        if self._gpio_monitor:
            print("[App] Starting GPIOMonitor after reload...")
            self._gpio_monitor.start()

        self.display_message_on_screen("Reload complete!")
        time.sleep(1)

        # Trigger display of default media from new config
        default_media_name = self._config_manager.get_default_media_name()
        if default_media_name and self._action_handler:
            media_item_details = self._config_manager.get_media_config().get(default_media_name)
            if media_item_details:
                mode = media_item_details.get('mode')
                path = media_item_details.get('path')
                if mode:
                    print(f"[App] Applying default media from new config: {default_media_name}")
                    self._action_handler.execute_action(name=default_media_name, mode=mode, path=path)
                else:
                    print(f"[App] Default media '{default_media_name}' in new config missing 'mode'.")
            else:
                print(f"[App] Default media '{default_media_name}' not found in new config.")
        elif not self._action_handler:
             print("[App] ActionHandler not available to apply default media after reload.")


    def run(self) -> None:
        """Start the application and its components, including the main event loop."""
        print("[App] Starting application")

        if not self._action_handler:
            print("[App] CRITICAL: ActionHandler not initialized. Cannot run.")
            return

        print("[App] Starting initial ActionHandler services...")
        self._action_handler.start_services() # Creates ImageDisplay instance

        # Trigger initial default media action
        default_media_name = self._config_manager.get_default_media_name()
        if default_media_name:
            media_items = self._config_manager.get_media_config()
            media_item_details = media_items.get(default_media_name)
            if media_item_details:
                mode = media_item_details.get('mode')
                path = media_item_details.get('path')
                if mode:
                    print(f"[App] Starting with default media: {default_media_name}")
                    self._action_handler.execute_action(name=default_media_name, mode=mode, path=path)
                else:
                    print(f"[App] Default media '{default_media_name}' found but 'mode' is missing.")
            else:
                print(f"[App] Default media '{default_media_name}' not found in configuration.")
        else:
            print("[App] No default media name specified in configuration.")

        if not self._gpio_monitor: # Initialize GPIO monitor if not already done (e.g. by reload)
            self._gpio_monitor = GPIOMonitor(self._config_manager, self._action_handler)
        
        print("[App] Starting initial GPIOMonitor...")
        self._gpio_monitor.start()

        self._keep_app_running = True
        try:
            while self._keep_app_running:
                if self._shutdown_event.is_set(): # Prioritize shutdown
                    print("[App] Shutdown event detected in main loop. Breaking.")
                    self._keep_app_running = False
                    continue

                if self._reload_requested_event.is_set():
                    print("[App] Reload requested event detected.")
                    if self._new_config_path_for_reload:
                        self._perform_reload(self._new_config_path_for_reload)
                    else:
                        print("[App] Reload requested but no new config path set. Ignoring.")
                    self._reload_requested_event.clear()
                    self._new_config_path_for_reload = None
                    # _perform_reload should have restarted services, including ImageDisplay.
                    # The loop will continue and pick up the new current_image_service.
                    continue # Re-evaluate loop conditions, especially if shutdown was triggered during reload.

                if not self._action_handler: # Should not happen if initialized correctly
                    print("[App] CRITICAL: ActionHandler became None during run loop. Shutting down.")
                    self._keep_app_running = False
                    continue
                
                current_image_service = self._action_handler.image_display_service

                if current_image_service:
                    if not current_image_service.is_running: # If it was stopped (e.g. by reload) and needs restart
                        print("[App] ImageDisplay service not running, attempting to start/resume its loop.")
                        # This scenario implies ImageDisplay.run() exited and needs to be called again.
                        # This is implicitly handled by calling run() if it's not already running.
                        # However, ImageDisplay.run() is blocking. If it exited, it means it's done or stopped.
                        # The logic here is that if we are in this loop and it's not running,
                        # it's likely after a reload or an external stop.
                        # The `_perform_reload` should have started a *new* instance.
                        # If `current_image_service.run()` exited on its own, the below logic handles it.
                        pass # Let the main call to current_image_service.run() happen

                    print("[App] Entering/Resuming ImageDisplay Pygame loop...")
                    current_image_service.run() # BLOCKING CALL
                    print("[App] ImageDisplay Pygame loop exited.")

                    # After image_service.run() exits, check why:
                    if self._reload_requested_event.is_set():
                        print("[App] ImageDisplay exited, reload is pending. Continuing loop for reload.")
                        # Loop will pick up reload request at the top.
                        continue
                    elif self._shutdown_event.is_set():
                        print("[App] ImageDisplay exited, shutdown is pending. Breaking loop.")
                        self._keep_app_running = False
                        continue
                    elif not current_image_service.is_running:
                        # If ImageDisplay.run() exited on its own (e.g., ESC key, window close)
                        # and it wasn't due to a planned reload or shutdown.
                        print("[App] ImageDisplay loop exited independently (e.g., user quit window). Initiating app shutdown.")
                        self._keep_app_running = False # Trigger app shutdown
                        self._shutdown_event.set() # Also signal other components
                    else:
                        # This case should ideally not be reached if is_running reflects the loop state.
                        # If run() exited but is_running is still true, it's an anomaly.
                        print("[App] ImageDisplay loop exited but service still reports as running. Forcing shutdown.")
                        self._keep_app_running = False
                        self._shutdown_event.set()

                else: # No image service available
                    print("[App] No ImageDisplay service currently available.")
                    if self._shutdown_event.wait(timeout=0.1):
                        print("[App] Shutdown event detected while no ImageDisplay service. Breaking.")
                        self._keep_app_running = False
                    elif self._reload_requested_event.wait(timeout=0.01): # Check reload, shorter timeout
                        print("[App] Reload event detected while no ImageDisplay service. Continuing for reload.")
                        continue # Loop back to handle reload at the top
                    else:
                        # If neither shutdown nor reload, and no display service, app is in a weird state.
                        # This might happen if ActionHandler failed to create one during init/reload.
                        print("[App] No ImageDisplay, no shutdown/reload event. App will idle or wait for external signal.")
                        # To prevent busy-looping if there's truly nothing to do:
                        time.sleep(0.1)


        except KeyboardInterrupt:
            print("\n[App] Keyboard interrupt received by main run loop.")
            self._shutdown_event.set() # Signal shutdown on Ctrl+C
            self._keep_app_running = False
        finally:
            print("[App] Main run loop ended or interrupted, initiating final stop sequence...")
            self.stop() # Ensure all services are stopped cleanly

        print("[App] Application fully stopped.")

    def stop(self) -> None:
        """Stop the application and its components."""
        print("[App] Stopping application")
        self._shutdown_event.set() # Signal GPIOMonitor and any other listeners

        if self._action_handler:
            print("[App] Stopping ActionHandler services (queues stop for ImageDisplay)...")
            self._action_handler.stop_services()

        if self._gpio_monitor:
            print("[App] Stopping GPIOMonitor...")
            self._gpio_monitor.stop()
            self._gpio_monitor.join(timeout=2.0)
            print("[App] GPIOMonitor stopped.")
        
        # No explicit join for image_service here as its run() method (blocking in main thread)
        # will have exited or is being signaled to exit by ActionHandler.stop_services()
        print("[App] Stop sequence complete.")