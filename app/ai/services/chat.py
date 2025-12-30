"""Main chat service for AI interactions"""

import logging
from datetime import datetime
from typing import Optional, Generator
from dataclasses import dataclass

from ..config import ai_config
from ..providers import get_llm_provider
from ..providers.base import Message
from ..context.classifier import QueryClassifier
from ..context.retriever import ContextRetriever
from ..prompts.templates import SYSTEM_PROMPT, get_prompt_template
from app.models.registry import get_models

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    """Response from chat service"""
    answer: str
    query_type: str
    context_summary: str
    confidence: float
    model_used: str
    processing_time_ms: int
    error: Optional[str] = None


class SchedulerChatService:
    """AI chat service for scheduling assistance"""

    def __init__(self, db_session):
        self.db = db_session
        self.provider = get_llm_provider()
        self.classifier = self._initialize_classifier()
        self.retriever = ContextRetriever(db_session)

        # Conversation history for follow-up context
        self.conversation_history: list = []
        self.max_history_turns: int = 5

    def _initialize_classifier(self) -> QueryClassifier:
        """Initialize classifier with known entities from database"""
        try:
            models = get_models()
            Employee = models['Employee']
            Event = models['Event']

            # Get employee names for entity extraction
            employees = self.db.query(Employee.name).filter(
                Employee.is_active == True
            ).all()
            employee_names = [e[0] for e in employees]

            # Get event names
            events = self.db.query(Event.project_name).limit(100).all()
            event_names = list(set([e[0] for e in events]))  # Deduplicate

            return QueryClassifier(
                employees=employee_names,
                events=event_names
            )
        except Exception as e:
            logger.warning(f"Could not initialize classifier with DB data: {e}")
            return QueryClassifier()

    def chat(self, user_message: str) -> ChatResponse:
        """Process a chat message and return response"""
        start_time = datetime.now()

        try:
            # Step 1: Analyze the query
            analysis = self.classifier.analyze(user_message)
            logger.info(f"Query classified as: {analysis.query_type.value}")

            # Step 2: Retrieve relevant context
            context = self.retriever.retrieve(analysis)
            context_text = context.to_prompt_context()

            # Step 3: Build the prompt
            prompt_template = get_prompt_template(analysis.query_type.value)
            user_prompt = prompt_template.format(
                context=context_text,
                question=user_message
            )

            # Step 4: Build message list
            messages = [
                Message(role="system", content=SYSTEM_PROMPT),
            ]

            # Add conversation history for context
            for hist in self.conversation_history[-self.max_history_turns:]:
                messages.append(Message(role="user", content=hist["user"]))
                messages.append(Message(role="assistant", content=hist["assistant"]))

            # Add current message
            messages.append(Message(role="user", content=user_prompt))

            # Step 5: Get LLM response
            response = self.provider.chat(
                messages=messages,
                temperature=ai_config.temperature,
                max_tokens=ai_config.max_response_tokens,
            )

            if not response.success:
                return ChatResponse(
                    answer="I encountered an error processing your request.",
                    query_type=analysis.query_type.value,
                    context_summary=f"Retrieved {len(context.employees)} employees, {len(context.events)} events",
                    confidence=0.0,
                    model_used=response.model,
                    processing_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error=response.error,
                )

            # Step 6: Update conversation history
            self.conversation_history.append({
                "user": user_message,
                "assistant": response.content,
            })

            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return ChatResponse(
                answer=response.content,
                query_type=analysis.query_type.value,
                context_summary=f"Retrieved {len(context.employees)} employees, {len(context.events)} events, {len(context.schedules)} schedules",
                confidence=analysis.confidence,
                model_used=response.model,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            logger.exception("Chat service error")
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return ChatResponse(
                answer="I'm sorry, I encountered an unexpected error. Please try again.",
                query_type="error",
                context_summary="",
                confidence=0.0,
                model_used="",
                processing_time_ms=processing_time,
                error=str(e),
            )

    def chat_stream(self, user_message: str) -> Generator[str, None, None]:
        """Stream chat response for real-time UI updates"""
        # Analyze and retrieve context
        analysis = self.classifier.analyze(user_message)
        context = self.retriever.retrieve(analysis)
        context_text = context.to_prompt_context()

        # Build prompt
        prompt_template = get_prompt_template(analysis.query_type.value)
        user_prompt = prompt_template.format(
            context=context_text,
            question=user_message
        )

        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=user_prompt),
        ]

        # Stream response
        full_response = ""
        for chunk in self.provider.chat_stream(
            messages=messages,
            temperature=ai_config.temperature,
            max_tokens=ai_config.max_response_tokens,
        ):
            full_response += chunk
            yield chunk

        # Update history after streaming completes
        self.conversation_history.append({
            "user": user_message,
            "assistant": full_response,
        })

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
