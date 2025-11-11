"""
OpenRouter API Translation for Weblate
Batch translation using OpenRouter API via OpenAI SDK
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from openai import OpenAI

if TYPE_CHECKING:
    from weblate.trans.models.translation import Translation


class OpenRouterTranslator:
    def __init__(
        self,
        api_key: str,
        model: str,
        logger: "Translation | None" = None,
    ):
        """
        Initialize the OpenRouter translator using OpenAI SDK
        
        Args:
            api_key: OpenRouter API key (required)
            model: Model name to use (required)
            logger: Optional translation object or logger with log_* methods
                   If provided, uses its logging methods (e.g., log_info, log_warning)
                   Otherwise falls back to basic logging
        """
        if not api_key:
            raise ValueError("OpenRouter API key is required.")
        if not model:
            raise ValueError("Model name is required.")
        
        # Initialize OpenAI client with OpenRouter endpoint
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=60 * 20  # 20 minutes
        )
        
        self.model = model
        self.logger = logger  # Store logger (typically Translation object)
        
        # Rate limiting
        self.request_delay = 1.0  # seconds between requests
        self.max_retries = 5  # maximum number of retries for 429 errors
        
        # Message history for maintaining context across chunks
        # Format: list of dicts with "role" and "content" keys
        self.message_history: list[dict[str, str]] = []
    
    def log_debug(self, msg, *args):
        """Log debug message using logger if available, otherwise use basic logging."""
        prefixed_msg = f"OpenRouterTranslator: {msg}"
        if self.logger and hasattr(self.logger, 'log_debug'):
            return self.logger.log_debug(prefixed_msg, *args)
        from weblate.logger import LOGGER
        return LOGGER.debug(prefixed_msg, *args)
    
    def log_info(self, msg, *args):
        """Log info message using logger if available, otherwise use basic logging."""
        prefixed_msg = f"OpenRouterTranslator: {msg}"
        if self.logger and hasattr(self.logger, 'log_info'):
            return self.logger.log_info(prefixed_msg, *args)
        from weblate.logger import LOGGER
        return LOGGER.info(prefixed_msg, *args)
    
    def log_warning(self, msg, *args):
        """Log warning message using logger if available, otherwise use basic logging."""
        prefixed_msg = f"OpenRouterTranslator: {msg}"
        if self.logger and hasattr(self.logger, 'log_warning'):
            return self.logger.log_warning(prefixed_msg, *args)
        from weblate.logger import LOGGER
        return LOGGER.warning(prefixed_msg, *args)
    
    def log_error(self, msg, *args):
        """Log error message using logger if available, otherwise use basic logging."""
        prefixed_msg = f"OpenRouterTranslator: {msg}"
        if self.logger and hasattr(self.logger, 'log_error'):
            return self.logger.log_error(prefixed_msg, *args)
        from weblate.logger import LOGGER
        return LOGGER.error(prefixed_msg, *args)
    
    def translate_batch_json(
        self,
        json_string: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Translate a batch of units provided as JSON string
        
        Args:
            json_string: JSON object with unit IDs as keys and source strings as values
                        Example: {"1": "Hello", "2": "World", "3": "Welcome"}
            system_prompt: System prompt for the translation model
            user_prompt: User prompt containing the translation request and data
            
        Returns:
            JSON object with unit IDs as keys and translated strings as values
                        Example: {"1": "你好", "2": "世界", "3": "欢迎"}
        """
        
        # Build messages array with history
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add message history from previous chunks (internal to translator)
        if self.message_history:
            messages.extend(self.message_history)
        
        # Add current user prompt
        messages.append({"role": "user", "content": user_prompt})
        
        # Retry logic with exponential backoff for 429 errors
        retry_delay = self.request_delay
        consecutive_429_errors = 0
        
        for attempt in range(self.max_retries + 1):
            try:
                completion = self.client.chat.completions.create(
                    extra_headers={
                        "X-Title": "Documentation Batch Translation"
                    },
                    model=self.model,
                    messages=messages,
                    response_format={
                        'type': 'json_object'
                    },
                    temperature=0,
                    max_tokens=60000
                )
                
                response_text = completion.choices[0].message.content.strip()
                
                # Clean up response - remove markdown code fences if present
                if response_text.startswith('```'):
                    # Remove markdown code fences
                    lines = response_text.split('\n')
                    # Remove first line if it's ```json or ```
                    if lines[0].startswith('```'):
                        lines = lines[1:]
                    # Remove last line if it's ```
                    if lines and lines[-1].strip() == '```':
                        lines = lines[:-1]
                    response_text = '\n'.join(lines).strip()
                
                # Update message history with current exchange
                self.message_history.append({"role": "user", "content": user_prompt})
                self.message_history.append({"role": "assistant", "content": response_text})
                
                # Reset consecutive 429 error counter on success
                consecutive_429_errors = 0
                
                # Add delay to respect rate limits
                time.sleep(self.request_delay)
                
                return response_text
                
            except Exception as e:
                error_str = str(e)
                
                # Check if it's a 429 rate limit error
                if "429" in error_str and "rate" in error_str.lower():
                    consecutive_429_errors += 1
                    
                    if attempt < self.max_retries:
                        # Calculate exponential backoff delay
                        backoff_delay = retry_delay * (2 ** consecutive_429_errors)
                        self.log_warning(
                            "Rate limit error (429) - attempt %s/%s. Retrying in %.1f seconds...",
                            attempt + 1,
                            self.max_retries + 1,
                            backoff_delay,
                        )
                        time.sleep(backoff_delay)
                        continue
                    else:
                        self.log_warning(
                            "Max retries (%s) exceeded for 429 errors. Returning original JSON.",
                            self.max_retries,
                        )
                        return json_string  # Return original if all retries fail
                else:
                    # For non-429 errors, raise immediately
                    self.log_error("Batch translation API request failed: %s", e)
                    raise
