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

        self._action_handler = ActionHandler(flash_duty_cycle=flash_duty_cycle, flash_duration=flash_duration)

    def run(self) -> None:
        """Start the application and its components."""
        print("[App] Starting application")

        if self._action_handler:
            print("[App] Starting ActionHandler services...")
            self._action_handler.start_services()

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
        self._gpio_monitor.start()

        try:
            while not self._shutdown_event.is_set():
                self._shutdown_event.wait(timeout=0.1)
        except KeyboardInterrupt:
            print("\n[App] Keyboard interrupt received")
            self.stop()

        print("[App] Application stopped")

    def stop(self) -> None:
        """Stop the application and its components."""
        print("[App] Stopping application")
        self._shutdown_event.set()

        if self._action_handler:
            print("[App] Stopping ActionHandler services...")
            self._action_handler.stop_services()

        if self._gpio_monitor:
            self._gpio_monitor.stop()
            self._gpio_monitor.join(timeout=2.0)