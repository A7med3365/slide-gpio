import threading
import time

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
            time.sleep(0.1)
        print("[Signal] Thread finished")