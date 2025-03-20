"""
Conversation history management for OllamaCode.
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime


def estimate_tokens(text: str) -> int:
    """Estimate token count for a given text
    
    This is a very rough estimate - approximately 4 characters per token
    For more accurate counts, a proper tokenizer would be needed
    """
    return len(text) // 4


class Message:
    """Represents a single message in the conversation"""
    
    def __init__(self, role: str, content: str, timestamp: Optional[datetime] = None):
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.token_estimate = estimate_tokens(content)
        self.importance = 1.0  # Default importance
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary format for Ollama API"""
        return {
            "role": self.role,
            "content": self.content
        }
    
    def __repr__(self) -> str:
        return f"Message({self.role}, {len(self.content)} chars, {self.token_estimate} tokens)"


class ConversationHistory:
    """Manages conversation history with smart pruning strategies"""
    
    def __init__(self, max_tokens: int = 16000, system_prompt: Optional[str] = None, logger: Optional[logging.Logger] = None):
        self.messages: List[Message] = []
        self.max_tokens = max_tokens
        self.current_token_count = 0
        self.logger = logger or logging.getLogger(__name__)
        
        # Add system prompt if provided
        if system_prompt:
            self.add_message("system", system_prompt)
    
    def add_message(self, role: str, content: str) -> Message:
        """Add a message to the conversation history"""
        message = Message(role, content)
        self.messages.append(message)
        self.current_token_count += message.token_estimate
        
        # Analyze message content to adjust importance
        self._adjust_importance(message)
        
        # Prune if needed
        if self.current_token_count > self.max_tokens:
            self._prune_history()
        
        return message
    
    def _adjust_importance(self, message: Message):
        """Adjust message importance based on content analysis"""
        content = message.content.lower()
        
        # Messages with code blocks are more important
        if "```" in content:
            message.importance = 1.5
        
        # Messages with specific important indicators
        if any(indicator in content for indicator in ["important", "remember", "note", "key"]):
            message.importance = 1.7
        
        # Long responses often contain important context
        if len(content) > 1000 and message.role == "assistant":
            message.importance = 1.3
        
        # Messages with tool/bash results are important
        if (message.role == "assistant" and 
            ("executing tool" in content or "executing bash" in content)):
            message.importance = 1.6
    
    def _prune_history(self):
        """Prune conversation history to fit within token limits
        
        Uses a smart strategy that considers message importance and position
        """
        if len(self.messages) <= 2:
            return  # Keep at least system prompt + one message
        
        # Never remove system messages
        prunable_messages = [msg for msg in self.messages if msg.role != "system"]
        if not prunable_messages:
            return
        
        # Calculate position importance - newer messages are more important
        for i, msg in enumerate(prunable_messages):
            # Position factor: 0.5 for oldest, increasing to 1.0 for newest
            position_factor = 0.5 + (0.5 * i / max(1, len(prunable_messages) - 1))
            msg.combined_score = msg.importance * position_factor
        
        # Sort by combined score (ascending)
        prunable_messages.sort(key=lambda msg: msg.combined_score)
        
        # Remove messages until we're under the token limit, starting with lowest score
        tokens_to_remove = self.current_token_count - self.max_tokens
        tokens_removed = 0
        
        self.logger.info(f"Pruning conversation history: need to remove {tokens_to_remove} tokens")
        
        for msg in prunable_messages:
            # Don't remove message if it would put us under the limit
            if tokens_removed >= tokens_to_remove:
                break
                
            # Find this message in the original list and remove it
            if msg in self.messages:
                self.messages.remove(msg)
                tokens_removed += msg.token_estimate
                self.current_token_count -= msg.token_estimate
                self.logger.debug(f"Removed message: {msg}")
        
        self.logger.info(f"Pruned {tokens_removed} tokens from conversation history")
    
    def clear(self):
        """Clear conversation history, preserving system prompt"""
        system_messages = [msg for msg in self.messages if msg.role == "system"]
        self.messages = system_messages
        self.current_token_count = sum(msg.token_estimate for msg in system_messages)
    
    def get_messages_for_api(self) -> List[Dict[str, str]]:
        """Get messages in the format required by Ollama API"""
        return [msg.to_dict() for msg in self.messages]
    
    def save_to_file(self, file_path: str):
        """Save conversation history to a file"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "importance": msg.importance
                }
                for msg in self.messages
            ]
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def load_from_file(self, file_path: str):
        """Load conversation history from a file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.messages = []
        self.current_token_count = 0
        
        for msg_data in data.get("messages", []):
            msg = Message(
                role=msg_data["role"],
                content=msg_data["content"],
                timestamp=datetime.fromisoformat(msg_data["timestamp"])
            )
            msg.importance = msg_data.get("importance", 1.0)
            self.messages.append(msg)
            self.current_token_count += msg.token_estimate