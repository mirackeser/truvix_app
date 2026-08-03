"""OpenAI chat completions client.

Implemented directly over the REST API with httpx rather than the vendor SDK:
the surface we use is one endpoint, and owning the HTTP layer means explicit
timeouts, explicit retry behaviour and no hidden global state.
"""

from __future__ import annotations

import asyncio
from typing import Any, Final

import httpx

from truvix.shared.ai.chat import ChatCompletion, ChatMessage
from truvix.shared.config import AISettings
from truvix.shared.errors import ExternalServiceError
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

_SERVICE_NAME: Final = "openai"
_COMPLETIONS_PATH: Final = "/chat/completions"

# Transient statuses worth one more attempt; everything else fails immediately.
_RETRYABLE_STATUSES: Final = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS: Final = 3
_BACKOFF_BASE_SECONDS: Final = 0.5


class OpenAIChatModel:
    """``ChatModel`` implementation backed by the OpenAI chat completions API."""

    def __init__(self, settings: AISettings) -> None:
        """Initialise the client.

        Args:
            settings: Provider configuration. ``api_key`` must be present;
                the container only constructs this class when it is.
        """
        if settings.api_key is None:
            raise ValueError("OpenAIChatModel requires an API key.")
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=str(settings.base_url).rstrip("/"),
            headers={"Authorization": f"Bearer {settings.api_key.get_secret_value()}"},
            timeout=httpx.Timeout(settings.request_timeout_seconds),
        )

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        json_response: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatCompletion:
        """Send a conversation to the model and return its reply.

        Args:
            messages: The conversation so far, oldest first.
            json_response: Whether to require a JSON object reply.
            max_output_tokens: Optional ceiling on the reply's length.

        Raises:
            ExternalServiceError: On network failure, provider errors that
                survive retrying, or an unparseable response body.
        """
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [
                {"role": message.role.value, "content": message.content} for message in messages
            ],
            "temperature": self._settings.temperature,
            "max_tokens": max_output_tokens or self._settings.max_output_tokens,
        }
        if json_response:
            payload["response_format"] = {"type": "json_object"}

        response = await self._post_with_retry(payload)
        return self._parse(response)

    async def aclose(self) -> None:
        """Release the underlying HTTP connection pool."""
        await self._client.aclose()

    async def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST the request, retrying transient provider failures."""
        last_error: str = "unknown"
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = await self._client.post(_COMPLETIONS_PATH, json=payload)
            except httpx.HTTPError as exc:
                last_error = f"network error: {exc}"
                _logger.warning("openai_request_failed", attempt=attempt, error=str(exc))
            else:
                if response.status_code == httpx.codes.OK:
                    body: dict[str, Any] = response.json()
                    return body
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in _RETRYABLE_STATUSES:
                    _logger.error(
                        "openai_request_rejected",
                        status_code=response.status_code,
                        body=response.text[:300],
                    )
                    break
                _logger.warning(
                    "openai_request_retryable",
                    attempt=attempt,
                    status_code=response.status_code,
                )

            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

        raise ExternalServiceError(
            "The AI provider could not be reached. Please try again shortly.",
            service=_SERVICE_NAME,
            details={"reason": last_error},
        )

    @staticmethod
    def _parse(body: dict[str, Any]) -> ChatCompletion:
        """Extract the reply and token usage from a completions response."""
        try:
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
            return ChatCompletion(
                content=content if isinstance(content, str) else "",
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ExternalServiceError(
                "The AI provider returned an unexpected response.",
                service=_SERVICE_NAME,
            ) from exc
