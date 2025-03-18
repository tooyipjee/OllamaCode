#!/usr/bin/env python3
"""
OllamaCode launcher script - Entry point for the OllamaCode application.
"""

import sys
import os

# Get the absolute path of the current directory and add it to the Python path
current_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, current_dir)

# Import and run the main function from the package
from ollamacode.main import main

if __name__ == "__main__":
    # Set environment variable to indicate we're running from the repository root
    os.environ['OLLAMACODE_REPO_ROOT'] = current_dir
    
    # Run the main function
    main()