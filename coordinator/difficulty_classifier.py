"""
Iris Task Difficulty Classifier

Classifies tasks using:
1. LLM-based classification via BASIC tier nodes (primary)
2. Local keyword-based classification (fallback)
"""

import asyncio
import re
from typing import Optional, TYPE_CHECKING
import structlog

from shared.models import TaskDifficulty, generate_id
from shared.protocol import (
    MessageType,
    ProtocolMessage,
    ClassifyAssignPayload,
    ClassifyResultPayload,
    ClassifyErrorPayload,
    parse_payload,
)

if TYPE_CHECKING:
    from .node_registry import NodeRegistry, ConnectedNode
    from .crypto import CoordinatorCrypto

logger = structlog.get_logger()

# Classification constants
CLASSIFICATION_TIMEOUT = 15  # seconds
CLASSIFICATION_PROMPT_TEMPLATE = """Classify the following user request into exactly one difficulty level.

Rules:
- SIMPLE: Short questions, translations, definitions, yes/no questions, simple lookups
- COMPLEX: Analysis, summaries, comparisons, explanations, lists, planning tasks
- ADVANCED: Code generation/debugging, mathematical proofs, complex reasoning, multi-step problems, architecture design

User request:
\"\"\"
{prompt}
\"\"\"

Respond with ONLY one word: SIMPLE, COMPLEX, or ADVANCED"""


