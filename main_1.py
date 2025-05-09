import subprocess
import os
import sys
import time
import signal
import glob
import threading
import queue # Using queue for potential future command passing, though direct state change is used here
from pyA64.gpio import port # Assuming 'port' might be needed if symbolic names were used
from pyA64.gpio import gpio

# --- Configuration ---

# 1. Map Button Pins to Folder Keys (or indices)
#    Use the actual integer pin numbers your pyA64 library uses.
#    Example: Pin 32 maps to key 0, Pin 33 maps to key 1, etc.
PIN_TO_FOLDER_KEY_MAP = {
    32: 0,
    33: 1,
    34: 2,
    35: 3,
    # Add pins for buttons 5 and 6 if needed
    # 36: 4,
    # 37: 5,
}

# 2. Map Folder Keys to actual Folder Paths
#    These paths should be relative to BASE_IMAGE_PATH or absolute paths.
BASE_IMAGE_PATH = "/home/olimex/Documents/slide/gpio_slideshow/image_sets" # CHANGE THIS to your base path
FOLDER_MAP = {
    0: os.path.join(BASE_IMAGE_PATH, "set0"),
    1: os.path.join(BASE_IMAGE_PATH, "set1"),
    2: os.path.join(BASE_IMAGE_PATH, "set2"),
    3: os.path.join(BASE_IMAGE_PATH, "set3"),
    # Add entries for keys 4 and 5 if using 6 buttons/folders
    # 4: os.path.join(BASE_IMAGE_PATH, "set4"),
    # 5: os.path.join(BASE_IMAGE_PATH, "set5"),
}

# 3. Slideshow Settings
SLIDESHOW_DELAY_SECONDS = 1 # Delay between images
INITIAL_FOLDER_KEY = 0     # Which folder key to start with

# 4. Button Settings
BUTTON_POLL_INTERVAL = 0.05 # How often to check button state (seconds)
DEBOUNCE_TIME = 0.3       # Ignore button changes for this duration after a press (seconds)

# --- Slideshow Manager Class ---

