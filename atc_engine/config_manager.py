import json
from typing import Dict, Any, Optional, List

class ConfigError(ValueError):
    """Custom exception for configuration errors."""
    pass

class ConfigManager:
    def __init__(self, config_path: str):
        self._config_path = config_path
        self._config_data: Dict[str, Any] = self._load_and_validate_config()
        print(f"[ConfigManager] Configuration loaded and validated from {config_path}")

    def _load_and_validate_config(self) -> Dict[str, Any]:
        try:
            with open(self._config_path, 'r') as f:
                config_data = json.load(f)
        except FileNotFoundError:
            raise ConfigError(f"Configuration file not found: {self._config_path}")
        except json.JSONDecodeError as e:
            raise ConfigError(f"Error decoding JSON from {self._config_path}: {e}")
        
        self._validate_config(config_data)
        return config_data

    def _validate_config(self, config: Dict[str, Any]):
        # Top-level keys
        required_top_level_keys = ["buttons", "media", "actions", "settings"]
        for key in required_top_level_keys:
            if key not in config:
                raise ConfigError(f"Missing required top-level key '{key}' in configuration.")
            if not isinstance(config[key], dict):
                raise ConfigError(f"Top-level key '{key}' must be a dictionary.")

        # Validate 'buttons'
        buttons = config.get("buttons", {})
        if not isinstance(buttons, dict): raise ConfigError("'buttons' section must be a dictionary.")
        for name, details in buttons.items():
            if not isinstance(details, dict): raise ConfigError(f"Button '{name}' details must be a dictionary.")
            if "value" not in details or not isinstance(details["value"], int):
                raise ConfigError(f"Button '{name}' must have an integer 'value'.")
            if "mode" not in details or not isinstance(details["mode"], str) or details["mode"] not in ["press", "toggle"]:
                raise ConfigError(f"Button '{name}' must have a 'mode' (press/toggle). Found: {details.get('mode')}")
        
        # Validate 'media'
        media = config.get("media", {})
        if not isinstance(media, dict): raise ConfigError("'media' section must be a dictionary.")
        valid_media_modes = ["image_still", "image_flash", "scroll_text", "slide"] # Add other valid modes
        for name, details in media.items():
            if not isinstance(details, dict): raise ConfigError(f"Media item '{name}' details must be a dictionary.")
            if "mode" not in details or not isinstance(details["mode"], str) or details["mode"] not in valid_media_modes:
                raise ConfigError(f"Media item '{name}' must have a valid 'mode'. Found: {details.get('mode')}")
            if "path" not in details or not isinstance(details["path"], str):
                # Slide mode might have a directory path, other modes file paths. Basic check for now.
                raise ConfigError(f"Media item '{name}' must have a string 'path'.")
            if "button" in details and not (isinstance(details["button"], str) or \
                                            (isinstance(details["button"], list) and all(isinstance(b, str) for b in details["button"]))):
                raise ConfigError(f"Media item '{name}' 'button' must be a string or list of strings.")

        # Validate 'actions'
        actions = config.get("actions", {})
        if not isinstance(actions, dict): raise ConfigError("'actions' section must be a dictionary.")
        valid_action_modes = ["hdmi_control", "load_config"] # Add other valid modes
        for name, details in actions.items():
            if not isinstance(details, dict): raise ConfigError(f"Action item '{name}' details must be a dictionary.")
            if "mode" not in details or not isinstance(details["mode"], str) or details["mode"] not in valid_action_modes:
                raise ConfigError(f"Action item '{name}' must have a valid 'mode'. Found: {details.get('mode')}")
            if "button" in details and not (isinstance(details["button"], str) or \
                                            (isinstance(details["button"], list) and all(isinstance(b, str) for b in details["button"]))):
                raise ConfigError(f"Action item '{name}' 'button' must be a string or list of strings.")

        # Validate 'settings'
        settings = config.get("settings", {})
        if not isinstance(settings, dict): raise ConfigError("'settings' section must be a dictionary.")
        expected_settings = {
            "debounce_time": (float, int), "poll_interval": (float, int),
            "default_combo_hold_time": (float, int), "default_media_name": str,
            "image_flash_duty_cycle": (float, int), "image_flash_duration": (float, int),
            "scroll_text_speed": int, "scroll_text_font_size": int,
            "scroll_text_font_color": str # "scroll_text_bg_color" is optional str
        }
        for key, expected_type in expected_settings.items():
            if key not in settings:
                # Allow some settings to be optional by not raising error, or check for specific optional keys
                if key in ["default_media_name"]: # Example of a required setting
                    raise ConfigError(f"Missing required setting '{key}'.")
                print(f"[ConfigManager] Optional setting '{key}' not found, will use default if applicable.")
                continue # Skip type check if key is missing and optional
            
            if not isinstance(settings[key], expected_type):
                raise ConfigError(f"Setting '{key}' must be of type {expected_type}. Found: {type(settings[key])} ({settings[key]})")
        
        if "scroll_text_bg_color" in settings and settings["scroll_text_bg_color"] is not None and not isinstance(settings["scroll_text_bg_color"], str):
            raise ConfigError(f"Setting 'scroll_text_bg_color' must be a string or null. Found: {type(settings['scroll_text_bg_color'])}")

        print("[ConfigManager] Configuration validation successful.")

    def get_config(self) -> Dict[str, Any]:
        return self._config_data

    def get_buttons_config(self) -> Dict[str, Any]:
        return self._config_data.get("buttons", {})

    def get_media_config(self) -> Dict[str, Any]:
        return self._config_data.get("media", {})

    def get_actions_config(self) -> Dict[str, Any]:
        return self._config_data.get("actions", {})

    def get_settings(self) -> Dict[str, Any]:
        return self._config_data.get("settings", {})

    def get_specific_setting(self, key: str, default: Any = None) -> Any:
        return self._config_data.get("settings", {}).get(key, default)

    def get_default_media_name(self) -> Optional[str]:
        return self._config_data.get("settings", {}).get("default_media_name")

    def get_combined_actions(self) -> List[Dict[str, Any]]:
        combined = []
        for action_type, actions_dict in [("media", self.get_media_config()),
                                            ("action", self.get_actions_config())]:
            for name, details in actions_dict.items():
                combined.append({
                    'name': name,
                    'details': details,
                    'type': action_type # 'media' or 'action'
                })
        return combined

