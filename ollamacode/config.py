"""
Configuration management for OllamaCode.
"""

import os
import json
import sys
import importlib.util
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
    
    # Load system prompt from file if specified
    if "system_prompt_file" in config and isinstance(config["system_prompt_file"], str):
        system_prompt = load_system_prompt_from_file(config["system_prompt_file"])
        if system_prompt:
            config["system_prompt"] = system_prompt
    
    # Check if config is empty (no files were loaded successfully)
    if not config:
        print(f"{Colors.RED}Error: Could not load any configuration. Please ensure config.json exists.{Colors.ENDC}")
        sys.exit(1)
    
    return config

def load_system_prompt_from_file(prompt_file_path: str) -> str:
    """Load system prompt from a file
    
    The file can be either:
    1. A Python module with a SYSTEM_PROMPT or similar variable
    2. A text file with the raw prompt content
    """
    # Get absolute path if not already
    if not os.path.isabs(prompt_file_path):
        package_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            os.path.join(package_dir, prompt_file_path),
            os.path.join(os.path.dirname(package_dir), prompt_file_path),
            os.path.join(os.getcwd(), prompt_file_path)
        ]
        for path in possible_paths:
            if os.path.exists(path):
                prompt_file_path = path
                break
    
    # Check if file exists
    if not os.path.exists(prompt_file_path):
        print(f"{Colors.YELLOW}Warning: System prompt file not found: {prompt_file_path}{Colors.ENDC}")
        return ""
    
    # Handle Python module file
    if prompt_file_path.endswith('.py'):
        try:
            spec = importlib.util.spec_from_file_location("prompt_module", prompt_file_path)
            prompt_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(prompt_module)
            
            # Look for prompt variable names in order of preference
            for var_name in ["CLAUDE_SYSTEM_PROMPT", "SYSTEM_PROMPT", "PROMPT"]:
                if hasattr(prompt_module, var_name):
                    return getattr(prompt_module, var_name)
            
            print(f"{Colors.YELLOW}Warning: No prompt variable found in {prompt_file_path}{Colors.ENDC}")
            return ""
            
        except Exception as e:
            print(f"{Colors.YELLOW}Warning: Error loading prompt from Python module: {e}{Colors.ENDC}")
            return ""
    
    # Handle text file (assume it's a simple text file with the prompt)
    try:
        with open(prompt_file_path, 'r') as f:
            return f.read()
    except Exception as e:
        print(f"{Colors.YELLOW}Warning: Error loading prompt from file: {e}{Colors.ENDC}")
        return ""

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