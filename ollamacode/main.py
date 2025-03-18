#!/usr/bin/env python3
"""
OllamaCode: A command-line tool for delegating coding tasks to local LLMs via Ollama
Enhanced with bash integration and tools framework for agent-like capabilities.
"""

import argparse
import os
import sys
import json
import readline
from typing import Dict, Any, List, Optional

from .config import load_config, save_config
from .client import OllamaCode
from .utils import Colors, execute_code, extract_code_blocks

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
    """Main entry point for OllamaCode"""
    # Create the command-line parser
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
        from . import __version__
        print(f"OllamaCode v{__version__}")
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
                
                code_blocks = extract_code_blocks(client.last_response)
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
            client.send_request(prompt)
            
        except KeyboardInterrupt:
            print("\nUse /quit or /exit to exit")
            continue
        except EOFError:
            print("\nGoodbye! 👋")
            break

# Entry point when run directly (for development)
if __name__ == "__main__":
    # Add the parent directory to path for relative imports to work
    import os
    import sys
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    repo_root = os.path.abspath(os.getcwd())
    
    for path in [parent_dir, repo_root]:
        if path not in sys.path:
            sys.path.insert(0, path)
    
    # Run the main function
    main()