class SlideshowManager(threading.Thread):
    """Manages the feh slideshow process in a separate thread."""

    def __init__(self, folder_map, initial_folder_key, delay_seconds):
        super().__init__(name="SlideshowThread")
        self.daemon = True # Allow main program to exit even if this thread is running
        self._folder_map = folder_map
        self._delay_seconds = delay_seconds
        self._target_folder_key = initial_folder_key
        self._current_folder_key = None # Start with none to force initial load
        self._feh_process = None
        self._image_files = []
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        print(f"[Slideshow] Initialized. Target key: {self._target_folder_key}")

    def _find_images(self, folder_path):
        """Finds image files in the specified folder."""
        if not os.path.isdir(folder_path):
            print(f"[Slideshow] Error: Folder not found or not accessible: {folder_path}")
            return []

        image_extensions = ('*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp')
        files = []
        print(f"[Slideshow] Searching for images in: {folder_path}")
        for ext in image_extensions:
            # Non-recursive search
            files.extend(glob.glob(os.path.join(folder_path, ext)))
            # Recursive search (optional, uncomment if needed)
            # files.extend(glob.glob(os.path.join(folder_path, '**', ext), recursive=True))

        files.sort()
        print(f"[Slideshow] Found {len(files)} images.")
        return files

    def _start_feh(self):
        """Starts the feh slideshow subprocess."""
        if self._feh_process and self._feh_process.poll() is None:
             print("[Slideshow] Warning: Attempted to start feh when already running.")
             return # Already running

        if not self._image_files:
            print("[Slideshow] No images found for the current folder. Not starting feh.")
            return

        command = [
            'feh',
            '--fullscreen',
            '--auto-zoom',
            '--hide-pointer',
            '--borderless',
            '--slideshow-delay', str(self._delay_seconds),
            '--quiet', # Reduce feh's own console output
            '--cycle-once', # Exit after one cycle (we restart it on change or if it exits)
            # Add key binding to allow easier exiting
            '--action1', "killall feh",
            '-Z', # Auto-zoom
            '-F', # Fullscreen shorthand
            '-Y', # Hide pointer shorthand
            '-B', 'black', # Set background to black for images that don't fill
            '-D', str(self._delay_seconds), # Delay shorthand
            '--image-bg', 'black', # Background for transparent images
        ] + self._image_files

        print(f"[Slideshow] Starting feh for folder key {self._current_folder_key}...")
        try:
            # Use Popen for non-blocking execution and process management
            self._feh_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL, # Suppress feh stdout
                stderr=subprocess.PIPE,    # Capture errors
                preexec_fn=None,           # Don't use process groups which can interfere with signal handling
            )
            print(f"[Slideshow] feh started with PID: {self._feh_process.pid}")
        except FileNotFoundError:
            print("[Slideshow] Error: 'feh' command not found. Is it installed and in PATH?")
            self._feh_process = None
        except Exception as e:
            print(f"[Slideshow] Error starting feh: {e}")
            self._feh_process = None

    def _stop_feh(self):
        """Stops the feh slideshow subprocess gracefully."""
        if self._feh_process and self._feh_process.poll() is None:
            print(f"[Slideshow] Stopping feh process (PID: {self._feh_process.pid})...")
            try:
                # Try terminating gracefully first
                self._feh_process.terminate()
                try:
                    # Wait a short time for it to terminate
                    self._feh_process.wait(timeout=1.0)
                    print("[Slideshow] feh terminated.")
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate
                    print("[Slideshow] feh did not terminate gracefully, killing...")
                    self._feh_process.kill()
                    self._feh_process.wait() # Wait for kill to complete
                    print("[Slideshow] feh killed.")
            except Exception as e:
                print(f"[Slideshow] Error stopping feh: {e}")
        self._feh_process = None # Ensure process handle is cleared

    def set_folder_key(self, key):
        """Thread-safely sets the target folder key."""
        with self._lock:
            if key in self._folder_map:
                if key != self._target_folder_key:
                    print(f"[Slideshow] Request received to switch to folder key: {key}")
                    self._target_folder_key = key
                else:
                    print(f"[Slideshow] Request received for current key {key}. No change.")
            else:
                print(f"[Slideshow] Warning: Invalid folder key requested: {key}")

    def stop(self):
        """Signals the thread to stop."""
        print("[Slideshow] Stop requested.")
        self._shutdown_event.set()
        self._stop_feh() # Attempt to stop feh immediately on shutdown signal

    def run(self):
        """Main loop for the slideshow manager thread."""
        print("[Slideshow] Thread started.")
        while not self._shutdown_event.is_set():
            folder_changed = False
            key_to_load = None

            with self._lock:
                if self._target_folder_key != self._current_folder_key:
                    folder_changed = True
                    key_to_load = self._target_folder_key
                    print(f"[Slideshow] Detected change: Target={key_to_load}, Current={self._current_folder_key}")

            if folder_changed and key_to_load is not None:
                self._stop_feh() # Stop current slideshow if running
                folder_path = self._folder_map.get(key_to_load)
                if folder_path:
                    self._image_files = self._find_images(folder_path)
                    self._current_folder_key = key_to_load # Update current key *after* finding images
                    if self._image_files:
                         self._start_feh()
                    else:
                         print(f"[Slideshow] No images found for key {self._current_folder_key}, feh not started.")
                else:
                     print(f"[Slideshow] Folder path not found for key {key_to_load}")
                     self._image_files = []
                     self._current_folder_key = key_to_load # Still update key, even if invalid path


            # Monitor if feh process exited unexpectedly (e.g., user quit manually)
            # or if it finished its cycle (--cycle-once)
            if self._feh_process and self._feh_process.poll() is not None:
                 stderr_output = ""
                 if self._feh_process.stderr:
                     stderr_output = self._feh_process.stderr.read().decode(errors='ignore')
                 print(f"[Slideshow] feh process (PID: {self._feh_process.pid}) exited with code {self._feh_process.returncode}.")
                 if stderr_output:
                     print(f"[Slideshow] feh stderr: {stderr_output.strip()}")

                 self._feh_process = None # Clear the handle

                 # If it exited and we aren't shutting down, restart it with current images
                 if not self._shutdown_event.is_set() and self._image_files:
                     print("[Slideshow] Restarting feh for the current folder...")
                     self._start_feh()
                 elif not self._image_files:
                     print("[Slideshow] feh exited and no images for current key. Staying stopped.")

            # Check for SIGINT event every half second (allows faster response to Ctrl+C)
            self._shutdown_event.wait(timeout=0.5)

        # Cleanup on exit
        self._stop_feh()
        print("[Slideshow] Thread finished.")


# --- Button Monitor Class ---

