import threading
from typing import Optional

class ActionHandler:
    """Handles the execution of actions when buttons are pressed."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._current_action: Optional[str] = None
    
    def execute_action(self, path: str) -> None:
        """Print the action that would be executed."""
        with self._lock:
            old_action = self._current_action
            self._current_action = path
            if old_action:
                print(f"[Action] Stopping: {old_action}")
            print(f"[Action] Starting: {path}")

    def stop_current(self) -> None:
        """Print the action being stopped."""
        with self._lock:
            if self._current_action:
                print(f"[Action] Stopping: {self._current_action}")
                self._current_action = None