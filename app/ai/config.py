"""AI Configuration Management"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AIConfig:
    """Configuration for AI services"""

    # Feature flags
    enabled: bool = True

    # Provider settings
    provider: str = "ollama"  # ollama | openai | anthropic
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    # Cloud fallback
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    fallback_enabled: bool = False

    # Generation settings
    max_context_tokens: int = 4000
    max_response_tokens: int = 1000
    temperature: float = 0.3
    timeout_seconds: int = 60

    # RAG settings
    max_employees_in_context: int = 50
    max_events_in_context: int = 30
    max_schedules_in_context: int = 100
    context_date_range_days: int = 14  # Look ahead/behind

    @classmethod
    def from_env(cls) -> "AIConfig":
        """Load configuration from environment variables"""
        return cls(
            enabled=os.getenv("AI_ENABLED", "true").lower() == "true",
            provider=os.getenv("AI_PROVIDER", "ollama"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            fallback_enabled=os.getenv("AI_FALLBACK_ENABLED", "false").lower() == "true",
            max_context_tokens=int(os.getenv("AI_MAX_CONTEXT_TOKENS", "4000")),
            max_response_tokens=int(os.getenv("AI_MAX_RESPONSE_TOKENS", "1000")),
            temperature=float(os.getenv("AI_TEMPERATURE", "0.3")),
            timeout_seconds=int(os.getenv("AI_TIMEOUT_SECONDS", "60")),
        )


# Global config instance
ai_config = AIConfig.from_env()
