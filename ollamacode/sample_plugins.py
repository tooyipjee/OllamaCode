"""
Sample tool plugin for OllamaCode.

This plugin demonstrates how to create custom tools that can be loaded dynamically.
"""

import random
from typing import Dict, Any
from pathlib import Path

from ollamacode.tool_plugins import ToolPlugin


class DiceRollTool(ToolPlugin):
    """Tool for simulating dice rolls"""
    
    name = "dice_roll"
    description = "Simulate rolling dice with different sides and counts"
    
    @classmethod
    @property
    def parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "sides": {
                "type": "number",
                "description": "Number of sides on the dice (default: 6)",
                "required": False
            },
            "count": {
                "type": "number",
                "description": "Number of dice to roll (default: 1)",
                "required": False
            }
        }
    
    def execute(self, params: Dict[str, Any], working_dir: Path, safe_mode: bool) -> Dict[str, Any]:
        # Get parameters with defaults
        sides = int(params.get("sides", 6))
        count = int(params.get("count", 1))
        
        # Validate parameter ranges
        if sides < 2:
            return {"status": "error", "error": "Dice must have at least 2 sides"}
        if sides > 1000:
            return {"status": "error", "error": "Dice cannot have more than 1000 sides"}
        if count < 1:
            return {"status": "error", "error": "Must roll at least 1 die"}
        if count > 100:
            return {"status": "error", "error": "Cannot roll more than 100 dice at once"}
        
        # Roll the dice
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)
        
        # Return results
        return {
            "status": "success",
            "dice": {
                "sides": sides,
                "count": count
            },
            "rolls": rolls,
            "total": total
        }


class TextAnalysisTool(ToolPlugin):
    """Tool for analyzing text"""
    
    name = "text_analyze"
    description = "Analyze text for statistics like word count, character count, etc."
    
    @classmethod
    @property
    def parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "text": {
                "type": "string",
                "description": "Text to analyze",
                "required": True
            },
            "include_punctuation": {
                "type": "boolean",
                "description": "Whether to include punctuation in character count (default: true)",
                "required": False
            }
        }
    
    def execute(self, params: Dict[str, Any], working_dir: Path, safe_mode: bool) -> Dict[str, Any]:
        if "text" not in params:
            return {"status": "error", "error": "Missing required parameter: text"}
        
        text = params["text"]
        include_punctuation = params.get("include_punctuation", True)
        
        # Perform analysis
        words = text.split()
        word_count = len(words)
        
        # Character count
        if include_punctuation:
            char_count = len(text)
        else:
            import re
            char_count = len(re.sub(r'[^\w\s]', '', text))
        
        # Line count
        line_count = text.count('\n') + 1
        
        # Average word length
        avg_word_length = sum(len(word) for word in words) / max(1, word_count)
        
        # Word frequency
        word_freq = {}
        for word in words:
            word_lower = word.lower()
            word_freq[word_lower] = word_freq.get(word_lower, 0) + 1
        
        # Get top 10 words
        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "status": "success",
            "statistics": {
                "word_count": word_count,
                "character_count": char_count,
                "line_count": line_count,
                "average_word_length": round(avg_word_length, 2)
            },
            "top_words": dict(top_words)
        }