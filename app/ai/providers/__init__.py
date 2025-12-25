"""LLM Provider Factory"""

from typing import Optional
import logging

from .base import BaseLLMProvider, Message, AIResponse
from .ollama import OllamaProvider
from ..config import ai_config

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating LLM providers"""

    _primary_provider: Optional[BaseLLMProvider] = None
    _fallback_provider: Optional[BaseLLMProvider] = None

    @classmethod
    def get_provider(cls, use_fallback: bool = False) -> BaseLLMProvider:
        """Get the configured LLM provider"""

        if use_fallback and cls._fallback_provider:
            return cls._fallback_provider

        if cls._primary_provider is None:
            cls._initialize_providers()

        return cls._primary_provider

    @classmethod
    def _initialize_providers(cls):
        """Initialize providers based on configuration"""

        # Primary provider
        if ai_config.provider == "ollama":
            cls._primary_provider = OllamaProvider()
        else:
            # Default to Ollama
            cls._primary_provider = OllamaProvider()

        # TODO: Add cloud fallback providers
        # if ai_config.fallback_enabled:
        #     if ai_config.openai_api_key:
        #         cls._fallback_provider = OpenAIProvider()

        logger.info(f"AI Provider initialized: {cls._primary_provider.provider_name}")

    @classmethod
    def reset(cls):
        """Reset providers (useful for testing or reconfiguration)"""
        cls._primary_provider = None
        cls._fallback_provider = None

    @classmethod
    def health_check(cls) -> dict:
        """Check health of all providers"""
        provider = cls.get_provider()

        return {
            "primary": {
                "provider": provider.provider_name,
                "healthy": provider.health_check(),
                "model": ai_config.ollama_model,
            },
            "fallback": {
                "enabled": ai_config.fallback_enabled,
                "healthy": cls._fallback_provider.health_check() if cls._fallback_provider else None,
            }
        }


def get_llm_provider() -> BaseLLMProvider:
    """Convenience function to get the LLM provider"""
    return ProviderFactory.get_provider()


__all__ = [
    'BaseLLMProvider',
    'Message',
    'AIResponse',
    'OllamaProvider',
    'ProviderFactory',
    'get_llm_provider',
]
