"""
Bash command execution functionality for OllamaCode with enhanced security.
"""

import os
import subprocess
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .utils import Colors
from .security import SecurityManager


class BashExecutor:
    """Handles execution of bash commands with enhanced security"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.working_dir = Path(config.get("working_directory", os.path.expanduser("~/ollamacode_workspace")))
        self.ensure_working_dir()
        
        # Initialize security manager
        self.security = SecurityManager(config, logger)
    
    def ensure_working_dir(self):
        """Ensure the working directory exists"""
        if not self.working_dir.exists():
            self.working_dir.mkdir(parents=True)
            self.logger.info(f"Created working directory: {self.working_dir}")
    
    def execute_command(self, command: str) -> Dict[str, Any]:
        """Execute a bash command and return the result"""
        # Check if command is safe to execute
        is_safe, reason = self.security.is_command_safe(command)
        if not is_safe:
            self.logger.warning(f"Command rejected: {command} - Reason: {reason}")
            return {
                "status": "error",
                "error": f"Command not allowed: {reason}"
            }
            
        try:
            self.logger.info(f"Executing command: {command}")
            
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
                    self.logger.warning(f"Command timed out after {max_execution_time} seconds: {command}")
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
            
            result = {
                "status": "success" if process.returncode == 0 else "error",
                "command": command,
                "return_code": process.returncode,
                "stdout": stdout,
                "stderr": stderr
            }
            
            if process.returncode != 0:
                self.logger.warning(f"Command failed with return code {process.returncode}: {command}")
            else:
                self.logger.info(f"Command executed successfully: {command}")
                
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing command: {command} - {str(e)}")
            return {
                "status": "error",
                "error": f"Error executing command: {str(e)}"
            }