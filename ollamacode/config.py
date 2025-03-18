"""
Configuration management for OllamaCode.
"""

import os
import json
import sys
from typing import Dict, Any

from .utils import Colors

def load_config() -> Dict[str, Any]:
    """Load configuration from config files"""
    # Define paths for default and user config
    # Try multiple locations for the default config
    package_dir = os.path.dirname(os.path.abspath(__file__))
    possible_config_paths = [
        os.path.join(package_dir, "config.json"),                     # Inside the package
        os.path.join(os.path.dirname(package_dir), "config.json"),    # Sibling to package dir
        os.path.join(os.getcwd(), "config.json")                      # Current working directory
    ]
    
    # Find the first config file that exists
    default_config_path = next((path for path in possible_config_paths if os.path.exists(path)), None)
    user_config_path = os.path.expanduser("~/.config/ollamacode/config.json")
    
    # Initialize with empty config
    config = {}
    
    # Load default config
    try:
        if default_config_path and os.path.exists(default_config_path):
            with open(default_config_path, 'r') as f:
                config.update(json.load(f))
            print(f"{Colors.GREEN}Loaded config from {default_config_path}{Colors.ENDC}")
        else:
            print(f"{Colors.YELLOW}Warning: Default config file not found. Tried locations:{Colors.ENDC}")
            for path in possible_config_paths:
                print(f"  - {path}")
    except (json.JSONDecodeError, IOError) as e:
        print(f"{Colors.YELLOW}Warning: Could not load default config file: {e}{Colors.ENDC}")
    
    # Override with user config if it exists
    if os.path.exists(user_config_path):
        try:
            with open(user_config_path, 'r') as f:
                user_config = json.load(f)
                config.update(user_config)
        except (json.JSONDecodeError, IOError) as e:
            print(f"{Colors.YELLOW}Warning: Could not load user config file: {e}{Colors.ENDC}")
    
    # Expand paths in config
    for key in ["history_file", "working_directory"]:
        if key in config and isinstance(config[key], str):
            config[key] = os.path.expanduser(config[key])
    
    # Check if config is empty (no files were loaded successfully)
    if not config:
        print(f"{Colors.RED}Error: Could not load any configuration. Please ensure config.json exists.{Colors.ENDC}")
        sys.exit(1)
    
    return config

def save_config(config: Dict[str, Any]):
    """Save configuration to user config file"""
    config_path = os.path.expanduser("~/.config/ollamacode/config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"{Colors.GREEN}Configuration saved to {config_path}{Colors.ENDC}")
    except IOError as e:
        print(f"{Colors.RED}Error saving configuration: {e}{Colors.ENDC}")