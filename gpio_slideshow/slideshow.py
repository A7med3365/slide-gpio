"""
Slideshow management module for controlling MPV-based image display.
"""
import subprocess
import os
import time
import signal
import glob
import threading
import queue
import json
import socket

from . import config

# Import configuration settings
FOLDER_MAP = config.FOLDER_MAP
INITIAL_FOLDER_KEY = config.INITIAL_FOLDER_KEY
SLIDESHOW_DELAY_SECONDS = config.SLIDESHOW_DELAY_SECONDS

class SlideshowManager(threading.Thread):
    """Manages the mpv slideshow process in a separate thread using IPC."""

    def __init__(self, folder_map, initial_folder_key, delay_seconds):
        super().__init__(name="SlideshowThread")
        self.daemon = True # Allow main program to exit even if this thread is running
        self._folder_map = folder_map
        self._delay_seconds = delay_seconds
        self._target_folder_key = initial_folder_key
        self._current_folder_key = None # Start with none to force initial load
        self._mpv_process = None
        self._image_files = [] # Represents the currently active set of files in mpv
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._ipc_socket_path = "/tmp/mpvsocket" # IPC socket path
        self._mpv_socket = None # IPC socket object
        print(f"[Slideshow] Initialized. Target key: {self._target_folder_key}")

    def _connect_ipc(self):
        """Establishes a connection to the mpv IPC socket with retries."""
        if self._mpv_socket: # Already connected
            return True

        max_retries = 5
        retry_delay = 0.3 # seconds

        for attempt in range(max_retries):
            try:
                if not os.path.exists(self._ipc_socket_path):
                    print(f"[Slideshow] IPC socket file not found: {self._ipc_socket_path}. Attempt {attempt + 1}/{max_retries}. Waiting...")
                    time.sleep(retry_delay)
                    continue

                print(f"[Slideshow] Attempting to connect to IPC socket: {self._ipc_socket_path} (Attempt {attempt + 1}/{max_retries})")
                self._mpv_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._mpv_socket.settimeout(1.0) # Set a timeout for the connect operation
                self._mpv_socket.connect(self._ipc_socket_path)
                print("[Slideshow] IPC socket connected.")
                return True
            except socket.timeout:
                print(f"[Slideshow] IPC socket connection timed out. Attempt {attempt + 1}/{max_retries}.")
                self._mpv_socket = None # Ensure socket is None if connect failed
            except socket.error as e:
                print(f"[Slideshow] Error connecting to IPC socket: {e}. Attempt {attempt + 1}/{max_retries}.")
                self._mpv_socket = None # Ensure socket is None if connect failed
            except Exception as e:
                print(f"[Slideshow] Unexpected error connecting to IPC socket: {e}. Attempt {attempt + 1}/{max_retries}.")
                self._mpv_socket = None
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

        print(f"[Slideshow] Failed to connect to IPC socket after {max_retries} attempts.")
        return False

    def _send_ipc_command(self, cmd_args):
        """Sends a command to mpv via the IPC socket."""
        if not self._mpv_socket:
            print("[Slideshow] IPC socket not connected. Attempting to reconnect...")
            if not self._connect_ipc():
                print("[Slideshow] Failed to connect to IPC. Command not sent.")
                return False

        command_str = json.dumps({"command": cmd_args}) + "\n"
        try:
            self._mpv_socket.sendall(command_str.encode('utf-8'))
            return True
        except socket.error as e:
            print(f"[Slideshow] IPC socket error sending command {cmd_args}: {e}")
            # Connection might be broken, try to clean up
            if self._mpv_socket:
                self._mpv_socket.close()
            self._mpv_socket = None
            return False
        except Exception as e:
            print(f"[Slideshow] Unexpected error sending IPC command {cmd_args}: {e}")
            return False

    def _find_images(self, folder_path):
        """Finds image files in the specified folder."""
        if not os.path.isdir(folder_path):
            print(f"[Slideshow] Error: Folder not found or not accessible: {folder_path}")
            return []

        image_extensions = ('*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp')
        files = []
        print(f"[Slideshow] Searching for images in: {folder_path}")
        for ext in image_extensions:
            files.extend(glob.glob(os.path.join(folder_path, ext)))
        files.sort()
        print(f"[Slideshow] Found {len(files)} images.")
        return files

    def _start_mpv(self):
        """Starts the mpv process with IPC enabled and idle."""
        if self._mpv_process and self._mpv_process.poll() is None:
            print("[Slideshow] mpv already running.")
            return self._mpv_process

        command = [
            'mpv',
            f'--input-ipc-server={self._ipc_socket_path}',
            '--idle', # Start mpv in idle mode, waiting for commands
            '--fs',   # Fullscreen
            '--no-osc' # No on-screen controller
        ]
        print(f"[Slideshow] Starting mpv with IPC: {' '.join(command)}")
        try:
            # Clean up old socket file if it exists
            if os.path.exists(self._ipc_socket_path):
                print(f"[Slideshow] Removing existing IPC socket file: {self._ipc_socket_path}")
                os.remove(self._ipc_socket_path)

            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=None,
            )
            print(f"[Slideshow] mpv started with PID: {process.pid}. Waiting for IPC socket...")
            time.sleep(0.1)

            if self._connect_ipc():
                print("[Slideshow] mpv started and IPC connected successfully.")
                return process
            else:
                print("[Slideshow] CRITICAL: Initial IPC connection failed after starting mpv. Terminating and attempting to get stderr.")
                
                stderr_text = ""
                original_pid = process.pid

                if process.poll() is None:
                    print(f"[Slideshow] Terminating problematic mpv process (PID: {original_pid}) to get stderr.")
                    process.kill()
                    try:
                        _, stderr_bytes = process.communicate(timeout=2.0)
                        if stderr_bytes:
                            stderr_text = stderr_bytes.decode(errors="ignore").strip()
                    except subprocess.TimeoutExpired:
                        stderr_text = f"TimeoutExpired while waiting for mpv (PID: {original_pid}) to die and communicate stderr after kill."
                        if process.poll() is None:
                            process.kill()
                    except Exception as e_comm:
                        stderr_text = f"Exception during communicate() for mpv (PID: {original_pid}): {e_comm}"
                else:
                    stderr_text = f"mpv process (PID: {original_pid}) already exited before explicit termination for stderr."
                    if process.stderr and not process.stderr.closed:
                        try:
                            remaining_stderr_bytes = process.stderr.read()
                            if remaining_stderr_bytes:
                                stderr_text += "\nRemaining stderr from already exited process: " + remaining_stderr_bytes.decode(errors='ignore').strip()
                        except Exception as e_read_rem:
                            stderr_text += f"\nError reading remaining stderr: {e_read_rem}"
                
                if process.stderr:
                    try:
                        process.stderr.close()
                    except Exception:
                        pass

                if stderr_text:
                    print(f"[Slideshow] MPV STDERR (PID: {original_pid}) from failed start: >>>\n{stderr_text}\n<<<")
                else:
                    print(f"[Slideshow] No specific stderr message captured from mpv (PID: {original_pid}) during failed startup.")

                if os.path.exists(self._ipc_socket_path):
                    try:
                        print(f"[Slideshow] Cleaning up socket file from failed mpv start: {self._ipc_socket_path}")
                        os.remove(self._ipc_socket_path)
                    except OSError as e_rm:
                        print(f"[Slideshow] Error removing socket file during failed startup cleanup: {e_rm}")
                return None

        except FileNotFoundError:
            print("[Slideshow] Error: 'mpv' command not found. Is it installed and in PATH?")
            return None
        except Exception as e:
            print(f"[Slideshow] Error starting mpv: {e}")
            if 'process' in locals() and process and process.poll() is None:
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass
            return None

    def _stop_mpv(self):
        """Stops the mpv slideshow subprocess gracefully using IPC and then terminate/kill."""
        print("[Slideshow] Attempting to stop mpv...")
        if self._mpv_socket:
            print("[Slideshow] Sending quit command via IPC.")
            self._send_ipc_command(["quit"])
            if self._mpv_process:
                try:
                    self._mpv_process.wait(timeout=0.5)
                    print("[Slideshow] mpv quit via IPC.")
                except subprocess.TimeoutExpired:
                    print("[Slideshow] mpv did not quit via IPC in time.")
                    pass
            if self._mpv_socket:
                self._mpv_socket.close()
                self._mpv_socket = None

        if self._mpv_process and self._mpv_process.poll() is None:
            print(f"[Slideshow] mpv still running (PID: {self._mpv_process.pid}). Terminating...")
            try:
                self._mpv_process.terminate()
                self._mpv_process.wait(timeout=1.0)
                print("[Slideshow] mpv terminated.")
            except subprocess.TimeoutExpired:
                print("[Slideshow] mpv did not terminate gracefully, killing...")
                self._mpv_process.kill()
                self._mpv_process.wait()
                print("[Slideshow] mpv killed.")
            except Exception as e:
                print(f"[Slideshow] Error stopping mpv process: {e}")
        
        self._mpv_process = None

        if os.path.exists(self._ipc_socket_path):
            try:
                print(f"[Slideshow] Removing IPC socket file: {self._ipc_socket_path}")
                os.remove(self._ipc_socket_path)
            except OSError as e:
                print(f"[Slideshow] Error removing IPC socket file {self._ipc_socket_path}: {e}")

    def set_folder_key(self, key):
        """Thread-safely sets the target folder key."""
        with self._lock:
            if key in self._folder_map:
                if key != self._target_folder_key:
                    print(f"[Slideshow] Request received to switch to folder key: {key}")
                    self._target_folder_key = key
            else:
                print(f"[Slideshow] Warning: Invalid folder key requested: {key}")

    def stop(self):
        """Signals the thread to stop and cleans up mpv."""
        print("[Slideshow] Stop requested.")
        self._shutdown_event.set()
        self._stop_mpv()

    def run(self):
        """Main loop for the slideshow manager thread."""
        print("[Slideshow] Thread started.")
        
        self._mpv_process = self._start_mpv()
        if not self._mpv_process:
            print("[Slideshow] Failed to start mpv initially. Thread will exit.")
            return

        while not self._shutdown_event.is_set():
            folder_changed = False
            key_to_load = None

            with self._lock:
                if self._target_folder_key != self._current_folder_key:
                    folder_changed = True
                    key_to_load = self._target_folder_key
                    print(f"[Slideshow] Detected change: Target={key_to_load}, Current={self._current_folder_key}")

            if folder_changed and key_to_load is not None:
                folder_path = self._folder_map.get(key_to_load)
                if folder_path:
                    next_images = self._find_images(folder_path)
                    if next_images:
                        print(f"[Slideshow] Loading content for key {key_to_load}: {len(next_images)} items.")
                        if len(next_images) == 1 and next_images[0].lower().endswith('.gif'):
                            print(f"[Slideshow] Loading single GIF: {next_images[0]}")
                            self._send_ipc_command(["loadfile", next_images[0], "replace"])
                            self._send_ipc_command(["set_property", "loop-file", "inf"])
                            self._send_ipc_command(["set_property", "loop-playlist", "no"])
                        else:
                            print(f"[Slideshow] Loading image playlist ({len(next_images)} images).")
                            self._send_ipc_command(["playlist-clear"])
                            for img_path in next_images:
                                self._send_ipc_command(["loadfile", img_path, "append"])
                            self._send_ipc_command(["set_property", "image-display-duration", self._delay_seconds])
                            self._send_ipc_command(["set_property", "loop-playlist", "inf"])
                            self._send_ipc_command(["set_property", "loop-file", "no"])
                            self._send_ipc_command(["playlist-play-index", 0])
                        
                        self._image_files = next_images
                        self._current_folder_key = key_to_load
                    else:
                        print(f"[Slideshow] No images found for key {key_to_load}. Clearing playlist.")
                        self._send_ipc_command(["playlist-clear"])
                        self._image_files = []
                        self._current_folder_key = key_to_load
                else:
                    print(f"[Slideshow] Folder path not found for key {key_to_load}. Clearing playlist.")
                    self._send_ipc_command(["playlist-clear"])
                    self._image_files = []
                    self._current_folder_key = key_to_load

            if self._mpv_process and self._mpv_process.poll() is not None:
                return_code = self._mpv_process.returncode
                stderr_output = ""
                if self._mpv_process.stderr:
                    try:
                        stderr_output = self._mpv_process.stderr.read().decode(errors='ignore')
                    except:
                        pass
                print(f"[Slideshow] mpv process (PID: {self._mpv_process.pid}) exited with code {return_code}.")
                if stderr_output:
                    print(f"[Slideshow] mpv stderr: {stderr_output.strip()}")

                if self._mpv_socket:
                    self._mpv_socket.close()
                    self._mpv_socket = None
                self._mpv_process = None
                self._current_folder_key = None

                if not self._shutdown_event.is_set():
                    print("[Slideshow] mpv exited unexpectedly. Attempting to restart...")
                    self._mpv_process = self._start_mpv()

            self._shutdown_event.wait(timeout=0.2)

        self._stop_mpv()
        print("[Slideshow] Thread finished.")