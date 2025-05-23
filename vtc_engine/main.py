"""
VTC Engine - Main Module
------------------------
Initializes and runs the VTC application.
"""

import os
import argparse
from vtc_engine.app import Application

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VTC Engine")
    parser.add_argument(
        "--windowed",
        action="store_true",
        default=False,
        help="Run in windowed mode (default: fullscreen)"
    )
    args = parser.parse_args()

    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    
    app = Application(config_path=config_path, fullscreen=not args.windowed)
    
    try:
        app.run()
    except Exception as e:
        print(f"[App] Unhandled exception: {e}")
    finally:
        print("[App] Exiting")