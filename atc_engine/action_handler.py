import threading
from typing import Optional, Dict, Any

class ActionHandler:
    """Handles the execution of actions when buttons are pressed."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._current_action_details: Optional[Dict[str, Any]] = None
    
    @property
    def current_action_name(self) -> Optional[str]:
        if self._current_action_details:
            return self._current_action_details['name']
        return None
    
    def execute_action(self, name: str, mode: str, path: Optional[str] = None) -> None:
        """Print the action that would be executed."""
        with self._lock:
            if self._current_action_details:
                print(f"[Action] Stopping: {self._current_action_details['name']}")
            
            self._current_action_details = {'name': name, 'mode': mode, 'path': path}
            path_str = path if path else 'N/A'
            print(f"[Action] Starting: {name} (Mode: {mode}, Path: {path_str})")

    def stop_current(self) -> None:
        """Print the action being stopped."""
        with self._lock:
            if self._current_action_details:
                print(f"[Action] Stopping: {self._current_action_details['name']}")
                self._current_action_details = None