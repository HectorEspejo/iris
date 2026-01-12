"""
Iris Multimodal Processor

Procesa archivos PDF usando Gemini via OpenRouter.
Genera resúmenes contextuales para enriquecer los prompts enviados a los nodos.

NOTA: Las imágenes se procesan directamente en nodos con modelos multimodales
(LLaVA, Qwen-VL, etc.) y no pasan por este procesador.
"""

import os
from typing import List, Optional
import httpx
import structlog

from shared.models import FileAttachment

logger = structlog.get_logger()

# Configuration
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "google/gemini-2.5-flash")
MULTIMODAL_TIMEOUT = int(os.environ.get("MULTIMODAL_TIMEOUT", "120"))


class MultimodalProcessor:
    """
    Procesa archivos PDF usando Gemini.

    Pipeline para PDFs:
    1. Recibe PDFs adjuntos + prompt del usuario
    2. Envía a Gemini para análisis y extracción de contexto
    3. Construye prompt enriquecido para los nodos LM Studio

    NOTA: Las imágenes NO se procesan aquí. Se envían directamente
    a nodos con modelos multimodales (LLaVA, Qwen-VL, etc.)
    """

    def __init__(
        self,
        model: str = GEMINI_MODEL,
        timeout: int = MULTIMODAL_TIMEOUT
    ):
        self.model = model
        self.timeout = timeout

    async def process_pdfs(
        self,
        pdfs: List[FileAttachment],
        user_prompt: str
    ) -> str:
        """
        Procesa PDFs con Gemini y retorna prompt enriquecido.

        NOTA: Este método solo procesa PDFs. Las imágenes se envían
        directamente a nodos con modelos multimodales.

        Args:
            pdfs: Lista de archivos PDF
            user_prompt: Prompt original del usuario

        Returns:
            Prompt enriquecido con el contexto extraído de los PDFs
        """
        if not pdfs:
            return user_prompt

        # Filtrar solo PDFs
        pdf_files = [f for f in pdfs if f.is_pdf]
        if not pdf_files:
            return user_prompt

        if not OPENROUTER_API_KEY:
            logger.warning("openrouter_api_key_not_set")
            return self._fallback_prompt(pdf_files, user_prompt)

        logger.info(
            "processing_pdf_files",
            file_count=len(pdf_files),
            total_size_mb=sum(f.size_bytes for f in pdf_files) / 1024 / 1024,
            model=self.model
        )

        try:
            # Construir contenido para Gemini (solo PDFs)
            content_parts = self._build_content_parts(pdf_files, user_prompt)

            # Enviar a Gemini via OpenRouter
            gemini_response = await self._call_gemini(content_parts)

            # Construir prompt enriquecido
            enriched_prompt = self._build_enriched_prompt(
                user_prompt,
                gemini_response,
                pdf_files
            )

            logger.info(
                "pdf_processing_complete",
                response_length=len(gemini_response),
                enriched_prompt_length=len(enriched_prompt)
            )

            return enriched_prompt

        except Exception as e:
            logger.error("pdf_processing_error", error=str(e))
            # Fallback: retornar prompt indicando que hay archivos
            return self._fallback_prompt(pdf_files, user_prompt)

    def _build_content_parts(
        self,
        pdfs: List[FileAttachment],
        user_prompt: str
    ) -> List[dict]:
        """Construye las partes del contenido para Gemini (solo PDFs)."""

        content_parts = []

        # Instrucción para Gemini
        analysis_prompt = f"""Analiza los siguientes documentos PDF en relación a esta consulta del usuario:

CONSULTA DEL USUARIO: {user_prompt}

INSTRUCCIONES:
1. Examina cada documento PDF cuidadosamente
2. Extrae la información relevante para responder la consulta
3. Proporciona un resumen estructurado del contenido
4. Identifica datos clave, cifras, conceptos importantes
5. Extrae el texto y estructura principales
6. NO respondas la pregunta directamente, solo proporciona el contexto extraído

FORMATO DE RESPUESTA:
## Análisis del Contenido
[Resumen del contenido de los documentos]

## Información Clave Extraída
[Datos, cifras y conceptos importantes]

## Contexto Relevante para la Consulta
[Información específica que ayuda a responder la consulta del usuario]"""

        content_parts.append({"type": "text", "text": analysis_prompt})

        # Agregar PDFs
        for pdf in pdfs:
            if pdf.is_pdf:
                content_parts.append({
                    "type": "file",
                    "file": {
                        "filename": pdf.filename,
                        "file_data": f"data:application/pdf;base64,{pdf.content_base64}"
                    }
                })
                logger.debug(
                    "added_pdf_to_request",
                    filename=pdf.filename,
                    size_kb=pdf.size_bytes / 1024
                )

        return content_parts

    async def _call_gemini(self, content_parts: List[dict]) -> str:
        """Llama a Gemini via OpenRouter API."""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": content_parts
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.3,
            "plugins": [
                {
                    "id": "file-parser",
                    "pdf": {"engine": "native"}
                }
            ]
        }

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://iris.network",
            "X-Title": "Iris Multimodal Processor"
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            logger.debug(
                "calling_gemini_api",
                model=self.model,
                content_parts_count=len(content_parts)
            )

            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                json=payload,
                headers=headers
            )

            if response.status_code != 200:
                error_text = response.text[:500]
                logger.error(
                    "gemini_api_error",
                    status_code=response.status_code,
                    response=error_text
                )
                raise Exception(
                    f"Gemini API error ({response.status_code}): {error_text}"
                )

            data = response.json()

            # Extraer respuesta
            choices = data.get("choices", [])
            if not choices:
                raise Exception("No choices in Gemini response")

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise Exception("Empty content in Gemini response")

            # Log usage stats if available
            usage = data.get("usage", {})
            if usage:
                logger.info(
                    "gemini_usage",
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens")
                )

            return content

    def _build_enriched_prompt(
        self,
        user_prompt: str,
        gemini_response: str,
        files: List[FileAttachment]
    ) -> str:
        """Construye el prompt enriquecido para el nodo."""

        # Lista de archivos procesados
        file_list = "\n".join([
            f"- {f.filename} ({f.mime_type}, {f.size_bytes / 1024:.1f}KB)"
            for f in files
        ])

        enriched_prompt = f"""El usuario ha proporcionado archivos adjuntos que han sido analizados por un modelo de visión.

## Archivos Adjuntos
{file_list}

## Consulta Original del Usuario
{user_prompt}

## Contexto Extraído de los Archivos
{gemini_response}

## Tu Tarea
Basándote en el contexto extraído de los archivos, responde la consulta del usuario de forma completa y precisa. Utiliza la información del análisis para fundamentar tu respuesta. Si el contexto no contiene información suficiente para responder, indícalo claramente."""

        return enriched_prompt

    def _fallback_prompt(
        self,
        files: List[FileAttachment],
        user_prompt: str
    ) -> str:
        """Prompt de fallback cuando Gemini no está disponible."""

        file_list = "\n".join([
            f"- {f.filename} ({f.mime_type})"
            for f in files
        ])

        return f"""El usuario ha adjuntado los siguientes archivos:
{file_list}

Sin embargo, no fue posible procesarlos en este momento.

Consulta del usuario: {user_prompt}

Por favor, indica al usuario que el procesamiento de archivos no está disponible temporalmente y que puede intentar de nuevo más tarde o proporcionar la información relevante en texto."""


# Instancia global del procesador
multimodal_processor = MultimodalProcessor()
