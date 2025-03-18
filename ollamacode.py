#!/usr/bin/env python3
"""
OllamaCode: A command-line tool for delegating coding tasks to local LLMs via Ollama
Enhanced with bash integration and tools framework for agent-like capabilities.
"""

import argparse
import os
import sys
import json
import textwrap
import requests
import subprocess
import re
import readline
import tempfile
import shlex
import time
import datetime
import platform
import uuid
from typing import Dict, Any, List, Optional, Tuple, Union, Callable
from pathlib import Path
import urllib.request
import urllib.parse
import base64

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Default configuration
DEFAULT_CONFIG = {
    "ollama_endpoint": "http://localhost:11434",
    "model": "mistral-nemo:latest",
    "context_window": 8000,
    "temperature": 0.7,
    "max_tokens": 4000,
    "history_file": os.path.expanduser("~/.ollamacode_history"),
    "system_prompt": """You are OllamaCode, a coding and shell assistant that can use tools to help with tasks.
You can execute bash commands, create scripts, run scripts and use tools to perform various operations.

To execute a bash command, use:
```bash
<command>
```

To use a tool, use the following format:
```tool
{
  "tool": "tool_name",
  "params": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

Available tools:
- file_read: Read a file's contents
  - params: {"path": "path/to/file"}
- file_write: Write content to a file
  - params: {"path": "path/to/file", "content": "content to write"}
- file_list: List files in a directory
  - params: {"directory": "path/to/directory"}
- web_get: Make an HTTP GET request
  - params: {"url": "https://example.com"}
- sys_info: Get system information
  - params: {}
- python_run: Execute a Python script
  - params: {"path": "path/to/script.py"} or {"code": "print('Hello World')"}

Always provide well-commented, efficient code solutions and explain your approach.
When you use bash commands or tools, always summarize what you did and what you found.
""",
    "enable_bash": True,
    "enable_tools": True,
    "safe_mode": True,  # Restricts certain dangerous operations
    "working_directory": os.path.expanduser("~/ollamacode_workspace"),
    "allowed_tools": ["file_read", "file_write", "file_list", "web_get", "sys_info", "python_run"],
    # New configuration options for code handling
    "auto_extract_code": False,  # Whether to automatically extract code blocks
    "auto_save_code": False,     # Whether to save extracted code to files
    "auto_run_python": False,    # Whether to automatically run Python code
    "code_directory": "",        # Subdirectory for saved code (empty = working_directory)
}

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

