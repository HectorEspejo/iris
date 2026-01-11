"""
Iris Task Difficulty Classifier

Classifies tasks using:
1. OpenRouter API with fast LLM (primary)
2. Local keyword-based classification (fallback)
"""

import asyncio
import os
import re
import httpx
from typing import Optional, TYPE_CHECKING
import structlog

from shared.models import TaskDifficulty

if TYPE_CHECKING:
    from .node_registry import NodeRegistry
    from .crypto import CoordinatorCrypto

logger = structlog.get_logger()

# OpenRouter configuration
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openai/gpt-5-nano"

# Classification constants
CLASSIFICATION_TIMEOUT = 10  # seconds
CLASSIFICATION_PROMPT_TEMPLATE = """Classify the following user request into exactly one difficulty level.

SIMPLE (basic questions, quick answers):
- Definitions: "What is X?"
- Translations: "Translate X to Y"
- Yes/no questions, factual lookups
- Simple greetings or short conversations

COMPLEX (requires analysis or structured output):
- Summaries, comparisons, pros/cons lists
- Explanations of concepts
- Planning, recommendations, advice
- Essay writing, creative short stories

ADVANCED (requires technical expertise or multi-step reasoning):
- ANY code/script/program creation or modification
- ANY algorithm implementation (Markov chains, sorting, ML, etc.)
- Mathematical proofs, equations, calculations
- System design, architecture planning
- Image/audio/video processing tasks
- API integrations, database queries
- Debugging, refactoring existing code
- Multi-step technical problems
- Scientific or research analysis

IMPORTANT: If the request mentions creating a script, program, code, algorithm, or any technical implementation, it is ALWAYS ADVANCED.

User request:
\"\"\"
{prompt}
\"\"\"

Respond with ONLY one word: SIMPLE, COMPLEX, or ADVANCED"""


class OpenRouterClassifier:
    """
    Classifies task difficulty using OpenRouter API.
    Falls back to local keyword-based classification if API fails.
    """

    def __init__(self):
        self._local_classifier = LocalDifficultyClassifier()

    async def classify(
        self,
        prompt: str,
        node_registry: Optional["NodeRegistry"] = None,
        coordinator_crypto: Optional["CoordinatorCrypto"] = None,
        subtask_count: int = 1,
        explicit_difficulty: Optional[TaskDifficulty] = None
    ) -> TaskDifficulty:
        """
        Classify task difficulty using OpenRouter API.

        Args:
            prompt: The user prompt to classify
            node_registry: Unused (kept for backwards compatibility)
            coordinator_crypto: Unused (kept for backwards compatibility)
            subtask_count: Number of subtasks (for local fallback)
            explicit_difficulty: User-specified difficulty (overrides all)

        Returns:
            TaskDifficulty enum value
        """
        # Honor explicit difficulty if provided
        if explicit_difficulty:
            logger.debug("difficulty_explicit", difficulty=explicit_difficulty.value)
            return explicit_difficulty

        # Try OpenRouter API classification
        try:
            difficulty = await self._classify_via_openrouter(prompt)
            if difficulty:
                return difficulty
        except Exception as e:
            logger.warning("openrouter_classification_failed", error=str(e))

        # Fallback to local classifier
        logger.info("using_local_classifier_fallback")
        return self._local_classifier.classify(prompt, subtask_count)

    async def _classify_via_openrouter(
        self,
        prompt: str
    ) -> Optional[TaskDifficulty]:
        """
        Send classification request to OpenRouter API.

        Returns:
            TaskDifficulty if successful, None if failed
        """
        # Check if API key is configured
        if not OPENROUTER_API_KEY:
            logger.warning("openrouter_api_key_not_set")
            return None

        # Build classification prompt (limit user prompt to first 1000 chars)
        classification_prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(
            prompt=prompt[:1000]
        )

        logger.info("openrouter_sending_request", model=OPENROUTER_MODEL, prompt_length=len(prompt))

        url = f"{OPENROUTER_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": classification_prompt
                }
            ],
            "max_tokens": 20,
            "temperature": 0.1
        }

        try:
            async with httpx.AsyncClient(timeout=CLASSIFICATION_TIMEOUT) as client:
                response = await client.post(url, headers=headers, json=payload)

                logger.info(
                    "openrouter_response_status",
                    status_code=response.status_code
                )

                if response.status_code != 200:
                    logger.warning(
                        "openrouter_api_error",
                        status_code=response.status_code,
                        response=response.text[:500]
                    )
                    return None

                data = response.json()

                # Log full response structure for debugging
                logger.info(
                    "openrouter_raw_response",
                    data=str(data)[:500]
                )

                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                # If content is empty, check for error in response
                if not content:
                    error = data.get("error", {})
                    if error:
                        logger.warning(
                            "openrouter_response_error",
                            error=str(error)[:200]
                        )
                    return None

                difficulty = self._parse_classification_response(content)

                if difficulty:
                    logger.info(
                        "openrouter_classification_success",
                        difficulty=difficulty.value,
                        model=OPENROUTER_MODEL,
                        raw_response=content[:50]
                    )
                    return difficulty
                else:
                    logger.warning(
                        "classification_parse_failed",
                        response=content[:100] if content else "(empty response)"
                    )
                    return None

        except httpx.TimeoutException:
            logger.warning("openrouter_timeout", timeout=CLASSIFICATION_TIMEOUT)
            return None
        except Exception as e:
            logger.error("openrouter_request_failed", error=str(e))
            return None

    def _parse_classification_response(
        self,
        response: str
    ) -> Optional[TaskDifficulty]:
        """
        Parse LLM response to extract difficulty level.

        Args:
            response: Raw LLM response text

        Returns:
            TaskDifficulty or None if parsing fails
        """
        # Normalize response
        response_upper = response.strip().upper()

        # Direct match (ideal case)
        if response_upper == "SIMPLE":
            return TaskDifficulty.SIMPLE
        elif response_upper == "COMPLEX":
            return TaskDifficulty.COMPLEX
        elif response_upper == "ADVANCED":
            return TaskDifficulty.ADVANCED

        # Search for keywords in response (LLM may add explanation)
        # Priority: ADVANCED > COMPLEX > SIMPLE (to avoid false SIMPLE)
        if "ADVANCED" in response_upper:
            return TaskDifficulty.ADVANCED
        elif "COMPLEX" in response_upper:
            return TaskDifficulty.COMPLEX
        elif "SIMPLE" in response_upper:
            return TaskDifficulty.SIMPLE

        # Failed to parse
        return None