class ButtonMonitor(threading.Thread):
    """Monitors GPIO buttons in a separate thread."""

    def __init__(self, pin_map, callback):
        super().__init__(name="ButtonThread")
        self.daemon = True
        self._pin_map = pin_map
        self._callback = callback
        self._shutdown_event = threading.Event()
        self._last_press_time = {pin: 0 for pin in pin_map} # For debouncing
        self._last_pin_state = {} # Store last known state (LOW=pressed)
        print(f"[Buttons] Initialized for pins: {list(pin_map.keys())}")

    def _init_gpio(self):
        """Initializes GPIO pins."""
        try:
            gpio.init()
            print("[Buttons] GPIO initialized.")
            for pin in self._pin_map.keys():
                gpio.setcfg(pin, gpio.INPUT)
                gpio.pullup(pin, gpio.PULLUP) # Use internal pull-up
                self._last_pin_state[pin] = gpio.input(pin) # Read initial state
                print(f"[Buttons] Configured Pin {pin} as INPUT with PULLUP. Initial state: {'HIGH (Not Pressed)' if self._last_pin_state[pin] == 1 else 'LOW (Pressed)'}")
            return True
        except Exception as e:
            print(f"[Buttons] Error initializing GPIO: {e}")
            print("[Buttons] *** Button monitoring will likely fail. ***")
            return False

    def stop(self):
        """Signals the thread to stop."""
        print("[Buttons] Stop requested.")
        self._shutdown_event.set()

    def run(self):
        """Main loop for the button monitor thread."""
        print("[Buttons] Thread started.")
        if not self._init_gpio():
             print("[Buttons] Exiting thread due to GPIO initialization failure.")
             return # Don't run loop if GPIO failed

        while not self._shutdown_event.is_set():
            current_time = time.monotonic() # Use monotonic clock for debounce timing

            for pin, folder_key in self._pin_map.items():
                try:
                    current_state = gpio.input(pin)
                except Exception as e:
                    print(f"[Buttons] Error reading pin {pin}: {e}. Skipping.")
                    continue # Skip this pin check if reading fails

                last_state = self._last_pin_state.get(pin, 1) # Default to HIGH if not seen before

                # Check for a press (transition from HIGH to LOW)
                if last_state == 1 and current_state == 0:
                    # Check debounce timer
                    if current_time - self._last_press_time.get(pin, 0) > DEBOUNCE_TIME:
                        print(f"[Buttons] Pin {pin} pressed! Triggering action for key: {folder_key}")
                        self._last_press_time[pin] = current_time # Update last press time
                        if self._callback:
                            try:
                                self._callback(folder_key) # Call the registered callback
                            except Exception as e:
                                print(f"[Buttons] Error executing callback for key {folder_key}: {e}")
                    # else:
                    #     print(f"[Buttons] Pin {pin} press detected, but within debounce period. Ignoring.")

                # Update last known state for this pin
                self._last_pin_state[pin] = current_state

            # Check for shutdown event more frequently
            self._shutdown_event.wait(timeout=BUTTON_POLL_INTERVAL)

        print("[Buttons] Thread finished.")


# Signal monitoring thread to ensure Ctrl+C is caught
class SignalMonitor(threading.Thread):
    """A dedicated thread that ensures we can process Ctrl+C signals."""
    
    def __init__(self):
        super().__init__(name="SignalThread")
        self.daemon = True
        self._shutdown_event = threading.Event()
        print("[Signal] Monitor thread initialized")
        
    def stop(self):
        print("[Signal] Stop requested.")
        self._shutdown_event.set()
        
    def run(self):
        print("[Signal] Thread started - monitoring for signals")
        while not self._shutdown_event.is_set():
            # This thread's only job is to keep waking up Python periodically
            # so it can check for signals even if other threads are blocked
            # by the feh process capturing keyboard input.
            time.sleep(0.1)
        print("[Signal] Thread finished")


# --- Main Application Class ---

