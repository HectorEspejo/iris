"""
ClubAI LM Studio Client

Wrapper for the LM Studio OpenAI-compatible API.
"""

from typing import Optional, AsyncGenerator
import httpx
import structlog

logger = structlog.get_logger()

# Default configuration
DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_TIMEOUT = 60.0


class LMStudioClient:
    """
    Async client for LM Studio's OpenAI-compatible API.

    LM Studio exposes an API at http://localhost:1234/v1 that is
    compatible with the OpenAI API format.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._model_name: Optional[str] = None

    async def __aenter__(self) -> "LMStudioClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )
        logger.info("lmstudio_client_connected", base_url=self.base_url)

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("lmstudio_client_disconnected")

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client."""
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._client

    async def health_check(self) -> bool:
        """
        Check if LM Studio is running and responsive.

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self.client.get("/models")
            return response.status_code == 200
        except Exception as e:
            logger.warning("lmstudio_health_check_failed", error=str(e))
            return False

    async def get_models(self) -> list[dict]:
        """
        Get list of available models.

        Returns:
            List of model information dictionaries
        """
        response = await self.client.get("/models")
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])

    async def get_loaded_model(self) -> Optional[str]:
        """
        Get the currently loaded model name.

        Returns:
            Model name or None if no model loaded
        """
        if self._model_name:
            return self._model_name

        try:
            models = await self.get_models()
            if models:
                model_data = models[0]
                # LM Studio may return model info in different fields
                # Try 'id' first, then check other common fields
                model_id = model_data.get("id", "")

                # Some versions of LM Studio use different field names
                if not model_id or model_id == "local-model":
                    model_id = model_data.get("name", model_data.get("model", "local-model"))

                self._model_name = model_id
                logger.debug("loaded_model_detected", model_id=model_id, raw_data=model_data)
                return self._model_name
        except Exception as e:
            logger.warning("get_loaded_model_failed", error=str(e))

        return None

    async def get_model_details(self) -> dict:
        """
        Get detailed information about the loaded model.

        Returns:
            Dictionary with model details (id, context_length, etc.)
        """
        try:
            models = await self.get_models()
            if models:
                model_data = models[0]
                return {
                    "id": model_data.get("id", "unknown"),
                    "name": model_data.get("name", model_data.get("id", "unknown")),
                    "owned_by": model_data.get("owned_by", "local"),
                    "context_length": model_data.get("context_length", 8192),
                    "max_tokens": model_data.get("max_tokens", 4096),
                    # Additional fields that LM Studio might provide
                    "architecture": model_data.get("architecture", ""),
                    "quantization": model_data.get("quantization", ""),
                }
        except Exception as e:
            logger.warning("get_model_details_failed", error=str(e))

        return {"id": "unknown", "name": "unknown"}

    async def chat_completion(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> dict:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (optional, uses loaded model)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response

        Returns:
            Chat completion response

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        if model is None:
            model = await self.get_loaded_model() or "local-model"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        logger.debug(
            "chat_completion_request",
            model=model,
            messages_count=len(messages)
        )

        response = await self.client.post(
            "/chat/completions",
            json=payload
        )
        response.raise_for_status()

        result = response.json()
        logger.debug(
            "chat_completion_response",
            model=model,
            tokens=result.get("usage", {})
        )

        return result

    async def chat_completion_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat completion response.

        Args:
            messages: List of message dicts
            model: Model name (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Yields:
            Content chunks as they arrive
        """
        if model is None:
            model = await self.get_loaded_model() or "local-model"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with self.client.stream(
            "POST",
            "/chat/completions",
            json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    import json
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content

    async def simple_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Simple completion helper that returns just the text response.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Generated text response
        """
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        result = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        # Extract text from response
        choices = result.get("choices", [])
        if not choices:
            return ""

        message = choices[0].get("message", {})
        return message.get("content", "")


class LMStudioError(Exception):
    """Custom exception for LM Studio errors."""
    pass
