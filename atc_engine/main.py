"""
ATC Engine - Main Module
------------------------
Initializes and runs the ATC application.
"""

import os
from atc_engine.app import Application
from atc_engine.action_handler import ActionHandler

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    
    action_handler = ActionHandler()
    app = Application(config_path=config_path, action_handler=action_handler)
    
    try:
        app.run()
    except Exception as e:
        print(f"[App] Unhandled exception: {e}")
    finally:
        print("[App] Exiting")