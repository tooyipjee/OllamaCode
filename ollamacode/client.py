"""
OllamaCode client for interacting with Ollama API.
"""

import os
import json
import requests
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from .utils import Colors, extract_bash_commands, extract_tool_calls, extract_code_blocks, generate_filename
from .tools import ToolsFramework
from .bash import BashExecutor

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
        history_file = self.config["history_file"]
        
        # If history file is not an absolute path, make it relative to the working directory
        if not os.path.isabs(history_file):
            if 'OLLAMACODE_REPO_ROOT' in os.environ:
                # If running from repo root, use that as base
                base_dir = os.environ['OLLAMACODE_REPO_ROOT']
            else:
                # Otherwise use current working directory
                base_dir = os.getcwd()
            history_path = Path(os.path.join(base_dir, history_file))
        else:
            history_path = Path(history_file)
            
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
    
    def execute_python_code(self, code: str, env_vars: Dict[str, str] = None) -> Tuple[bool, str]:
        """Execute Python code with improved environment and error handling"""
        import tempfile
        import subprocess
        import os
        
        # Create a temporary file
        fd, path = tempfile.mkstemp(suffix=".py")
        with os.fdopen(fd, 'w') as f:
            f.write(code)
        
        try:
            # Find Python executable
            from .utils import find_executable
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
            bash_commands = extract_bash_commands(response_text)
            
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
            tool_calls = extract_tool_calls(response_text)
            
            for tool_call in tool_calls:
                tool_name = tool_call["tool"]
                params = tool_call["params"]
                
                print(f"\n{Colors.YELLOW}Executing tool:{Colors.ENDC} {tool_name}")
                print(f"Parameters: {json.dumps(params, indent=2)}")
                
                # Special handling for python_run tool with code parameter
                if tool_name == "python_run" and "code" in params:
                    code = params["code"]
                    # Fix common syntax issues that models might introduce
                    import re
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
            code_blocks = extract_code_blocks(response_text)
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
                    filename = generate_filename(code, lang)
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
    
    def send_request(self, prompt: str, is_followup: bool = False, followup_depth: int = 0) -> str:
        """Send a request to the Ollama API and return the response
        
        Args:
            prompt: The message to send to the model
            is_followup: Whether this is a followup request triggered by command execution
            followup_depth: Tracks the recursion depth for follow-up messages
        """
        # Check for maximum followup depth to prevent infinite recursion
        max_followup_depth = self.config.get("max_followup_depth", 2)
        if followup_depth > max_followup_depth:
            print(f"{Colors.YELLOW}Warning: Maximum followup depth ({max_followup_depth}) reached.{Colors.ENDC}")
            return "Follow-up limit reached. Please continue with a new prompt."
        
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
            
            # Only print prefix for main responses and first-level followups
            if not is_followup or followup_depth <= 1:
                print(f"\n{Colors.CYAN}OllamaCode:{Colors.ENDC} ", end="", flush=True)
            
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            # Only print content for main responses and first-level followups
                            if not is_followup or followup_depth <= 1:
                                print(content, end="", flush=True)
                            full_response += content
                    except json.JSONDecodeError:
                        continue
            
            # Only add newline for main responses and first-level followups
            if not is_followup or followup_depth <= 1:
                print("\n")  # Add newline after response
            
            # Update conversation history (only for main conversation, not followups)
            if not is_followup:
                self.conversation_history.append({"role": "user", "content": prompt})
                self.conversation_history.append({"role": "assistant", "content": full_response})
                
                # Keep history within context window limits
                self._trim_history()
            
            # Store the last response (only update for main responses, not deep followups)
            if not is_followup or followup_depth <= 1:
                self.last_response = full_response
            
            # Process commands and tools in the response
            # Always process the first response, and followups if enabled and not too deep
            should_process = (
                not is_followup or  # Always process first response
                (
                    self.config.get("process_followup_commands", False) and  # Config enabled
                    followup_depth < max_followup_depth  # Not too deep
                )
            )
            
            if should_process:
                # Log when processing followup commands
                if is_followup:
                    print(f"\n{Colors.YELLOW}Processing commands in followup response (depth: {followup_depth})...{Colors.ENDC}")
                
                response_text, processed_results = self.process_bash_and_tools(full_response)
                
                # If we have results to share, send a followup prompt
                if processed_results:
                    followup_prompt = self.format_results_for_followup(processed_results)
                    if followup_prompt:
                        print(f"\n{Colors.YELLOW}Sharing command/tool results with the model...{Colors.ENDC}")
                        # Increment the depth for the next followup
                        followup_response = self.send_request(
                            followup_prompt, 
                            is_followup=True,
                            followup_depth=followup_depth + 1
                        )
                        
                        # Update the response to include the followup
                        # For main conversation or first-level followups only
                        if not is_followup or followup_depth <= 1:
                            full_response += "\n\n" + followup_response
                            self.last_response = full_response
            
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
        from .utils import save_code_to_file
        return save_code_to_file(code, language)