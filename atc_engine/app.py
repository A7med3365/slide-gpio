import threading
from .action_handler import ActionHandler
from .gpio_monitor import GPIOMonitor

class Application:
    """Main application class."""

    def __init__(self, config_path: str, action_handler: ActionHandler):
        self._config_path = config_path
        self._action_handler = action_handler
        self._gpio_monitor = None
        self._shutdown_event = threading.Event()

    def run(self) -> None:
        """Start the application and its components."""
        print("[App] Starting application")

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

        if self._gpio_monitor:
            self._gpio_monitor.stop()
            self._gpio_monitor.join(timeout=2.0)