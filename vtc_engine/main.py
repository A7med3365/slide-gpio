"""
VTC Engine - Main Module
------------------------
Initializes and runs the VTC application.
"""

import os
from atc_engine.app import Application

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    
    app = Application(config_path=config_path)
    
    try:
        app.run()
    except Exception as e:
        print(f"[App] Unhandled exception: {e}")
    finally:
        print("[App] Exiting")