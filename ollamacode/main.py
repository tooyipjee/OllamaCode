#!/usr/bin/env python3
"""
OllamaCode: A command-line tool for delegating coding tasks to local LLMs via Ollama
Enhanced with bash integration and tools framework for agent-like capabilities.
"""

import argparse
import os
import sys
import logging
from typing import Dict, Any, List, Optional

from .config import load_config, save_config
from .client import OllamaClient
from .utils import Colors
from .commands import CommandRegistry
from .logging import setup_logging, ErrorHandler


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
    parser.add_argument("--auto-save", action="store_true", help="Automatically save code to files")
    parser.add_argument("--auto-run", action="store_true", help="Automatically run Python code")
    parser.add_argument("--code-dir", help="Subdirectory for saved code")
    parser.add_argument("--log-level", help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("--log-file", help="Log file path")
    parser.add_argument("--plugins-dir", help="Directory for tool plugins")
    parser.add_argument("--no-plugins", action="store_true", help="Disable loading of plugins")
    
    args = parser.parse_args()
    
    if args.version:
        from . import __version__
        print(f"OllamaCode v{__version__}")
        return
    
    # Load configuration
    config = load_config()
    
    # Set up logging
    log_level = args.log_level or config.get("log_level", "INFO")
    log_file = args.log_file or config.get("log_file", "")
    
    # Create a config dict for logging
    log_config = {
        "log_level": log_level,
        "log_file": log_file,
        "log_to_console": True
    }
    
    logger = setup_logging(log_config)
    error_handler = ErrorHandler(logger)
    
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
    if args.auto_save:
        config["auto_extract_code"] = True
        config["auto_save_code"] = True
    if args.auto_run:
        config["auto_extract_code"] = True
        config["auto_run_python"] = True
    if args.code_dir:
        config["code_directory"] = args.code_dir
    
    try:
        # Initialize client
        client = OllamaClient(config, logger)
        
        # Initialize command registry
        command_registry = CommandRegistry(logger)
        
        # Check Ollama connection
        if not client.check_ollama_connection():
            error_message = error_handler.handle_error(
                Exception(f"Cannot connect to Ollama at {config['ollama_endpoint']}"),
                context="connection check",
                exit_on_error=True
            )
        
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
        if config.get("claude_code_style", True):
            print(f"\n{Colors.BOLD}{Colors.HEADER}🤖 Claude Code{Colors.ENDC} (powered by Ollama)")
            print(f"Using model: {Colors.BOLD}{config['model']}{Colors.ENDC}")
            print(f"Working directory: {config.get('working_directory')}")
            print(f"Type {Colors.YELLOW}/help{Colors.ENDC} for available commands or {Colors.YELLOW}/quit{Colors.ENDC} to exit")
        else:
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
            if config.get("claude_code_style", True):
                print(f"\n{Colors.GREEN}Human:{Colors.ENDC} {initial_prompt}")
            else:
                print(f"\n{Colors.GREEN}You:{Colors.ENDC} {initial_prompt}")
            client.send_request(initial_prompt)
        
        # Main REPL loop
        while True:
            try:
                # Get user input
                if config.get("claude_code_style", True):
                    prompt = input(f"\n{Colors.GREEN}Human:{Colors.ENDC} ")
                else:
                    prompt = input(f"\n{Colors.GREEN}You:{Colors.ENDC} ")
                
                # Handle empty input
                if prompt.strip() == "":
                    continue
                
                # Check if this is a command
                if prompt.strip().startswith("/"):
                    # Execute command and check if we should continue
                    continue_repl = command_registry.execute_command(prompt.strip(), client, config)
                    if not continue_repl:
                        break
                    continue
                
                # Handle normal prompt
                client.send_request(prompt)
                
            except KeyboardInterrupt:
                print("\nUse /quit or /exit to exit")
                continue
            except EOFError:
                print("\nGoodbye! 👋")
                break
            except Exception as e:
                error_handler.handle_error(e, context="main loop")
                continue
                
    except Exception as e:
        error_handler.handle_error(e, context="initialization", exit_on_error=True)


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