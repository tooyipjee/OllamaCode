"""
OllamaCode: A command-line tool for delegating coding tasks to local LLMs via Ollama
Enhanced with bash integration and tools framework for agent-like capabilities.
"""

__version__ = "0.2.0"

# Import key classes to make them available from the package
from .client import OllamaCode
from .tools import ToolsFramework
from .bash import BashExecutor
from .config import load_config, save_config