class LLMDifficultyClassifier:
    """
    Classifies task difficulty using LLM inference on BASIC tier nodes.
    Falls back to local keyword-based classification if LLM fails.
    """

    def __init__(self):
        self._pending_classifications: dict[str, asyncio.Event] = {}
        self._classification_results: dict[str, str] = {}
        self._local_classifier = LocalDifficultyClassifier()

    async def classify(
        self,
        prompt: str,
        node_registry: "NodeRegistry",
        coordinator_crypto: "CoordinatorCrypto",
        subtask_count: int = 1,
        explicit_difficulty: Optional[TaskDifficulty] = None
    ) -> TaskDifficulty:
        """
        Classify task difficulty using LLM-based classification.

        Args:
            prompt: The user prompt to classify
            node_registry: NodeRegistry instance for node selection
            coordinator_crypto: CoordinatorCrypto for encryption
            subtask_count: Number of subtasks (for local fallback)
            explicit_difficulty: User-specified difficulty (overrides all)

        Returns:
            TaskDifficulty enum value
        """
        # Honor explicit difficulty if provided
        if explicit_difficulty:
            logger.debug("difficulty_explicit", difficulty=explicit_difficulty.value)
            return explicit_difficulty

        # Try LLM-based classification
        try:
            difficulty = await self._classify_via_llm(
                prompt, node_registry, coordinator_crypto
            )
            if difficulty:
                return difficulty
        except Exception as e:
            logger.warning("llm_classification_failed", error=str(e))

        # Fallback to local classifier
        logger.info("using_local_classifier_fallback")
        return self._local_classifier.classify(prompt, subtask_count)

    async def _classify_via_llm(
        self,
        prompt: str,
        node_registry: "NodeRegistry",
        coordinator_crypto: "CoordinatorCrypto"
    ) -> Optional[TaskDifficulty]:
        """
        Send classification request to a BASIC tier node.

        Returns:
            TaskDifficulty if successful, None if failed
        """
        # Select fastest BASIC node
        node = await node_registry.select_fastest_basic_node()
        if not node:
            logger.info("no_basic_nodes_for_classification")
            return None

        classify_id = generate_id()

        # Build classification prompt (limit user prompt to first 1000 chars)
        classification_prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(
            prompt=prompt[:1000]
        )

        # Encrypt prompt for node
        encrypted_prompt = coordinator_crypto.encrypt_for_node(
            node.public_key,
            classification_prompt
        )

        # Create event for waiting
        self._pending_classifications[classify_id] = asyncio.Event()

        try:
            # Send classification request
            message = ProtocolMessage.create(
                MessageType.CLASSIFY_ASSIGN,
                ClassifyAssignPayload(
                    classify_id=classify_id,
                    encrypted_prompt=encrypted_prompt,
                    timeout_seconds=CLASSIFICATION_TIMEOUT
                )
            )

            success = await node_registry.send_to_node(node.node_id, message)
            if not success:
                logger.warning(
                    "classification_send_failed",
                    node_id=node.node_id
                )
                return None

            node_registry.increment_load(node.node_id)

            logger.info(
                "classification_sent",
                classify_id=classify_id,
                node_id=node.node_id
            )

            # Wait for result with timeout
            try:
                await asyncio.wait_for(
                    self._pending_classifications[classify_id].wait(),
                    timeout=CLASSIFICATION_TIMEOUT + 2  # Extra buffer
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "classification_timeout",
                    classify_id=classify_id,
                    node_id=node.node_id
                )
                # Update reputation for timeout
                from .reputation import reputation_system
                asyncio.create_task(
                    reputation_system.record_task_timeout(node.node_id)
                )
                node_registry.decrement_load(node.node_id)
                return None

            # Get and parse result
            result = self._classification_results.pop(classify_id, None)
            if result:
                difficulty = self._parse_classification_response(result)
                if difficulty:
                    logger.info(
                        "llm_classification_success",
                        classify_id=classify_id,
                        difficulty=difficulty.value,
                        node_id=node.node_id
                    )
                    return difficulty
                else:
                    logger.warning(
                        "classification_parse_failed",
                        classify_id=classify_id,
                        response=result[:100]
                    )
                    # Record as invalid response
                    from .reputation import reputation_system
                    asyncio.create_task(
                        reputation_system.record_task_failed(
                            node.node_id, "INVALID_RESPONSE"
                        )
                    )

            return None

        finally:
            # Cleanup
            self._pending_classifications.pop(classify_id, None)
            self._classification_results.pop(classify_id, None)

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

    async def handle_classify_result(
        self,
        node_id: str,
        message: ProtocolMessage,
        node_registry: "NodeRegistry",
        coordinator_crypto: "CoordinatorCrypto"
    ) -> None:
        """
        Handle a classification result from a node.

        Args:
            node_id: Node that sent the result
            message: The result message
            node_registry: NodeRegistry for node info
            coordinator_crypto: For decryption
        """
        payload = parse_payload(message, ClassifyResultPayload)

        try:
            node = node_registry.get_node(node_id)
            if not node:
                logger.error("classify_result_unknown_node", node_id=node_id)
                return

            # Decrypt response
            response = coordinator_crypto.decrypt_from_node(
                node.public_key,
                payload.encrypted_response
            )

            # Store result
            self._classification_results[payload.classify_id] = response

            # Signal completion
            if payload.classify_id in self._pending_classifications:
                self._pending_classifications[payload.classify_id].set()

            # Update reputation (successful task completion)
            from .reputation import reputation_system
            asyncio.create_task(
                reputation_system.record_task_completed(
                    node_id,
                    payload.execution_time_ms
                )
            )

            node_registry.decrement_load(node_id)

            logger.info(
                "classify_result_received",
                classify_id=payload.classify_id,
                node_id=node_id,
                execution_time_ms=payload.execution_time_ms
            )

        except Exception as e:
            logger.error(
                "classify_result_processing_failed",
                classify_id=payload.classify_id,
                error=str(e)
            )

    async def handle_classify_error(
        self,
        node_id: str,
        message: ProtocolMessage,
        node_registry: "NodeRegistry"
    ) -> None:
        """
        Handle a classification error from a node.
        """
        payload = parse_payload(message, ClassifyErrorPayload)

        # Signal completion (as failed)
        if payload.classify_id in self._pending_classifications:
            self._pending_classifications[payload.classify_id].set()

        node_registry.decrement_load(node_id)

        # Update reputation
        from .reputation import reputation_system
        asyncio.create_task(
            reputation_system.record_task_failed(node_id, payload.error_code)
        )

        logger.error(
            "classify_error_received",
            classify_id=payload.classify_id,
            node_id=node_id,
            error_code=payload.error_code
        )


class LocalDifficultyClassifier:
    """
    Local keyword-based classifier (fallback when LLM not available).

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
llm_difficulty_classifier = LLMDifficultyClassifier()
local_difficulty_classifier = LocalDifficultyClassifier()


# Convenience functions
async def classify_task_difficulty_async(
    prompt: str,
    node_registry: "NodeRegistry",
    coordinator_crypto: "CoordinatorCrypto",
    subtask_count: int = 1,
    explicit_difficulty: Optional[TaskDifficulty] = None
) -> TaskDifficulty:
    """Async convenience function for LLM-based task difficulty classification."""
    return await llm_difficulty_classifier.classify(
        prompt, node_registry, coordinator_crypto, subtask_count, explicit_difficulty
    )


def classify_task_difficulty(
    prompt: str,
    subtask_count: int = 1,
    explicit_difficulty: Optional[TaskDifficulty] = None
) -> TaskDifficulty:
    """Sync convenience function using local classifier only (for backwards compatibility)."""
    return local_difficulty_classifier.classify(prompt, subtask_count, explicit_difficulty)
