"""
Iris Task Orchestrator

Handles task division, node assignment, and task lifecycle management.
"""

import asyncio
import re
from datetime import datetime
from typing import Optional, Dict
import structlog

from typing import List
from shared.models import (
    Task,
    TaskStatus,
    TaskMode,
    TaskDifficulty,
    Subtask,
    SubtaskStatus,
    FileAttachment,
    generate_id,
)
from shared.protocol import (
    MessageType,
    ProtocolMessage,
    TaskAssignPayload,
    TaskResultPayload,
    TaskErrorPayload,
    TaskStreamPayload,
    FileData,
    parse_payload,
)
from .database import db
from .crypto import coordinator_crypto
from .node_registry import node_registry, circuit_breaker
from .difficulty_classifier import classify_task_difficulty, classify_task_difficulty_async
from .streaming import streaming_manager

logger = structlog.get_logger()

# Constants
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # Base delay for exponential backoff (seconds)

# Timeout por dificultad de tarea (en segundos)
# Para tareas complejas y avanzadas, usamos timeouts mucho más largos
# ya que el streaming mantiene la conexión activa
DIFFICULTY_TIMEOUTS = {
    TaskDifficulty.SIMPLE: 60,     # Tareas simples: 1 minuto
    TaskDifficulty.COMPLEX: 300,   # Tareas complejas: 5 minutos
    TaskDifficulty.ADVANCED: 600,  # Tareas avanzadas: 10 minutos (prácticamente sin límite)
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
        files: Optional[List[FileAttachment]] = None,
        mode: TaskMode = TaskMode.SUBTASKS,
        difficulty: Optional[TaskDifficulty] = None,
        enable_streaming: bool = False
    ) -> dict:
        """
        Create and begin processing a new task.

        Args:
            user_id: User who submitted the task
            prompt: The inference prompt
            files: Optional list of file attachments (PDFs, images)
            mode: Task division mode
            difficulty: Optional explicit difficulty (auto-detected if None)
            enable_streaming: If True, enable real-time streaming of response chunks

        Returns:
            Created task record
        """
        task_id = generate_id()

        # Process files:
        # - PDFs: Always processed by Gemini (LM Studio API doesn't support PDFs)
        # - Images: Sent directly to vision-capable nodes
        processed_prompt = prompt
        has_files = bool(files)
        vision_files = []  # Only images go to vision nodes

        if files:
            images = [f for f in files if f.is_image]
            pdfs = [f for f in files if f.is_pdf]

            # Log current vision nodes status
            all_connected_nodes = node_registry.get_all_nodes()
            vision_nodes = node_registry.get_vision_capable_nodes()

            logger.info(
                "processing_files",
                task_id=task_id,
                image_count=len(images),
                pdf_count=len(pdfs),
                total_size_mb=sum(f.size_bytes for f in files) / 1024 / 1024,
                total_connected_nodes=len(all_connected_nodes),
                vision_capable_nodes=len(vision_nodes),
                vision_node_ids=[n.node_id for n in vision_nodes],
                vision_node_models=[n.model_name for n in vision_nodes]
            )

            # PDFs: Always process with Gemini (LM Studio doesn't support PDF input)
            if pdfs:
                from .multimodal_processor import multimodal_processor
                processed_prompt = await multimodal_processor.process_pdfs(
                    pdfs=pdfs,
                    user_prompt=prompt
                )
                logger.info(
                    "pdfs_processed_via_gemini",
                    task_id=task_id,
                    pdf_count=len(pdfs),
                    original_prompt_length=len(prompt),
                    processed_prompt_length=len(processed_prompt)
                )

            # Images: Send to vision-capable nodes if available
            if images:
                if vision_nodes:
                    vision_files = images  # Only images, not PDFs
                    logger.info(
                        "images_will_be_sent_to_vision_nodes",
                        task_id=task_id,
                        image_count=len(images),
                        image_names=[f.filename for f in images]
                    )
                else:
                    # No vision nodes - cannot process images
                    image_names = ", ".join(f.filename for f in images)
                    processed_prompt = f"""NOTA: El usuario adjuntó imágenes ({image_names}) pero no hay nodos con capacidad de visión disponibles. No es posible procesar las imágenes en este momento.

{processed_prompt}"""
                    logger.warning(
                        "images_cannot_be_processed_no_vision_nodes",
                        task_id=task_id,
                        image_count=len(images)
                    )

            # Tasks with files are always ADVANCED
            difficulty = TaskDifficulty.ADVANCED

        # Auto-classify difficulty using LLM if not provided
        # Falls back to local classifier if no BASIC nodes available
        if difficulty is None:
            difficulty = await classify_task_difficulty_async(
                prompt=processed_prompt,
                node_registry=node_registry,
                coordinator_crypto=coordinator_crypto
            )

        # Create task in database with difficulty
        task = await db.create_task(
            id=task_id,
            user_id=user_id,
            mode=mode.value,
            original_prompt=prompt,
            difficulty=difficulty.value,
            has_files=has_files
        )

        # Create streaming queue if streaming is enabled
        if enable_streaming:
            streaming_manager.create_stream(task_id)

        logger.info(
            "task_created",
            task_id=task_id,
            user_id=user_id,
            mode=mode.value,
            difficulty=difficulty.value,
            streaming=enable_streaming,
            has_files=has_files
        )

        # Start processing in background (use processed_prompt for multimodal tasks)
        asyncio.create_task(self._process_task(
            task_id, processed_prompt, mode, difficulty, enable_streaming, vision_files
        ))

        return task

    async def _process_task(
        self,
        task_id: str,
        prompt: str,
        mode: TaskMode,
        difficulty: TaskDifficulty,
        enable_streaming: bool = False,
        files: Optional[List[FileAttachment]] = None
    ) -> None:
        """Process a task based on its mode. Files include both images and PDFs."""
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
                difficulty=adjusted_difficulty.value,
                streaming=enable_streaming,
                has_files=bool(files)
            )

            # Assign subtasks to nodes using intelligent matching with retries
            # If files are present, require vision-capable nodes
            assignments = await self._assign_subtasks(
                subtasks,
                adjusted_difficulty,
                enable_streaming,
                files=files
            )

            # Check if assignment failed for vision tasks
            if not assignments and files:
                error_msg = "No hay nodos con capacidad de visión disponibles para procesar los archivos. Por favor, inténtalo más tarde cuando haya un nodo con modelo de visión (LLaVA, Gemma-3, etc.) conectado."
                logger.error(
                    "vision_task_failed_no_nodes",
                    task_id=task_id,
                    file_count=len(files)
                )
                await db.update_task_status(task_id, TaskStatus.FAILED.value)
                await streaming_manager.complete_stream(task_id, error=error_msg)
                return

            # Wait for all subtasks to complete with individual timeouts
            # Each subtask gets its own timeout, and can be reassigned on failure
            wait_timeout = get_timeout_for_difficulty(adjusted_difficulty)
            await self._wait_for_completion(
                task_id=task_id,
                subtasks=subtasks,
                difficulty=adjusted_difficulty,
                assignments=assignments,
                timeout=wait_timeout,
                enable_streaming=enable_streaming
            )

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

    async def _assign_subtask_with_retry(
        self,
        subtask: dict,
        difficulty: TaskDifficulty,
        enable_streaming: bool = False,
        excluded_nodes: Optional[set[str]] = None,
        files: Optional[List[FileAttachment]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Assign a single subtask with retry logic and exponential backoff.

        Args:
            subtask: Subtask record to assign
            difficulty: Task difficulty level
            enable_streaming: If True, nodes will stream chunks back
            excluded_nodes: Node IDs to exclude from selection
            files: Optional files (images/PDFs) to send to vision-capable nodes

        Returns:
            Tuple of (success, assigned_node_id)
        """
        excluded = excluded_nodes.copy() if excluded_nodes else set()
        require_vision = bool(files)

        # Log vision requirement
        if require_vision:
            all_vision_nodes = node_registry.get_vision_capable_nodes()
            logger.info(
                "vision_required_for_task",
                subtask_id=subtask["id"],
                file_count=len(files),
                total_vision_nodes=len(all_vision_nodes),
                vision_node_ids=[n.node_id for n in all_vision_nodes]
            )

        for attempt in range(MAX_RETRIES):
            # PRIORITY: If files are present, ONLY select vision-capable nodes
            # This takes precedence over difficulty-based selection
            if require_vision:
                # Get vision-capable nodes that are not excluded
                vision_nodes = [
                    n for n in node_registry.get_vision_capable_nodes()
                    if n.node_id not in excluded and circuit_breaker.is_available(n.node_id)
                ]

                logger.info(
                    "selecting_vision_node",
                    subtask_id=subtask["id"],
                    attempt=attempt + 1,
                    available_vision_nodes=len(vision_nodes),
                    excluded_count=len(excluded)
                )

                nodes = vision_nodes[:1] if vision_nodes else []
            else:
                # No images - select a node using SED + P2C algorithm based on difficulty
                nodes = await node_registry.select_nodes_v3(
                    difficulty=difficulty,
                    n=1,
                    exclude=excluded
                )

            if not nodes:
                if require_vision:
                    # Special handling for vision tasks - be explicit about the issue
                    logger.error(
                        "no_vision_nodes_available_for_files",
                        subtask_id=subtask["id"],
                        file_count=len(files),
                        attempt=attempt + 1,
                        message="Task has files but no vision-capable nodes are connected"
                    )
                    # Don't retry for vision - if no vision nodes, fail immediately
                    # This prevents falling back to non-vision nodes
                    return False, None

                if attempt < MAX_RETRIES - 1:
                    # Wait with exponential backoff before retry
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "no_nodes_available_retrying",
                        subtask_id=subtask["id"],
                        attempt=attempt + 1,
                        delay=delay
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "no_nodes_available_exhausted",
                        subtask_id=subtask["id"],
                        attempts=MAX_RETRIES
                    )
                    return False, None

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

            # Convert files to FileData for protocol
            file_data = None
            if files:
                file_data = [
                    FileData(
                        filename=f.filename,
                        mime_type=f.mime_type,
                        content_base64=f.content_base64
                    )
                    for f in files
                ]

            # Create and send task assignment
            message = ProtocolMessage.create(
                MessageType.TASK_ASSIGN,
                TaskAssignPayload(
                    subtask_id=subtask["id"],
                    task_id=subtask["task_id"],
                    encrypted_prompt=encrypted_prompt,
                    timeout_seconds=timeout_seconds,
                    enable_streaming=enable_streaming,
                    files=file_data
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
                    timeout_seconds=timeout_seconds,
                    streaming=enable_streaming,
                    has_files=bool(files),
                    attempt=attempt + 1
                )
                return True, node.node_id
            else:
                # Record failure in circuit breaker
                await circuit_breaker.record_failure(node.node_id)
                excluded.add(node.node_id)

                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "subtask_send_failed_retrying",
                        subtask_id=subtask["id"],
                        node_id=node.node_id,
                        attempt=attempt + 1,
                        delay=delay
                    )
                    await asyncio.sleep(delay)

        return False, None

    async def _assign_subtasks(
        self,
        subtasks: list[dict],
        difficulty: TaskDifficulty,
        enable_streaming: bool = False,
        files: Optional[List[FileAttachment]] = None
    ) -> dict[str, str]:
        """
        Assign subtasks to available nodes using intelligent matching with retries.

        Uses select_nodes_v3 (SED + P2C) for optimal node selection.
        If files are present, requires vision-capable nodes.

        Args:
            subtasks: List of subtask records
            difficulty: Task difficulty level
            enable_streaming: If True, nodes will stream chunks back
            files: Optional files (images/PDFs) to send to vision-capable nodes

        Returns:
            Dict mapping subtask_id -> assigned_node_id for successful assignments
        """
        assignments = {}

        for subtask in subtasks:
            success, node_id = await self._assign_subtask_with_retry(
                subtask=subtask,
                difficulty=difficulty,
                enable_streaming=enable_streaming,
                files=files
            )

            if success and node_id:
                assignments[subtask["id"]] = node_id
            else:
                await db.fail_subtask(subtask["id"], SubtaskStatus.FAILED.value)
                logger.error(
                    "subtask_assignment_failed",
                    subtask_id=subtask["id"],
                    difficulty=difficulty.value
                )

        return assignments

    async def _try_reassign_subtask(
        self,
        subtask_id: str,
        difficulty: TaskDifficulty,
        failed_node_id: Optional[str] = None,
        enable_streaming: bool = False
    ) -> bool:
        """
        Try to reassign a timed-out or failed subtask to a different node.

        Args:
            subtask_id: ID of the subtask to reassign
            difficulty: Task difficulty level
            failed_node_id: Node that failed (to exclude from selection)
            enable_streaming: If True, enable streaming for reassignment

        Returns:
            True if reassignment was successful
        """
        # Get subtask from database
        subtask = await db.get_subtask_by_id(subtask_id)
        if not subtask:
            return False

        # Exclude the failed node
        excluded = {failed_node_id} if failed_node_id else set()

        # Record failure in circuit breaker if we have a failed node
        if failed_node_id:
            await circuit_breaker.record_failure(failed_node_id)
            node_registry.decrement_load(failed_node_id)

        # Try to reassign
        success, new_node_id = await self._assign_subtask_with_retry(
            subtask=subtask,
            difficulty=difficulty,
            enable_streaming=enable_streaming,
            excluded_nodes=excluded
        )

        if success:
            logger.info(
                "subtask_reassigned",
                subtask_id=subtask_id,
                from_node=failed_node_id,
                to_node=new_node_id
            )
            return True

        return False

    async def _wait_for_single_subtask(
        self,
        subtask: dict,
        difficulty: TaskDifficulty,
        timeout: int,
        assignments: Dict[str, str],
        enable_streaming: bool = False
    ) -> str:
        """
        Wait for a single subtask with timeout and optional reassignment.

        Args:
            subtask: Subtask record
            difficulty: Task difficulty
            timeout: Timeout in seconds
            assignments: Dict of subtask_id -> node_id
            enable_streaming: If True, enable streaming

        Returns:
            Status string: "completed", "reassigned", "timeout", "failed"
        """
        subtask_id = subtask["id"]

        if subtask_id not in self._pending_subtasks:
            return "failed"

        try:
            await asyncio.wait_for(
                self._pending_subtasks[subtask_id].wait(),
                timeout=timeout
            )
            return "completed"

        except asyncio.TimeoutError:
            logger.warning(
                "subtask_timeout",
                subtask_id=subtask_id,
                timeout=timeout
            )

            # Try to reassign to a different node
            failed_node = assignments.get(subtask_id)
            if await self._try_reassign_subtask(
                subtask_id=subtask_id,
                difficulty=difficulty,
                failed_node_id=failed_node,
                enable_streaming=enable_streaming
            ):
                # Wait again for the reassigned subtask (with reduced timeout)
                reassign_timeout = max(30, timeout // 2)
                try:
                    await asyncio.wait_for(
                        self._pending_subtasks[subtask_id].wait(),
                        timeout=reassign_timeout
                    )
                    return "reassigned"
                except asyncio.TimeoutError:
                    pass

            # Mark as timeout if all attempts failed
            await db.fail_subtask(subtask_id, SubtaskStatus.TIMEOUT.value)
            return "timeout"

    async def _wait_for_completion(
        self,
        task_id: str,
        subtasks: list[dict],
        difficulty: TaskDifficulty,
        assignments: Dict[str, str],
        timeout: int = 120,
        enable_streaming: bool = False
    ) -> None:
        """
        Wait for all subtasks to complete with individual timeouts and reassignment.

        Each subtask gets its own timeout. If a subtask times out, we attempt
        to reassign it to a different node before marking it as failed.

        Args:
            task_id: Parent task ID
            subtasks: List of subtask records
            difficulty: Task difficulty level
            assignments: Dict mapping subtask_id -> assigned_node_id
            timeout: Base timeout per subtask in seconds
            enable_streaming: If True, enable streaming for reassignments
        """
        # Create events for each subtask
        for subtask in subtasks:
            self._pending_subtasks[subtask["id"]] = asyncio.Event()

        try:
            # Wait for all subtasks with individual timeouts
            results = await asyncio.gather(*[
                self._wait_for_single_subtask(
                    subtask=subtask,
                    difficulty=difficulty,
                    timeout=timeout,
                    assignments=assignments,
                    enable_streaming=enable_streaming
                )
                for subtask in subtasks
                if subtask["id"] in self._pending_subtasks
            ], return_exceptions=True)

            # Log summary
            completed = sum(1 for r in results if r == "completed")
            reassigned = sum(1 for r in results if r == "reassigned")
            timeouts = sum(1 for r in results if r == "timeout")
            errors = sum(1 for r in results if isinstance(r, Exception))

            logger.info(
                "task_completion_summary",
                task_id=task_id,
                total=len(subtasks),
                completed=completed,
                reassigned=reassigned,
                timeouts=timeouts,
                errors=errors
            )

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

            # Record success in circuit breaker
            await circuit_breaker.record_success(node_id)

            # Update reputation (async)
            from .reputation import reputation_system
            asyncio.create_task(
                reputation_system.record_task_completed(
                    node_id,
                    payload.execution_time_ms
                )
            )

            # Complete the stream with final response
            await streaming_manager.complete_stream(
                payload.task_id,
                final_response=response
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

        # Record failure in circuit breaker
        await circuit_breaker.record_failure(node_id)

        # Notify streaming manager of error
        await streaming_manager.complete_stream(
            payload.task_id,
            error=f"{payload.error_code}: {payload.error_message}"
        )

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

    async def handle_task_stream(
        self,
        node_id: str,
        message: ProtocolMessage
    ) -> None:
        """Handle a streaming chunk from a node."""
        payload = parse_payload(message, TaskStreamPayload)

        try:
            # Get the node's public key
            node = node_registry.get_node(node_id)
            if not node:
                logger.error("unknown_node_for_stream", node_id=node_id)
                return

            # Decrypt the chunk
            chunk = coordinator_crypto.decrypt_from_node(
                node.public_key,
                payload.encrypted_chunk
            )

            logger.info(
                "stream_chunk_received_from_node",
                task_id=payload.task_id,
                subtask_id=payload.subtask_id,
                chunk_index=payload.chunk_index,
                chunk_length=len(chunk),
                node_id=node_id
            )

            # Push chunk to streaming manager
            success = await streaming_manager.push_chunk(payload.task_id, chunk)

            if not success:
                logger.warning(
                    "stream_chunk_push_failed",
                    task_id=payload.task_id,
                    chunk_index=payload.chunk_index
                )

        except Exception as e:
            logger.error(
                "stream_chunk_processing_failed",
                subtask_id=payload.subtask_id,
                error=str(e)
            )


# Global task orchestrator instance
task_orchestrator = TaskOrchestrator()
