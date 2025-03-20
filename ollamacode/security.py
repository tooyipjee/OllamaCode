"""
Enhanced security mechanisms for OllamaCode.
"""

import os
import re
import shlex
import subprocess
import logging
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple, Set
from pathlib import Path


class SecurityManager:
    """Manages security aspects of OllamaCode"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.safe_mode = config.get("safe_mode", True)
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize security rules
        self._init_command_rules()
        self._init_path_rules()
    
    def _init_command_rules(self):
        """Initialize command security rules"""
        # Base set of commands that are never allowed
        self.blacklisted_commands = {
            # System-destructive commands
            "rm -rf /", "rm -rf /*", "mkfs", "dd if=/dev/zero of=/dev/sda", 
            ":(){:|:&};:", "echo > /dev/sda", "mv /* /dev/null",
            
            # Privilege escalation
            "sudo", "su ", "sudo ", "pkexec", "doas",
            
            # Network attacks
            "nc -e", "ncat -e", "netcat -e",
            
            # Other dangerous commands
            "wget -O- | sh", "curl | sh", "wget -O- | bash", "curl | bash"
        }
        
        # Commands that require careful handling
        self.restricted_commands = {
            "chmod", "chown", "mount", "umount", "dd", "fdisk",
            "shutdown", "reboot", "halt", "poweroff"
        }
        
        # Additional restricted patterns (regex)
        self.restricted_patterns = [
            r">\s*/dev/",      # Writing to device files
            r">\s*/proc/",     # Writing to proc
            r">\s*/sys/",      # Writing to sys
            r"rm\s+-rf\s+[^/]", # rm -rf with argument
            r"wget\s+.+\s+\|\s+(?:sh|bash)", # Piping wget to shell
            r"curl\s+.+\s+\|\s+(?:sh|bash)"  # Piping curl to shell
        ]
    
    def _init_path_rules(self):
        """Initialize path security rules"""
        # System paths that should be read-only in safe mode
        self.read_only_paths = {
            "/etc", "/var", "/usr", "/boot", "/bin", "/sbin",
            "/lib", "/lib64", "/dev", "/proc", "/sys"
        }
        
        # Paths that should never be accessed
        self.forbidden_paths = {
            "/etc/shadow", "/etc/passwd", "/etc/sudoers",
            "/root", "/var/log/auth.log", "/var/log/secure"
        }
    
    def is_command_safe(self, command: str) -> Tuple[bool, str]:
        """Check if a command is safe to execute
        
        Args:
            command: The command to check
            
        Returns:
            Tuple of (is_safe, reason)
        """
        if not self.config.get("enable_bash", True):
            return False, "Bash execution is disabled in configuration"
            
        # Skip safety checks if safe mode is disabled
        if not self.safe_mode:
            self.logger.warning(f"Safe mode disabled, allowing command: {command}")
            return True, ""
        
        command_lower = command.lower()
        
        # Check against blacklisted commands
        for blacklisted in self.blacklisted_commands:
            if blacklisted in command_lower:
                self.logger.warning(f"Blocked blacklisted command: {command}")
                return False, f"Command contains blacklisted pattern: {blacklisted}"
        
        # Check against restricted patterns
        for pattern in self.restricted_patterns:
            if re.search(pattern, command_lower):
                self.logger.warning(f"Blocked command matching restricted pattern: {command}")
                return False, f"Command matches restricted pattern: {pattern}"
        
        # Parse command to get the executable
        try:
            cmd_parts = shlex.split(command)
            if not cmd_parts:
                return False, "Empty command"
                
            executable = cmd_parts[0]
            
            # Check against restricted commands
            if executable in self.restricted_commands:
                self.logger.warning(f"Blocked restricted command: {command}")
                return False, f"Command '{executable}' is restricted in safe mode"
                
        except Exception as e:
            return False, f"Error parsing command: {str(e)}"
        
        return True, ""
    
    def is_path_safe(self, path: str, operation: str = "read") -> Tuple[bool, str]:
        """Check if a path is safe to access
        
        Args:
            path: The path to check
            operation: The operation to perform ("read", "write", "execute")
            
        Returns:
            Tuple of (is_safe, reason)
        """
        # Skip safety checks if safe mode is disabled
        if not self.safe_mode:
            self.logger.warning(f"Safe mode disabled, allowing access to path: {path}")
            return True, ""
        
        # Normalize path
        path = os.path.abspath(os.path.expanduser(path))
        
        # Check against forbidden paths
        for forbidden in self.forbidden_paths:
            if path.startswith(forbidden) or path == forbidden:
                self.logger.warning(f"Blocked access to forbidden path: {path}")
                return False, f"Access to {forbidden} is forbidden"
        
        # Check write access to read-only paths
        if operation in ["write", "execute"] and any(path.startswith(p) for p in self.read_only_paths):
            matching_paths = [p for p in self.read_only_paths if path.startswith(p)]
            self.logger.warning(f"Blocked write access to read-only path: {path}")
            return False, f"Write access to {matching_paths[0]} is restricted in safe mode"
        
        # Check if path is within working directory
        working_dir = Path(self.config.get("working_directory", os.path.expanduser("~/ollamacode_workspace")))
        if not path.startswith(str(working_dir)) and operation in ["write", "execute"]:
            self.logger.warning(f"Blocked {operation} outside working directory: {path}")
            return False, f"Operation restricted to working directory: {working_dir}"
        
        return True, ""
    
    def sanitize_path(self, path: str, working_dir: Path) -> Tuple[Optional[Path], str]:
        """Sanitize path to prevent directory traversal attacks
        
        Args:
            path: The path to sanitize
            working_dir: The working directory
            
        Returns:
            Tuple of (sanitized_path, error_message)
            If error_message is empty, the path is safe
        """
        try:
            # Convert to absolute path
            if not os.path.isabs(path):
                path = os.path.join(working_dir, path)
            
            path = os.path.abspath(path)
            
            # Check if path is safe
            is_safe, reason = self.is_path_safe(path)
            if not is_safe:
                return None, reason
            
            return Path(path), ""
        except Exception as e:
            return None, f"Error sanitizing path: {str(e)}"
    
    def safe_web_request(self, url: str) -> Tuple[bool, str]:
        """Check if a web request is safe
        
        Args:
            url: The URL to check
            
        Returns:
            Tuple of (is_safe, reason)
        """
        # Skip safety checks if safe mode is disabled
        if not self.safe_mode:
            self.logger.warning(f"Safe mode disabled, allowing URL: {url}")
            return True, ""
        
        # Basic URL validation
        if not url.startswith(("http://", "https://")):
            return False, "URL must start with http:// or https://"
        
        try:
            # Parse the URL
            parsed_url = urllib.parse.urlparse(url)
            
            # Check for localhost and internal IPs
            hostname = parsed_url.netloc.split(':')[0].lower()
            
            # Check for localhost
            if hostname in ["localhost", "127.0.0.1", "::1"]:
                self.logger.warning(f"Blocked access to localhost URL: {url}")
                return False, "Access to localhost URLs is restricted"
            
            # Check for private IPs (simplified check)
            if (hostname.startswith("192.168.") or 
                hostname.startswith("10.") or 
                hostname.startswith("172.16.") or
                hostname.startswith("172.17.") or
                hostname.startswith("172.18.") or
                hostname.startswith("172.19.") or
                hostname.startswith("172.2") or
                hostname.startswith("172.30.") or
                hostname.startswith("172.31.")):
                self.logger.warning(f"Blocked access to private IP URL: {url}")
                return False, "Access to private IP URLs is restricted"
            
            # Check for restricted protocols
            if parsed_url.scheme in ["file", "ftp", "sftp", "smtp", "telnet"]:
                self.logger.warning(f"Blocked access to restricted protocol: {parsed_url.scheme}")
                return False, f"The {parsed_url.scheme} protocol is restricted"
                
        except Exception as e:
            return False, f"Error parsing URL: {str(e)}"
        
        return True, ""