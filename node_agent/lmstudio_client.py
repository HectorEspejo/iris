"""
Iris LM Studio Client

Wrapper for the LM Studio OpenAI-compatible API.
"""

from typing import Optional, AsyncGenerator
import httpx
import structlog

logger = structlog.get_logger()

# Default configuration
DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_TIMEOUT = 120.0  # Default timeout for health checks, model listing, etc.
MAX_GENERATION_TIMEOUT = 300.0  # Max timeout for text generation (5 minutes)


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

    async def supports_vision(self) -> bool:
        """
        Check if the loaded model supports vision/image input.

        LM Studio API returns vision capability in several ways:
        - type: "vlm" (Vision Language Model) vs "llm"
        - vision: true/false boolean field
        - arch field containing "vl" or "vision"

        Returns:
            True if the model supports vision/image processing
        """
        try:
            models = await self.get_models()
            if not models:
                logger.warning("no_models_loaded_for_vision_check")
                return False

            model_data = models[0]
            model_id = model_data.get("id", "unknown")

            # Log all model data for debugging
            logger.info(
                "checking_vision_support",
                model_id=model_id,
                model_data=model_data
            )

            # Method 1: Check type field (vlm = Vision Language Model)
            model_type = model_data.get("type", "").lower()
            if model_type == "vlm":
                logger.info("vision_detected_via_type", model=model_id, type=model_type)
                return True

            # Method 2: Check explicit vision field
            vision_field = model_data.get("vision")
            if vision_field is True:
                logger.info("vision_detected_via_field", model=model_id)
                return True

            # Method 3: Check architecture field for vision indicators
            arch = model_data.get("arch", model_data.get("architecture", "")).lower()
            vision_archs = ["vl", "vision", "vlm", "llava", "qwen_vl", "qwen2_vl"]
            for va in vision_archs:
                if va in arch:
                    logger.info("vision_detected_via_arch", model=model_id, arch=arch)
                    return True

            # Method 4: Check capabilities array if present
            capabilities = model_data.get("capabilities", [])
            if "vision" in capabilities or "image" in capabilities:
                logger.info("vision_detected_via_capabilities", model=model_id, capabilities=capabilities)
                return True

            logger.info(
                "vision_not_detected_from_api",
                model=model_id,
                type=model_type,
                arch=arch,
                available_fields=list(model_data.keys())
            )
            return False

        except Exception as e:
            logger.warning("vision_check_failed", error=str(e))
            return False

    async def chat_completion(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        timeout: Optional[float] = None
    ) -> dict:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (optional, uses loaded model)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            timeout: Request timeout in seconds (overrides client default)

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

        # Use custom timeout if provided, otherwise use max generation timeout
        request_timeout = timeout if timeout else MAX_GENERATION_TIMEOUT

        logger.debug(
            "chat_completion_request",
            model=model,
            messages_count=len(messages),
            timeout=request_timeout
        )

        response = await self.client.post(
            "/chat/completions",
            json=payload,
            timeout=request_timeout
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
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat completion response.

        Args:
            messages: List of message dicts
            model: Model name (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            timeout: Request timeout in seconds

        Yields:
            Content chunks as they arrive
        """
        import json as json_module

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

        # For streaming, use a longer read timeout since tokens come slowly
        # but connection timeout should be quick
        stream_timeout = httpx.Timeout(
            connect=30.0,
            read=timeout if timeout else MAX_GENERATION_TIMEOUT,
            write=30.0,
            pool=30.0
        )

        logger.debug(
            "chat_completion_stream_request",
            model=model,
            messages_count=len(messages),
            timeout=timeout
        )

        async with self.client.stream(
            "POST",
            "/chat/completions",
            json=payload,
            timeout=stream_timeout
        ) as response:
            # Check for errors and log full details from LM Studio
            if response.status_code >= 400:
                error_body = await response.aread()
                error_text = error_body.decode('utf-8', errors='replace')
                logger.error(
                    "lmstudio_api_error",
                    status_code=response.status_code,
                    error_body=error_text[:2000],
                    has_images="image_url" in str(payload)
                )
                raise LMStudioError(f"LM Studio API error {response.status_code}: {error_text[:500]}")

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json_module.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json_module.JSONDecodeError:
                        continue

    async def simple_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None
    ) -> str:
        """
        Simple completion helper that returns just the text response.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            timeout: Request timeout in seconds

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
            max_tokens=max_tokens,
            timeout=timeout
        )

        # Extract text from response
        choices = result.get("choices", [])
        if not choices:
            return ""

        message = choices[0].get("message", {})
        return message.get("content", "")

    async def _vision_completion(
        self,
        prompt: str,
        files: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        on_token: Optional[callable] = None
    ) -> str:
        """
        Handle vision/multimodal completion with files (images and PDFs).

        Uses non-streaming API first as it's more reliable for vision in LM Studio.

        Args:
            prompt: User prompt
            files: List of files (mime_type, content_base64) - images and PDFs
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            timeout: Request timeout
            on_token: Optional callback for progress

        Returns:
            Generated text response
        """
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        # Build multimodal content - handle both images and PDFs
        content = [{"type": "text", "text": prompt}]

        images_count = 0
        pdfs_count = 0

        for file in files:
            mime_type = file['mime_type'].lower()

            if mime_type.startswith('image/'):
                # Handle images
                # LM Studio may have issues with webp
                if mime_type == 'image/webp':
                    mime_type = 'image/png'

                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{file['content_base64']}"
                    }
                })
                images_count += 1

            elif mime_type == 'application/pdf':
                # Handle PDFs - use file type for LM Studio
                content.append({
                    "type": "file",
                    "file": {
                        "filename": file.get('filename', 'document.pdf'),
                        "file_data": f"data:application/pdf;base64,{file['content_base64']}"
                    }
                })
                pdfs_count += 1

        messages.append({
            "role": "user",
            "content": content
        })

        logger.info(
            "vision_completion_request",
            file_count=len(files),
            images_count=images_count,
            pdfs_count=pdfs_count,
            prompt_length=len(prompt),
            mime_types=[f['mime_type'] for f in files]
        )

        # Use non-streaming request for vision (more reliable)
        model = await self.get_loaded_model() or "local-model"
        request_timeout = timeout if timeout else MAX_GENERATION_TIMEOUT

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,  # Non-streaming for vision
            "max_tokens": max_tokens or 4096
        }

        try:
            response = await self.client.post(
                "/chat/completions",
                json=payload,
                timeout=request_timeout
            )

            if response.status_code >= 400:
                error_text = response.text[:2000]
                logger.error(
                    "vision_api_error",
                    status_code=response.status_code,
                    error=error_text,
                    model=model
                )
                raise LMStudioError(f"Vision API error {response.status_code}: {error_text}")

            result = response.json()

            # Extract response
            choices = result.get("choices", [])
            if not choices:
                logger.warning("vision_no_choices_in_response")
                return ""

            response_text = choices[0].get("message", {}).get("content", "")

            # Call on_token callback with full response (simulate streaming)
            if on_token and response_text:
                # Send response in chunks to simulate streaming
                chunk_size = 20
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i + chunk_size]
                    try:
                        on_token(chunk, i // chunk_size + 1)
                    except Exception:
                        pass

            logger.info(
                "vision_completion_success",
                response_length=len(response_text),
                model=model
            )

            return response_text

        except httpx.HTTPStatusError as e:
            logger.error(
                "vision_http_error",
                status_code=e.response.status_code,
                error=str(e)
            )
            raise LMStudioError(f"Vision HTTP error: {e}")
        except Exception as e:
            logger.error(
                "vision_completion_error",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def simple_completion_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        on_token: Optional[callable] = None,
        images: Optional[list[dict]] = None
    ) -> str:
        """
        Simple completion using streaming - better for slow models.

        Accumulates the streamed response and returns the full text.
        Connection stays alive as long as tokens are being generated,
        avoiding timeout issues with slow models.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            timeout: Request timeout in seconds
            on_token: Optional callback called for each token (for progress tracking)
            images: Optional list of images for vision models. Each dict should have:
                    - mime_type: str (e.g., "image/jpeg")
                    - content_base64: str (base64 encoded image data)

        Returns:
            Generated text response (accumulated from stream)
        """
        # If files are present, use non-streaming API (more reliable for vision)
        if images:
            return await self._vision_completion(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                files=images,  # images parameter contains files (images + PDFs)
                on_token=on_token
            )

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

        # Accumulate response from stream
        response_parts = []
        token_count = 0

        async for chunk in self.chat_completion_stream(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        ):
            response_parts.append(chunk)
            token_count += 1

            # Call progress callback if provided
            if on_token:
                try:
                    on_token(chunk, token_count)
                except Exception:
                    pass  # Don't let callback errors break generation

        response = "".join(response_parts)

        logger.debug(
            "stream_completion_finished",
            tokens_received=token_count,
            response_length=len(response)
        )

        return response


class LMStudioError(Exception):
    """Custom exception for LM Studio errors."""
    pass
