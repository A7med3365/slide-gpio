"""
Config Loader Module
------------------
Handles loading and validation of configuration files.
"""

import json
import os
from typing import Dict, Any, List, Union

def validate_button_config(name: str, config: Dict[str, Any]) -> None:
    """Validate a button configuration."""
    if 'value' not in config:
        raise ValueError(f"Button '{name}' missing 'value' field")
    if not isinstance(config['value'], int):
        raise ValueError(f"Button '{name}' value must be an integer")
    
    if 'mode' not in config:
        raise ValueError(f"Button '{name}' missing 'mode' field")
    if config['mode'] not in ['press', 'toggle']:
        raise ValueError(f"Button '{name}' has invalid mode '{config['mode']}'")

def validate_media_config(name: str, config: Dict[str, Any], valid_buttons: List[str]) -> None:
    """Validate a media configuration."""
    if 'mode' not in config:
        raise ValueError(f"Media '{name}' missing 'mode' field")
    if config['mode'] not in ['flash', 'still', 'slide', 'scroll_text']:
        raise ValueError(f"Media '{name}' has invalid mode '{config['mode']}'")

    if 'path' not in config:
        raise ValueError(f"Media '{name}' missing 'path' field")
    if not os.path.exists(config['path']):
        raise ValueError(f"Media '{name}' path '{config['path']}' does not exist")

    if 'button' in config:
        buttons = config['button'] if isinstance(config['button'], list) else [config['button']]
        for btn in buttons:
            if btn not in valid_buttons:
                raise ValueError(f"Media '{name}' references invalid button '{btn}'")

    if 'hold_time' in config and not isinstance(config['hold_time'], (int, float)):
        raise ValueError(f"Media '{name}' hold_time must be a number")

def validate_action_config(name: str, config: Dict[str, Any], valid_buttons: List[str]) -> None:
    """Validate an action configuration."""
    if 'mode' not in config:
        raise ValueError(f"Action '{name}' missing 'mode' field")
    if config['mode'] not in ['hdmi_control', 'load_config']:
        raise ValueError(f"Action '{name}' has invalid mode '{config['mode']}'")

    if 'button' not in config:
        raise ValueError(f"Action '{name}' missing 'button' field")
    
    buttons = config['button'] if isinstance(config['button'], list) else [config['button']]
    for btn in buttons:
        if btn not in valid_buttons:
            raise ValueError(f"Action '{name}' references invalid button '{btn}'")

    if 'hold_time' in config and not isinstance(config['hold_time'], (int, float)):
        raise ValueError(f"Action '{name}' hold_time must be a number")

def validate_settings(config: Dict[str, Any]) -> None:
    """Validate global settings."""
    required_settings = {
        'debounce_time': 0.5,
        'poll_interval': 0.05,
        'default_combo_hold_time': 1.0
    }
    
    for key, default_value in required_settings.items():
        if key not in config:
            config[key] = default_value
        elif not isinstance(config[key], (int, float)):
            raise ValueError(f"Setting '{key}' must be a number")

def load_config(config_path: str) -> Dict[str, Any]:
    """Load and validate configuration from JSON file.
    
    Args:
        config_path: Path to the configuration JSON file
        
    Returns:
        Dict containing the validated configuration
        
    Raises:
        Exception: If configuration file cannot be loaded or is invalid
    """
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Validate required top-level sections
        required_sections = ['buttons', 'media', 'actions', 'settings']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing '{section}' section in config")

        # Validate buttons section
        for name, button_config in config['buttons'].items():
            validate_button_config(name, button_config)

        # Get list of valid button names for reference
        valid_buttons = list(config['buttons'].keys())

        # Validate media section
        for name, media_config in config['media'].items():
            validate_media_config(name, media_config, valid_buttons)

        # Validate actions section
        for name, action_config in config['actions'].items():
            validate_action_config(name, action_config, valid_buttons)

        # Validate settings
        validate_settings(config['settings'])

        print(f"[Config] Loaded configuration successfully:")
        print(f"- {len(config['buttons'])} buttons")
        print(f"- {len(config['media'])} media items")
        print(f"- {len(config['actions'])} actions")
        
        return config

    except Exception as e:
        print(f"[Config] Error loading configuration: {e}")
        raise