class LocalDifficultyClassifier:
    """
    Local keyword-based classifier (fallback when API not available).

    Classification criteria:
    - SIMPLE: Short questions, simple translations, direct answers
    - COMPLEX: Analysis, summaries, comparisons, explanations
    - ADVANCED: Code, math, complex reasoning, multi-step problems
    """

    # Keywords that indicate advanced difficulty
    ADVANCED_KEYWORDS = [
        # Code-related
        "código", "code", "programa", "program", "function", "función",
        "algorithm", "algoritmo", "implement", "implementa", "debug",
        "refactor", "class", "clase", "api", "endpoint", "database",
        "sql", "query", "script", "bug", "error", "exception",
        "crea un script", "create a script", "write a script", "escribe un script",
        "genera un programa", "generate a program", "desarrolla", "develop",
        # Algorithms and ML
        "markov", "neural", "machine learning", "deep learning",
        "clustering", "classification", "regression", "modelo", "model",
        "training", "entrenamiento", "dataset", "tensorflow", "pytorch",
        "sorting", "search algorithm", "recursion", "recursivo",
        # Image/Audio/Video processing
        "imagen", "image", "audio", "video", "processing", "procesamiento",
        "generar imagen", "generate image", "crear imagen", "create image",
        "ffmpeg", "opencv", "pillow", "pil", "matplotlib",
        # Math-related
        "matemáticas", "math", "calcul", "equation", "ecuación",
        "formula", "fórmula", "integral", "derivada", "derivative",
        "probabilidad", "probability", "estadística", "statistics",
        "cadenas de markov", "markov chain", "monte carlo",
        # Reasoning-related
        "razon", "reason", "logic", "lógica", "proof", "prueba",
        "demostración", "theorem", "teorema", "hypothesis", "hipótesis",
        "deducir", "deduce", "infer", "inferir",
        # Architecture
        "arquitectura", "architecture", "design pattern", "patrón de diseño",
        "system design", "diseño de sistema", "microservice",
        # Complex tasks
        "optimiza", "optimize", "benchmark", "performance", "rendimiento",
        "automatiza", "automate", "pipeline", "workflow",
        # File operations
        "parsear", "parse", "serializar", "serialize", "json", "xml", "csv",
    ]

    # Keywords that indicate complex difficulty
    COMPLEX_KEYWORDS = [
        # Analysis
        "analiza", "analyze", "analysis", "análisis", "evalúa", "evaluate",
        "compara", "compare", "comparison", "comparación", "contrasta",
        # Summaries
        "resume", "summarize", "summary", "resumen", "sintetiza",
        # Explanations
        "explica", "explain", "explanation", "explicación", "describe",
        "descripción", "detalla", "detail",
        # Lists and identification
        "lista", "list", "enumera", "enumerate", "identifica", "identify",
        "clasifica", "classify", "categoriza", "categorize",
        # Reviews
        "revisa", "review", "critica", "critique", "evalúa",
        # Plans
        "planifica", "plan", "estrategia", "strategy", "organiza",
    ]

    # Keywords that indicate simple tasks
    SIMPLE_KEYWORDS = [
        "qué es", "what is", "define", "definición", "definition",
        "traduce", "translate", "traducción", "translation",
        "cuánto", "how much", "cuántos", "how many",
        "dónde", "where", "cuándo", "when", "quién", "who",
        "sí o no", "yes or no", "verdadero o falso", "true or false",
    ]

    def __init__(self):
        # Compile regex patterns for efficiency
        self._advanced_pattern = re.compile(
            '|'.join(re.escape(kw) for kw in self.ADVANCED_KEYWORDS),
            re.IGNORECASE
        )
        self._complex_pattern = re.compile(
            '|'.join(re.escape(kw) for kw in self.COMPLEX_KEYWORDS),
            re.IGNORECASE
        )
        self._simple_pattern = re.compile(
            '|'.join(re.escape(kw) for kw in self.SIMPLE_KEYWORDS),
            re.IGNORECASE
        )

    def classify(
        self,
        prompt: str,
        subtask_count: int = 1,
        explicit_difficulty: Optional[TaskDifficulty] = None
    ) -> TaskDifficulty:
        """
        Classify task difficulty based on prompt and context.

        Args:
            prompt: The task prompt to analyze
            subtask_count: Number of subtasks (if already divided)
            explicit_difficulty: User-specified difficulty (overrides auto)

        Returns:
            TaskDifficulty enum value
        """
        # Honor explicit difficulty if provided
        if explicit_difficulty:
            logger.debug(
                "difficulty_explicit",
                difficulty=explicit_difficulty.value
            )
            return explicit_difficulty

        # Estimate token count (rough: ~4 chars per token)
        token_estimate = len(prompt.split())
        char_count = len(prompt)

        # Score-based classification
        score = self._calculate_score(
            prompt,
            token_estimate,
            char_count,
            subtask_count
        )

        if score >= 70:
            difficulty = TaskDifficulty.ADVANCED
        elif score >= 40:
            difficulty = TaskDifficulty.COMPLEX
        else:
            difficulty = TaskDifficulty.SIMPLE

        logger.debug(
            "difficulty_classified_local",
            difficulty=difficulty.value,
            score=score,
            token_estimate=token_estimate,
            subtask_count=subtask_count
        )

        return difficulty

    def _calculate_score(
        self,
        prompt: str,
        token_count: int,
        char_count: int,
        subtask_count: int
    ) -> float:
        """
        Calculate difficulty score from 0-100.

        Scoring breakdown:
        - Keyword matches: 0-40 points
        - Length/complexity: 0-30 points
        - Subtask count: 0-30 points
        """
        score = 0.0

        # Keyword analysis (0-40 points)
        advanced_matches = len(self._advanced_pattern.findall(prompt))
        complex_matches = len(self._complex_pattern.findall(prompt))
        simple_matches = len(self._simple_pattern.findall(prompt))

        # Advanced keywords have highest weight
        if advanced_matches > 0:
            score += min(advanced_matches * 15, 40)
        elif complex_matches > 0:
            score += min(complex_matches * 10, 25)
        elif simple_matches > 0:
            score -= min(simple_matches * 5, 15)

        # Length analysis (0-30 points)
        if token_count > 500:
            score += 30
        elif token_count > 200:
            score += 20
        elif token_count > 100:
            score += 10
        elif token_count < 20:
            score -= 5

        # Subtask count analysis (0-30 points)
        if subtask_count >= 5:
            score += 30
        elif subtask_count >= 3:
            score += 20
        elif subtask_count >= 2:
            score += 10

        # Detect code blocks or technical content
        if '```' in prompt or 'def ' in prompt or 'class ' in prompt:
            score += 15

        # Detect mathematical notation
        if any(c in prompt for c in ['∑', '∫', '√', '∂', '≈', '≤', '≥']):
            score += 15

        return max(0, min(100, score))

    def estimate_complexity_reason(self, prompt: str) -> str:
        """
        Provide a brief explanation of why a task was classified.

        Args:
            prompt: The task prompt

        Returns:
            Human-readable complexity reason
        """
        reasons = []

        advanced_matches = self._advanced_pattern.findall(prompt)
        if advanced_matches:
            reasons.append(f"advanced keywords: {', '.join(set(advanced_matches[:3]))}")

        complex_matches = self._complex_pattern.findall(prompt)
        if complex_matches and not advanced_matches:
            reasons.append(f"complex keywords: {', '.join(set(complex_matches[:3]))}")

        token_count = len(prompt.split())
        if token_count > 200:
            reasons.append(f"long prompt ({token_count} words)")

        if '```' in prompt:
            reasons.append("contains code blocks")

        if not reasons:
            reasons.append("standard request")

        return "; ".join(reasons)


# Global instances
openrouter_classifier = OpenRouterClassifier()
local_difficulty_classifier = LocalDifficultyClassifier()

# Backwards compatibility alias
llm_difficulty_classifier = openrouter_classifier


# Convenience functions
async def classify_task_difficulty_async(
    prompt: str,
    node_registry: Optional["NodeRegistry"] = None,
    coordinator_crypto: Optional["CoordinatorCrypto"] = None,
    subtask_count: int = 1,
    explicit_difficulty: Optional[TaskDifficulty] = None
) -> TaskDifficulty:
    """Async convenience function for OpenRouter-based task difficulty classification."""
    return await openrouter_classifier.classify(
        prompt, node_registry, coordinator_crypto, subtask_count, explicit_difficulty
    )


def classify_task_difficulty(
    prompt: str,
    subtask_count: int = 1,
    explicit_difficulty: Optional[TaskDifficulty] = None
) -> TaskDifficulty:
    """Sync convenience function using local classifier only (for backwards compatibility)."""
    return local_difficulty_classifier.classify(prompt, subtask_count, explicit_difficulty)
