"""
Command pattern implementation for OllamaCode CLI commands.
"""

from typing import Dict, Any, Callable, List, Optional
import logging
from .utils import Colors
from .config import save_config


class Command:
    """Base class for CLI commands"""
    
    def __init__(self, name: str, help_text: str, aliases: List[str] = None):
        self.name = name
        self.help_text = help_text
        self.aliases = aliases or []
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        """Execute the command with given arguments
        
        Args:
            args: Command arguments as string
            client: OllamaCode client instance
            config: Current configuration
            
        Returns:
            bool: True if the REPL should continue, False to exit
        """
        raise NotImplementedError("Command subclasses must implement execute()")
    
    def get_help(self) -> str:
        """Get help text for the command"""
        return self.help_text


class HelpCommand(Command):
    def __init__(self, command_registry):
        super().__init__("help", "Show this help message", ["/help"])
        self.registry = command_registry
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        print(f"\n{Colors.BOLD}{Colors.HEADER}OllamaCode Help{Colors.ENDC}")
        print(f"\n{Colors.BOLD}Commands:{Colors.ENDC}")
        
        # Get all commands from registry and sort by name
        commands = sorted(self.registry.commands.values(), key=lambda cmd: cmd.name)
        
        for cmd in commands:
            aliases = ", ".join(f"{Colors.YELLOW}{a}{Colors.ENDC}" for a in cmd.aliases)
            print(f"  {aliases}")
            print(f"    {cmd.help_text}")
        
        print()
        return True


