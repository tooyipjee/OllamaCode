"""
Plugin-based architecture for OllamaCode tools.
"""

import os
import json
import importlib
import importlib.util
import inspect
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Type, Optional, Set
from pathlib import Path


class ToolPlugin(ABC):
    """Base class for tool plugins"""
    
    name = "base_tool"  # Override in subclasses
    description = "Base tool plugin"  # Override in subclasses
    
    @classmethod
    @property
    def parameters(cls) -> Dict[str, Dict[str, Any]]:
        """Get parameter definitions for the tool
        
        Returns:
            Dict of parameter name -> parameter definition
        """
        return {}
    
    @classmethod
    def validate_params(cls, params: Dict[str, Any]) -> List[str]:
        """Validate parameters for the tool
        
        Returns:
            List of error messages, empty if valid
        """
        errors = []
        for param_name, param_info in cls.parameters.items():
            if param_info.get("required", False) and param_name not in params:
                errors.append(f"Missing required parameter: {param_name}")
                
            # Type validation
            if param_name in params and "type" in param_info:
                param_type = param_info["type"]
                value = params[param_name]
                
                # Basic type validation
                if param_type == "string" and not isinstance(value, str):
                    errors.append(f"Parameter '{param_name}' must be a string")
                elif param_type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Parameter '{param_name}' must be a number")
                elif param_type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Parameter '{param_name}' must be a boolean")
                elif param_type == "object" and not isinstance(value, dict):
                    errors.append(f"Parameter '{param_name}' must be an object")
                elif param_type == "array" and not isinstance(value, list):
                    errors.append(f"Parameter '{param_name}' must be an array")
                    
        return errors
    
    @abstractmethod
    def execute(self, params: Dict[str, Any], working_dir: Path, safe_mode: bool) -> Dict[str, Any]:
        """Execute the tool with the given parameters
        
        Args:
            params: Tool parameters
            working_dir: Working directory
            safe_mode: Whether safe mode is enabled
            
        Returns:
            Tool execution result
        """
        pass


class FileReadTool(ToolPlugin):
    """Tool for reading file contents"""
    
    name = "file_read"
    description = "Read a file's contents"
    
    @classmethod
    @property
    def parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "path": {
                "type": "string",
                "description": "Path to the file to read",
                "required": True
            }
        }
    
    def execute(self, params: Dict[str, Any], working_dir: Path, safe_mode: bool) -> Dict[str, Any]:
        from .security import SecurityManager
        
        if "path" not in params:
            return {"status": "error", "error": "Missing required parameter: path"}
        
        try:
            # Create a temporary security manager for path validation
            config = {"safe_mode": safe_mode, "working_directory": str(working_dir)}
            security = SecurityManager(config)
            
            path_str = params["path"]
            sanitized_path, error = security.sanitize_path(path_str, working_dir)
            
            if error:
                return {"status": "error", "error": error}
            
            if not sanitized_path.exists():
                return {"status": "error", "error": f"File not found: {sanitized_path}"}
            
            if not sanitized_path.is_file():
                return {"status": "error", "error": f"Not a file: {sanitized_path}"}
            
            # Check file size to prevent reading very large files
            size = sanitized_path.stat().st_size
            if size > 10 * 1024 * 1024:  # 10MB limit
                return {
                    "status": "error", 
                    "error": f"File too large ({size / 1024 / 1024:.2f} MB). Maximum size is 10MB."
                }
            
            content = sanitized_path.read_text(errors='replace')
            
            return {
                "status": "success",
                "content": content,
                "size": size,
                "path": str(sanitized_path)
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}


class FileWriteTool(ToolPlugin):
    """Tool for writing content to a file"""
    
    name = "file_write"
    description = "Write content to a file"
    
    @classmethod
    @property
    def parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "path": {
                "type": "string",
                "description": "Path to the file to write",
                "required": True
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
                "required": True
            },
            "append": {
                "type": "boolean",
                "description": "Whether to append to the file (default: false)",
                "required": False
            }
        }
    
    def execute(self, params: Dict[str, Any], working_dir: Path, safe_mode: bool) -> Dict[str, Any]:
        from .security import SecurityManager
        
        if "path" not in params:
            return {"status": "error", "error": "Missing required parameter: path"}
        if "content" not in params:
            return {"status": "error", "error": "Missing required parameter: content"}
        
        try:
            # Create a temporary security manager for path validation
            config = {"safe_mode": safe_mode, "working_directory": str(working_dir)}
            security = SecurityManager(config)
            
            path_str = params["path"]
            content = params["content"]
            append = params.get("append", False)
            
            # For write operations, we need to check with "write" operation
            is_safe, reason = security.is_path_safe(path_str, "write")
            if not is_safe:
                return {"status": "error", "error": reason}
                
            sanitized_path, error = security.sanitize_path(path_str, working_dir)
            if error:
                return {"status": "error", "error": error}
            
            # Create parent directories if they don't exist
            sanitized_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write or append to the file
            mode = "a" if append else "w"
            with open(sanitized_path, mode) as f:
                f.write(content)
            
            return {
                "status": "success",
                "message": f"Content {'appended to' if append else 'written to'} {sanitized_path}",
                "path": str(sanitized_path),
                "size": len(content)
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}


class ToolRegistry:
    """Registry for tool plugins"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.tools: Dict[str, Type[ToolPlugin]] = {}
        self.logger = logger or logging.getLogger(__name__)
    
    def register_tool(self, tool_cls: Type[ToolPlugin]):
        """Register a tool plugin"""
        if not hasattr(tool_cls, 'name') or not tool_cls.name:
            self.logger.warning(f"Cannot register tool without a name: {tool_cls}")
            return
            
        self.tools[tool_cls.name] = tool_cls
        self.logger.debug(f"Registered tool plugin: {tool_cls.name}")
    
    def get_tool(self, name: str) -> Optional[Type[ToolPlugin]]:
        """Get a tool plugin by name"""
        return self.tools.get(name)
    
    def get_all_tools(self) -> List[Type[ToolPlugin]]:
        """Get all registered tool plugins"""
        return list(self.tools.values())
    
    def discover_plugins(self, plugin_dir: str):
        """Discover and load tool plugins from a directory"""
        plugin_path = Path(plugin_dir)
        if not plugin_path.exists() or not plugin_path.is_dir():
            self.logger.warning(f"Plugin directory not found: {plugin_dir}")
            return
        
        self.logger.info(f"Scanning for plugins in: {plugin_dir}")
        
        for file_path in plugin_path.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            
            module_name = file_path.stem
            try:
                # Import the module
                spec = importlib.util.spec_from_file_location(
                    f"ollamacode.plugins.{module_name}", 
                    file_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Look for tool plugin classes
                plugin_count = 0
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, ToolPlugin) and 
                        attr is not ToolPlugin and 
                        attr.__module__ == module.__name__):  # Only register from this module
                        
                        self.register_tool(attr)
                        plugin_count += 1
                
                if plugin_count > 0:
                    self.logger.info(f"Loaded {plugin_count} plugins from {file_path}")
                
            except Exception as e:
                self.logger.error(f"Error loading plugin {module_name}: {e}")


# Initialize the tool registry with built-in tools
tool_registry = ToolRegistry()
tool_registry.register_tool(FileReadTool)
tool_registry.register_tool(FileWriteTool)
# Register more built-in tools as needed