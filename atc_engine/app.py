import threading
import json
from .action_handler import ActionHandler
from .gpio_monitor import GPIOMonitor
from .config_manager import ConfigManager, ConfigError

class Application:
    """Main application class."""

    def __init__(self, config_path: str):
        self._config_path = config_path
        try:
            self._config_manager = ConfigManager(config_path)
        except ConfigError as e:
            print(f"[App] Critical configuration error: {e}")
            # Decide how to handle: raise, exit, or run with defaults/limited functionality
            # For now, let's re-raise to stop the app if config is fundamentally flawed.
            raise
        
        self._gpio_monitor = None
        self._shutdown_event = threading.Event()
        # self._app_config = {} # No longer needed directly like this

        settings = self._config_manager.get_settings()
        flash_duty_cycle = settings.get('image_flash_duty_cycle', 0.75) # Keep defaults here for now
        flash_duration = settings.get('image_flash_duration', 1.0)
        scroll_text_speed = settings.get('scroll_text_speed', 3)
        scroll_text_font_size = settings.get('scroll_text_font_size', 60)
        scroll_text_font_color = settings.get('scroll_text_font_color', "white")
        scroll_text_bg_color = settings.get('scroll_text_bg_color') # Already handles None

        media_config = self._config_manager.get_media_config()
        self._action_handler = ActionHandler( # ActionHandler now takes media_config directly
            media_config=media_config,
            flash_duty_cycle=flash_duty_cycle,
            flash_duration=flash_duration,
            scroll_text_speed=scroll_text_speed,
            scroll_text_font_size=scroll_text_font_size,
            scroll_text_font_color=scroll_text_font_color,
            scroll_text_bg_color=scroll_text_bg_color
        )

    def run(self) -> None:
        """Start the application and its components."""
        print("[App] Starting application")

        if self._action_handler:
            print("[App] Starting ActionHandler services...")
            self._action_handler.start_services() # Creates ImageDisplay instance
        
        image_service = self._action_handler.image_display_service

        # Trigger default media action
        default_media_name = self._config_manager.get_default_media_name()
        if default_media_name:
            media_items = self._config_manager.get_media_config() # Use ConfigManager
            media_item_details = media_items.get(default_media_name)
            if media_item_details:
                mode = media_item_details.get('mode')
                path = media_item_details.get('path')
                if mode: # Ensure mode is present
                    print(f"[App] Starting with default media: {default_media_name}")
                    self._action_handler.execute_action(name=default_media_name, mode=mode, path=path)
                else:
                    print(f"[App] Default media '{default_media_name}' found but 'mode' is missing.")
            else:
                print(f"[App] Default media '{default_media_name}' not found in configuration.")
        else:
            print("[App] No default media name specified in configuration.")

        # self._gpio_monitor = GPIOMonitor(self._config_path, self._action_handler) # Old
        self._gpio_monitor = GPIOMonitor(self._config_manager, self._action_handler) # New
        self._gpio_monitor.start() # GPIO runs in background thread

        try:
            if image_service:
                print("[App] Starting ImageDisplay Pygame loop in main thread...")
                image_service.run() # BLOCKING CALL
                print("[App] ImageDisplay Pygame loop finished.")
            else:
                print("[App] No ImageDisplay service. Waiting for shutdown signal.")
                # Fallback if no UI, or app can just proceed to shutdown if this is not desired
                while not self._shutdown_event.is_set():
                    self._shutdown_event.wait(timeout=0.1)
                
        except KeyboardInterrupt:
            print("\n[App] Keyboard interrupt received")
            # self.stop() will be called in finally
        finally:
            print("[App] Main loop ended or interrupted, initiating stop...")
            self.stop() # Ensure all services are stopped

        print("[App] Application stopped")

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