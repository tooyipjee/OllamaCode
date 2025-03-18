"""
Bash command execution functionality for OllamaCode.
"""

import os
import subprocess
import time
from typing import Dict, Any
from pathlib import Path

from .utils import Colors

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