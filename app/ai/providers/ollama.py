"""Ollama LLM Provider"""

import logging
from typing import List, Generator, Optional

from .base import BaseLLMProvider, Message, AIResponse
from ..config import ai_config

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.base_url = base_url or ai_config.ollama_base_url
        self.model = model or ai_config.ollama_model
        self._client = None

    @property
    def client(self):
        """Lazy initialization of Ollama client"""
        if self._client is None:
            try:
                import ollama
                self._client = ollama.Client(host=self.base_url)
            except ImportError:
                logger.error("ollama package not installed. Run: pip install ollama")
                raise
        return self._client

    @property
    def provider_name(self) -> str:
        return "ollama"

    def health_check(self) -> bool:
        """Check if Ollama is running and model is available"""
        try:
            # List available models
            response = self.client.list()

            # Handle different response formats from ollama library versions
            model_names = []

            # Try to get models list - handle both dict and object responses
            models_data = None
            if isinstance(response, dict):
                models_data = response.get('models', [])
            elif hasattr(response, 'models'):
                models_data = response.models
            else:
                # Try to iterate directly
                models_data = response if response else []

            # Extract model names - handle both dict and object model entries
            for m in models_data:
                if isinstance(m, dict):
                    name = m.get('name', m.get('model', ''))
                elif hasattr(m, 'name'):
                    name = m.name
                elif hasattr(m, 'model'):
                    name = m.model
                else:
                    name = str(m)
                if name:
                    model_names.append(name)

            logger.debug(f"Available Ollama models: {model_names}")

            # Check if our model is available
            model_available = any(
                self.model in name or name.startswith(self.model.split(':')[0])
                for name in model_names
            )

            if not model_available:
                logger.warning(
                    f"Model {self.model} not found. Available: {model_names}"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> AIResponse:
        """Send chat completion request to Ollama"""
        try:
            # Convert messages to Ollama format
            ollama_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]

            response = self.client.chat(
                model=self.model,
                messages=ollama_messages,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                }
            )

            return AIResponse(
                content=response['message']['content'],
                model=self.model,
                provider=self.provider_name,
                tokens_used=response.get('eval_count'),
                finish_reason="stop",
            )

        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            return AIResponse(
                content="",
                model=self.model,
                provider=self.provider_name,
                error=f"Request failed: {str(e)}",
            )

    def chat_stream(
        self,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> Generator[str, None, None]:
        """Stream chat completion response"""
        try:
            ollama_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]

            stream = self.client.chat(
                model=self.model,
                messages=ollama_messages,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
                stream=True,
            )

            for chunk in stream:
                if 'message' in chunk and 'content' in chunk['message']:
                    yield chunk['message']['content']

        except Exception as e:
            logger.error(f"Ollama stream failed: {e}")
            yield f"[Error: {str(e)}]"

    def pull_model(self) -> bool:
        """Pull the model if not available"""
        try:
            logger.info(f"Pulling model {self.model}...")
            self.client.pull(self.model)
            logger.info(f"Model {self.model} pulled successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to pull model: {e}")
            return False
