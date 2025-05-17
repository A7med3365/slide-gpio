"""
GPIO Slideshow Application
------------------------
Main application module that orchestrates the slideshow functionality with GPIO button control.

The application consists of three main components:
1. SlideshowManager - Handles image display and presentation logic
2. ButtonMonitor - Manages GPIO button inputs for slideshow control
3. SignalMonitor - Handles system signals for graceful shutdown

The Application class coordinates these components and manages the application lifecycle.
"""

# Standard library imports
import os
import sys
import signal
import threading
import subprocess

# Project module imports
from . import config
from . import slideshow
from . import gpio_button
from . import signal_handler

class Application:
    """
    Main application class that orchestrates the slideshow and button monitoring.
    
    This class coordinates three main components:
    - SlideshowManager: Controls the image display and transitions
    - ButtonMonitor: Handles GPIO button press events
    - SignalMonitor: Manages system signals for clean shutdown
    
    The application uses threading to run these components concurrently while
    maintaining proper shutdown sequences when the program is terminated.
    """

    def __init__(self, folder_map, pin_to_key_map, initial_key, delay):
        """
        Initialize the application with configuration parameters.

        Args:
            folder_map (dict): Mapping of keys to image folder paths
            pin_to_key_map (dict): Mapping of GPIO pins to folder keys
            initial_key (str): Starting folder key for the slideshow
            delay (float): Delay between image transitions in seconds
        """
        self._folder_map = folder_map
        self._pin_to_key_map = pin_to_key_map
        self._initial_key = initial_key
        self._delay = delay
        self._slideshow_manager = None
        self._button_monitor = None
        self._signal_monitor = None
        self._shutdown_event = threading.Event()

    def _handle_button_press(self, folder_key):
        """Handle button press events by updating the slideshow folder."""
        if self._slideshow_manager:
            self._slideshow_manager.set_folder_key(folder_key)

    def _setup_signal_handlers(self):
        """Configure signal handlers for graceful application shutdown."""
        def graceful_shutdown_handler(signum, frame):
            print(f"\n[App] Received signal {signal.Signals(signum).name}. Initiating shutdown...")
            self.stop()
            
        signal.signal(signal.SIGINT, graceful_shutdown_handler)
        signal.signal(signal.SIGTERM, graceful_shutdown_handler)
        print("[App] Signal handlers set up for graceful shutdown.")

    def _check_mpv_installed(self):
        """Verify that the required mpv media player is installed."""
        try:
            subprocess.run(['which', 'mpv'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("[App] 'mpv' command found.")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[App] Error: 'mpv' command not found.")
            print("       Please install it (e.g., 'sudo apt update && sudo apt install mpv')")
            return False

    def run(self):
        """
        Start and manage the application lifecycle.
        
        This method initializes all components, starts the necessary threads,
        and maintains the main application loop while handling shutdown requests.
        """
        print("[App] Starting application...")
        self._setup_signal_handlers()

        if not self._check_mpv_installed():
            sys.exit(1)

        # Validate initial folder key
        if self._initial_key not in self._folder_map:
            print(f"[App] Error: Initial folder key '{self._initial_key}' not found in FOLDER_MAP.")
            print(f"       Available keys: {list(self._folder_map.keys())}")
            if self._folder_map:
                self._initial_key = list(self._folder_map.keys())[0]
                print(f"[App] Warning: Falling back to initial key '{self._initial_key}'.")
            else:
                print("[App] Error: FOLDER_MAP is empty. Cannot start.")
                sys.exit(1)

        # Create and start component threads
        self._slideshow_manager = slideshow.SlideshowManager(self._folder_map, self._initial_key, self._delay)
        self._button_monitor = gpio_button.ButtonMonitor(self._pin_to_key_map, self._handle_button_press)
        self._signal_monitor = signal_handler.SignalMonitor()

        print("[App] Starting threads...")
        self._signal_monitor.start()
        self._button_monitor.start()
        self._slideshow_manager.start()
        
        print("[App] Application running. Press Ctrl+C to exit.")
        
        try:
            while not self._shutdown_event.is_set():
                self._shutdown_event.wait(timeout=0.2)
        except KeyboardInterrupt:
            print("\n[App] KeyboardInterrupt caught in main thread (backup).")
            self.stop()

        print("[App] Main loop finished. Waiting for threads to join...")

        # Join threads with timeouts to prevent hanging
        join_timeout = 2.0
        if self._slideshow_manager and self._slideshow_manager.is_alive():
            print("[App] Waiting for SlideshowManager to join...")
            self._slideshow_manager.join(timeout=join_timeout + 1.0)
        if self._button_monitor and self._button_monitor.is_alive():
            print("[App] Waiting for ButtonMonitor to join...")
            self._button_monitor.join(timeout=join_timeout)
        if self._signal_monitor and self._signal_monitor.is_alive():
            print("[App] Waiting for SignalMonitor to join...")
            self._signal_monitor.join(timeout=1.0)

        print("[App] All threads joined or timed out. Exiting.")

    def stop(self):
        """
        Initiate a graceful shutdown sequence.
        
        This method ensures all components are stopped in the correct order
        and resources are properly cleaned up.
        """
        if self._shutdown_event.is_set():
            return 
            
        print("[App] Stop initiated.")
        self._shutdown_event.set() 
        
        # Stop threads in reverse order of dependency
        if self._slideshow_manager:
            print("[App] Stopping SlideshowManager...")
            self._slideshow_manager.stop()
        if self._button_monitor:
            print("[App] Stopping ButtonMonitor...")
            self._button_monitor.stop()
        if self._signal_monitor:
            print("[App] Stopping SignalMonitor...")
            self._signal_monitor.stop()

if __name__ == "__main__":
    # Validate configuration
    if not isinstance(config.FOLDER_MAP, dict) or not config.FOLDER_MAP:
        print("Error: FOLDER_MAP configuration is invalid or empty.")
        sys.exit(1)
    if not isinstance(config.PIN_TO_FOLDER_KEY_MAP, dict) or not config.PIN_TO_FOLDER_KEY_MAP:
        print("Error: PIN_TO_FOLDER_KEY_MAP configuration is invalid or empty.")
        sys.exit(1)

    # Create and run application
    app = Application(
        folder_map=config.FOLDER_MAP,
        pin_to_key_map=config.PIN_TO_FOLDER_KEY_MAP,
        initial_key=config.INITIAL_FOLDER_KEY,
        delay=config.SLIDESHOW_DELAY_SECONDS
    )
    
    try:
        app.run()
    except Exception as e:
        print(f"\n[App] UNHANDLED EXCEPTION in app.run(): {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("[App] Application has shut down.")
        try:
            subprocess.run(['killall', '-9', 'mpv'], check=False, 
                         stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception:
            pass