class BashExecutor:
    """Handles execution of bash commands"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.working_dir = Path(config.get("working_directory", os.path.expanduser("~/ollamacode_workspace")))
        self.ensure_working_dir()
        
        # Commands that are never allowed
        self.blacklisted_commands = [
            "rm -rf /", "rm -rf /*", "mkfs", "dd if=/dev/zero", 
            ":(){:|:&};:", "echo > /dev/sda", "mv /* /dev/null"
        ]
        
    def ensure_working_dir(self):
        """Ensure the working directory exists"""
        if not self.working_dir.exists():
            self.working_dir.mkdir(parents=True)
    
    def is_command_safe(self, command: str) -> bool:
        """Check if a command is safe to execute"""
        if not self.config.get("enable_bash", True):
            return False
            
        # Skip safety checks if safe mode is disabled
        if not self.config.get("safe_mode", True):
            return True
            
        # Check against blacklisted commands
        command_lower = command.lower()
        for blacklisted in self.blacklisted_commands:
            if blacklisted in command_lower:
                return False
                
        # Additional safety checks
        if "sudo" in command_lower or "su " in command_lower:
            return False
            
        # More complex safety checks could be added here
        return True
    
    def execute_command(self, command: str) -> Dict[str, Any]:
        """Execute a bash command and return the result"""
        if not self.is_command_safe(command):
            return {
                "status": "error",
                "error": "Command not allowed for security reasons."
            }
            
        try:
            # Execute the command
            process = subprocess.Popen(
                command, 
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.working_dir)
            )
            
            # Set a timeout for command execution
            start_time = time.time()
            max_execution_time = 30  # 30 seconds max
            
            stdout, stderr = "", ""
            
            # Non-blocking read with timeout
            while process.poll() is None:
                # Check if we've exceeded max execution time
                if time.time() - start_time > max_execution_time:
                    process.terminate()
                    return {
                        "status": "error",
                        "error": f"Command execution timed out after {max_execution_time} seconds."
                    }
                
                # Wait a bit to avoid busy-waiting
                time.sleep(0.1)
            
            # Get outputs
            stdout, stderr = process.communicate()
            
            # Limit output size to avoid context overflow
            max_output_size = 10000
            if len(stdout) > max_output_size:
                stdout = stdout[:max_output_size] + f"\n... (output truncated, total size: {len(stdout)} bytes)"
            
            if len(stderr) > max_output_size:
                stderr = stderr[:max_output_size] + f"\n... (error output truncated, total size: {len(stderr)} bytes)"
            
            return {
                "status": "success" if process.returncode == 0 else "error",
                "command": command,
                "return_code": process.returncode,
                "stdout": stdout,
                "stderr": stderr
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Error executing command: {str(e)}"
            }

class OllamaCode:
    def __init__(self, config: Dict[str, Any]):
        """Initialize the OllamaCode client with configuration"""
        self.config = config
        self.conversation_history = []
        self.ensure_history_dir()
        
        # Initialize tools and bash executor
        self.tools = ToolsFramework(config)
        self.bash = BashExecutor(config)
        
        # Last response and actions tracking
        self.last_response = ""
        self.last_bash_result = None
        self.last_tool_result = None
    
    def ensure_history_dir(self):
        """Ensure the directory for the history file exists"""
        history_path = Path(self.config["history_file"])
        history_dir = history_path.parent
        if not history_dir.exists():
            history_dir.mkdir(parents=True)
        if not history_path.exists():
            with open(history_path, 'w') as f:
                pass
    
    def get_available_models(self) -> List[str]:
        """Get list of available models from Ollama"""
        try:
            response = requests.get(f"{self.config['ollama_endpoint']}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
            else:
                print(f"{Colors.RED}Error fetching models: HTTP {response.status_code}{Colors.ENDC}")
                return []
        except requests.RequestException as e:
            print(f"{Colors.RED}Connection error: {e}{Colors.ENDC}")
            print(f"Is Ollama running at {self.config['ollama_endpoint']}?")
            return []
    
    def validate_model(self, model_name: str) -> bool:
        """Check if the specified model is available in Ollama"""
        available_models = self.get_available_models()
        if not available_models:
            # If we couldn't fetch models, assume it might work
            return True
        return model_name in available_models
    
    def check_ollama_connection(self) -> bool:
        """Check if Ollama server is reachable"""
        try:
            response = requests.get(f"{self.config['ollama_endpoint']}/api/tags")
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def format_messages(self, prompt: str) -> Dict[str, Any]:
        """Format messages for the Ollama API"""
        # Format the conversation history and new prompt for the API
        messages = []
        
        # Add system prompt
        if self.config["system_prompt"]:
            messages.append({"role": "system", "content": self.config["system_prompt"]})
        
        # Add conversation history
        for message in self.conversation_history:
            messages.append(message)
        
        # Add the new user prompt
        messages.append({"role": "user", "content": prompt})
        
        return {
            "model": self.config["model"],
            "messages": messages,
            "stream": True,
            "temperature": self.config["temperature"],
            "max_tokens": self.config["max_tokens"]
        }
    
    def extract_bash_commands(self, text: str) -> List[str]:
        """Extract bash commands from markdown code blocks"""
        bash_blocks = re.findall(r"```(?:bash|shell|sh)\n([\s\S]*?)```", text)
        return [block.strip() for block in bash_blocks]
    
    def extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Extract tool calls from markdown tool blocks"""
        tool_blocks = re.findall(r"```tool\n([\s\S]*?)```", text)
        tool_calls = []
        
        for block in tool_blocks:
            try:
                tool_data = json.loads(block.strip())
                if "tool" in tool_data and "params" in tool_data:
                    tool_calls.append(tool_data)
            except json.JSONDecodeError:
                continue
                
        return tool_calls
    
    def extract_code_blocks(self, text: str) -> List[Tuple[str, str]]:
        """Extract code blocks with their language from markdown text"""
        pattern = r"```(\w*)\n([\s\S]*?)```"
        matches = re.findall(pattern, text)
        return [(lang.strip() if lang.strip() else "txt", code.strip()) for lang, code in matches]
    
    def generate_filename(self, code: str, language: str) -> str:
        """Generate a meaningful filename based on code content"""
        # Try to extract a name from first line comment
        first_line = code.strip().split('\n')[0]
        name_match = re.search(r'#\s*([\w\s]+)\.?', first_line)
        
        if name_match:
            name = re.sub(r'\W+', '_', name_match.group(1).lower().strip())
        else:
            # Use a timestamp and language as fallback
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            name = f"code_{timestamp}"
        
        # Map language to file extension
        extension_map = {
            "python": ".py", "py": ".py", 
            "javascript": ".js", "js": ".js",
            "typescript": ".ts", "ts": ".ts",
            "html": ".html",
            "css": ".css",
            "c": ".c",
            "cpp": ".cpp", "c++": ".cpp",
            "java": ".java",
            "rust": ".rs",
            "go": ".go",
            "ruby": ".rb",
            "php": ".php",
            "bash": ".sh", "shell": ".sh", "sh": ".sh",
            "sql": ".sql",
            "json": ".json",
            "xml": ".xml",
            "yaml": ".yml", "yml": ".yml",
            "markdown": ".md", "md": ".md",
            "txt": ".txt",
        }
        ext = extension_map.get(language.lower(), ".txt")
        
        return f"{name}{ext}"
    
    def execute_python_code(self, code: str, env_vars: Dict[str, str] = None) -> Tuple[bool, str]:
        """Execute Python code with improved environment and error handling"""
        # Create a temporary file
        fd, path = tempfile.mkstemp(suffix=".py")
        with os.fdopen(fd, 'w') as f:
            f.write(code)
        
        try:
            # Find Python executable
            python_exec = find_executable("python3") or find_executable("python")
            if not python_exec:
                return False, "Python executable not found."
            
            # Set up environment
            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)
            
            # Execute with proper error handling
            process = subprocess.Popen(
                [python_exec, path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=str(self.tools.working_dir)
            )
            
            stdout, stderr = process.communicate(timeout=15)
            
            if process.returncode == 0:
                return True, stdout
            else:
                # Format error message for better readability
                error_msg = f"Execution failed (code {process.returncode}):\n"
                if stderr:
                    error_lines = stderr.strip().split('\n')
                    for line in error_lines:
                        # Highlight error location if possible
                        if "File " in line and ", line " in line:
                            error_msg += f"{Colors.RED}{line}{Colors.ENDC}\n"
                        else:
                            error_msg += f"{line}\n"
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            return False, "Execution timed out after 15 seconds."
        except Exception as e:
            return False, f"Error executing code: {str(e)}"
        finally:
            # Clean up
            try:
                os.unlink(path)
            except:
                pass
    
    def process_bash_and_tools(self, response_text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Process bash commands and tool calls in the response"""
        processed_results = []
        
        # Process bash commands
        if self.config.get("enable_bash", True):
            bash_commands = self.extract_bash_commands(response_text)
            
            for command in bash_commands:
                print(f"\n{Colors.YELLOW}Executing bash command:{Colors.ENDC} {command}")
                result = self.bash.execute_command(command)
                self.last_bash_result = result
                
                if result["status"] == "success":
                    print(f"{Colors.GREEN}Command executed successfully{Colors.ENDC}")
                    if result.get("stdout"):
                        print(f"\n{Colors.CYAN}Output:{Colors.ENDC}\n{result['stdout']}")
                else:
                    print(f"{Colors.RED}Command execution failed:{Colors.ENDC} {result.get('error', 'Unknown error')}")
                    if result.get("stderr"):
                        print(f"\n{Colors.RED}Error output:{Colors.ENDC}\n{result['stderr']}")
                
                processed_results.append({
                    "type": "bash",
                    "command": command,
                    "result": result
                })
        
        # Process tool calls
        if self.config.get("enable_tools", True):
            tool_calls = self.extract_tool_calls(response_text)
            
            for tool_call in tool_calls:
                tool_name = tool_call["tool"]
                params = tool_call["params"]
                
                print(f"\n{Colors.YELLOW}Executing tool:{Colors.ENDC} {tool_name}")
                print(f"Parameters: {json.dumps(params, indent=2)}")
                
                # Special handling for python_run tool with code parameter
                if tool_name == "python_run" and "code" in params:
                    code = params["code"]
                    # Fix common syntax issues that models might introduce
                    fixed_code = code
                    # Replace common errors with correct Python syntax
                    fixed_code = re.sub(r'for \* in', 'for _ in', fixed_code)  # Fix asterisk in for loop
                    fixed_code = re.sub(r'([a-zA-Z0-9_]+)\*([a-zA-Z0-9_]+)', r'\1_\2', fixed_code)  # Fix variable names with asterisks
                    
                    # Check if code was modified
                    if fixed_code != code:
                        print(f"{Colors.YELLOW}Fixed potential syntax issues in Python code{Colors.ENDC}")
                        params["code"] = fixed_code
                
                result = self.tools.execute_tool(tool_name, params)
                self.last_tool_result = result
                
                if result["status"] == "success":
                    print(f"{Colors.GREEN}Tool executed successfully{Colors.ENDC}")
                    # Show abbreviated result if it's lengthy
                    if isinstance(result.get("content"), str) and len(result.get("content", "")) > 500:
                        content_preview = result["content"][:500] + "... (content truncated)"
                        display_result = result.copy()
                        display_result["content"] = content_preview
                        print(f"Result: {json.dumps(display_result, indent=2)}")
                    else:
                        # Remove content field for display if it's very large
                        display_result = result.copy()
                        if isinstance(result.get("content"), str) and len(result.get("content", "")) > 500:
                            display_result["content"] = f"[{len(result['content'])} characters]"
                        print(f"Result: {json.dumps(display_result, indent=2)}")
                else:
                    print(f"{Colors.RED}Tool execution failed:{Colors.ENDC} {result.get('error', 'Unknown error')}")
                
                processed_results.append({
                    "type": "tool",
                    "tool": tool_name,
                    "params": params,
                    "result": result
                })
        
        # Add automatic code extraction and handling
        if self.config.get("auto_extract_code", False):
            code_blocks = self.extract_code_blocks(response_text)
            for lang, code in code_blocks:
                # Skip bash blocks (already handled above) and tool blocks
                if lang.lower() in ["bash", "shell", "sh", "tool"]:
                    continue
                    
                # Handle Python code specially
                if lang.lower() in ["python", "py"] and self.config.get("auto_run_python", False):
                    print(f"\n{Colors.YELLOW}Auto-executing Python code...{Colors.ENDC}")
                    success, result = self.execute_python_code(code)
                    
                    # Show execution results
                    if success:
                        print(f"{Colors.GREEN}Execution successful:{Colors.ENDC}")
                        print(result)
                    else:
                        print(f"{Colors.RED}Execution failed:{Colors.ENDC}")
                        print(result)
                
                # Save code to a permanent file in working directory
                if self.config.get("auto_save_code", False):
                    # Get the directory for saving code
                    code_dir = self.config.get("code_directory", "")
                    if code_dir:
                        save_dir = os.path.join(self.tools.working_dir, code_dir)
                        os.makedirs(save_dir, exist_ok=True)
                    else:
                        save_dir = self.tools.working_dir
                    
                    # Generate a filename based on first line comment or code content
                    filename = self.generate_filename(code, lang)
                    save_path = os.path.join(save_dir, filename)
                    
                    with open(save_path, 'w') as f:
                        f.write(code)
                    print(f"{Colors.GREEN}Code saved to {save_path}{Colors.ENDC}")
                    
                    processed_results.append({
                        "type": "code_saved",
                        "language": lang,
                        "path": save_path
                    })
        
        return response_text, processed_results
    
    def format_results_for_followup(self, processed_results: List[Dict[str, Any]]) -> str:
        """Format processed results as a followup prompt"""
        if not processed_results:
            return ""
            
        followup = "\n\nHere are the results of the commands and tools you requested:\n\n"
        
        for result in processed_results:
            if result["type"] == "bash":
                cmd_result = result["result"]
                followup += f"## Bash Command Result: `{result['command']}`\n\n"
                if cmd_result["status"] == "success":
                    followup += "Command executed successfully.\n\n"
                    if cmd_result.get("stdout"):
                        followup += f"**Output:**\n```\n{cmd_result['stdout']}\n```\n\n"
                    else:
                        followup += "Command produced no output.\n\n"
                else:
                    followup += f"Command execution failed with error: {cmd_result.get('error', 'Unknown error')}\n\n"
                    if cmd_result.get("stderr"):
                        followup += f"**Error output:**\n```\n{cmd_result['stderr']}\n```\n\n"
            
            elif result["type"] == "tool":
                tool_result = result["result"]
                followup += f"## Tool Result: `{result['tool']}`\n\n"
                
                if tool_result["status"] == "success":
                    followup += "Tool executed successfully.\n\n"
                    
                    # Handle special output formatting based on tool type
                    if result['tool'] == "file_read" and "content" in tool_result:
                        # For file reading, format the content as a code block
                        file_path = tool_result.get("path", "unknown")
                        extension = os.path.splitext(file_path)[1]
                        language = ""
                        
                        # Try to infer language from file extension
                        if extension:
                            ext_to_lang = {
                                ".py": "python",
                                ".js": "javascript",
                                ".html": "html",
                                ".css": "css",
                                ".json": "json",
                                ".md": "markdown",
                                ".c": "c",
                                ".cpp": "cpp",
                                ".h": "c",
                                ".sh": "bash",
                                ".txt": "",
                                ".xml": "xml",
                                ".yml": "yaml",
                                ".yaml": "yaml",
                                ".java": "java",
                                ".rb": "ruby",
                                ".php": "php",
                                ".go": "go",
                                ".rs": "rust",
                                ".ts": "typescript",
                            }
                            language = ext_to_lang.get(extension.lower(), "")
                        
                        followup += f"**File content ({tool_result.get('path')}):**\n```{language}\n{tool_result['content']}\n```\n\n"
                    
                    elif result['tool'] == "file_list" and "items" in tool_result:
                        # Format directory listing in a cleaner way
                        followup += f"**Directory contents of {tool_result.get('directory')}:**\n\n"
                        
                        # Sort items - directories first, then files
                        sorted_items = sorted(
                            tool_result["items"], 
                            key=lambda x: (0 if x["type"] == "directory" else 1, x["name"].lower())
                        )
                        
                        for item in sorted_items:
                            if item["type"] == "directory":
                                followup += f"- 📁 {item['name']}/\n"
                            else:
                                size_str = f" ({item['size']} bytes)" if item['size'] is not None else ""
                                followup += f"- 📄 {item['name']}{size_str}\n"
                        
                        followup += "\n"
                    
                    elif result['tool'] == "web_get" and "content" in tool_result:
                        # For web content, provide metadata and content
                        followup += f"**URL:** {tool_result.get('url')}\n"
                        followup += f"**Status code:** {tool_result.get('status_code')}\n"
                        followup += f"**Content type:** {tool_result.get('content_type')}\n\n"
                        
                        # Add content, possibly truncated
                        content = tool_result['content']
                        if len(content) > 1000:
                            content = content[:1000] + "... (content truncated)"
                        
                        followup += f"**Content:**\n```\n{content}\n```\n\n"
                    
                    elif result['tool'] == "sys_info" and "info" in tool_result:
                        # Format system info in a readable way
                        info = tool_result["info"]
                        followup += "**System Information:**\n\n"
                        followup += f"- OS: {info.get('os')} {info.get('os_release')}\n"
                        followup += f"- Version: {info.get('os_version')}\n"
                        followup += f"- Architecture: {info.get('architecture')}\n"
                        followup += f"- Processor: {info.get('processor')}\n"
                        followup += f"- Hostname: {info.get('hostname')}\n"
                        followup += f"- Python version: {info.get('python_version')}\n"
                        followup += f"- Current time: {info.get('time')}\n"
                        followup += f"- Working directory: {info.get('working_directory')}\n\n"
                        
                        if "environment" in info:
                            followup += "**Environment Variables:**\n\n"
                            for key, value in info["environment"].items():
                                followup += f"- {key}={value}\n"
                            followup += "\n"
                            
                    elif result['tool'] == "python_run":
                        # Format Python execution results
                        followup += f"**Python Script Execution:**\n\n"
                        followup += f"Script: {tool_result.get('script_path', 'Unknown')}\n\n"
                        
                        if tool_result["status"] == "success":
                            followup += "Execution successful.\n\n"
                            
                            if tool_result.get("stdout"):
                                followup += f"**Output:**\n```\n{tool_result['stdout']}\n```\n\n"
                            else:
                                followup += "Script executed without producing any output.\n\n"
                        else:
                            # Handle specific Python syntax errors
                            if "Python syntax error" in tool_result.get("error", ""):
                                followup += f"**Syntax Error:**\n{tool_result.get('error')}\n\n"
                                
                                # Add more detailed syntax error information if available
                                if tool_result.get("line") and tool_result.get("text"):
                                    followup += f"Line {tool_result.get('line')}: `{tool_result.get('text')}`\n"
                                    if tool_result.get("offset"):
                                        # Create a pointer to the error position
                                        pointer = " " * (tool_result.get("offset") - 1) + "^"
                                        followup += f"`{pointer}`\n\n"
                                
                                # If code is provided directly, show it for context
                                if tool_result.get("code"):
                                    followup += f"**Code with error:**\n```python\n{tool_result['code']}\n```\n\n"
                            else:
                                # Regular runtime errors
                                followup += f"Execution failed with error code: {tool_result.get('returncode', 'Unknown')}\n\n"
                                
                                if tool_result.get("stderr"):
                                    followup += f"**Error:**\n```\n{tool_result['stderr']}\n```\n\n"
                                
                                if tool_result.get("stdout"):
                                    followup += f"**Output before error:**\n```\n{tool_result['stdout']}\n```\n\n"
                    
                    else:
                        # Generic formatting for other tool results
                        result_copy = tool_result.copy()
                        
                        # Remove very long content fields for display
                        for key, value in tool_result.items():
                            if isinstance(value, str) and len(value) > 1000:
                                result_copy[key] = f"[{len(value)} characters]"
                        
                        # Format as JSON
                        followup += f"**Result:**\n```json\n{json.dumps(result_copy, indent=2)}\n```\n\n"
                else:
                    followup += f"Tool execution failed with error: {tool_result.get('error', 'Unknown error')}\n\n"
            
            elif result["type"] == "code_saved":
                followup += f"## Code Saved: `{os.path.basename(result['path'])}`\n\n"
                followup += f"A {result['language']} code file was saved to: {result['path']}\n\n"
        
        followup += "Please continue based on these results. What would you like to do next?\n"
        return followup
    
    def send_request(self, prompt: str, is_followup: bool = False) -> str:
        """Send a request to the Ollama API and return the response"""
        if not self.check_ollama_connection():
            print(f"{Colors.RED}Error: Cannot connect to Ollama at {self.config['ollama_endpoint']}{Colors.ENDC}")
            print("Make sure Ollama is running and accessible.")
            sys.exit(1)
        
        # Validate that the model exists
        if not self.validate_model(self.config["model"]):
            print(f"{Colors.RED}Error: Model '{self.config['model']}' not found in Ollama.{Colors.ENDC}")
            print(f"Available models: {', '.join(self.get_available_models())}")
            print(f"You may need to pull it first with: ollama pull {self.config['model']}")
            sys.exit(1)
        
        data = self.format_messages(prompt)
        
        try:
            # Use streaming API for real-time responses
            response = requests.post(
                f"{self.config['ollama_endpoint']}/api/chat",
                json=data,
                stream=True
            )
            
            if response.status_code != 200:
                print(f"{Colors.RED}Error: HTTP {response.status_code}{Colors.ENDC}")
                try:
                    error_data = response.json()
                    print(f"Error message: {error_data.get('error', 'Unknown error')}")
                except:
                    print(f"Response: {response.text}")
                sys.exit(1)
            
            # Process the streaming response
            full_response = ""
            print(f"\n{Colors.CYAN}OllamaCode:{Colors.ENDC} ", end="", flush=True)
            
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            print(content, end="", flush=True)
                            full_response += content
                    except json.JSONDecodeError:
                        continue
            
            print("\n")  # Add newline after response
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": prompt})
            self.conversation_history.append({"role": "assistant", "content": full_response})
            
            # Keep history within context window limits
            self._trim_history()
            
            # Store the last response
            self.last_response = full_response
            
            # Process bash commands and tool calls if this isn't a followup
            # (to avoid infinite loops)
            if not is_followup:
                response_text, processed_results = self.process_bash_and_tools(full_response)
                
                # If we have results to share, send a followup prompt
                if processed_results:
                    followup_prompt = self.format_results_for_followup(processed_results)
                    if followup_prompt:
                        print(f"\n{Colors.YELLOW}Sharing command/tool results with the model...{Colors.ENDC}")
                        followup_response = self.send_request(followup_prompt, is_followup=True)
                        
                        # Update the last response to include the followup
                        self.last_response += "\n\n" + followup_response
                        
                        # The full response should now include the followup as well
                        full_response += "\n\n" + followup_response
            
            return full_response
        
        except requests.RequestException as e:
            print(f"{Colors.RED}Error communicating with Ollama: {e}{Colors.ENDC}")
            sys.exit(1)
    
    def _trim_history(self):
        """Trim conversation history to fit within context window"""
        # Simple character count-based trimming
        total_chars = sum(len(msg["content"]) for msg in self.conversation_history)
        
        while total_chars > self.config["context_window"] and len(self.conversation_history) > 2:
            # Remove oldest pair of messages (user + assistant)
            if len(self.conversation_history) >= 2:
                removed1 = self.conversation_history.pop(0)
                total_chars -= len(removed1["content"])
                
                if self.conversation_history:
                    removed2 = self.conversation_history.pop(0)
                    total_chars -= len(removed2["content"])
    
    def save_code_to_file(self, code: str, language: str) -> str:
        """Save code to a temporary file with appropriate extension"""
        # Map common language names to file extensions
        extension_map = {
            "python": ".py",
            "py": ".py",
            "javascript": ".js",
            "js": ".js",
            "typescript": ".ts",
            "ts": ".ts",
            "html": ".html",
            "css": ".css",
            "c": ".c",
            "cpp": ".cpp",
            "c++": ".cpp",
            "java": ".java",
            "rust": ".rs",
            "go": ".go",
            "ruby": ".rb",
            "php": ".php",
            "bash": ".sh",
            "shell": ".sh",
            "sh": ".sh",
            "sql": ".sql",
            "json": ".json",
            "xml": ".xml",
            "yaml": ".yml",
            "yml": ".yml",
            "markdown": ".md",
            "md": ".md",
            "txt": ".txt",
        }
        
        # Get file extension
        ext = extension_map.get(language.lower(), ".txt")
        
        # Create temporary file
        fd, path = tempfile.mkstemp(suffix=ext)
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(code)
        
        return path

def load_config() -> Dict[str, Any]:
    """Load configuration from config file or use defaults"""
    config_path = os.path.expanduser("~/.config/ollamacode/config.json")
    config = DEFAULT_CONFIG.copy()
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                config.update(user_config)
        except (json.JSONDecodeError, IOError) as e:
            print(f"{Colors.YELLOW}Warning: Could not load config file: {e}{Colors.ENDC}")
            print(f"Using default configuration.")
    
    return config

def save_config(config: Dict[str, Any]):
    """Save configuration to config file"""
    config_path = os.path.expanduser("~/.config/ollamacode/config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"{Colors.GREEN}Configuration saved to {config_path}{Colors.ENDC}")
    except IOError as e:
        print(f"{Colors.RED}Error saving configuration: {e}{Colors.ENDC}")

def find_executable(cmd: str) -> Optional[str]:
    """Find the executable in PATH"""
    return subprocess.run(
        ["which", cmd], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        text=True
    ).stdout.strip() or None

def execute_code(file_path: str, language: str) -> Tuple[bool, str]:
    """Execute code and return the result"""
    language = language.lower()
    
    # Map language to execution command
    cmd = None
    if language in ["python", "py"]:
        python_exec = find_executable("python3") or find_executable("python")
        if python_exec:
            cmd = [python_exec, file_path]
    elif language in ["javascript", "js"]:
        node_exec = find_executable("node")
        if node_exec:
            cmd = [node_exec, file_path]
    elif language in ["bash", "shell", "sh"]:
        bash_exec = find_executable("bash")
        if bash_exec:
            # Make sure file is executable
            os.chmod(file_path, 0o755)
            cmd = [bash_exec, file_path]
    elif language in ["c", "cpp", "c++"]:
        # For C/C++, we need to compile first
        gcc_exec = find_executable("gcc") if language == "c" else find_executable("g++")
        if gcc_exec:
            output_file = file_path + ".out"
            compile_cmd = [gcc_exec, file_path, "-o", output_file]
            compile_result = subprocess.run(
                compile_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if compile_result.returncode != 0:
                return False, f"Compilation error:\n{compile_result.stderr}"
            
            cmd = [output_file]
    
    if not cmd:
        return False, f"Execution not supported for language '{language}' or required executable not found."
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10  # Add timeout to prevent infinite loops
        )
        
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, f"Execution error (code {result.returncode}):\n{result.stderr}"
    
    except subprocess.TimeoutExpired:
        return False, "Execution timed out after 10 seconds."
    except Exception as e:
        return False, f"Error executing code: {str(e)}"

def show_help():
    """Display help information"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}OllamaCode Help{Colors.ENDC}")
    print(f"\n{Colors.BOLD}Commands:{Colors.ENDC}")
    print(f"  {Colors.YELLOW}/help{Colors.ENDC}             Show this help message")
    print(f"  {Colors.YELLOW}/quit{Colors.ENDC} or {Colors.YELLOW}/exit{Colors.ENDC}   Exit OllamaCode")
    print(f"  {Colors.YELLOW}/clear{Colors.ENDC}            Clear the conversation history")
    print(f"  {Colors.YELLOW}/models{Colors.ENDC}           List available models in Ollama")
    print(f"  {Colors.YELLOW}/model <n>{Colors.ENDC}     Switch to a different model")
    print(f"  {Colors.YELLOW}/run{Colors.ENDC}              Extract and run the last code block")
    print(f"  {Colors.YELLOW}/save <path>{Colors.ENDC}      Save the last response to a file")
    print(f"  {Colors.YELLOW}/config{Colors.ENDC}           Show current configuration")
    print(f"  {Colors.YELLOW}/temp <value>{Colors.ENDC}     Set temperature (0.0-1.0)")
    print(f"  {Colors.YELLOW}/tools{Colors.ENDC}            List available tools")
    print(f"  {Colors.YELLOW}/toggle_bash{Colors.ENDC}      Enable/disable bash execution")
    print(f"  {Colors.YELLOW}/toggle_tools{Colors.ENDC}     Enable/disable tools")
    print(f"  {Colors.YELLOW}/toggle_safe{Colors.ENDC}      Enable/disable safe mode")
    print(f"  {Colors.YELLOW}/toggle_auto_save{Colors.ENDC} Enable/disable automatic code saving")
    print(f"  {Colors.YELLOW}/toggle_auto_run{Colors.ENDC}  Enable/disable automatic Python execution")
    print(f"  {Colors.YELLOW}/list_code{Colors.ENDC}        List saved code files")
    print(f"  {Colors.YELLOW}/workspace{Colors.ENDC}        Show working directory")
    print()

def list_tools(config: Dict[str, Any]):
    """Display information about available tools"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}Available Tools{Colors.ENDC}")
    
    tools_enabled = config.get("enable_tools", True)
    bash_enabled = config.get("enable_bash", True)
    safe_mode = config.get("safe_mode", True)
    auto_save = config.get("auto_save_code", False)
    auto_run = config.get("auto_run_python", False)
    
    print(f"\n{Colors.BOLD}Status:{Colors.ENDC}")
    print(f"  Tools enabled: {Colors.GREEN if tools_enabled else Colors.RED}{tools_enabled}{Colors.ENDC}")
    print(f"  Bash enabled: {Colors.GREEN if bash_enabled else Colors.RED}{bash_enabled}{Colors.ENDC}")
    print(f"  Safe mode: {Colors.GREEN if safe_mode else Colors.RED}{safe_mode}{Colors.ENDC}")
    print(f"  Auto-save code: {Colors.GREEN if auto_save else Colors.RED}{auto_save}{Colors.ENDC}")
    print(f"  Auto-run Python: {Colors.GREEN if auto_run else Colors.RED}{auto_run}{Colors.ENDC}")
    
    if tools_enabled:
        print(f"\n{Colors.BOLD}Available Tools:{Colors.ENDC}")
        print(f"  {Colors.YELLOW}file_read{Colors.ENDC}      - Read a file's contents")
        print(f"    params: " + '{"path": "path/to/file"}')
        
        print(f"  {Colors.YELLOW}file_write{Colors.ENDC}     - Write content to a file")
        print(f"    params: " + '{"path": "path/to/file", "content": "content to write"}')
        
        print(f"  {Colors.YELLOW}file_list{Colors.ENDC}      - List files in a directory")
        print(f"    params: " + '{"directory": "path/to/directory"}')
        
        print(f"  {Colors.YELLOW}web_get{Colors.ENDC}        - Make an HTTP GET request")
        print(f"    params: " + '{"url": "https://example.com"}')
        
        print(f"  {Colors.YELLOW}sys_info{Colors.ENDC}       - Get system information")
        print(f"    params: " + '{}')
        
        print(f"  {Colors.YELLOW}python_run{Colors.ENDC}     - Execute a Python script")
        print(f"    params: " + '{"path": "path/to/script.py"}' + " or " + '{"code": "print(\'Hello\')"}')
    
    if bash_enabled:
        print(f"\n{Colors.BOLD}Bash Commands:{Colors.ENDC}")
        print(f"  Use triple backtick blocks with bash, sh, or shell language tag:")
        print(f"  ```bash")
        print(f"  ls -la")
        print(f"  ```")
        
        if safe_mode:
            print(f"\n  {Colors.YELLOW}Note:{Colors.ENDC} Safe mode is enabled. Certain commands are restricted.")
        
    print()

def main():
    parser = argparse.ArgumentParser(description="OllamaCode - A Claude Code alternative using Ollama")
    parser.add_argument("prompt", nargs="*", help="The initial prompt (optional)")
    parser.add_argument("--model", "-m", help="Specify the Ollama model to use")
    parser.add_argument("--endpoint", "-e", help="Specify the Ollama API endpoint")
    parser.add_argument("--temperature", "-t", type=float, help="Set the temperature (0.0-1.0)")
    parser.add_argument("--list-models", "-l", action="store_true", help="List available models and exit")
    parser.add_argument("--version", "-v", action="store_true", help="Show version and exit")
    parser.add_argument("--disable-bash", action="store_true", help="Disable bash command execution")
    parser.add_argument("--disable-tools", action="store_true", help="Disable tools")
    parser.add_argument("--unsafe", action="store_true", help="Disable safety restrictions")
    parser.add_argument("--workspace", help="Set the working directory for bash and tools")
    # New command line arguments
    parser.add_argument("--auto-save", action="store_true", help="Automatically save code to files")
    parser.add_argument("--auto-run", action="store_true", help="Automatically run Python code")
    parser.add_argument("--code-dir", help="Subdirectory for saved code")
    
    args = parser.parse_args()
    
    if args.version:
        print("OllamaCode v0.2.0")
        return
    
    # Load configuration
    config = load_config()
    
    # Override config with command line arguments
    if args.model:
        config["model"] = args.model
    if args.endpoint:
        config["ollama_endpoint"] = args.endpoint
    if args.temperature is not None:
        config["temperature"] = max(0.0, min(1.0, args.temperature))
    if args.disable_bash:
        config["enable_bash"] = False
    if args.disable_tools:
        config["enable_tools"] = False
    if args.unsafe:
        config["safe_mode"] = False
    if args.workspace:
        config["working_directory"] = os.path.abspath(args.workspace)
    # Handle new command line arguments
    if args.auto_save:
        config["auto_extract_code"] = True
        config["auto_save_code"] = True
    if args.auto_run:
        config["auto_extract_code"] = True
        config["auto_run_python"] = True
    if args.code_dir:
        config["code_directory"] = args.code_dir
    
    # Initialize client
    client = OllamaCode(config)
    
    # Check Ollama connection
    if not client.check_ollama_connection():
        print(f"{Colors.RED}Error: Cannot connect to Ollama at {config['ollama_endpoint']}{Colors.ENDC}")
        print("Make sure Ollama is running and accessible.")
        return
    
    # List models and exit if requested
    if args.list_models:
        models = client.get_available_models()
        if models:
            print(f"{Colors.BOLD}Available Ollama models:{Colors.ENDC}")
            for model in models:
                marker = "* " if model == config["model"] else "  "
                print(f"{marker}{model}")
        else:
            print(f"{Colors.YELLOW}No models found or couldn't retrieve model list.{Colors.ENDC}")
        return
    
    # Print welcome message
    print(f"\n{Colors.BOLD}{Colors.HEADER}🤖 OllamaCode{Colors.ENDC} - A Claude Code alternative using Ollama")
    print(f"Using model: {Colors.BOLD}{config['model']}{Colors.ENDC}")
    print(f"Bash commands: {Colors.GREEN if config.get('enable_bash', True) else Colors.RED}{'Enabled' if config.get('enable_bash', True) else 'Disabled'}{Colors.ENDC}")
    print(f"Tools: {Colors.GREEN if config.get('enable_tools', True) else Colors.RED}{'Enabled' if config.get('enable_tools', True) else 'Disabled'}{Colors.ENDC}")
    print(f"Safe mode: {Colors.GREEN if config.get('safe_mode', True) else Colors.RED}{'Enabled' if config.get('safe_mode', True) else 'Disabled'}{Colors.ENDC}")
    print(f"Auto-save code: {Colors.GREEN if config.get('auto_save_code', False) else Colors.RED}{'Enabled' if config.get('auto_save_code', False) else 'Disabled'}{Colors.ENDC}")
    print(f"Auto-run Python: {Colors.GREEN if config.get('auto_run_python', False) else Colors.RED}{'Enabled' if config.get('auto_run_python', False) else 'Disabled'}{Colors.ENDC}")
    print(f"Working directory: {config.get('working_directory')}")
    print(f"Type {Colors.YELLOW}/help{Colors.ENDC} for available commands or {Colors.YELLOW}/quit{Colors.ENDC} to exit")
    
    # Handle initial prompt if provided
    if args.prompt:
        initial_prompt = " ".join(args.prompt)
        print(f"\n{Colors.GREEN}You:{Colors.ENDC} {initial_prompt}")
        client.send_request(initial_prompt)
    
    # Main REPL loop
    last_response = ""
    while True:
        try:
            # Get user input
            prompt = input(f"\n{Colors.GREEN}You:{Colors.ENDC} ")
            
            # Handle special commands
            if prompt.strip() == "":
                continue
            elif prompt.strip() in ["/quit", "/exit", "/q"]:
                print("Goodbye! 👋")
                break
            elif prompt.strip() == "/help":
                show_help()
                continue
            elif prompt.strip() == "/clear":
                client.conversation_history = []
                print(f"{Colors.YELLOW}Conversation history cleared.{Colors.ENDC}")
                continue
            elif prompt.strip() == "/models":
                models = client.get_available_models()
                if models:
                    print(f"{Colors.BOLD}Available models:{Colors.ENDC}")
                    for model in models:
                        marker = "* " if model == config["model"] else "  "
                        print(f"{marker}{model}")
                else:
                    print(f"{Colors.YELLOW}No models found or couldn't retrieve model list.{Colors.ENDC}")
                continue
            elif prompt.strip().startswith("/model "):
                new_model = prompt.strip()[7:].strip()
                if not new_model:
                    print(f"{Colors.YELLOW}Current model: {config['model']}{Colors.ENDC}")
                    continue
                
                if not client.validate_model(new_model):
                    print(f"{Colors.RED}Error: Model '{new_model}' not found in Ollama.{Colors.ENDC}")
                    available = client.get_available_models()
                    if available:
                        print(f"Available models: {', '.join(available)}")
                    print(f"You may need to pull it first with: ollama pull {new_model}")
                    continue
                
                config["model"] = new_model
                save_config(config)
                print(f"{Colors.GREEN}Switched to model: {new_model}{Colors.ENDC}")
                continue
            elif prompt.strip() == "/run":
                if not client.last_response:
                    print(f"{Colors.YELLOW}No code blocks found in the last response.{Colors.ENDC}")
                    continue
                
                code_blocks = client.extract_code_blocks(client.last_response)
                if not code_blocks:
                    print(f"{Colors.YELLOW}No code blocks found in the last response.{Colors.ENDC}")
                    continue
                
                # Get the last code block
                language, code = code_blocks[-1]
                print(f"{Colors.BLUE}Running {language} code...{Colors.ENDC}")
                
                # Save code to temporary file and execute
                file_path = client.save_code_to_file(code, language)
                success, result = execute_code(file_path, language)
                
                if success:
                    print(f"{Colors.GREEN}Execution successful:{Colors.ENDC}")
                    print(result)
                else:
                    print(f"{Colors.RED}Execution failed:{Colors.ENDC}")
                    print(result)
                
                continue
            elif prompt.strip().startswith("/save "):
                if not client.last_response:
                    print(f"{Colors.YELLOW}No response to save.{Colors.ENDC}")
                    continue
                
                file_path = prompt.strip()[6:].strip()
                if not file_path:
                    print(f"{Colors.YELLOW}Please specify a file path.{Colors.ENDC}")
                    continue
                
                try:
                    with open(os.path.expanduser(file_path), 'w') as f:
                        f.write(client.last_response)
                    print(f"{Colors.GREEN}Response saved to {file_path}{Colors.ENDC}")
                except IOError as e:
                    print(f"{Colors.RED}Error saving file: {e}{Colors.ENDC}")
                
                continue
            elif prompt.strip() == "/config":
                print(f"{Colors.BOLD}Current configuration:{Colors.ENDC}")
                for key, value in config.items():
                    if key != "system_prompt":  # Skip long system prompt
                        print(f"  {key}: {value}")
                continue
            elif prompt.strip().startswith("/temp "):
                try:
                    temp_value = float(prompt.strip()[6:].strip())
                    if 0.0 <= temp_value <= 1.0:
                        config["temperature"] = temp_value
                        save_config(config)
                        print(f"{Colors.GREEN}Temperature set to {temp_value}{Colors.ENDC}")
                    else:
                        print(f"{Colors.YELLOW}Temperature must be between 0.0 and 1.0{Colors.ENDC}")
                except ValueError:
                    print(f"{Colors.YELLOW}Invalid temperature value{Colors.ENDC}")
                continue
            elif prompt.strip() == "/tools":
                list_tools(config)
                continue
            elif prompt.strip() == "/toggle_bash":
                config["enable_bash"] = not config.get("enable_bash", True)
                save_config(config)
                status = "enabled" if config["enable_bash"] else "disabled"
                print(f"{Colors.GREEN}Bash execution {status}.{Colors.ENDC}")
                continue
            elif prompt.strip() == "/toggle_tools":
                config["enable_tools"] = not config.get("enable_tools", True)
                save_config(config)
                status = "enabled" if config["enable_tools"] else "disabled"
                print(f"{Colors.GREEN}Tools {status}.{Colors.ENDC}")
                continue
            elif prompt.strip() == "/toggle_safe":
                config["safe_mode"] = not config.get("safe_mode", True)
                save_config(config)
                status = "enabled" if config["safe_mode"] else "disabled"
                print(f"{Colors.GREEN if config['safe_mode'] else Colors.YELLOW}Safe mode {status}.{Colors.ENDC}")
                if not config["safe_mode"]:
                    print(f"{Colors.YELLOW}Warning: Disabling safe mode removes security restrictions.{Colors.ENDC}")
                continue
            elif prompt.strip() == "/toggle_auto_save":
                config["auto_save_code"] = not config.get("auto_save_code", False)
                config["auto_extract_code"] = config["auto_save_code"] or config.get("auto_run_python", False)
                save_config(config)
                status = "enabled" if config["auto_save_code"] else "disabled"
                print(f"{Colors.GREEN}Auto-save code {status}.{Colors.ENDC}")
                continue
            elif prompt.strip() == "/toggle_auto_run":
                config["auto_run_python"] = not config.get("auto_run_python", False)
                config["auto_extract_code"] = config["auto_run_python"] or config.get("auto_save_code", False)
                save_config(config)
                status = "enabled" if config["auto_run_python"] else "disabled"
                print(f"{Colors.GREEN}Auto-run Python code {status}.{Colors.ENDC}")
                continue
            elif prompt.strip() == "/list_code":
                code_dir = config.get("code_directory", "")
                if code_dir:
                    dir_path = os.path.join(client.tools.working_dir, code_dir)
                else:
                    dir_path = client.tools.working_dir
                
                try:
                    files = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]
                    if files:
                        print(f"{Colors.BOLD}Saved code files in {dir_path}:{Colors.ENDC}")
                        for file in sorted(files):
                            ext = os.path.splitext(file)[1].lower()
                            # Highlight code files with color based on extension
                            if ext in ['.py', '.js', '.ts', '.html', '.css', '.c', '.cpp', '.java', '.go', '.rs']:
                                print(f"  {Colors.CYAN}{file}{Colors.ENDC}")
                            else:
                                print(f"  {file}")
                    else:
                        print(f"{Colors.YELLOW}No code files found in {dir_path}{Colors.ENDC}")
                except Exception as e:
                    print(f"{Colors.RED}Error listing files: {e}{Colors.ENDC}")
                continue
            elif prompt.strip() == "/workspace":
                workspace = config.get("working_directory")
                print(f"Current working directory: {workspace}")
                
                # Show directory contents
                try:
                    items = os.listdir(workspace)
                    if items:
                        print(f"\nContents ({len(items)} items):")
                        for item in sorted(items):
                            item_path = os.path.join(workspace, item)
                            if os.path.isdir(item_path):
                                print(f"  📁 {item}/")
                            else:
                                size = os.path.getsize(item_path)
                                print(f"  📄 {item} ({size} bytes)")
                    else:
                        print("\nDirectory is empty.")
                except Exception as e:
                    print(f"{Colors.RED}Error reading directory: {e}{Colors.ENDC}")
                continue
            
            # Send normal prompt to Ollama
            last_response = client.send_request(prompt)
            
        except KeyboardInterrupt:
            print("\nUse /quit or /exit to exit")
            continue
        except EOFError:
            print("\nGoodbye! 👋")
            break

if __name__ == "__main__":
    main()