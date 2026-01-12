"""
Iris Node Heartbeat

Manages periodic heartbeat messages to the coordinator.
"""

import asyncio
from datetime import datetime
from typing import Optional, Callable, Awaitable
import structlog

from shared.protocol import (
    MessageType,
    ProtocolMessage,
    NodeHeartbeatPayload,
)

logger = structlog.get_logger()

# Default heartbeat interval
DEFAULT_HEARTBEAT_INTERVAL = 30  # seconds


class HeartbeatManager:
    """
    Manages periodic heartbeat messages to keep the connection alive
    and report node status to the coordinator.
    """

    def __init__(
        self,
        node_id: str,
        interval: int = DEFAULT_HEARTBEAT_INTERVAL
    ):
        self.node_id = node_id
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._send_callback: Optional[Callable[[ProtocolMessage], Awaitable[None]]] = None
        self._get_load_callback: Optional[Callable[[], int]] = None
        self._start_time = datetime.utcnow()
        self._last_sent: Optional[datetime] = None
        self._last_ack: Optional[datetime] = None

    @property
    def uptime_seconds(self) -> int:
        """Get the node's uptime in seconds."""
        return int((datetime.utcnow() - self._start_time).total_seconds())

    @property
    def is_running(self) -> bool:
        """Check if heartbeat is running."""
        return self._running

    def set_send_callback(
        self,
        callback: Callable[[ProtocolMessage], Awaitable[None]]
    ) -> None:
        """
        Set the callback for sending messages.

        Args:
            callback: Async function that sends a ProtocolMessage
        """
        self._send_callback = callback

    def set_load_callback(self, callback: Callable[[], int]) -> None:
        """
        Set the callback for getting current load.

        Args:
            callback: Function that returns current task count
        """
        self._get_load_callback = callback

    def start(self) -> None:
        """Start the heartbeat loop."""
        if self._running:
            logger.warning("heartbeat_already_running", node_id=self.node_id)
            return

        self._running = True
        self._start_time = datetime.utcnow()
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            "heartbeat_started",
            node_id=self.node_id,
            interval=self.interval
        )

    def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("heartbeat_stopped", node_id=self.node_id)

    def acknowledge(self) -> None:
        """Record receipt of heartbeat acknowledgment."""
        self._last_ack = datetime.utcnow()
        logger.debug("heartbeat_acknowledged", node_id=self.node_id)

    async def _heartbeat_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                await self._send_heartbeat()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "heartbeat_error",
                    node_id=self.node_id,
                    error=str(e)
                )
                # Wait a bit before retrying
                await asyncio.sleep(5)

    async def _send_heartbeat(self) -> None:
        """Send a single heartbeat message."""
        if not self._send_callback:
            logger.warning("no_send_callback", node_id=self.node_id)
            return

        # Get current load
        current_load = 0
        if self._get_load_callback:
            current_load = self._get_load_callback()

        # Create heartbeat message with timestamp for latency measurement
        message = ProtocolMessage.create(
            MessageType.NODE_HEARTBEAT,
            NodeHeartbeatPayload(
                node_id=self.node_id,
                current_load=current_load,
                uptime_seconds=self.uptime_seconds,
                sent_at=datetime.utcnow()
            )
        )

        # Send via callback
        await self._send_callback(message)
        self._last_sent = datetime.utcnow()

        logger.debug(
            "heartbeat_sent",
            node_id=self.node_id,
            load=current_load,
            uptime=self.uptime_seconds
        )

    def get_status(self) -> dict:
        """Get heartbeat status information."""
        return {
            "node_id": self.node_id,
            "running": self._running,
            "interval": self.interval,
            "uptime_seconds": self.uptime_seconds,
            "last_sent": self._last_sent.isoformat() if self._last_sent else None,
            "last_ack": self._last_ack.isoformat() if self._last_ack else None
        }
