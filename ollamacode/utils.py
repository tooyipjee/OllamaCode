"""
Utility functions and classes for OllamaCode.
"""

import os
import re
import tempfile
import subprocess
from typing import Dict, Any, List, Optional, Tuple, Union

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

def extract_bash_commands(text: str) -> List[str]:
    """Extract bash commands from markdown code blocks"""
    bash_blocks = re.findall(r"```(?:bash|shell|sh)\n([\s\S]*?)```", text)
    return [block.strip() for block in bash_blocks]

def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Extract tool calls from markdown tool blocks"""
    import json
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

def extract_code_blocks(text: str) -> List[Tuple[str, str]]:
    """Extract code blocks with their language from markdown text"""
    pattern = r"```(\w*)\n([\s\S]*?)```"
    matches = re.findall(pattern, text)
    return [(lang.strip() if lang.strip() else "txt", code.strip()) for lang, code in matches]

def generate_filename(code: str, language: str) -> str:
    """Generate a meaningful filename based on code content"""
    import datetime
    import re
    
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

def save_code_to_file(code: str, language: str) -> str:
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