class Application:
    """Orchestrates the slideshow and button monitoring."""

    def __init__(self, folder_map, pin_to_key_map, initial_key, delay):
        self._folder_map = folder_map
        self._pin_to_key_map = pin_to_key_map
        self._initial_key = initial_key
        self._delay = delay
        self._slideshow_manager = None
        self._button_monitor = None
        self._signal_monitor = None
        self._shutdown_event = threading.Event() # Main app shutdown event

    def _handle_button_press(self, folder_key):
        """Callback function passed to ButtonMonitor."""
        print(f"[App] Button press handled for key: {folder_key}")
        if self._slideshow_manager:
            self._slideshow_manager.set_folder_key(folder_key)

    def _setup_signal_handlers(self):
        """Sets up signal handlers for graceful shutdown."""
        def force_exit_handler(signum, frame):
            """Emergency exit handler for SIGINT/SIGTERM."""
            try:
                # First kill any feh processes that might be capturing input
                print(f"\n[App] Received signal {signal.Signals(signum).name}. Emergency shutdown...")
                subprocess.run(['killall', '-9', 'feh'], check=False, 
                               stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            except Exception:
                pass

            # Call our normal stop method
            self.stop()
            
        # Setup the signal handlers
        signal.signal(signal.SIGINT, force_exit_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, force_exit_handler)  # Termination signal
        print("[App] Signal handlers set up with emergency exit handling")

    def _check_feh_installed(self):
        """Checks if the feh command is available."""
        try:
            # Use check=True to raise error if command fails (not found)
            subprocess.run(['which', 'feh'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("[App] 'feh' command found.")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[App] Error: 'feh' command not found.")
            print("       Please install it (e.g., 'sudo apt update && sudo apt install feh')")
            return False

    def run(self):
        """Starts and manages the application."""
        print("[App] Starting application...")
        self._setup_signal_handlers()

        if not self._check_feh_installed():
            sys.exit(1)

        # Validate initial folder key
        if self._initial_key not in self._folder_map:
             print(f"[App] Error: Initial folder key '{self._initial_key}' not found in FOLDER_MAP.")
             print(f"       Available keys: {list(self._folder_map.keys())}")
             # Attempt to use the first available key as fallback
             if self._folder_map:
                 self._initial_key = list(self._folder_map.keys())[0]
                 print(f"[App] Warning: Falling back to initial key '{self._initial_key}'.")
             else:
                 print("[App] Error: FOLDER_MAP is empty. Cannot start.")
                 sys.exit(1)

        # Create threads
        self._slideshow_manager = SlideshowManager(self._folder_map, self._initial_key, self._delay)
        self._button_monitor = ButtonMonitor(self._pin_to_key_map, self._handle_button_press)
        self._signal_monitor = SignalMonitor()  # Add dedicated signal monitoring thread

        print("[App] Starting threads...")
        self._signal_monitor.start()  # Start signal monitor first
        self._button_monitor.start()
        self._slideshow_manager.start()
        
        print("[App] Application running. Press Ctrl+C to exit.")
        print("[App] If Ctrl+C doesn't work, try pressing 1 (action key in feh) to terminate.")
        
        try:
            # Use a loop with timeout to ensure signals are processed
            while not self._shutdown_event.is_set():
                # Check for shutdown event with timeout (more responsive to signals)
                self._shutdown_event.wait(timeout=0.2)
        except KeyboardInterrupt:
            # Direct handling of KeyboardInterrupt in main thread
            print("\n[App] KeyboardInterrupt caught in main thread.")
            self.stop()

        print("[App] Main loop finished. Waiting for threads to join...")

        # Wait for threads to finish with timeouts
        join_timeout = 2.0
        if self._signal_monitor and self._signal_monitor.is_alive():
             self._signal_monitor.join(timeout=1.0)
        if self._button_monitor and self._button_monitor.is_alive():
             self._button_monitor.join(timeout=join_timeout)
        if self._slideshow_manager and self._slideshow_manager.is_alive():
             self._slideshow_manager.join(timeout=join_timeout)

        print("[App] All threads joined or timed out. Exiting.")

    def stop(self):
        """Initiates the shutdown sequence."""
        if self._shutdown_event.is_set():
            return  # Already stopping
            
        print("[App] Stop initiated.")
        self._shutdown_event.set() # Signal main loop to stop waiting
        
        # Kill any feh processes immediately
        try:
            subprocess.run(['killall', 'feh'], check=False, 
                           stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception:
            pass

        # Signal worker threads to stop
        if self._signal_monitor:
            self._signal_monitor.stop()
        if self._button_monitor:
            self._button_monitor.stop()
        if self._slideshow_manager:
            self._slideshow_manager.stop()


# --- Main Execution ---

if __name__ == "__main__":
    # Basic validation of configuration
    if not isinstance(FOLDER_MAP, dict) or not FOLDER_MAP:
        print("Error: FOLDER_MAP configuration is invalid or empty.")
        sys.exit(1)
    if not isinstance(PIN_TO_FOLDER_KEY_MAP, dict) or not PIN_TO_FOLDER_KEY_MAP:
        print("Error: PIN_TO_FOLDER_KEY_MAP configuration is invalid or empty.")
        sys.exit(1)

    app = Application(
        folder_map=FOLDER_MAP,
        pin_to_key_map=PIN_TO_FOLDER_KEY_MAP,
        initial_key=INITIAL_FOLDER_KEY,
        delay=SLIDESHOW_DELAY_SECONDS
    )
    try:
        app.run()
    except KeyboardInterrupt:
        # This is a backup handler in case the signal handler fails
        print("\n[App] KeyboardInterrupt caught in main. Initiating emergency stop.")
        try:
            # Force kill any feh processes first
            subprocess.run(['killall', '-9', 'feh'], check=False, 
                           stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception:
            pass
        # Then do normal cleanup
        app.stop()
    except Exception as e:
        print(f"\n[App] An unexpected error occurred: {e}")
        # Attempt graceful shutdown even on unexpected error
        app.stop()
        sys.exit(1)