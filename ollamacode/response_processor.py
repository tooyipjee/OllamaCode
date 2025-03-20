"""
Response processing for OllamaCode - extracted from client.py to reduce complexity.
"""

import re
import json
import os
import logging
from typing import Dict, Any, List, Tuple, Optional

from .utils import Colors, extract_bash_commands, extract_tool_calls, extract_code_blocks, generate_filename
from .bash import BashExecutor
from .tools import ToolsFramework


class ResponseProcessor:
    """Processes LLM responses including command execution and followup generation"""
    
    def __init__(self, config: Dict[str, Any], bash: BashExecutor, tools: ToolsFramework, logger: Optional[logging.Logger] = None):
        self.config = config
        self.bash = bash
        self.tools = tools
        self.logger = logger or logging.getLogger(__name__)
        
        # Result tracking
        self.last_bash_result = None
        self.last_tool_result = None
    
    def process_response(self, response_text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Process a response including bash commands, tools, and code extraction
        
        Args:
            response_text: The raw response text from the LLM
            
        Returns:
            Tuple of (processed_text, process_results)
        """
        processed_results = []
        
        # Process bash commands
        if self.config.get("enable_bash", True):
            bash_results = self._process_bash_commands(response_text)
            processed_results.extend(bash_results)
        
        # Process tool calls
        if self.config.get("enable_tools", True):
            tool_results = self._process_tool_calls(response_text)
            processed_results.extend(tool_results)
        
        # Process code blocks
        if self.config.get("auto_extract_code", False):
            code_results = self._process_code_blocks(response_text)
            processed_results.extend(code_results)
        
        return response_text, processed_results
    
    def _process_bash_commands(self, response_text: str) -> List[Dict[str, Any]]:
        """Process bash commands in the response"""
        results = []
        bash_commands = extract_bash_commands(response_text)
        
        for command in bash_commands:
            print(f"\n{Colors.YELLOW}Executing bash command:{Colors.ENDC} {command}")
            self.logger.info(f"Executing bash command: {command}")
            
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
            
            results.append({
                "type": "bash",
                "command": command,
                "result": result
            })
        
        return results
    
    def _process_tool_calls(self, response_text: str) -> List[Dict[str, Any]]:
        """Process tool calls in the response"""
        results = []
        tool_calls = extract_tool_calls(response_text)
        
        for tool_call in tool_calls:
            tool_name = tool_call["tool"]
            params = tool_call["params"]
            
            print(f"\n{Colors.YELLOW}Executing tool:{Colors.ENDC} {tool_name}")
            print(f"Parameters: {json.dumps(params, indent=2)}")
            self.logger.info(f"Executing tool: {tool_name} with params: {json.dumps(params)}")
            
            # Special handling for python_run tool with code parameter
            if tool_name == "python_run" and "code" in params:
                params["code"] = self._preprocess_python_code(params["code"])
            
            result = self.tools.execute_tool(tool_name, params)
            self.last_tool_result = result
            
            if result["status"] == "success":
                print(f"{Colors.GREEN}Tool executed successfully{Colors.ENDC}")
                self._display_tool_result_preview(result)
            else:
                print(f"{Colors.RED}Tool execution failed:{Colors.ENDC} {result.get('error', 'Unknown error')}")
                self.logger.error(f"Tool execution failed: {result.get('error', 'Unknown error')}")
            
            results.append({
                "type": "tool",
                "tool": tool_name,
                "params": params,
                "result": result
            })
        
        return results
    
    def _preprocess_python_code(self, code: str) -> str:
        """Preprocess Python code to fix common LLM generation issues"""
        # Fix common syntax issues that models might introduce
        fixed_code = code
        # Replace common errors with correct Python syntax
        fixed_code = re.sub(r'for \* in', 'for _ in', fixed_code)  # Fix asterisk in for loop
        fixed_code = re.sub(r'([a-zA-Z0-9_]+)\*([a-zA-Z0-9_]+)', r'\1_\2', fixed_code)  # Fix variable names with asterisks
        
        # Check if code was modified
        if fixed_code != code:
            print(f"{Colors.YELLOW}Fixed potential syntax issues in Python code{Colors.ENDC}")
            self.logger.info("Fixed potential syntax issues in Python code")
        
        return fixed_code
    
    def _display_tool_result_preview(self, result: Dict[str, Any]):
        """Display a preview of tool execution result"""
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
    
    def _process_code_blocks(self, response_text: str) -> List[Dict[str, Any]]:
        """Process code blocks in the response for auto-execution or saving"""
        results = []
        code_blocks = extract_code_blocks(response_text)
        
        for lang, code in code_blocks:
            # Skip bash blocks (already handled above) and tool blocks
            if lang.lower() in ["bash", "shell", "sh", "tool"]:
                continue
                
            # Handle Python code specially
            if lang.lower() in ["python", "py"] and self.config.get("auto_run_python", False):
                python_results = self._execute_python_code(code)
                results.extend(python_results)
            
            # Save code to file if enabled
            if self.config.get("auto_save_code", False):
                save_results = self._save_code_to_file(code, lang)
                results.extend(save_results)
        
        return results
    
    def _execute_python_code(self, code: str) -> List[Dict[str, Any]]:
        """Execute Python code and return results"""
        from .utils import execute_code, save_code_to_file
        
        results = []
        print(f"\n{Colors.YELLOW}Auto-executing Python code...{Colors.ENDC}")
        self.logger.info("Auto-executing Python code")
        
        # Save code to temporary file and execute
        file_path = save_code_to_file(code, "python")
        success, result = execute_code(file_path, "python")
        
        # Show execution results
        if success:
            print(f"{Colors.GREEN}Execution successful:{Colors.ENDC}")
            print(result)
            self.logger.info("Python execution successful")
            results.append({
                "type": "code_executed",
                "language": "python",
                "success": True,
                "output": result
            })
        else:
            print(f"{Colors.RED}Execution failed:{Colors.ENDC}")
            print(result)
            self.logger.error(f"Python execution failed: {result}")
            results.append({
                "type": "code_executed",
                "language": "python",
                "success": False,
                "error": result
            })
        
        return results
    
    def _save_code_to_file(self, code: str, lang: str) -> List[Dict[str, Any]]:
        """Save code to a file"""
        results = []
        
        # Get the directory for saving code
        code_dir = self.config.get("code_directory", "")
        if code_dir:
            save_dir = os.path.join(self.tools.working_dir, code_dir)
            os.makedirs(save_dir, exist_ok=True)
        else:
            save_dir = self.tools.working_dir
        
        # Generate a filename based on first line comment or code content
        filename = generate_filename(code, lang)
        save_path = os.path.join(save_dir, filename)
        
        with open(save_path, 'w') as f:
            f.write(code)
        print(f"{Colors.GREEN}Code saved to {save_path}{Colors.ENDC}")
        self.logger.info(f"Code saved to {save_path}")
        
        results.append({
            "type": "code_saved",
            "language": lang,
            "path": save_path
        })
        
        return results
    
    def format_results_for_followup(self, processed_results: List[Dict[str, Any]]) -> str:
        """Format processed results as a followup prompt"""
        if not processed_results:
            return ""
            
        followup = "\n\nHere are the results of the commands and tools you requested:\n\n"
        
        for result in processed_results:
            if result["type"] == "bash":
                followup += self._format_bash_result(result)
            elif result["type"] == "tool":
                followup += self._format_tool_result(result)
            elif result["type"] == "code_saved":
                followup += self._format_code_saved_result(result)
            elif result["type"] == "code_executed":
                followup += self._format_code_executed_result(result)
        
        followup += "Please continue based on these results. What would you like to do next?\n"
        return followup
    
    def _format_bash_result(self, result: Dict[str, Any]) -> str:
        """Format a bash command result"""
        cmd_result = result["result"]
        output = f"## Bash Command Result: `{result['command']}`\n\n"
        
        if cmd_result["status"] == "success":
            output += "Command executed successfully.\n\n"
            if cmd_result.get("stdout"):
                output += f"**Output:**\n```\n{cmd_result['stdout']}\n```\n\n"
            else:
                output += "Command produced no output.\n\n"
        else:
            output += f"Command execution failed with error: {cmd_result.get('error', 'Unknown error')}\n\n"
            if cmd_result.get("stderr"):
                output += f"**Error output:**\n```\n{cmd_result['stderr']}\n```\n\n"
        
        return output
    
    def _format_tool_result(self, result: Dict[str, Any]) -> str:
        """Format a tool result"""
        tool_result = result["result"]
        tool_name = result["tool"]
        output = f"## Tool Result: `{tool_name}`\n\n"
        
        if tool_result["status"] == "success":
            output += "Tool executed successfully.\n\n"
            
            # Format based on tool type
            if tool_name == "file_read":
                output += self._format_file_read_result(tool_result)
            elif tool_name == "file_list":
                output += self._format_file_list_result(tool_result)
            elif tool_name == "web_get":
                output += self._format_web_get_result(tool_result)
            elif tool_name == "sys_info":
                output += self._format_sys_info_result(tool_result)
            elif tool_name == "python_run":
                output += self._format_python_run_result(tool_result)
            else:
                # Generic formatting for other tools
                output += self._format_generic_tool_result(tool_result)
        else:
            output += f"Tool execution failed with error: {tool_result.get('error', 'Unknown error')}\n\n"
        
        return output
    
    def _format_file_read_result(self, result: Dict[str, Any]) -> str:
        """Format a file_read tool result"""
        file_path = result.get("path", "unknown")
        extension = os.path.splitext(file_path)[1]
        language = ""
        
        # Try to infer language from file extension
        ext_to_lang = {
            ".py": "python", ".js": "javascript", ".html": "html", ".css": "css",
            ".json": "json", ".md": "markdown", ".c": "c", ".cpp": "cpp",
            ".h": "c", ".sh": "bash", ".txt": "", ".xml": "xml",
            ".yml": "yaml", ".yaml": "yaml", ".java": "java", ".rb": "ruby",
            ".php": "php", ".go": "go", ".rs": "rust", ".ts": "typescript",
        }
        language = ext_to_lang.get(extension.lower(), "")
        
        return f"**File content ({result.get('path')}):**\n```{language}\n{result['content']}\n```\n\n"
    
    def _format_file_list_result(self, result: Dict[str, Any]) -> str:
        """Format a file_list tool result"""
        output = f"**Directory contents of {result.get('directory')}:**\n\n"
        
        # Sort items - directories first, then files
        sorted_items = sorted(
            result["items"], 
            key=lambda x: (0 if x["type"] == "directory" else 1, x["name"].lower())
        )
        
        for item in sorted_items:
            if item["type"] == "directory":
                output += f"- 📁 {item['name']}/\n"
            else:
                size_str = f" ({item['size']} bytes)" if item['size'] is not None else ""
                output += f"- 📄 {item['name']}{size_str}\n"
        
        return output + "\n"
    
    def _format_web_get_result(self, result: Dict[str, Any]) -> str:
        """Format a web_get tool result"""
        output = f"**URL:** {result.get('url')}\n"
        output += f"**Status code:** {result.get('status_code')}\n"
        output += f"**Content type:** {result.get('content_type')}\n\n"
        
        # Add content, possibly truncated
        content = result['content']
        if len(content) > 1000:
            content = content[:1000] + "... (content truncated)"
        
        output += f"**Content:**\n```\n{content}\n```\n\n"
        return output
    
    def _format_sys_info_result(self, result: Dict[str, Any]) -> str:
        """Format a sys_info tool result"""
        info = result["info"]
        output = "**System Information:**\n\n"
        output += f"- OS: {info.get('os')} {info.get('os_release')}\n"
        output += f"- Version: {info.get('os_version')}\n"
        output += f"- Architecture: {info.get('architecture')}\n"
        output += f"- Processor: {info.get('processor')}\n"
        output += f"- Hostname: {info.get('hostname')}\n"
        output += f"- Python version: {info.get('python_version')}\n"
        output += f"- Current time: {info.get('time')}\n"
        output += f"- Working directory: {info.get('working_directory')}\n\n"
        
        if "environment" in info:
            output += "**Environment Variables:**\n\n"
            for key, value in info["environment"].items():
                output += f"- {key}={value}\n"
            output += "\n"
        
        return output
    
    def _format_python_run_result(self, result: Dict[str, Any]) -> str:
        """Format a python_run tool result"""
        output = f"**Python Script Execution:**\n\n"
        output += f"Script: {result.get('script_path', 'Unknown')}\n\n"
        
        if "status" in result and result["status"] == "success":
            output += "Execution successful.\n\n"
            
            if result.get("stdout"):
                output += f"**Output:**\n```\n{result['stdout']}\n```\n\n"
            else:
                output += "Script executed without producing any output.\n\n"
        else:
            # Handle specific Python syntax errors
            if "Python syntax error" in result.get("error", ""):
                output += f"**Syntax Error:**\n{result.get('error')}\n\n"
                
                # Add more detailed syntax error information if available
                if result.get("line") and result.get("text"):
                    output += f"Line {result.get('line')}: `{result.get('text')}`\n"
                    if result.get("offset"):
                        # Create a pointer to the error position
                        pointer = " " * (result.get("offset") - 1) + "^"
                        output += f"`{pointer}`\n\n"
                
                # If code is provided directly, show it for context
                if result.get("code"):
                    output += f"**Code with error:**\n```python\n{result['code']}\n```\n\n"
            else:
                # Regular runtime errors
                output += f"Execution failed with error code: {result.get('returncode', 'Unknown')}\n\n"
                
                if result.get("stderr"):
                    output += f"**Error:**\n```\n{result['stderr']}\n```\n\n"
                
                if result.get("stdout"):
                    output += f"**Output before error:**\n```\n{result['stdout']}\n```\n\n"
        
        return output
    
    def _format_generic_tool_result(self, result: Dict[str, Any]) -> str:
        """Format a generic tool result"""
        result_copy = result.copy()
        
        # Remove very long content fields for display
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 1000:
                result_copy[key] = f"[{len(value)} characters]"
        
        # Format as JSON
        return f"**Result:**\n```json\n{json.dumps(result_copy, indent=2)}\n```\n\n"
    
    def _format_code_saved_result(self, result: Dict[str, Any]) -> str:
        """Format a code_saved result"""
        return f"## Code Saved: `{os.path.basename(result['path'])}`\n\n" + \
               f"A {result['language']} code file was saved to: {result['path']}\n\n"
    
    def _format_code_executed_result(self, result: Dict[str, Any]) -> str:
        """Format a code_executed result"""
        output = f"## Code Execution: {result['language']}\n\n"
        
        if result['success']:
            output += "Code executed successfully.\n\n"
            if result.get('output'):
                output += f"**Output:**\n```\n{result['output']}\n```\n\n"
            else:
                output += "No output was produced.\n\n"
        else:
            output += "Code execution failed.\n\n"
            if result.get('error'):
                output += f"**Error:**\n```\n{result['error']}\n```\n\n"
        
        return output