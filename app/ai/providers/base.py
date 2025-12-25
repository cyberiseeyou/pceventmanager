"""Abstract base class for LLM providers"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Generator
import logging

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Chat message"""
    role: str  # system | user | assistant
    content: str


@dataclass
class AIResponse:
    """Standardized AI response"""
    content: str
    model: str
    provider: str
    tokens_used: Optional[int] = None
    finish_reason: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> AIResponse:
        """Send chat completion request"""
        pass

    @abstractmethod
    def chat_stream(
        self,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> Generator[str, None, None]:
        """Stream chat completion response"""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if provider is available"""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier"""
        pass
