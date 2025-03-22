import os
import json
import glob
import re
import subprocess
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import logging

from .security import SecurityManager
from .tools import ToolsFramework


class FunctionTools:
    """Extended tools that implement Claude Code-like functionality"""
    
    def __init__(self, tools_framework: ToolsFramework, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.tools = tools_framework
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.working_dir = Path(config.get("working_directory", os.path.expanduser("~/ollamacode_workspace")))
    
    def _sanitize_path(self, path: str) -> Path:
        """Sanitize path to prevent directory traversal attacks"""
        # Create a temporary security manager for path validation
        config = {"safe_mode": self.config.get("safe_mode", True), "working_directory": str(self.working_dir)}
        security = SecurityManager(config)
        
        path_str = path
        sanitized_path, error = security.sanitize_path(path_str, self.working_dir)
        
        if error:
            raise ValueError(error)
            
        return sanitized_path
    
    def file_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search for files using glob patterns"""
        if "pattern" not in params:
            return {"status": "error", "error": "Missing required parameter: pattern"}
        
        pattern = params["pattern"]
        search_path = params.get("path", ".")
        
        try:
            # Sanitize the search path
            sanitized_path = self._sanitize_path(search_path)
            
            # Use glob to find matching files
            full_pattern = str(sanitized_path / "**" / pattern) if "**" not in pattern else str(sanitized_path / pattern)
            matching_files = glob.glob(full_pattern, recursive=True)
            
            # Sort by modification time (newest first)
            matching_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            
            # Convert to relative paths for display
            relative_paths = [os.path.relpath(f, start=str(sanitized_path)) for f in matching_files]
            
            return {
                "status": "success",
                "pattern": pattern,
                "search_path": str(sanitized_path),
                "matches": relative_paths,
                "count": len(matching_files)
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def file_grep(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search for content in files using regular expressions"""
        if "pattern" not in params:
            return {"status": "error", "error": "Missing required parameter: pattern"}
        
        pattern = params["pattern"]
        search_path = params.get("path", ".")
        include = params.get("include", "*")
        
        try:
            # Sanitize the search path
            sanitized_path = self._sanitize_path(search_path)
            
            # Find all files that match the include pattern
            if "**" in include:
                file_pattern = str(sanitized_path / include)
            else:
                file_pattern = str(sanitized_path / "**" / include)
                
            matching_files = glob.glob(file_pattern, recursive=True)
            
            # Filter to only include regular files (not directories)
            matching_files = [f for f in matching_files if os.path.isfile(f)]
            
            # Sort by modification time (newest first)
            matching_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            
            # Search in each file for the pattern
            results = []
            pattern_regex = re.compile(pattern)
            
            for file_path in matching_files:
                try:
                    with open(file_path, 'r', errors='replace') as f:
                        content = f.read()
                        
                    if pattern_regex.search(content):
                        # Find the matching lines
                        matches = []
                        for i, line in enumerate(content.splitlines(), 1):
                            if pattern_regex.search(line):
                                matches.append({
                                    "line_number": i,
                                    "line": line
                                })
                                
                        if matches:
                            results.append({
                                "file": os.path.relpath(file_path, start=str(sanitized_path)),
                                "matches": matches[:10],  # Limit to first 10 matches per file
                                "match_count": len(matches)
                            })
                except Exception as e:
                    self.logger.warning(f"Error searching file {file_path}: {str(e)}")
                    continue
            
            return {
                "status": "success",
                "pattern": pattern,
                "search_path": str(sanitized_path),
                "include": include,
                "matches": results[:20],  # Limit to first 20 files
                "total_files_searched": len(matching_files),
                "total_files_matched": len(results)
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def edit_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Edit a file by replacing a specific string"""
        if "file_path" not in params:
            return {"status": "error", "error": "Missing required parameter: file_path"}
        if "old_string" not in params:
            return {"status": "error", "error": "Missing required parameter: old_string"}
        if "new_string" not in params:
            return {"status": "error", "error": "Missing required parameter: new_string"}
        
        file_path = params["file_path"]
        old_string = params["old_string"]
        new_string = params["new_string"]
        
        try:
            # Sanitize the file path
            sanitized_path = self._sanitize_path(file_path)
            
            # Check if we're creating a new file
            creating_new_file = not sanitized_path.exists() and old_string == ""
            
            if not creating_new_file and not sanitized_path.exists():
                return {"status": "error", "error": f"File not found: {sanitized_path}"}
            
            if not creating_new_file and not sanitized_path.is_file():
                return {"status": "error", "error": f"Not a file: {sanitized_path}"}
            
            # Create a new file
            if creating_new_file:
                sanitized_path.parent.mkdir(parents=True, exist_ok=True)
                with open(sanitized_path, 'w') as f:
                    f.write(new_string)
                    
                return {
                    "status": "success",
                    "message": f"Created new file: {sanitized_path}",
                    "path": str(sanitized_path)
                }
            
            # Edit existing file
            content = sanitized_path.read_text(errors='replace')
            
            # Check if old_string exists and is unique
            if old_string not in content:
                return {
                    "status": "error", 
                    "error": f"The specified text was not found in {sanitized_path}"
                }
                
            occurrences = content.count(old_string)
            if occurrences > 1:
                return {
                    "status": "error", 
                    "error": f"The specified text appears {occurrences} times in {sanitized_path}. Please provide a more specific text to replace."
                }
            
            # Replace the text and write back to file
            new_content = content.replace(old_string, new_string, 1)
            sanitized_path.write_text(new_content)
            
            return {
                "status": "success",
                "message": f"Successfully edited {sanitized_path}",
                "path": str(sanitized_path)
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
            
    def batch_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute multiple tools in a single batch"""
        if "invocations" not in params:
            return {"status": "error", "error": "Missing required parameter: invocations"}
        
        invocations = params["invocations"]
        if not isinstance(invocations, list):
            return {"status": "error", "error": "Parameter 'invocations' must be a list"}
        
        batch_description = params.get("description", "Batch operation")
        results = []
        
        for idx, invocation in enumerate(invocations):
            try:
                if not isinstance(invocation, dict):
                    results.append({
                        "status": "error",
                        "error": f"Invocation {idx} is not a valid object"
                    })
                    continue
                    
                tool_name = invocation.get("tool_name")
                input_params = invocation.get("input", {})
                
                if not tool_name:
                    results.append({
                        "status": "error",
                        "error": f"Missing 'tool_name' in invocation {idx}"
                    })
                    continue
                
                # Map tool names to methods
                tool_methods = {
                    "file_search": self.file_search,
                    "file_grep": self.file_grep,
                    "edit": self.edit_file,
                    "file_read": lambda p: self.tools.file_read(p),
                    "file_write": lambda p: self.tools.file_write(p),
                    "file_list": lambda p: self.tools.file_list(p),
                    "web_get": lambda p: self.tools.web_get(p),
                    "sys_info": lambda p: self.tools.sys_info(p),
                    "python_run": lambda p: self.tools.python_run(p),
                    "bash": self._execute_bash
                }
                
                if tool_name not in tool_methods:
                    results.append({
                        "status": "error",
                        "error": f"Unknown tool '{tool_name}' in invocation {idx}"
                    })
                    continue
                
                # Execute the tool
                tool_result = tool_methods[tool_name](input_params)
                results.append({
                    "tool_name": tool_name,
                    "result": tool_result
                })
                
            except Exception as e:
                results.append({
                    "status": "error",
                    "error": f"Error in invocation {idx}: {str(e)}"
                })
        
        return {
            "status": "success",
            "description": batch_description,
            "results": results,
            "count": len(results)
        }
    
    def _execute_bash(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a bash command"""
        if "command" not in params:
            return {"status": "error", "error": "Missing required parameter: command"}
        
        command = params["command"]
        timeout = params.get("timeout", 30)  # Default 30 seconds timeout
        
        # Create a temporary security manager for command validation
        config = {"safe_mode": self.config.get("safe_mode", True), "working_directory": str(self.working_dir)}
        security = SecurityManager(config)
        
        # Check if the command is safe to execute
        is_safe, reason = security.safe_bash_command(command)
        if not is_safe:
            return {"status": "error", "error": reason}
        
        try:
            # Execute the command in the working directory
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.working_dir)
            )
            
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                return {"status": "error", "error": f"Command execution timed out after {timeout} seconds"}
            
            if process.returncode == 0:
                result = {
                    "status": "success",
                    "command": command,
                    "stdout": stdout,
                    "returncode": process.returncode
                }
                
                # Print output for visibility
                if stdout:
                    print(f"\n{Colors.CYAN}Output:{Colors.ENDC}")
                    print(stdout)
                
                return result
            else:
                result = {
                    "status": "error",
                    "command": command,
                    "stderr": stderr,
                    "stdout": stdout,
                    "returncode": process.returncode,
                    "error": f"Command failed with return code {process.returncode}"
                }
                
                # Print error for visibility
                if stderr:
                    print(f"\n{Colors.RED}Error output:{Colors.ENDC}")
                    print(stderr)
                    
                return result
                
        except Exception as e:
            return {"status": "error", "error": f"Error executing bash command: {str(e)}"}            