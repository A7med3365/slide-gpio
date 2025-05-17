"""
Application Module
---------------
Contains the main Application class that orchestrates all components.
"""

import threading
from typing import Optional

from .action_handler import ActionHandler
from .button_manager import ButtonManager
from .gpio_handler import GPIOMonitor
from .config_loader import load_config

class Application:
    """Main application class that coordinates all components."""
    
    def __init__(self, config_path: str):
        """Initialize application with config path."""
        self._config_path = config_path
        self._config = None
        self._button_manager: Optional[ButtonManager] = None
        self._gpio_handler: Optional[GPIOMonitor] = None
        self._action_handler: Optional[ActionHandler] = None
        self._shutdown_event = threading.Event()
        
    def _init_components(self) -> bool:
        """Initialize all application components in correct order."""
        try:
            print("[App] Loading configuration")
            self._config = load_config(self._config_path)
            
            print("[App] Initializing button manager")
            self._button_manager = ButtonManager(self._config)
            
            print("[App] Initializing action handler")
            self._action_handler = ActionHandler(self._config)
            
            print("[App] Initializing GPIO handler")
            self._gpio_handler = GPIOMonitor(
                self._config,
                self._button_manager,
                self._action_handler
            )
            
            return True
            
        except Exception as e:
            print(f"[App] Error initializing components: {e}")
            return False
        
    def run(self) -> None:
        """Start the application and its components."""
        print("[App] Starting application")
        
        # Initialize components
        if not self._init_components():
            print("[App] Failed to initialize components. Exiting.")
            return
        
        # Start GPIO monitoring
        self._gpio_handler.start()

        # Display default media
        if self._action_handler and self._config:
            default_media_name = self._config.get('settings', {}).get('default_media_name')
            if default_media_name and default_media_name in self._config.get('media', {}):
                default_media_config = self._config['media'][default_media_name]
                print(f"[App] Displaying default media: {default_media_name}")
                self._action_handler.execute_media(default_media_name, default_media_config)
            else:
                print(f"[App] Warning: Default media '{default_media_name}' not found in config.")
        
        try:
            # Main application loop
            print("[App] Running main loop")
            while not self._shutdown_event.is_set():
                self._shutdown_event.wait(timeout=0.1)
                
        except KeyboardInterrupt:
            print("\n[App] Keyboard interrupt received")
            self.stop()
        except Exception as e:
            print(f"[App] Error in main loop: {e}")
            self.stop()
            
        print("[App] Application stopped")
    
    def stop(self) -> None:
        """Stop the application and its components cleanly."""
        print("[App] Stopping application")
        self._shutdown_event.set()
        
        # Stop GPIO handler
        if self._gpio_handler:
            print("[App] Stopping GPIO handler")
            self._gpio_handler.stop()
            self._gpio_handler.join(timeout=2.0)
        
        # Clean up action handler
        if self._action_handler:
            print("[App] Cleaning up action handler")
            self._action_handler.cleanup()
        
        # Clean up button manager
        if self._button_manager:
            print("[App] Cleaning up button manager")
            self._button_manager.reset_button_states()
            
        print("[App] Cleanup complete")