# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
import os
import ujson
from string import Template
from pathlib import Path
from typing import Dict

class MessageTemplate:
    """Message template manager that loads templates from a JSON file"""
     
    def __init__(self, file_path: os.PathLike, auto_load: bool = True):
        """
        Initialize MessageTemplate instance.
        
        Args:
            file_path: Path to JSON file with message templates
            auto_load: If True, automatically load templates on initialization
        """
        self.file_path = Path(file_path)
        self.messages: Dict[str, str] = {}

        if auto_load:
            self.load()

    def load(self) -> None:
        """
        Load message templates from the configured JSON file.
        
        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file contains invalid JSON or structure
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"Message template file not found: {self.file_path}")
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = ujson.load(f)
        except ujson.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in file {self.file_path}: {e}")
        except UnicodeDecodeError as e:
            raise ValueError(f"Encoding error in file {self.file_path}: {e}")
        
        # Validate structure
        if not isinstance(data, dict):
            raise ValueError(f"JSON file must contain a dictionary, got {type(data).__name__}")
        
        # Validate all values are strings
        for key, value in data.items():
            if not isinstance(value, str):
                raise ValueError(
                    f"Template value for key '{key}' must be a string, "
                    f"got {type(value).__name__}"
                )
        
        self.messages = data


    def get_template(self, key: str) -> Template:
        if key in self.messages:
            return Template(self.messages[key])
        
        raise KeyError(f"Message template '{key}' not found")
    
    def format(self, key: str, **kwargs) -> str:
        """
        Format a message template with provided values.
        
        Args:
            key: Template key to format
            **kwargs: Values to substitute in the template
            
        Returns:
            Formatted string with substituted values
        """
        template = self.get_template(key)
        try:
            return template.substitute(**kwargs)
        except KeyError as e:
            # Fallback to safe substitution for missing variables
            missing_var = str(e).strip("'")
            return template.safe_substitute({**kwargs, missing_var: f"{{{missing_var}}}"})