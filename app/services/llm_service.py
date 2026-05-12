from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from openai import APIConnectionError, AsyncOpenAI, OpenAIError, RateLimitError

from app.core.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_openai_client: AsyncOpenAI | None = None


@dataclass(slots=True)
class ChatAnswer:
    text: str
    model_name: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMService:
    """Generate grounded answers using the configured OpenAI chat model."""

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
            logger.info("Initialized OpenAI chat client. model='%s'", settings.OPENAI_CHAT_MODEL)
        return _openai_client

    async def answer_question(
        self,
        question: str,
        context_blocks: list[str],
        conversation_history: list[tuple[str, str]] | None = None,
        model_name: str | None = None,
        user_reference: str | None = None,
    ) -> ChatAnswer:
        client = self._get_client()
        resolved_model = (model_name or settings.OPENAI_CHAT_MODEL).strip()
        if not resolved_model:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI chat model is not configured on the server",
            )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": settings.CHAT_SYSTEM_PROMPT},
        ]
        for role, content in conversation_history or []:
            if role not in {"user", "assistant"}:
                continue
            messages.append({"role": role, "content": content})

        context_text = "\n\n".join(context_blocks).strip() or "No relevant document context was retrieved."
        messages.append(
            {
                "role": "user",
                "content": (
                    "Answer the following question using the supplied context.\n\n"
                    f"Question:\n{question}\n\n"
                    f"Document Context:\n{context_text}"
                ),
            }
        )

        try:
            logger.info(
                "Requesting grounded chat completion. model='%s' history_messages=%s context_blocks=%s",
                resolved_model,
                len(conversation_history or []),
                len(context_blocks),
            )
            response = await client.chat.completions.create(
                model=resolved_model,
                messages=messages,
                temperature=settings.OPENAI_CHAT_TEMPERATURE,
                max_completion_tokens=settings.OPENAI_CHAT_MAX_COMPLETION_TOKENS,
                user=user_reference,
                timeout=settings.OPENAI_CHAT_TIMEOUT_SECONDS,
            )
            answer_text = (response.choices[0].message.content or "").strip()
            if not answer_text:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="OpenAI chat service returned an empty answer",
                )

            usage = response.usage
            return ChatAnswer(
                text=answer_text,
                model_name=response.model or resolved_model,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )
        except HTTPException:
            raise
        except RateLimitError as exc:
            logger.warning("OpenAI chat rate limit exceeded. model='%s'", resolved_model)
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
            logger.exception("OpenAI chat request failed. model='%s'", resolved_model)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OpenAI chat request failed",
            ) from exc