def get_config_path(self) -> str:
        """Returns the path to the configuration file."""
        return self._config_path
if __name__ == '__main__':
    # Example usage (assuming a config.json exists in the same directory or a valid path is given)
    try:
        # Create a dummy config.json for testing if it doesn't exist
        dummy_config_content = """
        {
            "buttons": {"btn1": {"value": 1, "mode": "press"}},
            "media": {"home": {"mode": "image_still", "path": "img.jpg"}},
            "actions": {"shutdown": {"mode": "hdmi_control", "button": "btn1"}},
            "settings": {
                "debounce_time": 0.5, "poll_interval": 0.05, "default_media_name": "home",
                "image_flash_duty_cycle": 0.75, "image_flash_duration": 1.0,
                "scroll_text_speed": 2, "scroll_text_font_size": 60, "scroll_text_font_color": "yellow"
            }
        }
        """
        # Determine path relative to this script for testing
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        test_config_path = os.path.join(script_dir, "test_config.json")
        with open(test_config_path, "w") as f:
            f.write(dummy_config_content)
        
        print(f"Attempting to load test config: {test_config_path}")
        manager = ConfigManager(test_config_path)
        print("Config loaded successfully.")
        print("Settings:", manager.get_settings())
        print("Default media name:", manager.get_default_media_name())
        print("Combined actions:", manager.get_combined_actions())

        # Test a failing validation
        invalid_config_content = """{"buttons": "not a dict"}"""
        invalid_config_path = os.path.join(script_dir, "invalid_config.json")
        with open(invalid_config_path, "w") as f:
            f.write(invalid_config_content)
        print(f"\nAttempting to load invalid config: {invalid_config_path}")
        try:
            manager_fail = ConfigManager(invalid_config_path)
        except ConfigError as e:
            print(f"Caught expected ConfigError: {e}")
        
        # Clean up test files
        os.remove(test_config_path)
        os.remove(invalid_config_path)

    except ConfigError as e:
        print(f"ConfigManager Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")