"""
ClubAI Node Agent - Main Application

Agent that runs on each node to connect to the coordinator
and execute inference tasks using LM Studio.
"""

import asyncio
import os
import sys
import time
from typing import Optional
import websockets
import structlog

from shared.protocol import (
    MessageType,
    ProtocolMessage,
    NodeRegisterPayload,
    RegisterAckPayload,
    TaskAssignPayload,
    TaskResultPayload,
    TaskErrorPayload,
    parse_payload,
)
from .crypto import node_crypto
from .lmstudio_client import LMStudioClient
from .heartbeat import HeartbeatManager
from .gpu_info import detect_gpu, GPUDetector
from .model_info import parse_model_info

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class NodeAgent:
    """
    Node agent that connects to the coordinator and executes inference tasks.

    The agent:
    1. Connects to the coordinator via WebSocket
    2. Registers with its capabilities
    3. Sends periodic heartbeats
    4. Receives and executes tasks
    5. Returns results to the coordinator
    """

    def __init__(
        self,
        node_id: str,
        coordinator_url: str,
        lmstudio_url: str = "http://localhost:1234/v1",
        key_path: str = "data/node.key"
    ):
        self.node_id = node_id
        self.coordinator_url = coordinator_url
        self.lmstudio_url = lmstudio_url
        self.key_path = key_path

        self._ws = None  # WebSocket connection
        self._lm_client: Optional[LMStudioClient] = None
        self._heartbeat: Optional[HeartbeatManager] = None
        self._running = False
        self._current_tasks: dict[str, asyncio.Task] = {}
        self._reconnect_delay = 1  # Start with 1 second

        # Extended capabilities
        self._gpu_info = None
        self._model_info = None
        self._tokens_per_second: float = 0.0
        self._total_tokens: int = 0
        self._total_time_ms: int = 0

    @property
    def current_load(self) -> int:
        """Get the number of currently executing tasks."""
        return len(self._current_tasks)

    async def start(self) -> None:
        """Start the node agent."""
        logger.info(
            "node_agent_starting",
            node_id=self.node_id,
            coordinator=self.coordinator_url
        )

        # Initialize crypto
        node_crypto.key_path = self.key_path
        node_crypto.initialize()

        # Initialize LM Studio client
        self._lm_client = LMStudioClient(base_url=self.lmstudio_url)
        await self._lm_client.connect()

        # Check LM Studio health
        if not await self._lm_client.health_check():
            logger.error("lmstudio_not_available", url=self.lmstudio_url)
            raise RuntimeError("LM Studio is not available")

        # Get model info
        model_name = await self._lm_client.get_loaded_model()
        logger.info("lmstudio_connected", model=model_name)

        # Detect GPU
        self._gpu_info = detect_gpu()
        logger.info(
            "gpu_detected",
            name=self._gpu_info.name,
            vram_gb=self._gpu_info.vram_total_gb
        )

        # Parse model information
        self._model_info = parse_model_info(model_name or "unknown")
        logger.info(
            "model_parsed",
            params_b=self._model_info.params_billions,
            quantization=self._model_info.quantization
        )

        # Initialize heartbeat
        self._heartbeat = HeartbeatManager(self.node_id)
        self._heartbeat.set_load_callback(lambda: self.current_load)

        # Start connection loop
        self._running = True
        await self._connection_loop()

    async def stop(self) -> None:
        """Stop the node agent gracefully."""
        logger.info("node_agent_stopping", node_id=self.node_id)
        self._running = False

        # Stop heartbeat
        if self._heartbeat:
            self._heartbeat.stop()

        # Cancel running tasks
        for task in self._current_tasks.values():
            task.cancel()
        self._current_tasks.clear()

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        # Close LM Studio client
        if self._lm_client:
            await self._lm_client.disconnect()

        logger.info("node_agent_stopped", node_id=self.node_id)

    async def _connection_loop(self) -> None:
        """Main connection loop with reconnection logic."""
        while self._running:
            try:
                await self._connect_and_run()
            except websockets.ConnectionClosed as e:
                logger.warning(
                    "connection_closed",
                    code=e.code,
                    reason=e.reason
                )
            except Exception as e:
                logger.error("connection_error", error=str(e))

            if self._running:
                # Exponential backoff for reconnection
                logger.info(
                    "reconnecting",
                    delay=self._reconnect_delay
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

    async def _connect_and_run(self) -> None:
        """Connect to coordinator and run message loop."""
        async with websockets.connect(self.coordinator_url) as ws:
            self._ws = ws
            self._reconnect_delay = 1  # Reset delay on successful connection

            # Register with coordinator
            if not await self._register():
                logger.error("registration_failed")
                return

            # Start heartbeat
            self._heartbeat.set_send_callback(self._send_message)
            self._heartbeat.start()

            # Message loop
            try:
                await self._message_loop()
            finally:
                self._heartbeat.stop()

    async def _register(self) -> bool:
        """Register this node with the coordinator."""
        model_name = await self._lm_client.get_loaded_model() or "unknown"

        # Use detected GPU info or fallback to env var
        vram_gb = self._gpu_info.vram_total_gb if self._gpu_info else float(
            os.environ.get("NODE_VRAM_GB", "8")
        )

        message = ProtocolMessage.create(
            MessageType.NODE_REGISTER,
            NodeRegisterPayload(
                node_id=self.node_id,
                public_key=node_crypto.public_key,
                lmstudio_port=int(self.lmstudio_url.split(":")[-1].split("/")[0]),
                model_name=model_name,
                max_context=8192,  # TODO: Get from LM Studio
                vram_gb=vram_gb,
                available_hours=list(range(24)),  # Available 24/7
                # Extended capabilities
                gpu_name=self._gpu_info.name if self._gpu_info else "Unknown",
                gpu_vram_free=self._gpu_info.vram_free_gb if self._gpu_info else 0.0,
                model_params=self._model_info.params_billions if self._model_info else 7.0,
                model_quantization=self._model_info.quantization if self._model_info else "Q4",
                tokens_per_second=self._tokens_per_second
            )
        )

        await self._send_message(message)

        # Wait for acknowledgment
        try:
            response = await asyncio.wait_for(
                self._ws.recv(),
                timeout=10.0
            )
            msg = ProtocolMessage.from_json(response)

            if msg.type == MessageType.REGISTER_ACK:
                payload = parse_payload(msg, RegisterAckPayload)
                if payload.success:
                    node_crypto.set_coordinator_public_key(
                        payload.coordinator_public_key
                    )
                    logger.info("registered_with_coordinator")
                    return True
                else:
                    logger.error(
                        "registration_rejected",
                        message=payload.message
                    )
        except asyncio.TimeoutError:
            logger.error("registration_timeout")

        return False

    async def _message_loop(self) -> None:
        """Process incoming messages from the coordinator."""
        async for message in self._ws:
            try:
                msg = ProtocolMessage.from_json(message)
                await self._handle_message(msg)
            except Exception as e:
                logger.error("message_handling_error", error=str(e))

    async def _handle_message(self, message: ProtocolMessage) -> None:
        """Handle a single message from the coordinator."""
        if message.type == MessageType.HEARTBEAT_ACK:
            self._heartbeat.acknowledge()

        elif message.type == MessageType.TASK_ASSIGN:
            await self._handle_task_assign(message)

        elif message.type == MessageType.ERROR:
            logger.error("coordinator_error", payload=message.payload)

        else:
            logger.warning("unknown_message_type", type=message.type)

    async def _handle_task_assign(self, message: ProtocolMessage) -> None:
        """Handle a task assignment from the coordinator."""
        payload = parse_payload(message, TaskAssignPayload)

        logger.info(
            "task_received",
            subtask_id=payload.subtask_id,
            task_id=payload.task_id
        )

        # Execute task in background
        task = asyncio.create_task(
            self._execute_task(payload)
        )
        self._current_tasks[payload.subtask_id] = task

        # Clean up when done
        task.add_done_callback(
            lambda t: self._current_tasks.pop(payload.subtask_id, None)
        )

    async def _execute_task(self, payload: TaskAssignPayload) -> None:
        """Execute an assigned task."""
        start_time = time.time()

        try:
            # Decrypt the prompt
            prompt = node_crypto.decrypt_from_coordinator(
                payload.encrypted_prompt
            )

            logger.debug("task_decrypted", subtask_id=payload.subtask_id)

            # Execute via LM Studio
            response = await asyncio.wait_for(
                self._lm_client.simple_completion(prompt),
                timeout=payload.timeout_seconds
            )

            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Update tokens/second metric (rough estimate: ~4 chars per token)
            estimated_tokens = len(response) // 4
            self._total_tokens += estimated_tokens
            self._total_time_ms += execution_time_ms
            if self._total_time_ms > 0:
                self._tokens_per_second = (
                    self._total_tokens / (self._total_time_ms / 1000)
                )

            # Encrypt response
            encrypted_response = node_crypto.encrypt_for_coordinator(response)

            # Send result
            result_message = ProtocolMessage.create(
                MessageType.TASK_RESULT,
                TaskResultPayload(
                    subtask_id=payload.subtask_id,
                    task_id=payload.task_id,
                    encrypted_response=encrypted_response,
                    execution_time_ms=execution_time_ms
                )
            )
            await self._send_message(result_message)

            logger.info(
                "task_completed",
                subtask_id=payload.subtask_id,
                execution_time_ms=execution_time_ms,
                tokens_per_second=round(self._tokens_per_second, 2)
            )

        except asyncio.TimeoutError:
            await self._send_task_error(
                payload,
                "TIMEOUT",
                f"Task exceeded timeout of {payload.timeout_seconds}s"
            )

        except Exception as e:
            await self._send_task_error(
                payload,
                "EXECUTION_ERROR",
                str(e)
            )

    async def _send_task_error(
        self,
        payload: TaskAssignPayload,
        error_code: str,
        error_message: str
    ) -> None:
        """Send a task error message."""
        error_msg = ProtocolMessage.create(
            MessageType.TASK_ERROR,
            TaskErrorPayload(
                subtask_id=payload.subtask_id,
                task_id=payload.task_id,
                error_code=error_code,
                error_message=error_message
            )
        )
        await self._send_message(error_msg)
        logger.error(
            "task_failed",
            subtask_id=payload.subtask_id,
            error_code=error_code,
            error_message=error_message
        )

    async def _send_message(self, message: ProtocolMessage) -> None:
        """Send a message to the coordinator."""
        if self._ws:
            await self._ws.send(message.to_json())


async def main():
    """Entry point for the node agent."""
    # Configuration from environment
    node_id = os.environ.get("NODE_ID", f"node-{os.getpid()}")
    coordinator_url = os.environ.get(
        "COORDINATOR_URL",
        "ws://localhost:8000/nodes/connect"
    )
    lmstudio_url = os.environ.get(
        "LMSTUDIO_URL",
        "http://localhost:1234/v1"
    )
    key_path = os.environ.get(
        "NODE_KEY_PATH",
        "data/node.key"
    )

    agent = NodeAgent(
        node_id=node_id,
        coordinator_url=coordinator_url,
        lmstudio_url=lmstudio_url,
        key_path=key_path
    )

    try:
        await agent.start()
    except KeyboardInterrupt:
        pass
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
