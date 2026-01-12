"""
Iris OpenRouter Client

Cliente async para OpenRouter API - reemplazo drop-in para LMStudioClient.
Usado por los "fake nodes" que actuan como nodos pero llaman a OpenRouter.
"""

import os
import json
from typing import Optional, AsyncGenerator
import httpx
import structlog

logger = structlog.get_logger()

# Configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT = 120.0
MAX_GENERATION_TIMEOUT = 300.0

# Models conocidos con soporte de vision
VISION_MODELS = [
    "qwen/qwen-2-vl",
    "qwen/qwen2-vl",
    "google/gemini",
    "anthropic/claude-3",
    "openai/gpt-4-vision",
    "openai/gpt-4o",
]


class OpenRouterClient:
    """
    Cliente async para OpenRouter API.

    Implementa la misma interfaz que LMStudioClient para ser
    un reemplazo drop-in en los fake nodes.
    """

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT
    ):
        """
        Inicializar cliente OpenRouter.

        Args:
            model: Modelo de OpenRouter (ej: "qwen/qwen-2.5-72b-instruct")
            api_key: API key de OpenRouter (o usar OPENROUTER_API_KEY env)
            timeout: Timeout por defecto en segundos
        """
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "OpenRouterClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Inicializar el cliente HTTP."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        logger.info(
            "openrouter_client_connected",
            model=self.model,
            has_api_key=bool(self.api_key)
        )

    async def disconnect(self) -> None:
        """Cerrar el cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("openrouter_client_disconnected")

    @property
    def client(self) -> httpx.AsyncClient:
        """Obtener cliente HTTP."""
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._client

    def _headers(self) -> dict:
        """Headers para requests a OpenRouter."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://iris.network",
            "X-Title": "Iris Fake Node"
        }

    async def health_check(self) -> bool:
        """
        Verificar si OpenRouter esta accesible.

        Returns:
            True si accesible, False si no
        """
        try:
            response = await self.client.get(
                f"{OPENROUTER_BASE_URL}/models",
                headers=self._headers()
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning("openrouter_health_check_failed", error=str(e))
            return False

    async def get_loaded_model(self) -> str:
        """
        Obtener nombre del modelo configurado.

        Returns:
            Nombre del modelo
        """
        return self.model

    async def supports_vision(self) -> bool:
        """
        Verificar si el modelo soporta vision/imagenes.

        Returns:
            True si soporta vision
        """
        model_lower = self.model.lower()
        for vision_model in VISION_MODELS:
            if vision_model in model_lower:
                return True
        return False

    async def get_models(self) -> list[dict]:
        """
        Obtener lista de modelos disponibles en OpenRouter.

        Returns:
            Lista de modelos
        """
        try:
            response = await self.client.get(
                f"{OPENROUTER_BASE_URL}/models",
                headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.warning("openrouter_get_models_failed", error=str(e))
            return []

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
        Completar prompt con streaming.

        Acumula la respuesta streameada y retorna el texto completo.
        Compatible con la interfaz de LMStudioClient.

        Args:
            prompt: Prompt del usuario
            system_prompt: System prompt opcional
            temperature: Temperatura de sampling
            max_tokens: Tokens maximos a generar
            timeout: Timeout de request en segundos
            on_token: Callback llamado por cada token (chunk, count)
            images: NO SOPORTADO - Fake nodes no procesan imagenes

        Returns:
            Respuesta generada completa
        """
        # Fake nodes no soportan imagenes
        if images:
            logger.warning(
                "openrouter_fake_node_images_not_supported",
                image_count=len(images)
            )
            return "Error: Este nodo no soporta procesamiento de imagenes. Por favor, intenta de nuevo y el sistema asignara un nodo con capacidad de vision."

        # Construir messages
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

        # Payload para OpenRouter
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "max_tokens": max_tokens or 4096
        }

        request_timeout = timeout if timeout else MAX_GENERATION_TIMEOUT

        logger.debug(
            "openrouter_stream_request",
            model=self.model,
            prompt_length=len(prompt),
            timeout=request_timeout
        )

        # Acumular respuesta
        response_parts = []
        token_count = 0

        try:
            stream_timeout = httpx.Timeout(
                connect=30.0,
                read=request_timeout,
                write=30.0,
                pool=30.0
            )

            async with self.client.stream(
                "POST",
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=stream_timeout
            ) as response:
                if response.status_code >= 400:
                    error_body = await response.aread()
                    error_text = error_body.decode('utf-8', errors='replace')
                    logger.error(
                        "openrouter_api_error",
                        status_code=response.status_code,
                        error=error_text[:500]
                    )
                    raise OpenRouterError(f"OpenRouter API error {response.status_code}: {error_text[:500]}")

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # Quitar "data: " prefix
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                response_parts.append(content)
                                token_count += 1

                                # Llamar callback si existe
                                if on_token:
                                    try:
                                        on_token(content, token_count)
                                    except Exception:
                                        pass  # No romper generacion por errores del callback
                    except json.JSONDecodeError:
                        continue

            response_text = "".join(response_parts)

            logger.info(
                "openrouter_stream_complete",
                model=self.model,
                tokens_received=token_count,
                response_length=len(response_text)
            )

            return response_text

        except httpx.TimeoutException as e:
            logger.error("openrouter_timeout", error=str(e), timeout=request_timeout)
            raise OpenRouterError(f"OpenRouter timeout after {request_timeout}s")
        except httpx.HTTPStatusError as e:
            logger.error("openrouter_http_error", status=e.response.status_code, error=str(e))
            raise OpenRouterError(f"OpenRouter HTTP error: {e}")
        except Exception as e:
            logger.error("openrouter_error", error=str(e), error_type=type(e).__name__)
            raise

    async def chat_completion_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream de chat completion.

        Args:
            messages: Lista de mensajes
            model: Modelo (usa el configurado si no se especifica)
            temperature: Temperatura
            max_tokens: Tokens maximos
            timeout: Timeout

        Yields:
            Chunks de contenido
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "max_tokens": max_tokens or 4096
        }

        request_timeout = timeout if timeout else MAX_GENERATION_TIMEOUT

        stream_timeout = httpx.Timeout(
            connect=30.0,
            read=request_timeout,
            write=30.0,
            pool=30.0
        )

        async with self.client.stream(
            "POST",
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=stream_timeout
        ) as response:
            if response.status_code >= 400:
                error_body = await response.aread()
                raise OpenRouterError(f"API error {response.status_code}: {error_body[:500]}")

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                    content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue


class OpenRouterError(Exception):
    """Exception para errores de OpenRouter."""
    pass
