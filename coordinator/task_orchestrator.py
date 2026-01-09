"""
ClubAI Task Orchestrator

Handles task division, node assignment, and task lifecycle management.
"""

import asyncio
import re
from datetime import datetime
from typing import Optional
import structlog

from shared.models import (
    Task,
    TaskStatus,
    TaskMode,
    TaskDifficulty,
    Subtask,
    SubtaskStatus,
    generate_id,
)
from shared.protocol import (
    MessageType,
    ProtocolMessage,
    TaskAssignPayload,
    TaskResultPayload,
    TaskErrorPayload,
    parse_payload,
)
from .database import db
from .crypto import coordinator_crypto
from .node_registry import node_registry
from .difficulty_classifier import classify_task_difficulty

logger = structlog.get_logger()

# Constants
MAX_RETRIES = 3

# Timeout por dificultad de tarea (en segundos)
DIFFICULTY_TIMEOUTS = {
    TaskDifficulty.SIMPLE: 60,    # Tareas simples: 1 minuto
    TaskDifficulty.COMPLEX: 120,  # Tareas complejas: 2 minutos
    TaskDifficulty.ADVANCED: 180, # Tareas avanzadas: 3 minutos
}
DEFAULT_TIMEOUT = 60  # Fallback


def get_timeout_for_difficulty(difficulty: TaskDifficulty) -> int:
    """Get the timeout in seconds for a given task difficulty."""
    return DIFFICULTY_TIMEOUTS.get(difficulty, DEFAULT_TIMEOUT)


