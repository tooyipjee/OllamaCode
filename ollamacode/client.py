"""
OllamaCode client for interacting with Ollama API.
"""

import os
import json
import requests
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import logging

from .conversation import ConversationHistory
from .response_processor import ResponseProcessor
from .utils import Colors, save_code_to_file
from .tools import ToolsFramework
from .bash import BashExecutor


class OllamaClient:
    """Client for interacting with Ollama API"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """Initialize the OllamaCode client with configuration"""
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize conversation history
        self.conversation = ConversationHistory(
            max_tokens=self.config.get("context_window", 16000),
            system_prompt=self.config.get("system_prompt", "")
        )
        
        # Initialize tools and bash executor
        self.tools = ToolsFramework(config)
        self.bash = BashExecutor(config)
        
        # Initialize response processor
        self.processor = ResponseProcessor(config, self.bash, self.tools)
        
        # Last response tracking
        self.last_response = ""
        
        # Set up working directory
        self.ensure_working_dir()
    
    def ensure_working_dir(self):
        """Ensure the working directory exists"""
        working_dir = Path(self.config.get("working_directory", os.path.expanduser("~/ollamacode_workspace")))
        if not working_dir.exists():
            working_dir.mkdir(parents=True)
    
    def check_ollama_connection(self) -> bool:
        """Check if Ollama server is reachable"""
        try:
            response = requests.get(f"{self.config['ollama_endpoint']}/api/tags")
            return response.status_code == 200
        except requests.RequestException as e:
            self.logger.error(f"Connection error: {e}")
            return False
    
    def get_available_models(self) -> List[str]:
        """Get list of available models from Ollama"""
        try:
            response = requests.get(f"{self.config['ollama_endpoint']}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
            else:
                self.logger.error(f"Error fetching models: HTTP {response.status_code}")
                return []
        except requests.RequestException as e:
            self.logger.error(f"Connection error: {e}")
            return []
    
    def validate_model(self, model_name: str) -> bool:
        """Check if the specified model is available in Ollama"""
        available_models = self.get_available_models()
        if not available_models:
            # If we couldn't fetch models, assume it might work
            return True
        return model_name in available_models
    
    def format_messages(self, prompt: str) -> Dict[str, Any]:
        """Format messages for the Ollama API"""
        return {
            "model": self.config["model"],
            "messages": self.conversation.get_messages_for_api(),
            "stream": True,
            "temperature": self.config["temperature"],
            "max_tokens": self.config["max_tokens"]
        }
    
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
            self.logger.warning(f"Maximum followup depth ({max_followup_depth}) reached")
            return "Follow-up limit reached. Please continue with a new prompt."
        
        if not self.check_ollama_connection():
            error_msg = f"Error: Cannot connect to Ollama at {self.config['ollama_endpoint']}"
            print(f"{Colors.RED}{error_msg}{Colors.ENDC}")
            self.logger.error(error_msg)
            print("Make sure Ollama is running and accessible.")
            sys.exit(1)
        
        # Validate that the model exists
        if not self.validate_model(self.config["model"]):
            error_msg = f"Error: Model '{self.config['model']}' not found in Ollama"
            print(f"{Colors.RED}{error_msg}{Colors.ENDC}")
            self.logger.error(error_msg)
            print(f"Available models: {', '.join(self.get_available_models())}")
            print(f"You may need to pull it first with: ollama pull {self.config['model']}")
            sys.exit(1)
        
        # Add user prompt to conversation history
        if not is_followup:
            self.conversation.add_message("user", prompt)
        
        # Format API request
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
                self.conversation.add_message("assistant", full_response)
                
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
                    self.logger.info(f"Processing commands in followup response (depth: {followup_depth})")
                    print(f"\n{Colors.YELLOW}Processing commands in followup response (depth: {followup_depth})...{Colors.ENDC}")
                
                # Process the response using the ResponseProcessor
                response_text, processed_results = self.processor.process_response(full_response)
                
                # If we have results to share, send a followup prompt
                if processed_results:
                    print(f"\n{Colors.YELLOW}Sharing command/tool results with the model...{Colors.ENDC}")
                    
                    # Generate the followup prompt
                    followup_prompt = self.processor.format_results_for_followup(processed_results)
                    
                    if followup_prompt:
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
            error_msg = f"Error communicating with Ollama: {e}"
            print(f"{Colors.RED}{error_msg}{Colors.ENDC}")
            self.logger.error(error_msg)
            sys.exit(1)
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation.clear()
        self.logger.info("Conversation history cleared")
    
    def save_history(self, file_path: str):
        """Save conversation history to a file"""
        try:
            self.conversation.save_to_file(file_path)
            self.logger.info(f"Conversation history saved to {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving conversation history: {e}")
            return False
    
    def load_history(self, file_path: str):
        """Load conversation history from a file"""
        try:
            self.conversation.load_from_file(file_path)
            self.logger.info(f"Conversation history loaded from {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error loading conversation history: {e}")
            return False
    
    def save_code_to_file(self, code: str, language: str) -> str:
        """Save code to a temporary file with appropriate extension"""
        return save_code_to_file(code, language)