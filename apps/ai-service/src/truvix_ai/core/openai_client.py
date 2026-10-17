"""OpenAI API client implementation."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import SecretStr
import structlog

from truvix_ai.core.chat import ChatCompletion, ChatMessage, ImageAttachment
from truvix_ai.core.errors import ExternalServiceError

logger = structlog.get_logger(__name__)


class OpenAIChatModel:
    """Implementation of ChatModel using OpenAI's API directly."""
    
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: SecretStr,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> None:
        """Initialize the model."""
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def complete(self, messages: list[ChatMessage]) -> ChatCompletion:
        """Generate a completion using OpenAI's API."""
        encoded_messages = [self._encode(m) for m in messages]
        payload = {
            "model": self._model,
            "messages": encoded_messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        
        response = await self._post_with_retry("/chat/completions", payload)
        return self._parse(response)

    def _encode(self, message: ChatMessage) -> dict[str, Any]:
        """Encode a ChatMessage into OpenAI's format."""
        if not message.images:
            return {"role": message.role.value, "content": message.content}
            
        content: list[dict[str, Any]] = [{"type": "text", "text": message.content}]
        
        for image in message.images:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": image.as_data_url()
                }
            })
            
        return {"role": message.role.value, "content": content}

    async def _post_with_retry(
        self, endpoint: str, payload: dict[str, Any], max_attempts: int = 3
    ) -> dict[str, Any]:
        """POST to OpenAI API with exponential backoff on retryable errors."""
        url = f"{self._base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        
        retryable_statuses = {429, 500, 502, 503, 504}
        
        for attempt in range(max_attempts):
            try:
                response = await self._client.post(url, headers=headers, json=payload)
                
                if response.status_code not in retryable_statuses:
                    response.raise_for_status()
                    return response.json()
                    
                logger.warning(
                    "openai_request_failed_retryable", 
                    status=response.status_code, 
                    attempt=attempt + 1
                )
                
            except httpx.HTTPError as e:
                if attempt == max_attempts - 1:
                    logger.error("openai_request_failed_final", error=str(e))
                    raise ExternalServiceError(
                        service="openai", 
                        message="OpenAI API request failed", 
                        details={"error": str(e)}
                    ) from e
                
                logger.warning("openai_request_error", error=str(e), attempt=attempt + 1)
            
            if attempt < max_attempts - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
        raise ExternalServiceError(
            service="openai", 
            message="Max retries exceeded", 
            details={"endpoint": endpoint}
        )

    def _parse(self, response_data: dict[str, Any]) -> ChatCompletion:
        """Parse the OpenAI response into a ChatCompletion."""
        try:
            choice = response_data["choices"][0]
            message = choice["message"]
            return ChatCompletion(
                content=message.get("content", ""),
                finish_reason=choice.get("finish_reason")
            )
        except (KeyError, IndexError) as e:
            logger.error("openai_response_parsing_failed", error=str(e), data=response_data)
            raise ExternalServiceError(
                service="openai",
                message="Failed to parse API response",
                details={"error": str(e)}
            ) from e
