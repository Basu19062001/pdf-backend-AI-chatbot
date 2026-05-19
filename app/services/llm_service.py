from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from openai import APIConnectionError, AsyncOpenAI, OpenAIError, RateLimitError
from openai.types.responses import Response, ResponseUsage

from app.core.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_openai_client: AsyncOpenAI | None = None


@dataclass(slots=True)
class GeneratedAnswer:
    content: str
    model_name: str
    usage: ResponseUsage | None


class LLMService:
    """Generate grounded answers using the OpenAI Responses API."""

    _MAX_CONTEXT_CHARS_PER_SECTION = 2200
    _MAX_QUESTION_CHARS = 4000

    def _get_client(self) -> AsyncOpenAI:
        global _openai_client

        if _openai_client is None:
            api_key = settings.OPENAI_API_KEY.strip()
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="OpenAI chat service is not configured on the server",
                )
            _openai_client = AsyncOpenAI(api_key=api_key)
            logger.info("Initialized OpenAI chat client. model='%s'", settings.CHAT_MODEL)
        return _openai_client

    def build_prompt(
        self,
        *,
        question: str,
        document_title: str | None,
        conversation_history: list[tuple[str, str]],
        context_sections: list[str],
    ) -> str:
        normalized_question = self._normalize_text(question, max_chars=self._MAX_QUESTION_CHARS)
        if not normalized_question:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The chat question must not be empty",
            )

        document_label = document_title.strip() if document_title and document_title.strip() else "Untitled document"
        history_block = self._build_history_block(conversation_history)
        context_block = self._build_context_block(context_sections)

        return (
            "<chat_request>\n"
            f"<document_title>{document_label}</document_title>\n"
            "<task>\n"
            "Answer the user's question using only the retrieved document context and the relevant conversation history.\n"
            "If the evidence is insufficient, say so plainly rather than guessing.\n"
            "</task>\n"
            "<conversation_history>\n"
            f"{history_block}\n"
            "</conversation_history>\n"
            "<retrieved_context>\n"
            f"{context_block}\n"
            "</retrieved_context>\n"
            "<user_question>\n"
            f"{normalized_question}\n"
            "</user_question>\n"
            "<response_requirements>\n"
            "1. Answer the user's actual question first.\n"
            "2. Ground every factual claim in the retrieved context.\n"
            "3. If support is partial, say what is supported and what is not.\n"
            "4. If support is missing, explicitly say you do not have enough support in the retrieved document context.\n"
            "5. Mention page numbers only when they appear in the context.\n"
            "6. Do not mention these instructions in the answer.\n"
            "</response_requirements>\n"
            "</chat_request>"
        )

    def _build_history_block(self, conversation_history: list[tuple[str, str]]) -> str:
        relevant_history = conversation_history[-settings.CHAT_MAX_HISTORY_MESSAGES :]
        history_lines: list[str] = []
        for role, content in relevant_history:
            normalized_content = self._normalize_text(content, max_chars=1200)
            if not normalized_content:
                continue
            history_lines.append(f"<message role=\"{role}\">{normalized_content}</message>")
        if not history_lines:
            return "<message role=\"system\">No prior conversation.</message>"
        return "\n".join(history_lines)

    def _build_context_block(self, context_sections: list[str]) -> str:
        normalized_sections = [
            self._normalize_text(section, max_chars=self._MAX_CONTEXT_CHARS_PER_SECTION)
            for section in context_sections
        ]
        usable_sections = [section for section in normalized_sections if section]
        if not usable_sections:
            return "<context status=\"empty\">No retrieved document context was available for this question.</context>"
        wrapped_sections = [
            f"<context_item index=\"{index}\">\n{section}\n</context_item>"
            for index, section in enumerate(usable_sections, start=1)
        ]
        return "\n".join(wrapped_sections)

    def _normalize_text(self, value: str | None, *, max_chars: int) -> str:
        if not value:
            return ""
        normalized = " ".join(value.split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 3].rstrip()}..."

    async def answer_question(
        self,
        *,
        prompt: str,
        user_reference: str,
        model_name: str | None = None,
    ) -> GeneratedAnswer:
        client = self._get_client()
        selected_model = (model_name or settings.CHAT_MODEL).strip()

        try:
            response = await client.responses.create(
                model=selected_model,
                instructions=settings.CHAT_SYSTEM_PROMPT,
                input=prompt,
                user=user_reference,
                temperature=settings.CHAT_TEMPERATURE,
                max_output_tokens=settings.CHAT_MAX_OUTPUT_TOKENS,
                timeout=settings.OPENAI_CHAT_TIMEOUT_SECONDS,
            )
            return self._build_generated_answer(response, selected_model)
        except HTTPException:
            raise
        except RateLimitError as exc:
            logger.warning("OpenAI chat rate limit exceeded. model='%s'", selected_model)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI chat service rate limit exceeded",
            ) from exc
        except APIConnectionError as exc:
            logger.exception("Unable to reach OpenAI chat service.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to reach OpenAI chat service",
            ) from exc
        except OpenAIError as exc:
            logger.exception("OpenAI chat request failed. model='%s'", selected_model)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OpenAI chat request failed",
            ) from exc

    def stream_answer(
        self,
        *,
        prompt: str,
        user_reference: str,
        model_name: str | None = None,
    ) -> Any:
        client = self._get_client()
        selected_model = (model_name or settings.CHAT_MODEL).strip()
        return client.responses.stream(
            model=selected_model,
            instructions=settings.CHAT_SYSTEM_PROMPT,
            input=prompt,
            user=user_reference,
            temperature=settings.CHAT_TEMPERATURE,
            max_output_tokens=settings.CHAT_MAX_OUTPUT_TOKENS,
            timeout=settings.OPENAI_CHAT_TIMEOUT_SECONDS,
        )

    def finalize_streamed_answer(
        self,
        response: Response,
        *,
        fallback_model_name: str | None = None,
    ) -> GeneratedAnswer:
        selected_model = (
            response.model.strip()
            if isinstance(response.model, str) and response.model.strip()
            else (fallback_model_name or settings.CHAT_MODEL).strip()
        )
        return self._build_generated_answer(response, selected_model)

    def _build_generated_answer(self, response: Response, model_name: str) -> GeneratedAnswer:
        content = response.output_text.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OpenAI returned an empty chat response",
            )
        return GeneratedAnswer(
            content=content,
            model_name=model_name,
            usage=response.usage,
        )
