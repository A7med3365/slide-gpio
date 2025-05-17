"""
ATC Engine - Main Entry Point
----------------------------
Initializes and runs the application.
"""

import os
from .app import Application

def main():
    """Main entry point for the ATC Engine application."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    app = Application(config_path)
    
    try:
        app.run()
    except Exception as e:
        print(f"[App] Unhandled exception: {e}")
    finally:
        print("[App] Exiting")

if __name__ == "__main__":
    main()
