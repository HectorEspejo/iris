"""
Iris Node Agent - Main Application

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
    TaskStreamPayload,
    ClassifyAssignPayload,
    ClassifyResultPayload,
    ClassifyErrorPayload,
    parse_payload,
)
from .crypto import node_crypto
from .lmstudio_client import LMStudioClient
from .heartbeat import HeartbeatManager
from .gpu_info import detect_gpu, GPUDetector
from .model_info import parse_model_info, detect_vision_support

# Configure logging
import logging
logging.basicConfig(
    format="%(message)s",
    level=logging.INFO,
)

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
        coordinator_url: str = "ws://168.119.10.189:8000/nodes/connect",
        lmstudio_url: str = "http://localhost:1234/v1",
        key_path: str = "data/node.key",
        account_key: Optional[str] = None,
        enrollment_token: Optional[str] = None  # Deprecated, use account_key
    ):
        self.node_id = node_id
        self.coordinator_url = coordinator_url
        self.lmstudio_url = lmstudio_url
        self.key_path = key_path
        self.account_key = account_key
        self.enrollment_token = enrollment_token  # Deprecated

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

    async def _run_benchmark(self) -> None:
        """
        Run a quick benchmark to measure tokens/second.

        Sends a short prompt to the model and measures generation speed.
        This ensures the node registers with accurate performance metrics.
        """
        logger.info("running_benchmark", message="Measuring tokens/second...")

        benchmark_prompt = "Count from 1 to 20, one number per line."

        try:
            start_time = time.time()
            tokens_generated = 0

            def on_token(chunk: str, count: int):
                nonlocal tokens_generated
                tokens_generated = count

            # Run benchmark with 30 second timeout
            await self._lm_client.simple_completion_stream(
                benchmark_prompt,
                timeout=30.0,
                max_tokens=100,
                on_token=on_token
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # Calculate tokens/second
            if elapsed_ms > 0 and tokens_generated > 0:
                self._tokens_per_second = tokens_generated / (elapsed_ms / 1000)
                self._total_tokens = tokens_generated
                self._total_time_ms = int(elapsed_ms)

            logger.info(
                "benchmark_complete",
                tokens_generated=tokens_generated,
                elapsed_ms=round(elapsed_ms, 2),
                tokens_per_second=round(self._tokens_per_second, 2)
            )

        except asyncio.TimeoutError:
            logger.warning("benchmark_timeout", message="Benchmark timed out, using default tps=0")
            self._tokens_per_second = 0.0

        except Exception as e:
            logger.warning("benchmark_failed", error=str(e), message="Using default tps=0")
            self._tokens_per_second = 0.0

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

        # Run benchmark to measure tokens/second
        await self._run_benchmark()

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

        # Debug: Log account key status
        if self.account_key:
            logger.info(
                "registering_with_account_key",
                key_prefix=self.account_key[:4] if len(self.account_key) >= 4 else "???",
                key_length=len(self.account_key)
            )
        else:
            logger.warning("registering_without_account_key")

        # Detect if model supports vision/image processing
        # Primary: Check LM Studio API for vision capability
        supports_vision = await self._lm_client.supports_vision()

        # Fallback: Use pattern matching on model name if API didn't detect
        if not supports_vision:
            supports_vision = detect_vision_support(model_name)
            if supports_vision:
                logger.info(
                    "vision_detected_via_pattern_fallback",
                    model=model_name
                )

        if supports_vision:
            logger.info(
                "vision_capable_model_detected",
                model=model_name,
                message="This node can process images"
            )
        else:
            logger.info(
                "model_does_not_support_vision",
                model=model_name
            )

        message = ProtocolMessage.create(
            MessageType.NODE_REGISTER,
            NodeRegisterPayload(
                node_id=self.node_id,
                public_key=node_crypto.public_key,
                account_key=self.account_key,  # Mullvad-style account key
                enrollment_token=self.enrollment_token,  # Deprecated, for backwards compatibility
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
                tokens_per_second=self._tokens_per_second,
                supports_vision=supports_vision  # Vision/multimodal capability
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

        elif message.type == MessageType.CLASSIFY_ASSIGN:
            await self._handle_classify_assign(message)

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

            # Execute via LM Studio using streaming
            # Streaming keeps connection alive while tokens are generated,
            # avoiding timeout issues with slow models
            # Check if this task has images (multimodal)
            has_images = bool(payload.images)
            logger.info(
                "executing_inference_stream",
                subtask_id=payload.subtask_id,
                timeout_seconds=payload.timeout_seconds,
                streaming_enabled=payload.enable_streaming,
                has_images=has_images,
                image_count=len(payload.images) if payload.images else 0
            )

            # Track token generation for metrics and streaming
            tokens_generated = 0
            chunk_index = 0

            # For streaming: use a queue to send chunks to coordinator
            # This avoids issues with asyncio.create_task in sync callbacks
            stream_queue: asyncio.Queue = asyncio.Queue() if payload.enable_streaming else None
            stream_task = None

            async def stream_sender():
                """Background task to send stream chunks from the queue."""
                nonlocal chunk_index
                while True:
                    try:
                        chunk_text = await asyncio.wait_for(stream_queue.get(), timeout=0.5)
                        if chunk_text is None:  # Sentinel to stop
                            break
                        encrypted_chunk = node_crypto.encrypt_for_coordinator(chunk_text)
                        stream_message = ProtocolMessage.create(
                            MessageType.TASK_STREAM,
                            TaskStreamPayload(
                                subtask_id=payload.subtask_id,
                                task_id=payload.task_id,
                                encrypted_chunk=encrypted_chunk,
                                chunk_index=chunk_index
                            )
                        )
                        await self._send_message(stream_message)
                        logger.info(
                            "stream_chunk_sent",
                            task_id=payload.task_id,
                            chunk_index=chunk_index,
                            chunk_length=len(chunk_text)
                        )
                        chunk_index += 1
                    except asyncio.TimeoutError:
                        # No chunk available, continue waiting
                        continue
                    except Exception as e:
                        logger.error("stream_sender_error", error=str(e))
                        break

            # Start stream sender if streaming is enabled
            if payload.enable_streaming:
                stream_task = asyncio.create_task(stream_sender())
                logger.info("stream_sender_started", task_id=payload.task_id)

            # Buffer for batching tokens
            chunk_buffer = []
            last_stream_time = time.time()

            def on_token(chunk: str, count: int):
                nonlocal tokens_generated, chunk_buffer, last_stream_time
                tokens_generated = count

                # If streaming is enabled, buffer chunks and send periodically
                if payload.enable_streaming and stream_queue:
                    chunk_buffer.append(chunk)
                    current_time = time.time()
                    # Send every 5 tokens or every 150ms, whichever comes first
                    if len(chunk_buffer) >= 5 or (current_time - last_stream_time) >= 0.15:
                        chunk_text = "".join(chunk_buffer)
                        chunk_buffer.clear()
                        last_stream_time = current_time
                        # Put chunk in queue (non-blocking for sync callback)
                        try:
                            stream_queue.put_nowait(chunk_text)
                        except asyncio.QueueFull:
                            logger.warning("stream_queue_full", task_id=payload.task_id)

            # Convert images to dict format for lmstudio_client
            images_for_lm = None
            if payload.images:
                images_for_lm = [
                    {
                        "mime_type": img.mime_type,
                        "content_base64": img.content_base64
                    }
                    for img in payload.images
                ]
                logger.info(
                    "sending_images_to_model",
                    task_id=payload.task_id,
                    image_count=len(images_for_lm)
                )

            response = await self._lm_client.simple_completion_stream(
                prompt,
                timeout=float(payload.timeout_seconds),
                on_token=on_token,
                images=images_for_lm
            )

            # Send any remaining buffered chunks
            if payload.enable_streaming and chunk_buffer and stream_queue:
                try:
                    stream_queue.put_nowait("".join(chunk_buffer))
                except asyncio.QueueFull:
                    pass

            # Stop the stream sender
            if payload.enable_streaming and stream_queue:
                await stream_queue.put(None)  # Sentinel to stop
                if stream_task:
                    try:
                        await asyncio.wait_for(stream_task, timeout=5.0)
                    except asyncio.TimeoutError:
                        stream_task.cancel()
                logger.info("stream_sender_stopped", task_id=payload.task_id, chunks_sent=chunk_index)

            logger.debug(
                "inference_complete",
                subtask_id=payload.subtask_id,
                tokens_generated=tokens_generated,
                chunks_sent=chunk_index if payload.enable_streaming else 0
            )

            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Update tokens/second metric using actual token count from stream
            # tokens_generated comes from the streaming callback
            actual_tokens = tokens_generated if tokens_generated > 0 else len(response) // 4
            self._total_tokens += actual_tokens
            self._total_time_ms += execution_time_ms
            if self._total_time_ms > 0:
                self._tokens_per_second = (
                    self._total_tokens / (self._total_time_ms / 1000)
                )

            # Encrypt response
            encrypted_response = node_crypto.encrypt_for_coordinator(response)

            # Send final result
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
                tokens_generated=actual_tokens,
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

    async def _handle_classify_assign(self, message: ProtocolMessage) -> None:
        """Handle a classification task from the coordinator."""
        payload = parse_payload(message, ClassifyAssignPayload)

        logger.info(
            "classify_task_received",
            classify_id=payload.classify_id
        )

        # Execute classification in background
        task = asyncio.create_task(
            self._execute_classification(payload)
        )
        self._current_tasks[f"classify_{payload.classify_id}"] = task

        task.add_done_callback(
            lambda t: self._current_tasks.pop(f"classify_{payload.classify_id}", None)
        )

    async def _execute_classification(
        self,
        payload: ClassifyAssignPayload
    ) -> None:
        """Execute a classification task."""
        start_time = time.time()

        try:
            # Decrypt the prompt
            prompt = node_crypto.decrypt_from_coordinator(
                payload.encrypted_prompt
            )

            logger.debug(
                "classify_prompt_decrypted",
                classify_id=payload.classify_id
            )

            # Execute via LM Studio with tight timeout
            # Use lower max_tokens for classification (only need one word)
            logger.info(
                "executing_classification",
                classify_id=payload.classify_id,
                timeout_seconds=payload.timeout_seconds
            )

            response = await self._lm_client.simple_completion_stream(
                prompt,
                timeout=float(payload.timeout_seconds),
                max_tokens=20  # Only need one word: SIMPLE/COMPLEX/ADVANCED
            )

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Encrypt response
            encrypted_response = node_crypto.encrypt_for_coordinator(response)

            # Send result
            result_message = ProtocolMessage.create(
                MessageType.CLASSIFY_RESULT,
                ClassifyResultPayload(
                    classify_id=payload.classify_id,
                    encrypted_response=encrypted_response,
                    execution_time_ms=execution_time_ms
                )
            )
            await self._send_message(result_message)

            logger.info(
                "classify_completed",
                classify_id=payload.classify_id,
                execution_time_ms=execution_time_ms,
                response=response[:50]  # Log first 50 chars
            )

        except asyncio.TimeoutError:
            await self._send_classify_error(
                payload,
                "TIMEOUT",
                f"Classification exceeded timeout of {payload.timeout_seconds}s"
            )

        except Exception as e:
            await self._send_classify_error(
                payload,
                "EXECUTION_ERROR",
                str(e)
            )

    async def _send_classify_error(
        self,
        payload: ClassifyAssignPayload,
        error_code: str,
        error_message: str
    ) -> None:
        """Send a classification error message."""
        error_msg = ProtocolMessage.create(
            MessageType.CLASSIFY_ERROR,
            ClassifyErrorPayload(
                classify_id=payload.classify_id,
                error_code=error_code,
                error_message=error_message
            )
        )
        await self._send_message(error_msg)
        logger.error(
            "classify_failed",
            classify_id=payload.classify_id,
            error_code=error_code
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
        "ws://168.119.10.189:8000/nodes/connect"  # Default production coordinator
    )
    lmstudio_url = os.environ.get(
        "LMSTUDIO_URL",
        "http://localhost:1234/v1"
    )
    key_path = os.environ.get(
        "NODE_KEY_PATH",
        "data/node.key"
    )

    # Mullvad-style account key (primary authentication)
    account_key = os.environ.get("IRIS_ACCOUNT_KEY")

    # Deprecated: enrollment token (for backwards compatibility)
    enrollment_token = os.environ.get("ENROLLMENT_TOKEN")

    # Validate that at least one authentication method is provided
    if not account_key and not enrollment_token:
        logger.error(
            "no_authentication_provided",
            message="IRIS_ACCOUNT_KEY environment variable is required"
        )
        print("\n" + "="*60)
        print("ERROR: Account key required")
        print("="*60)
        print("\nTo run a node, you need an account key.")
        print("Generate one with: iris account generate")
        print("\nThen set the environment variable:")
        print('  export IRIS_ACCOUNT_KEY="1234 5678 9012 3456"')
        print("="*60 + "\n")
        sys.exit(1)

    agent = NodeAgent(
        node_id=node_id,
        coordinator_url=coordinator_url,
        lmstudio_url=lmstudio_url,
        key_path=key_path,
        account_key=account_key,
        enrollment_token=enrollment_token
    )

    try:
        await agent.start()
    except KeyboardInterrupt:
        pass
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
