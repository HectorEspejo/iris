"""
Iris Task Difficulty Classifier

Classifies tasks into difficulty levels based on prompt analysis.
"""

import re
from typing import Optional
import structlog

from shared.models import TaskDifficulty

logger = structlog.get_logger()


class DifficultyClassifier:
    """
    Classifies task difficulty based on prompt content and structure.

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
        # Math-related
        "matemáticas", "math", "calcul", "equation", "ecuación",
        "formula", "fórmula", "integral", "derivada", "derivative",
        "probabilidad", "probability", "estadística", "statistics",
        # Reasoning-related
        "razon", "reason", "logic", "lógica", "proof", "prueba",
        "demostración", "theorem", "teorema", "hypothesis", "hipótesis",
        "deducir", "deduce", "infer", "inferir",
        # Architecture
        "arquitectura", "architecture", "design pattern", "patrón de diseño",
        "system design", "diseño de sistema", "microservice",
        # Complex tasks
        "optimiza", "optimize", "benchmark", "performance", "rendimiento",
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
            "difficulty_classified",
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


# Global classifier instance
difficulty_classifier = DifficultyClassifier()


def classify_task_difficulty(
    prompt: str,
    subtask_count: int = 1,
    explicit_difficulty: Optional[TaskDifficulty] = None
) -> TaskDifficulty:
    """Convenience function for task difficulty classification."""
    return difficulty_classifier.classify(prompt, subtask_count, explicit_difficulty)
