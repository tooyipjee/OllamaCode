"""
Logging module for OllamaCode.
"""

import os
import sys
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

from .utils import Colors


def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """Set up logging with configuration
    
    Args:
        config: Configuration dictionary with logging settings
        
    Returns:
        Configured logger
    """
    # Get logging configuration
    log_level = config.get("log_level", "INFO").upper()
    log_file = config.get("log_file", "")
    log_to_console = config.get("log_to_console", True)
    
    # Parse log level
    level = getattr(logging, log_level, logging.INFO)
    
    # Configure logging format
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Create logger
    logger = logging.getLogger("ollamacode")
    logger.setLevel(level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(log_format, date_format)
    
    # Add console handler if enabled
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ColoredFormatter(log_format, date_format))
        console_handler.setLevel(level)
        logger.addHandler(console_handler)
    
    # Add file handler if specified
    if log_file:
        # Expand ~ in path
        log_file = os.path.expanduser(log_file)
        
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    
    return logger


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels"""
    
    # Define log levels with corresponding colors
    COLORS = {
        "DEBUG": Colors.BLUE,
        "INFO": Colors.GREEN,
        "WARNING": Colors.YELLOW,
        "ERROR": Colors.RED,
        "CRITICAL": Colors.RED + Colors.BOLD
    }
    
    def format(self, record):
        # Save original levelname
        orig_levelname = record.levelname
        
        # Add color if running in terminal
        if sys.stdout.isatty():
            if record.levelname in self.COLORS:
                record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{Colors.ENDC}"
        
        # Format the record
        result = super().format(record)
        
        # Restore original levelname
        record.levelname = orig_levelname
        
        return result


class ErrorHandler:
    """Centralized error handling for OllamaCode"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def handle_error(self, error: Exception, context: str = "", exit_on_error: bool = False) -> str:
        """Handle an error and return a user-friendly message
        
        Args:
            error: The exception that occurred
            context: Additional context about where the error occurred
            exit_on_error: Whether to exit the program after handling the error
            
        Returns:
            User-friendly error message
        """
        error_type = type(error).__name__
        error_msg = str(error)
        
        # Log the error with traceback
        if context:
            self.logger.error(f"Error in {context}: {error_type}: {error_msg}")
        else:
            self.logger.error(f"{error_type}: {error_msg}")
        
        self.logger.debug(f"Traceback: {traceback.format_exc()}")
        
        # Create user-friendly message
        if context:
            user_msg = f"{Colors.RED}Error in {context}: {error_msg}{Colors.ENDC}"
        else:
            user_msg = f"{Colors.RED}Error: {error_msg}{Colors.ENDC}"
        
        # Print message to console
        print(user_msg)
        
        # Exit if required
        if exit_on_error:
            sys.exit(1)
        
        return user_msg
    
    def handle_api_error(self, response, context: str = "") -> str:
        """Handle an API error response
        
        Args:
            response: The API response object
            context: Additional context about the API call
            
        Returns:
            User-friendly error message
        """
        try:
            error_data = response.json()
            error_msg = error_data.get("error", f"HTTP {response.status_code}")
        except:
            error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
        
        # Log the error
        if context:
            self.logger.error(f"API error in {context}: {error_msg}")
        else:
            self.logger.error(f"API error: {error_msg}")
        
        # Create user-friendly message
        if context:
            user_msg = f"{Colors.RED}API error in {context}: {error_msg}{Colors.ENDC}"
        else:
            user_msg = f"{Colors.RED}API error: {error_msg}{Colors.ENDC}"
        
        # Print message to console
        print(user_msg)
        
        return user_msg