class ExitCommand(Command):
    def __init__(self):
        super().__init__("exit", "Exit OllamaCode", ["/quit", "/exit", "/q"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        print("Goodbye! 👋")
        return False


class ClearCommand(Command):
    def __init__(self):
        super().__init__("clear", "Clear the conversation history", ["/clear"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        client.clear_history()
        print(f"{Colors.YELLOW}Conversation history cleared.{Colors.ENDC}")
        return True


class ModelsCommand(Command):
    def __init__(self):
        super().__init__("models", "List available models in Ollama", ["/models"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        models = client.get_available_models()
        if models:
            print(f"{Colors.BOLD}Available models:{Colors.ENDC}")
            for model in models:
                marker = "* " if model == config["model"] else "  "
                print(f"{marker}{model}")
        else:
            print(f"{Colors.YELLOW}No models found or couldn't retrieve model list.{Colors.ENDC}")
        return True


class ModelSwitchCommand(Command):
    def __init__(self):
        super().__init__("model", "Switch to a different model", ["/model"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        new_model = args.strip()
        if not new_model:
            print(f"{Colors.YELLOW}Current model: {config['model']}{Colors.ENDC}")
            return True
        
        if not client.validate_model(new_model):
            print(f"{Colors.RED}Error: Model '{new_model}' not found in Ollama.{Colors.ENDC}")
            available = client.get_available_models()
            if available:
                print(f"Available models: {', '.join(available)}")
            print(f"You may need to pull it first with: ollama pull {new_model}")
            return True
        
        config["model"] = new_model
        save_config(config)
        print(f"{Colors.GREEN}Switched to model: {new_model}{Colors.ENDC}")
        return True


class RunCodeCommand(Command):
    def __init__(self):
        super().__init__("run", "Extract and run the last code block", ["/run"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        from .utils import extract_code_blocks, execute_code
        
        if not client.last_response:
            print(f"{Colors.YELLOW}No code blocks found in the last response.{Colors.ENDC}")
            return True
        
        code_blocks = extract_code_blocks(client.last_response)
        if not code_blocks:
            print(f"{Colors.YELLOW}No code blocks found in the last response.{Colors.ENDC}")
            return True
        
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
        
        return True


class SaveResponseCommand(Command):
    def __init__(self):
        super().__init__("save", "Save the last response to a file", ["/save"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        import os
        
        if not client.last_response:
            print(f"{Colors.YELLOW}No response to save.{Colors.ENDC}")
            return True
        
        file_path = args.strip()
        if not file_path:
            print(f"{Colors.YELLOW}Please specify a file path.{Colors.ENDC}")
            return True
        
        try:
            with open(os.path.expanduser(file_path), 'w') as f:
                f.write(client.last_response)
            print(f"{Colors.GREEN}Response saved to {file_path}{Colors.ENDC}")
        except IOError as e:
            print(f"{Colors.RED}Error saving file: {e}{Colors.ENDC}")
        
        return True


class ConfigCommand(Command):
    def __init__(self):
        super().__init__("config", "Show current configuration", ["/config"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        print(f"{Colors.BOLD}Current configuration:{Colors.ENDC}")
        for key, value in config.items():
            if key != "system_prompt":  # Skip long system prompt
                print(f"  {key}: {value}")
        return True


class TemperatureCommand(Command):
    def __init__(self):
        super().__init__("temp", "Set temperature (0.0-1.0)", ["/temp"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        try:
            temp_value = float(args.strip())
            if 0.0 <= temp_value <= 1.0:
                config["temperature"] = temp_value
                save_config(config)
                print(f"{Colors.GREEN}Temperature set to {temp_value}{Colors.ENDC}")
            else:
                print(f"{Colors.YELLOW}Temperature must be between 0.0 and 1.0{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.YELLOW}Invalid temperature value{Colors.ENDC}")
        return True


class ToolsCommand(Command):
    def __init__(self):
        super().__init__("tools", "List available tools", ["/tools"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        tools_enabled = config.get("enable_tools", True)
        bash_enabled = config.get("enable_bash", True)
        safe_mode = config.get("safe_mode", True)
        auto_save = config.get("auto_save_code", False)
        auto_run = config.get("auto_run_python", False)
        
        print(f"\n{Colors.BOLD}{Colors.HEADER}Available Tools{Colors.ENDC}")
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
        return True


class ToggleBashCommand(Command):
    def __init__(self):
        super().__init__("toggle_bash", "Enable/disable bash execution", ["/toggle_bash"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        config["enable_bash"] = not config.get("enable_bash", True)
        save_config(config)
        status = "enabled" if config["enable_bash"] else "disabled"
        print(f"{Colors.GREEN}Bash execution {status}.{Colors.ENDC}")
        return True


class ToggleToolsCommand(Command):
    def __init__(self):
        super().__init__("toggle_tools", "Enable/disable tools", ["/toggle_tools"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        config["enable_tools"] = not config.get("enable_tools", True)
        save_config(config)
        status = "enabled" if config["enable_tools"] else "disabled"
        print(f"{Colors.GREEN}Tools {status}.{Colors.ENDC}")
        return True


class ToggleSafeCommand(Command):
    def __init__(self):
        super().__init__("toggle_safe", "Enable/disable safe mode", ["/toggle_safe"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        config["safe_mode"] = not config.get("safe_mode", True)
        save_config(config)
        status = "enabled" if config["safe_mode"] else "disabled"
        print(f"{Colors.GREEN if config['safe_mode'] else Colors.YELLOW}Safe mode {status}.{Colors.ENDC}")
        if not config["safe_mode"]:
            print(f"{Colors.YELLOW}Warning: Disabling safe mode removes security restrictions.{Colors.ENDC}")
        return True


class ToggleAutoSaveCommand(Command):
    def __init__(self):
        super().__init__("toggle_auto_save", "Enable/disable automatic code saving", ["/toggle_auto_save"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        config["auto_save_code"] = not config.get("auto_save_code", False)
        config["auto_extract_code"] = config["auto_save_code"] or config.get("auto_run_python", False)
        save_config(config)
        status = "enabled" if config["auto_save_code"] else "disabled"
        print(f"{Colors.GREEN}Auto-save code {status}.{Colors.ENDC}")
        return True


class ToggleAutoRunCommand(Command):
    def __init__(self):
        super().__init__("toggle_auto_run", "Enable/disable automatic Python execution", ["/toggle_auto_run"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        config["auto_run_python"] = not config.get("auto_run_python", False)
        config["auto_extract_code"] = config["auto_run_python"] or config.get("auto_save_code", False)
        save_config(config)
        status = "enabled" if config["auto_run_python"] else "disabled"
        print(f"{Colors.GREEN}Auto-run Python code {status}.{Colors.ENDC}")
        return True


class ListCodeCommand(Command):
    def __init__(self):
        super().__init__("list_code", "List saved code files", ["/list_code"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        import os
        
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
        return True


class WorkspaceCommand(Command):
    def __init__(self):
        super().__init__("workspace", "Show working directory", ["/workspace"])
    
    def execute(self, args: str, client, config: Dict[str, Any]) -> bool:
        import os
        
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
        return True


class CommandRegistry:
    """Registry for CLI commands"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.commands = {}
        self.aliases = {}
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize with help command (which needs registry reference)
        self._help_command = HelpCommand(self)
        self.register_command(self._help_command)
        
        # Register built-in commands
        self.register_command(ExitCommand())
        self.register_command(ClearCommand())
        self.register_command(ModelsCommand())
        self.register_command(ModelSwitchCommand())
        self.register_command(RunCodeCommand())
        self.register_command(SaveResponseCommand())
        self.register_command(ConfigCommand())
        self.register_command(TemperatureCommand())
        self.register_command(ToolsCommand())
        self.register_command(ToggleBashCommand())
        self.register_command(ToggleToolsCommand())
        self.register_command(ToggleSafeCommand())
        self.register_command(ToggleAutoSaveCommand())
        self.register_command(ToggleAutoRunCommand())
        self.register_command(ListCodeCommand())
        self.register_command(WorkspaceCommand())
    
    def register_command(self, command: Command):
        """Register a new command"""
        self.commands[command.name] = command
        self.logger.debug(f"Registered command: {command.name}")
        
        # Register aliases
        for alias in command.aliases:
            self.aliases[alias] = command.name
            self.logger.debug(f"Registered alias: {alias} -> {command.name}")
    
    def get_command(self, name: str) -> Optional[Command]:
        """Get a command by name or alias"""
        # Check aliases first
        if name in self.aliases:
            name = self.aliases[name]
        
        return self.commands.get(name)
    
    def execute_command(self, command_str: str, client, config: Dict[str, Any]) -> bool:
        """Execute a command string
        
        Returns:
            bool: True if the REPL should continue, False to exit
        """
        # Parse command and arguments
        parts = command_str.strip().split(' ', 1)
        cmd_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        
        self.logger.info(f"Executing command: {cmd_name} with args: {args}")
        
        command = self.get_command(cmd_name)
        if command:
            try:
                return command.execute(args, client, config)
            except Exception as e:
                self.logger.error(f"Error executing command {cmd_name}: {e}", exc_info=True)
                print(f"{Colors.RED}Error executing command: {e}{Colors.ENDC}")
                return True
        
        print(f"{Colors.YELLOW}Unknown command: {cmd_name}. Type /help for available commands.{Colors.ENDC}")
        return True