class TaskOrchestrator:
    """
    Orchestrates the distribution of inference tasks across nodes.

    Supports multiple modes:
    - SUBTASKS: Divide task into independent subtasks
    - CONSENSUS: Send same task to multiple nodes
    - CONTEXT: Split long context across nodes
    """

    def __init__(self):
        self._pending_subtasks: dict[str, asyncio.Event] = {}
        self._subtask_results: dict[str, str] = {}

    async def create_task(
        self,
        user_id: str,
        prompt: str,
        mode: TaskMode = TaskMode.SUBTASKS,
        difficulty: Optional[TaskDifficulty] = None
    ) -> dict:
        """
        Create and begin processing a new task.

        Args:
            user_id: User who submitted the task
            prompt: The inference prompt
            mode: Task division mode
            difficulty: Optional explicit difficulty (auto-detected if None)

        Returns:
            Created task record
        """
        task_id = generate_id()

        # Auto-classify difficulty if not provided
        if difficulty is None:
            difficulty = classify_task_difficulty(prompt)

        # Create task in database with difficulty
        task = await db.create_task(
            id=task_id,
            user_id=user_id,
            mode=mode.value,
            original_prompt=prompt,
            difficulty=difficulty.value
        )

        logger.info(
            "task_created",
            task_id=task_id,
            user_id=user_id,
            mode=mode.value,
            difficulty=difficulty.value
        )

        # Start processing in background
        asyncio.create_task(self._process_task(task_id, prompt, mode, difficulty))

        return task

    async def _process_task(
        self,
        task_id: str,
        prompt: str,
        mode: TaskMode,
        difficulty: TaskDifficulty
    ) -> None:
        """Process a task based on its mode."""
        try:
            # Update status to processing
            await db.update_task_status(task_id, TaskStatus.PROCESSING.value)

            # Divide task into subtasks based on mode
            if mode == TaskMode.SUBTASKS:
                subtask_prompts = self._divide_into_subtasks(prompt)
            elif mode == TaskMode.CONSENSUS:
                subtask_prompts = [prompt] * 3  # Send to 3 nodes
            else:  # CONTEXT mode
                subtask_prompts = self._divide_by_context(prompt)

            # Adjust difficulty based on subtask count
            # More subtasks can indicate higher complexity
            adjusted_difficulty = classify_task_difficulty(
                prompt,
                subtask_count=len(subtask_prompts),
                explicit_difficulty=difficulty
            )

            # Create subtask records
            subtasks = []
            for sp in subtask_prompts:
                subtask = await db.create_subtask(
                    id=generate_id(),
                    task_id=task_id,
                    prompt=sp
                )
                subtasks.append(subtask)

            logger.info(
                "subtasks_created",
                task_id=task_id,
                count=len(subtasks),
                difficulty=adjusted_difficulty.value
            )

            # Assign subtasks to nodes using intelligent matching
            await self._assign_subtasks(subtasks, adjusted_difficulty)

            # Wait for all subtasks to complete with difficulty-based timeout
            # Add extra buffer time for coordination overhead
            wait_timeout = get_timeout_for_difficulty(adjusted_difficulty) + 30
            await self._wait_for_completion(task_id, subtasks, timeout=wait_timeout)

            # Aggregate results
            from .response_aggregator import response_aggregator
            final_response = await response_aggregator.aggregate(
                task_id=task_id,
                mode=mode,
                original_prompt=prompt
            )

            # Update task with final response
            await db.update_task_status(
                task_id,
                TaskStatus.COMPLETED.value,
                final_response=final_response
            )

            logger.info("task_completed", task_id=task_id)

        except Exception as e:
            logger.error("task_processing_failed", task_id=task_id, error=str(e))
            await db.update_task_status(task_id, TaskStatus.FAILED.value)

    def _divide_into_subtasks(self, prompt: str) -> list[str]:
        """
        Divide a prompt into subtasks using heuristics.

        Detection patterns:
        - Numbered items: "1.", "2.", etc.
        - Lettered items: "a)", "b)", etc.
        - Bullet points: "-", "*", "•"
        - Conjunctions: "and", "también", "además", "y"
        - Key phrases: "extract X, Y, and Z"

        Args:
            prompt: Original prompt

        Returns:
            List of subtask prompts
        """
        subtasks = []

        # Pattern 1: Numbered or lettered lists
        list_pattern = r'(?:^|\n)\s*(?:\d+[.)]\s*|[a-zA-Z][.)]\s*|[-*•]\s*)(.+?)(?=(?:\n\s*(?:\d+[.)]\s*|[a-zA-Z][.)]\s*|[-*•]\s*))|$)'
        list_matches = re.findall(list_pattern, prompt, re.MULTILINE | re.DOTALL)

        if len(list_matches) >= 2:
            # Found list items
            base_context = self._extract_context(prompt)
            for item in list_matches:
                item = item.strip()
                if item:
                    subtask = f"{base_context}\n\nTask: {item}" if base_context else item
                    subtasks.append(subtask)
            logger.debug("divided_by_list", count=len(subtasks))
            return subtasks

        # Pattern 2: Comma-separated or "and"-separated items in instructions
        extract_pattern = r'(?:extract|analyze|identify|find|get|list|describe)\s+(?:the\s+)?(.+?)(?:\.|$)'
        extract_match = re.search(extract_pattern, prompt, re.IGNORECASE)

        if extract_match:
            items_str = extract_match.group(1)
            # Split by commas and "and"/"y"
            items = re.split(r',\s*(?:and|y)?\s*|\s+(?:and|y)\s+', items_str)
            items = [i.strip() for i in items if i.strip()]

            if len(items) >= 2:
                base_context = self._extract_context(prompt)
                action = extract_match.group(0).split()[0]  # Get the verb
                for item in items:
                    subtask = f"{base_context}\n\n{action} {item}" if base_context else f"{action} {item}"
                    subtasks.append(subtask)
                logger.debug("divided_by_extraction", count=len(subtasks))
                return subtasks

        # Pattern 3: Multiple sentences with different tasks
        sentences = re.split(r'(?<=[.!?])\s+', prompt)
        task_sentences = [s for s in sentences if self._is_task_sentence(s)]

        if len(task_sentences) >= 2:
            base_context = self._extract_context(prompt)
            for sentence in task_sentences:
                subtask = f"{base_context}\n\n{sentence}" if base_context else sentence
                subtasks.append(subtask)
            logger.debug("divided_by_sentences", count=len(subtasks))
            return subtasks

        # No division possible - return as single task
        logger.debug("no_division_possible")
        return [prompt]

    def _extract_context(self, prompt: str) -> str:
        """Extract context/preamble from a prompt."""
        # Look for context indicators
        context_patterns = [
            r'^(.*?(?:following|below|this|given)[^:]*:)',  # "Analyze the following:"
            r'^((?:Given|Considering|Based on|With)[^.]*\.)',  # "Given X, do Y"
            r'^([^.]*?(?:text|document|data|content)[^.]*\.)',  # "In the following text..."
        ]

        for pattern in context_patterns:
            match = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        return ""

    def _is_task_sentence(self, sentence: str) -> bool:
        """Check if a sentence represents a task/instruction."""
        task_indicators = [
            r'\b(analyze|extract|identify|find|list|describe|explain|summarize|compare)\b',
            r'\b(what|how|why|where|when|who)\b',
            r'\b(should|must|need to|have to)\b',
        ]
        return any(re.search(p, sentence, re.IGNORECASE) for p in task_indicators)

    def _divide_by_context(self, prompt: str, chunk_size: int = 4000) -> list[str]:
        """
        Divide a long prompt into chunks for parallel processing.

        Args:
            prompt: Original prompt
            chunk_size: Maximum characters per chunk

        Returns:
            List of chunk prompts
        """
        if len(prompt) <= chunk_size:
            return [prompt]

        # Find the instruction part vs content part
        instruction_match = re.match(
            r'^(.*?(?:analyze|process|review|examine)[^:]*:?\s*)',
            prompt,
            re.IGNORECASE | re.DOTALL
        )

        if instruction_match:
            instruction = instruction_match.group(1)
            content = prompt[len(instruction):]
        else:
            instruction = "Analyze the following section:\n\n"
            content = prompt

        # Split content into chunks with overlap
        chunks = []
        overlap = 200
        pos = 0

        while pos < len(content):
            end = min(pos + chunk_size, len(content))

            # Try to break at sentence boundary
            if end < len(content):
                sentence_end = content.rfind('.', pos, end)
                if sentence_end > pos + chunk_size // 2:
                    end = sentence_end + 1

            chunk = content[pos:end]
            chunks.append(f"{instruction}[Section {len(chunks) + 1}]\n{chunk}")

            pos = end - overlap if end < len(content) else end

        return chunks

    async def _assign_subtasks(
        self,
        subtasks: list[dict],
        difficulty: TaskDifficulty
    ) -> None:
        """
        Assign subtasks to available nodes using intelligent matching.

        Uses select_nodes_v2 to match task difficulty with node capabilities.
        """
        for subtask in subtasks:
            # Select a node using intelligent tier-based matching
            nodes = await node_registry.select_nodes_v2(
                difficulty=difficulty,
                n=1
            )

            if not nodes:
                logger.warning(
                    "no_nodes_available",
                    subtask_id=subtask["id"],
                    difficulty=difficulty.value
                )
                await db.fail_subtask(subtask["id"], SubtaskStatus.FAILED.value)
                continue

            node = nodes[0]

            # Encrypt prompt for the node
            encrypted_prompt = coordinator_crypto.encrypt_for_node(
                node.public_key,
                subtask["prompt"]
            )

            # Update subtask in database
            await db.assign_subtask(
                subtask["id"],
                node.node_id,
                encrypted_prompt
            )

            # Get timeout based on difficulty
            timeout_seconds = get_timeout_for_difficulty(difficulty)

            # Create and send task assignment
            message = ProtocolMessage.create(
                MessageType.TASK_ASSIGN,
                TaskAssignPayload(
                    subtask_id=subtask["id"],
                    task_id=subtask["task_id"],
                    encrypted_prompt=encrypted_prompt,
                    timeout_seconds=timeout_seconds
                )
            )

            success = await node_registry.send_to_node(node.node_id, message)

            if success:
                node_registry.increment_load(node.node_id)
                logger.info(
                    "subtask_assigned",
                    subtask_id=subtask["id"],
                    node_id=node.node_id,
                    node_tier=node.node_tier.value,
                    difficulty=difficulty.value,
                    timeout_seconds=timeout_seconds
                )
            else:
                await db.fail_subtask(subtask["id"], SubtaskStatus.FAILED.value)

    async def _wait_for_completion(
        self,
        task_id: str,
        subtasks: list[dict],
        timeout: int = 120
    ) -> None:
        """Wait for all subtasks to complete."""
        # Create events for each subtask
        for subtask in subtasks:
            self._pending_subtasks[subtask["id"]] = asyncio.Event()

        try:
            # Wait with timeout
            await asyncio.wait_for(
                asyncio.gather(*[
                    self._pending_subtasks[s["id"]].wait()
                    for s in subtasks
                    if s["id"] in self._pending_subtasks
                ]),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning("task_timeout", task_id=task_id)
            # Mark remaining as timeout
            for subtask in subtasks:
                current = await db.get_subtask_by_id(subtask["id"])
                if current and current["status"] in ("pending", "assigned"):
                    await db.fail_subtask(subtask["id"], SubtaskStatus.TIMEOUT.value)
        finally:
            # Clean up events
            for subtask in subtasks:
                self._pending_subtasks.pop(subtask["id"], None)

    async def handle_task_result(
        self,
        node_id: str,
        message: ProtocolMessage
    ) -> None:
        """Handle a task result from a node."""
        payload = parse_payload(message, TaskResultPayload)

        try:
            # Get the node's public key
            node = node_registry.get_node(node_id)
            if not node:
                logger.error("unknown_node", node_id=node_id)
                return

            # Decrypt the response
            response = coordinator_crypto.decrypt_from_node(
                node.public_key,
                payload.encrypted_response
            )

            # Update subtask
            await db.complete_subtask(
                payload.subtask_id,
                response=response,
                encrypted_response=payload.encrypted_response,
                execution_time_ms=payload.execution_time_ms
            )

            # Store result
            self._subtask_results[payload.subtask_id] = response

            # Signal completion
            if payload.subtask_id in self._pending_subtasks:
                self._pending_subtasks[payload.subtask_id].set()

            # Update node load
            node_registry.decrement_load(node_id)

            # Update reputation (async)
            from .reputation import reputation_system
            asyncio.create_task(
                reputation_system.record_task_completed(
                    node_id,
                    payload.execution_time_ms
                )
            )

            logger.info(
                "task_result_received",
                subtask_id=payload.subtask_id,
                node_id=node_id,
                execution_time_ms=payload.execution_time_ms
            )

        except Exception as e:
            logger.error(
                "task_result_processing_failed",
                subtask_id=payload.subtask_id,
                error=str(e)
            )

    async def handle_task_error(
        self,
        node_id: str,
        message: ProtocolMessage
    ) -> None:
        """Handle a task error from a node."""
        payload = parse_payload(message, TaskErrorPayload)

        # Update subtask status
        await db.fail_subtask(payload.subtask_id, SubtaskStatus.FAILED.value)

        # Signal completion (even though failed)
        if payload.subtask_id in self._pending_subtasks:
            self._pending_subtasks[payload.subtask_id].set()

        # Update node load
        node_registry.decrement_load(node_id)

        # Update reputation
        from .reputation import reputation_system
        asyncio.create_task(
            reputation_system.record_task_failed(node_id, payload.error_code)
        )

        logger.error(
            "task_error_received",
            subtask_id=payload.subtask_id,
            node_id=node_id,
            error_code=payload.error_code,
            error_message=payload.error_message
        )


# Global task orchestrator instance
task_orchestrator = TaskOrchestrator()
