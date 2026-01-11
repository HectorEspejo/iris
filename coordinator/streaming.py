"""
Iris Streaming Manager

Manages streaming queues for real-time response delivery to clients.
"""

import asyncio
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
import structlog

logger = structlog.get_logger()


@dataclass
class StreamingTask:
    """Represents a streaming task with its queue and metadata."""
    task_id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    created_at: datetime = field(default_factory=datetime.utcnow)
    chunks_received: int = 0
    is_complete: bool = False
    final_response: Optional[str] = None
    error: Optional[str] = None


class StreamingManager:
    """
    Manages streaming queues for tasks.

    When a streaming task is created, clients can subscribe to receive
    chunks as they arrive from nodes.
    """

    def __init__(self):
        self._tasks: dict[str, StreamingTask] = {}
        self._cleanup_interval = 300  # Clean up old tasks every 5 minutes
        self._task_ttl = 600  # Tasks expire after 10 minutes

    def create_stream(self, task_id: str) -> StreamingTask:
        """
        Create a new streaming task.

        Args:
            task_id: The task ID to stream

        Returns:
            StreamingTask instance
        """
        if task_id in self._tasks:
            logger.warning("stream_already_exists", task_id=task_id)
            return self._tasks[task_id]

        stream_task = StreamingTask(task_id=task_id)
        self._tasks[task_id] = stream_task

        logger.info("stream_created", task_id=task_id, active_streams=len(self._tasks))
        return stream_task

    def get_stream(self, task_id: str) -> Optional[StreamingTask]:
        """Get an existing streaming task."""
        stream = self._tasks.get(task_id)
        if stream:
            logger.info("stream_retrieved", task_id=task_id, chunks_received=stream.chunks_received)
        else:
            logger.warning("stream_not_found", task_id=task_id, available_streams=list(self._tasks.keys()))
        return stream

    async def push_chunk(self, task_id: str, chunk: str) -> bool:
        """
        Push a chunk to a streaming task's queue.

        Args:
            task_id: The task ID
            chunk: The text chunk to push

        Returns:
            True if successful, False if task not found
        """
        stream_task = self._tasks.get(task_id)
        if not stream_task:
            logger.warning("stream_not_found_for_chunk", task_id=task_id, available_streams=list(self._tasks.keys()))
            return False

        await stream_task.queue.put({"type": "chunk", "content": chunk})
        stream_task.chunks_received += 1

        logger.info(
            "chunk_pushed",
            task_id=task_id,
            chunks_received=stream_task.chunks_received,
            chunk_preview=chunk[:50] if len(chunk) > 50 else chunk
        )
        return True

    async def complete_stream(
        self,
        task_id: str,
        final_response: Optional[str] = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Mark a streaming task as complete.

        Args:
            task_id: The task ID
            final_response: The complete response (if successful)
            error: Error message (if failed)

        Returns:
            True if successful, False if task not found
        """
        stream_task = self._tasks.get(task_id)
        if not stream_task:
            logger.warning("stream_not_found_for_complete", task_id=task_id)
            return False

        stream_task.is_complete = True
        stream_task.final_response = final_response
        stream_task.error = error

        # Send completion signal
        if error:
            await stream_task.queue.put({"type": "error", "content": error})
        else:
            await stream_task.queue.put({"type": "done", "content": final_response})

        logger.debug(
            "stream_completed",
            task_id=task_id,
            chunks_received=stream_task.chunks_received,
            has_error=error is not None
        )
        return True

    def remove_stream(self, task_id: str) -> bool:
        """Remove a streaming task."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.debug("stream_removed", task_id=task_id)
            return True
        return False

    async def cleanup_old_streams(self):
        """Remove expired streaming tasks."""
        now = datetime.utcnow()
        expired = []

        for task_id, stream_task in self._tasks.items():
            age = (now - stream_task.created_at).total_seconds()
            if age > self._task_ttl:
                expired.append(task_id)

        for task_id in expired:
            self.remove_stream(task_id)

        if expired:
            logger.info("streams_cleaned_up", count=len(expired))

    @property
    def active_streams(self) -> int:
        """Get the number of active streaming tasks."""
        return len(self._tasks)


# Global instance
streaming_manager = StreamingManager()
