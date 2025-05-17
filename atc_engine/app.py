import threading
import json
from .action_handler import ActionHandler
from .gpio_monitor import GPIOMonitor

class Application:
    """Main application class."""

    def __init__(self, config_path: str):
        self._config_path = config_path
        self._gpio_monitor = None
        self._shutdown_event = threading.Event()
        self._app_config = {}
        try:
            with open(config_path, 'r') as f:
                self._app_config = json.load(f)
        except Exception as e:
            print(f"[App] Error loading configuration: {e}")
            # self._app_config remains {} or handle error more gracefully

        settings = self._app_config.get('settings', {})
        flash_duty_cycle = settings.get('image_flash_duty_cycle', 0.75)
        flash_duration = settings.get('image_flash_duration', 1.0)

        media_config = self._app_config.get('media', {})
        self._action_handler = ActionHandler(
            media_config=media_config,
            flash_duty_cycle=flash_duty_cycle,
            flash_duration=flash_duration
        )

    def run(self) -> None:
        """Start the application and its components."""
        print("[App] Starting application")

        if self._action_handler:
            print("[App] Starting ActionHandler services...")
            self._action_handler.start_services() # Creates ImageDisplay instance
        
        image_service = self._action_handler.image_display_service

        # Trigger default media action
        default_media_name = self._app_config.get('settings', {}).get('default_media_name')
        if default_media_name:
            media_items = self._app_config.get('media', {})
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

        self._gpio_monitor = GPIOMonitor(self._config_path, self._action_handler)
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