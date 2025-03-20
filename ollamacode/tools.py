import os
import json
import subprocess
import urllib.request
import urllib.parse
import base64
import datetime
import tempfile
import platform
import logging
from typing import Dict, Any, Optional, List, Type
from pathlib import Path

from .utils import find_executable, Colors
from .security import SecurityManager
from .tool_plugins import ToolPlugin, tool_registry

class ToolsFramework:
    """Framework for executing tools requested by the LLM"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.working_dir = Path(config.get("working_directory", os.path.expanduser("~/ollamacode_workspace")))
        self.ensure_working_dir()
        
    def ensure_working_dir(self):
        """Ensure the working directory exists"""
        if not self.working_dir.exists():
            self.working_dir.mkdir(parents=True)
    
    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return its result"""
        if tool_name not in self.config.get("allowed_tools", []):
            return {
                "status": "error",
                "error": f"Tool '{tool_name}' is not allowed or does not exist."
            }
        
        # Map tool names to handler methods
        tool_handlers = {
            "file_read": self.file_read,
            "file_write": self.file_write,
            "file_list": self.file_list,
            "web_get": self.web_get,
            "sys_info": self.sys_info,
            "python_run": self.python_run,
            # Add more tools here
        }
        
        if tool_name not in tool_handlers:
            return {
                "status": "error",
                "error": f"Tool '{tool_name}' is not implemented."
            }
        
        try:
            return tool_handlers[tool_name](params)
        except Exception as e:
            return {
                "status": "error",
                "error": f"Error executing tool '{tool_name}': {str(e)}"
            }
    
    def _sanitize_path(self, path: str) -> Path:
        """Sanitize path to prevent directory traversal attacks"""
        # Convert to absolute path
        if not os.path.isabs(path):
            path = os.path.join(self.working_dir, path)
        
        path = os.path.abspath(path)
        
        # Check if path is within allowed directories
        if self.config.get("safe_mode", True):
            if not path.startswith(str(self.working_dir)):
                raise ValueError(f"Access denied: Path must be within {self.working_dir}")
        
        return Path(path)
    
    def file_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read a file and return its contents"""
        if "path" not in params:
            return {"status": "error", "error": "Missing required parameter: path"}
        
        try:
            path = self._sanitize_path(params["path"])
            
            if not path.exists():
                return {"status": "error", "error": f"File not found: {path}"}
            
            if not path.is_file():
                return {"status": "error", "error": f"Not a file: {path}"}
            
            # Check file size to prevent reading very large files
            size = path.stat().st_size
            if size > 10 * 1024 * 1024:  # 10MB limit
                return {
                    "status": "error", 
                    "error": f"File too large ({size / 1024 / 1024:.2f} MB). Maximum size is 10MB."
                }
            
            content = path.read_text(errors='replace')
            
            return {
                "status": "success",
                "content": content,
                "size": size,
                "path": str(path)
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def file_write(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Write content to a file"""
        if "path" not in params:
            return {"status": "error", "error": "Missing required parameter: path"}
        if "content" not in params:
            return {"status": "error", "error": "Missing required parameter: content"}
        
        try:
            path = self._sanitize_path(params["path"])
            content = params["content"]
            
            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            path.write_text(content)
            
            return {
                "status": "success",
                "message": f"Content written to {path}",
                "path": str(path),
                "size": len(content)
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def file_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List files in a directory"""
        directory = params.get("directory", ".")
        
        try:
            path = self._sanitize_path(directory)
            
            if not path.exists():
                return {"status": "error", "error": f"Directory not found: {path}"}
            
            if not path.is_dir():
                return {"status": "error", "error": f"Not a directory: {path}"}
            
            files = []
            for item in path.iterdir():
                files.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                    "last_modified": datetime.datetime.fromtimestamp(
                        item.stat().st_mtime
                    ).isoformat()
                })
            
            return {
                "status": "success",
                "directory": str(path),
                "items_count": len(files),
                "items": files
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def web_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make a GET request to a URL and return the response"""
        if "url" not in params:
            return {"status": "error", "error": "Missing required parameter: url"}
        
        url = params["url"]
        
        try:
            # Basic URL validation
            if not url.startswith(("http://", "https://")):
                return {"status": "error", "error": "URL must start with http:// or https://"}
            
            # Make the request
            headers = {'User-Agent': 'OllamaCode/1.0'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                status_code = response.getcode()
                content_type = response.getheader('Content-Type', 'text/plain')
                
                # Read response data
                data = response.read()
                
                # If content is likely to be text, decode it
                if 'text' in content_type or 'json' in content_type or 'xml' in content_type:
                    encoding = response.headers.get_content_charset('utf-8')
                    content = data.decode(encoding, errors='replace')
                else:
                    # For binary data, encode as base64
                    content = f"[Binary data, {len(data)} bytes, Content-Type: {content_type}]"
                    # Limit binary response size for context window
                    if len(data) > 1024:
                        content += " (truncated)"
                        data = data[:1024]
                    
                    # Only include base64 if it's reasonably small
                    if len(data) <= 1024:
                        content += f"\nBase64: {base64.b64encode(data).decode('ascii')}"
            
            return {
                "status": "success",
                "url": url,
                "status_code": status_code,
                "content_type": content_type,
                "content": content[:50000]  # Limit content size
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def sys_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get system information"""
        try:
            info = {
                "os": platform.system(),
                "os_release": platform.release(),
                "os_version": platform.version(),
                "architecture": platform.machine(),
                "processor": platform.processor(),
                "hostname": platform.node(),
                "python_version": platform.python_version(),
                "time": datetime.datetime.now().isoformat(),
                "working_directory": str(self.working_dir)
            }
            
            # Add environment variables (filtered for safety)
            safe_env_vars = ["PATH", "USER", "HOME", "SHELL", "LANG", "PWD", "TERM"]
            env = {}
            for var in safe_env_vars:
                if var in os.environ:
                    env[var] = os.environ[var]
            
            info["environment"] = env
            
            return {
                "status": "success",
                "info": info
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
            
    def python_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a Python script"""
        # Check if we have a path or code
        if "path" not in params and "code" not in params:
            return {"status": "error", "error": "Missing required parameter: either 'path' or 'code'"}
        
        try:
            # Find Python executable
            python_exec = find_executable("python3") or find_executable("python")
            if not python_exec:
                return {"status": "error", "error": "Python executable not found."}
            
            temp_file = None
            script_path = None
            
            # If code is provided, write it to a temporary file
            if "code" in params:
                code = params["code"]
                
                # Create temporary file
                fd, temp_file = tempfile.mkstemp(suffix=".py")
                with os.fdopen(fd, 'w') as f:
                    f.write(code)
                
                script_path = temp_file
                
                # Try to check for syntax errors first
                try:
                    compile(code, '<string>', 'exec')
                except SyntaxError as e:
                    return {
                        "status": "error",
                        "error": f"Python syntax error: {str(e)}",
                        "code": code,
                        "line": e.lineno if hasattr(e, 'lineno') else None,
                        "offset": e.offset if hasattr(e, 'offset') else None,
                        "text": e.text if hasattr(e, 'text') else None
                    }
            
            # If path is provided, use that file
            elif "path" in params:
                script_path = self._sanitize_path(params["path"])
                
                if not script_path.exists():
                    return {"status": "error", "error": f"Script file not found: {script_path}"}
                
                if not script_path.is_file():
                    return {"status": "error", "error": f"Not a file: {script_path}"}
                
                # Try to check for syntax errors
                try:
                    with open(script_path, 'r') as f:
                        code = f.read()
                    compile(code, str(script_path), 'exec')
                except SyntaxError as e:
                    return {
                        "status": "error",
                        "error": f"Python syntax error in file {script_path}: {str(e)}",
                        "line": e.lineno if hasattr(e, 'lineno') else None,
                        "offset": e.offset if hasattr(e, 'offset') else None,
                        "text": e.text if hasattr(e, 'text') else None
                    }
            
            # Execute the Python script
            process = subprocess.Popen(
                [python_exec, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.working_dir)
            )
            
            # Set a timeout for execution
            try:
                stdout, stderr = process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                return {"status": "error", "error": "Python script execution timed out after 15 seconds."}
            
            # Clean up if we used a temporary file
            if temp_file:
                try:
                    os.unlink(temp_file)
                except:
                    pass
            
            if process.returncode == 0:
                return {
                    "status": "success",
                    "returncode": process.returncode,
                    "stdout": stdout,
                    "script_path": str(script_path)
                }
            else:
                return {
                    "status": "error",
                    "returncode": process.returncode,
                    "stderr": stderr,
                    "stdout": stdout,
                    "script_path": str(script_path)
                }
                
        except Exception as e:
            return {"status": "error", "error": f"Error executing Python script: {str(e)}"}