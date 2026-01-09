"""
Iris Reputation System

Tracks and manages node reputation scores based on performance.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import structlog

from shared.models import ReputationChangeReason
from .database import db

logger = structlog.get_logger()

# Reputation constants
INITIAL_REPUTATION = 100.0
MIN_REPUTATION = 10.0

# Points for various events
TASK_COMPLETED_POINTS = 10.0
TASK_FAST_BONUS = 5.0
TASK_TIMEOUT_PENALTY = -20.0
TASK_INVALID_PENALTY = -50.0
UPTIME_HOUR_BONUS = 1.0
UPTIME_BROKEN_PENALTY = -5.0
WEEKLY_DECAY_PERCENT = 0.01  # 1%

# Threshold for "fast" completion (median should be calculated dynamically)
FAST_THRESHOLD_MS = 30000  # 30 seconds


class ReputationSystem:
    """
    Manages node reputation scores.

    Reputation changes:
    - +10 pts: Task completed successfully
    - +5 pts bonus: Faster than threshold
    - -20 pts: Task timeout
    - -50 pts: Invalid/corrupt response
    - +1 pt/hour: Uptime bonus
    - -5 pts/hour: Promised but disconnected
    - -1% weekly: Decay to encourage activity
    """

    def __init__(self):
        self._uptime_tracker: dict[str, datetime] = {}

    async def get_reputation(self, node_id: str) -> float:
        """Get current reputation for a node."""
        node = await db.get_node_by_id(node_id)
        if node:
            return node.get("reputation", INITIAL_REPUTATION)
        return INITIAL_REPUTATION

    async def _update_reputation(
        self,
        node_id: str,
        change: float,
        reason: ReputationChangeReason
    ) -> float:
        """
        Update a node's reputation.

        Args:
            node_id: Node ID
            change: Points to add/subtract
            reason: Reason for change

        Returns:
            New reputation value
        """
        # Get current reputation
        current = await self.get_reputation(node_id)

        # Calculate new reputation (with minimum)
        new_reputation = max(MIN_REPUTATION, current + change)

        # Update in database
        await db.update_node_reputation(node_id, new_reputation)

        # Log the change
        await db.log_reputation_change(node_id, change, reason.value)

        logger.info(
            "reputation_updated",
            node_id=node_id,
            change=change,
            reason=reason.value,
            old=current,
            new=new_reputation
        )

        return new_reputation

    async def record_task_completed(
        self,
        node_id: str,
        execution_time_ms: int,
        threshold_ms: int = FAST_THRESHOLD_MS
    ) -> float:
        """
        Record a successful task completion.

        Args:
            node_id: Node that completed the task
            execution_time_ms: Time taken in milliseconds
            threshold_ms: Threshold for fast bonus

        Returns:
            New reputation value
        """
        # Base points for completion
        change = TASK_COMPLETED_POINTS

        # Fast bonus
        if execution_time_ms < threshold_ms:
            change += TASK_FAST_BONUS
            reason = ReputationChangeReason.TASK_FAST
            logger.debug(
                "fast_completion_bonus",
                node_id=node_id,
                execution_time_ms=execution_time_ms
            )
        else:
            reason = ReputationChangeReason.TASK_COMPLETED

        # Update task count
        await db.increment_node_tasks(node_id)

        return await self._update_reputation(node_id, change, reason)

    async def record_task_timeout(self, node_id: str) -> float:
        """
        Record a task timeout.

        Args:
            node_id: Node that timed out

        Returns:
            New reputation value
        """
        return await self._update_reputation(
            node_id,
            TASK_TIMEOUT_PENALTY,
            ReputationChangeReason.TASK_TIMEOUT
        )

    async def record_task_failed(
        self,
        node_id: str,
        error_code: str
    ) -> float:
        """
        Record a task failure.

        Args:
            node_id: Node that failed
            error_code: Error code from the failure

        Returns:
            New reputation value
        """
        # Different penalties based on error type
        if error_code in ("INVALID_RESPONSE", "DECRYPTION_FAILED"):
            penalty = TASK_INVALID_PENALTY
            reason = ReputationChangeReason.TASK_INVALID
        else:
            penalty = TASK_TIMEOUT_PENALTY  # Generic failure
            reason = ReputationChangeReason.TASK_TIMEOUT

        return await self._update_reputation(node_id, penalty, reason)

    async def record_uptime_hour(self, node_id: str) -> float:
        """
        Record an hour of uptime.

        Args:
            node_id: Node that was online

        Returns:
            New reputation value
        """
        return await self._update_reputation(
            node_id,
            UPTIME_HOUR_BONUS,
            ReputationChangeReason.UPTIME_HOUR
        )

    async def record_broken_promise(
        self,
        node_id: str,
        hours: int = 1
    ) -> float:
        """
        Record hours where node promised to be online but wasn't.

        Args:
            node_id: Node that broke promise
            hours: Number of hours

        Returns:
            New reputation value
        """
        penalty = UPTIME_BROKEN_PENALTY * hours
        return await self._update_reputation(
            node_id,
            penalty,
            ReputationChangeReason.UPTIME_BROKEN
        )

    async def apply_weekly_decay(self) -> dict[str, float]:
        """
        Apply weekly decay to all nodes.

        Should be called once per week by a scheduler.

        Returns:
            Dictionary of node_id -> new reputation
        """
        nodes = await db.get_all_nodes()
        results = {}

        for node in nodes:
            node_id = node["id"]
            current = node.get("reputation", INITIAL_REPUTATION)

            # Calculate decay
            decay = current * WEEKLY_DECAY_PERCENT

            # Apply (with minimum)
            new_reputation = max(MIN_REPUTATION, current - decay)

            if new_reputation != current:
                await db.update_node_reputation(node_id, new_reputation)
                await db.log_reputation_change(
                    node_id,
                    -decay,
                    ReputationChangeReason.WEEKLY_DECAY.value
                )
                results[node_id] = new_reputation

        logger.info("weekly_decay_applied", nodes_affected=len(results))
        return results

    def track_node_online(self, node_id: str) -> None:
        """Start tracking uptime for a node."""
        self._uptime_tracker[node_id] = datetime.utcnow()

    def track_node_offline(self, node_id: str) -> Optional[int]:
        """
        Stop tracking uptime and return hours online.

        Args:
            node_id: Node going offline

        Returns:
            Hours online, or None if not tracked
        """
        start = self._uptime_tracker.pop(node_id, None)
        if start:
            duration = datetime.utcnow() - start
            return int(duration.total_seconds() // 3600)
        return None

    async def get_leaderboard(self, limit: int = 20) -> list[dict]:
        """
        Get reputation leaderboard.

        Args:
            limit: Maximum number of entries

        Returns:
            List of nodes with reputation info
        """
        nodes = await db.get_all_nodes()

        # Sort by reputation
        sorted_nodes = sorted(
            nodes,
            key=lambda n: n.get("reputation", 0),
            reverse=True
        )[:limit]

        return [
            {
                "rank": i + 1,
                "node_id": n["id"],
                "reputation": n.get("reputation", INITIAL_REPUTATION),
                "tasks_completed": n.get("total_tasks_completed", 0),
                "model_name": n.get("model_name", "unknown")
            }
            for i, n in enumerate(sorted_nodes)
        ]

    async def get_node_history(
        self,
        node_id: str,
        limit: int = 50
    ) -> list[dict]:
        """
        Get reputation history for a node.

        Args:
            node_id: Node ID
            limit: Maximum entries

        Returns:
            List of reputation changes
        """
        return await db.get_reputation_history(node_id, limit)


# Global reputation system instance
reputation_system = ReputationSystem()
