"""
Process Claude Code-style function calls in model responses
"""

import re
import json
import os
import logging
from typing import Dict, Any, List, Tuple, Optional

from .utils import Colors
from .function_tools import FunctionTools


class FunctionCallingProcessor:
    """Processes model responses to extract and execute function calls in Claude Code style"""
    
    def __init__(self, function_tools: FunctionTools, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.function_tools = function_tools
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        
    def extract_function_calls(self, response_text: str) -> List[Dict[str, Any]]:
        """Extract function calls from the response text
        
        Example function call format:
        ```tool
        {
          "tool": "file_read",
          "params": {
            "path": "path/to/file"
          }
        }
        ```
        """
        # Match code blocks with 'tool' or 'function' language identifier
        pattern = r"```(?:tool|function)\s*\n(.*?)```"
        matches = re.finditer(pattern, response_text, re.DOTALL)
        
        function_calls = []
        for match in matches:
            function_json = match.group(1).strip()
            try:
                function_data = json.loads(function_json)
                # Add the raw text for tool execution
                function_data["_raw"] = match.group(0)
                function_calls.append(function_data)
            except json.JSONDecodeError:
                self.logger.warning(f"Failed to parse function call: {function_json}")
                continue
                
        return function_calls
    
    def process_function_calls(self, response_text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Process function calls in the response
        
        Args:
            response_text: The raw response text from the model
            
        Returns:
            Tuple of (response_text_with_results, execution_results)
        """
        function_calls = self.extract_function_calls(response_text)
        if not function_calls:
            return response_text, []
            
        execution_results = []
        response_with_results = response_text
        
        for function_call in function_calls:
            raw_text = function_call.pop("_raw", None)
            function_result = self._execute_function(function_call)
            execution_results.append({
                "function_call": function_call,
                "result": function_result
            })
            
            # Replace the function call with the result
            if raw_text and self.config.get("replace_function_calls", True):
                result_text = self._format_function_result(function_call, function_result)
                response_with_results = response_with_results.replace(raw_text, result_text)
                
        return response_with_results, execution_results
    
    def _execute_function(self, function_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a function call"""
        tool_name = function_call.get("tool")
        params = function_call.get("params", {})
        
        if not tool_name:
            return {"status": "error", "error": "Missing tool name in function call"}
            
        # Print execution details
        print(f"\n{Colors.YELLOW}Executing tool:{Colors.ENDC} {tool_name}")
        print(f"Parameters: {json.dumps(params, indent=2)}")
        
        # Map tool names to function methods
        tool_methods = {
            "file_read": self.function_tools.tools.file_read,
            "file_write": self.function_tools.tools.file_write,
            "file_list": self.function_tools.tools.file_list,
            "file_search": self.function_tools.file_search,
            "file_grep": self.function_tools.file_grep,
            "edit": self.function_tools.edit_file,
            "web_get": self.function_tools.tools.web_get,
            "sys_info": self.function_tools.tools.sys_info,
            "python_run": self.function_tools.tools.python_run,
            "bash": self.function_tools._execute_bash,
            "batch": self.function_tools.batch_tool
        }
        
        if tool_name not in tool_methods:
            return {"status": "error", "error": f"Unknown tool: {tool_name}"}
            
        try:
            # Execute the tool
            result = tool_methods[tool_name](params)
            
            # Display execution result
            if result.get("status") == "success":
                print(f"{Colors.GREEN}Tool executed successfully{Colors.ENDC}")
                self._display_result_preview(result)
            else:
                print(f"{Colors.RED}Tool execution failed:{Colors.ENDC} {result.get('error', 'Unknown error')}")
                
            return result
        except Exception as e:
            error_message = f"Error executing tool '{tool_name}': {str(e)}"
            self.logger.error(error_message)
            print(f"{Colors.RED}{error_message}{Colors.ENDC}")
            return {"status": "error", "error": error_message}
    
    def _display_result_preview(self, result: Dict[str, Any]):
        """Display a preview of the function execution result"""
        display_result = result.copy()
        
        # Truncate long content
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 500:
                display_result[key] = value[:500] + "... (truncated)"
                
        print(f"Result: {json.dumps(display_result, indent=2)}")
    
    def _format_function_result(self, function_call: Dict[str, Any], result: Dict[str, Any]) -> str:
        """Format the function result to be included in the response"""
        tool_name = function_call.get("tool", "unknown")
        tool_status = result.get("status", "unknown")
        
        formatted_result = f"```tool-result\n{{\n  \"tool\": \"{tool_name}\",\n  \"status\": \"{tool_status}\""
        
        # Add specific result details based on tool
        if tool_status == "success":
            if tool_name == "file_read" and "content" in result:
                # For file_read, include truncated content
                content = result["content"]
                if len(content) > 500:
                    truncated = content[:500] + "... (truncated)"
                    formatted_result += f",\n  \"content\": \"{truncated}\""
                else:
                    formatted_result += f",\n  \"content\": \"{content}\""
                    
            elif tool_name == "file_list" and "items" in result:
                # For file_list, include item count
                formatted_result += f",\n  \"count\": {len(result['items'])}"
                
            elif tool_name == "file_search" and "matches" in result:
                # For file_search, include match count
                formatted_result += f",\n  \"count\": {len(result['matches'])}"
                
            elif tool_name == "file_grep" and "matches" in result:
                # For file_grep, include match count
                formatted_result += f",\n  \"count\": {result.get('total_files_matched', 0)}"
                
            elif tool_name == "bash" and "stdout" in result:
                # For bash, include truncated stdout
                stdout = result["stdout"]
                if len(stdout) > 500:
                    truncated = stdout[:500] + "... (truncated)"
                    formatted_result += f",\n  \"stdout\": \"{truncated}\""
                else:
                    formatted_result += f",\n  \"stdout\": \"{stdout}\""
        else:
            # Include error message for failed executions
            if "error" in result:
                formatted_result += f",\n  \"error\": \"{result['error']}\""
                
        formatted_result += "\n}\n```"
        return formatted_result
    
    def format_results_for_followup(self, execution_results: List[Dict[str, Any]]) -> str:
        """Format execution results as a followup prompt for the model"""
        if not execution_results:
            return ""
            
        followup = "\n\nHere are the results of the function calls:\n\n"
        
        for result_item in execution_results:
            function_call = result_item["function_call"]
            result = result_item["result"]
            
            tool_name = function_call.get("tool", "unknown")
            followup += f"## {tool_name} Result\n\n"
            
            # Format based on tool type
            if tool_name == "file_read":
                followup += self._format_file_read_result(result)
            elif tool_name == "file_list":
                followup += self._format_file_list_result(result)
            elif tool_name == "file_search":
                followup += self._format_file_search_result(result)
            elif tool_name == "file_grep":
                followup += self._format_file_grep_result(result)
            elif tool_name == "bash":
                followup += self._format_bash_result(result)
            elif tool_name == "python_run":
                followup += self._format_python_run_result(result)
            else:
                # Generic formatting for other tools
                followup += f"Status: {result.get('status', 'unknown')}\n\n"
                
                if result.get("status") == "success":
                    followup += "Operation completed successfully.\n\n"
                else:
                    followup += f"Error: {result.get('error', 'Unknown error')}\n\n"
                    
                # Include other relevant fields
                for key, value in result.items():
                    if key not in ["status", "error"] and not key.startswith("_"):
                        if isinstance(value, str) and len(value) > 500:
                            followup += f"{key}: {value[:500]}... (truncated)\n"
                        elif isinstance(value, (list, dict)):
                            followup += f"{key}: {json.dumps(value, indent=2)}\n"
                        else:
                            followup += f"{key}: {value}\n"
                
                followup += "\n"
        
        followup += "Please continue based on these results. What would you like to do next?\n"
        return followup
    
    def _format_file_read_result(self, result: Dict[str, Any]) -> str:
        """Format a file_read result"""
        if result.get("status") != "success":
            return f"Error: {result.get('error', 'Failed to read file')}\n\n"
            
        file_path = result.get("path", "unknown")
        content = result.get("content", "")
        
        # Try to infer language from file extension
        extension = os.path.splitext(file_path)[1] if file_path else ""
        language = ""
        
        # Map extensions to languages
        ext_to_lang = {
            ".py": "python", ".js": "javascript", ".html": "html", ".css": "css",
            ".json": "json", ".md": "markdown", ".c": "c", ".cpp": "cpp",
            ".h": "c", ".sh": "bash", ".txt": "", ".xml": "xml",
            ".yml": "yaml", ".yaml": "yaml", ".java": "java", ".rb": "ruby",
            ".php": "php", ".go": "go", ".rs": "rust", ".ts": "typescript",
        }
        language = ext_to_lang.get(extension.lower(), "")
        
        return f"File: {file_path}\n\n```{language}\n{content}\n```\n\n"
    
    def _format_file_list_result(self, result: Dict[str, Any]) -> str:
        """Format a file_list result"""
        if result.get("status") != "success":
            return f"Error: {result.get('error', 'Failed to list files')}\n\n"
            
        directory = result.get("directory", "unknown")
        items = result.get("items", [])
        
        output = f"Directory: {directory}\n\n"
        
        # Sort items - directories first, then files
        sorted_items = sorted(
            items, 
            key=lambda x: (0 if x["type"] == "directory" else 1, x["name"].lower())
        )
        
        for item in sorted_items:
            if item["type"] == "directory":
                output += f"- 📁 {item['name']}/\n"
            else:
                size_str = f" ({item['size']} bytes)" if item.get('size') is not None else ""
                output += f"- 📄 {item['name']}{size_str}\n"
        
        return output + "\n"
    
    def _format_file_search_result(self, result: Dict[str, Any]) -> str:
        """Format a file_search result"""
        if result.get("status") != "success":
            return f"Error: {result.get('error', 'Failed to search files')}\n\n"
            
        pattern = result.get("pattern", "unknown")
        search_path = result.get("search_path", "unknown")
        matches = result.get("matches", [])
        count = result.get("count", 0)
        
        output = f"Pattern: {pattern}\nPath: {search_path}\nMatches: {count}\n\n"
        
        for match in matches[:20]:  # Limit to first 20 matches
            output += f"- {match}\n"
            
        if len(matches) > 20:
            output += f"... and {len(matches) - 20} more matches\n"
            
        return output + "\n"
    
    def _format_file_grep_result(self, result: Dict[str, Any]) -> str:
        """Format a file_grep result"""
        if result.get("status") != "success":
            return f"Error: {result.get('error', 'Failed to grep files')}\n\n"
            
        pattern = result.get("pattern", "unknown")
        search_path = result.get("search_path", "unknown")
        include = result.get("include", "*")
        matches = result.get("matches", [])
        total_files_searched = result.get("total_files_searched", 0)
        total_files_matched = result.get("total_files_matched", 0)
        
        output = f"Pattern: {pattern}\n"
        output += f"Path: {search_path}\n"
        output += f"Include: {include}\n"
        output += f"Files searched: {total_files_searched}\n"
        output += f"Files with matches: {total_files_matched}\n\n"
        
        for file_match in matches[:20]:  # Limit to first 20 files
            file_path = file_match.get("file", "unknown")
            file_matches = file_match.get("matches", [])
            match_count = file_match.get("match_count", 0)
            
            output += f"File: {file_path} ({match_count} matches)\n"
            
            for line_match in file_matches[:5]:  # Limit to first 5 matches per file
                line_num = line_match.get("line_number", 0)
                line = line_match.get("line", "").strip()
                output += f"  Line {line_num}: {line}\n"
                
            if len(file_matches) > 5:
                output += f"  ... and {len(file_matches) - 5} more matches in this file\n"
                
            output += "\n"
            
        if len(matches) > 20:
            output += f"... and {len(matches) - 20} more files with matches\n\n"
            
        return output
    
    def _format_bash_result(self, result: Dict[str, Any]) -> str:
        """Format a bash result"""
        command = result.get("command", "unknown")
        output = f"Command: `{command}`\n\n"
        
        if result.get("status") == "success":
            output += "Command executed successfully.\n\n"
            
            if result.get("stdout"):
                output += f"```\n{result['stdout']}\n```\n\n"
            else:
                output += "Command produced no output.\n\n"
        else:
            output += f"Command failed with error code: {result.get('returncode', 'unknown')}\n\n"
            
            if result.get("stderr"):
                output += f"Error output:\n```\n{result['stderr']}\n```\n\n"
                
            if result.get("stdout"):
                output += f"Standard output:\n```\n{result['stdout']}\n```\n\n"
                
        return output
    
    def _format_python_run_result(self, result: Dict[str, Any]) -> str:
        """Format a python_run result"""
        script_path = result.get("script_path", "unknown")
        output = f"Script: {script_path}\n\n"
        
        if result.get("status") == "success":
            output += "Python script executed successfully.\n\n"
            
            if result.get("stdout"):
                output += f"```\n{result['stdout']}\n```\n\n"
            else:
                output += "Script produced no output.\n\n"
        else:
            output += f"Script execution failed with error code: {result.get('returncode', 'unknown')}\n\n"
            
            if result.get("stderr"):
                output += f"Error output:\n```\n{result['stderr']}\n```\n\n"
                
            if result.get("stdout"):
                output += f"Standard output:\n```\n{result['stdout']}\n```\n\n"
                
        return output