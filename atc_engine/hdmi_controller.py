import subprocess
import os
from typing import Optional
import time # Added for __main__ test

class HDMIController:
    def __init__(self, hdmi_output_name: str = 'HDMI-1'):
        self._hdmi_output_name = hdmi_output_name
        # Attempt to determine initial state, or assume a default.
        # For simplicity, let's assume it's initially on, or query it.
        # Querying xrandr at init might be slow or fail if X isn't ready.
        # Let's start with an assumed state and toggle.
        self._is_hdmi_on = True # Initial assumption, or could be queried
        print(f"[HDMIController] Initialized. Assumed HDMI state: {'ON' if self._is_hdmi_on else 'OFF'}")


    def _run_xrandr_command(self, args: list[str]) -> Optional[str]:
        env = os.environ.copy()
        env['DISPLAY'] = ':0'
        try:
            result = subprocess.run(
                ['xrandr'] + args,
                capture_output=True,
                text=True,
                check=False, # Don't check=True, as --off might return non-zero if already off
                env=env,
                timeout=5
            )
            if result.returncode != 0:
                print(f"[HDMIController] xrandr command {' '.join(['xrandr'] + args)} failed with code {result.returncode}: {result.stderr.strip()}")
                # Check stderr for common "cannot find output" errors if needed
                if "cannot find output" in result.stderr and args[0] == '--output' and args[2] == '--off':
                    # If trying to turn off an output that's already off or disconnected, xrandr might error.
                    # We can interpret this as it's effectively off.
                    print(f"[HDMIController] Interpreting xrandr error as {self._hdmi_output_name} is already off or disconnected.")
                    self._is_hdmi_on = False # Update state if it seems it's off
                    return result.stdout # Still return stdout if any
                return None # Indicate command execution issue
            return result.stdout
        except FileNotFoundError:
            print("[HDMIController] Error: xrandr command not found.")
            return None
        except subprocess.TimeoutExpired:
            print(f"[HDMIController] Error: xrandr command timed out: {' '.join(['xrandr'] + args)}")
            return None
        except Exception as e:
            print(f"[HDMIController] Error running xrandr: {e}")
            return None

    def turn_on_hdmi(self) -> bool:
        print(f"[HDMIController] Attempting to turn ON {self._hdmi_output_name}...")
        result = self._run_xrandr_command(['--output', self._hdmi_output_name, '--auto'])
        if result is not None: # Command executed (even if xrandr reported an issue handled by _run_xrandr_command)
            # We assume --auto will turn it on if possible.
            # A more robust check would parse xrandr output after --auto.
            self._is_hdmi_on = True
            print(f"[HDMIController] {self._hdmi_output_name} turned ON. State: {self._is_hdmi_on}")
            return True
        print(f"[HDMIController] Failed to turn ON {self._hdmi_output_name}. State: {self._is_hdmi_on}")
        return False

    def turn_off_hdmi(self) -> bool:
        print(f"[HDMIController] Attempting to turn OFF {self._hdmi_output_name}...")
        result = self._run_xrandr_command(['--output', self._hdmi_output_name, '--off'])
        if result is not None: # Command executed
            # If _run_xrandr_command updated _is_hdmi_on to False due to "cannot find output", it's already handled.
            # Otherwise, assume --off worked.
            if "cannot find output" not in (result or ""): # A bit simplistic check of stdout
                self._is_hdmi_on = False
            print(f"[HDMIController] {self._hdmi_output_name} turned OFF. State: {self._is_hdmi_on}")
            return True
        print(f"[HDMIController] Failed to turn OFF {self._hdmi_output_name}. State: {self._is_hdmi_on}")
        return False

    def toggle_hdmi(self) -> None:
        print(f"[HDMIController] Toggling HDMI. Current assumed state: {'ON' if self._is_hdmi_on else 'OFF'}")
        if self._is_hdmi_on:
            self.turn_off_hdmi()
        else:
            self.turn_on_hdmi()
        # The actual state is updated within turn_on/off_hdmi methods
        print(f"[HDMIController] HDMI state after toggle: {'ON' if self._is_hdmi_on else 'OFF'}")

    def get_hdmi_status_message(self) -> str:
        return f"HDMI {self._hdmi_output_name} is currently {'ON' if self._is_hdmi_on else 'OFF'}"

if __name__ == '__main__':
    # Basic test
    controller = HDMIController()
    print(controller.get_hdmi_status_message())
    controller.toggle_hdmi() # Turn OFF
    print(controller.get_hdmi_status_message())
    time.sleep(2)
    controller.toggle_hdmi() # Turn ON
    print(controller.get_hdmi_status_message())
    time.sleep(2)
    controller.turn_off_hdmi() # Explicitly OFF
    print(controller.get_hdmi_status_message())