"""
Iris Fake Node Agent - OpenRouter Backend

Un node agent que usa OpenRouter API en lugar de LM Studio.
Usado para proporcionar capacidad de inferencia siempre disponible como fallback.

Los fake nodes tienen penalizacion en el sistema de seleccion para que
las tareas vayan preferentemente a nodos reales con account keys.

Configuracion:
    IRIS_ACCOUNT_KEY: Account key para autenticacion
    OPENROUTER_API_KEY: API key de OpenRouter
    OPENROUTER_MODEL: Modelo a usar (ej: "qwen/qwen-2.5-72b-instruct")
    NODE_ID: Identificador unico del nodo
    FAKE_NODE_TPS: TPS reportado (default: 5.0 - bajo para penalizacion)
    FAKE_NODE_ARTIFICIAL_LOAD: Load artificial en heartbeats (default: 3)
    COORDINATOR_URL: URL WebSocket del coordinator
"""

import asyncio
import os
import random
import sys
import time
from typing import Optional
import websockets
import structlog

from shared.protocol import (
    MessageType,
    ProtocolMessage,
    NodeRegisterPayload,
    NodeHeartbeatPayload,
    HeartbeatAckPayload,
    RegisterAckPayload,
    TaskAssignPayload,
    TaskResultPayload,
    TaskErrorPayload,
    TaskStreamPayload,
    parse_payload,
)
from .crypto import node_crypto
from .openrouter_client import OpenRouterClient

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

# Lista de GPUs para simular nodos reales
FAKE_GPU_LIST = [
    # NVIDIA Consumer
    "NVIDIA GeForce RTX 4090",
    "NVIDIA GeForce RTX 4080",
    "NVIDIA GeForce RTX 4070 Ti",
    "NVIDIA GeForce RTX 3090",
    "NVIDIA GeForce RTX 3080 Ti",
    "NVIDIA GeForce RTX 3080",
    "NVIDIA GeForce RTX 3070 Ti",
    # NVIDIA Professional
    "NVIDIA RTX A6000",
    "NVIDIA RTX A5000",
    "NVIDIA RTX A4000",
    # AMD
    "AMD Radeon RX 7900 XTX",
    "AMD Radeon RX 7900 XT",
    "AMD Radeon RX 6950 XT",
    "AMD Radeon RX 6900 XT",
    # Apple Silicon
    "Apple M2 Ultra",
    "Apple M2 Max",
    "Apple M2 Pro",
    "Apple M3 Max",
    "Apple M3 Pro",
]


class FakeNodeAgent:
    """
    Fake node agent que usa OpenRouter en lugar de LM Studio.

    Disenado para tener menor prioridad que nodos reales via:
    - TPS bajo reportado (expected_delay mas alto)
    - Load artificial alto (siempre reporta carga)

    Esto asegura que los nodos reales sean seleccionados preferentemente,
    y los fake nodes solo se usen cuando no hay nodos reales disponibles.
    """

    def __init__(
        self,
        node_id: str,
        model: str,
        coordinator_url: str = "ws://168.119.10.189:8000/nodes/connect",
        api_key: Optional[str] = None,
        account_key: Optional[str] = None,
        reported_tps: float = 5.0,           # TPS bajo = menor prioridad
        artificial_load: int = 3,            # Load artificial = menor prioridad
        reported_vram: float = 24.0,         # VRAM reportado
        reported_params: float = 70.0,       # Params para tier PREMIUM
        key_path: str = "data/fake_node.key"
    ):
        self.node_id = node_id
        self.model = model
        self.coordinator_url = coordinator_url
        self.account_key = account_key
        self.reported_tps = reported_tps
        self.artificial_load = artificial_load
        self.reported_vram = reported_vram
        self.reported_params = reported_params
        self.key_path = key_path
        self.gpu_name = random.choice(FAKE_GPU_LIST)

        self._client = OpenRouterClient(model=model, api_key=api_key)
        self._ws = None
        self._running = False
        self._current_tasks: dict[str, asyncio.Task] = {}
        self._reconnect_delay = 1
        self._heartbeat_task = None
        self._start_time = None

    @property
    def current_load(self) -> int:
        """Carga actual mas load artificial para penalizacion."""
        return len(self._current_tasks) + self.artificial_load

    @property
    def uptime_seconds(self) -> int:
        """Tiempo de uptime en segundos."""
        if self._start_time:
            return int(time.time() - self._start_time)
        return 0

    async def start(self) -> None:
        """Iniciar el fake node agent."""
        logger.info(
            "fake_node_starting",
            node_id=self.node_id,
            model=self.model,
            gpu=self.gpu_name,
            coordinator=self.coordinator_url,
            reported_tps=self.reported_tps,
            artificial_load=self.artificial_load
        )

        self._start_time = time.time()

        # Inicializar crypto
        node_crypto.key_path = self.key_path
        node_crypto.initialize()

        # Inicializar cliente OpenRouter
        await self._client.connect()

        # Verificar que OpenRouter esta accesible
        if not await self._client.health_check():
            logger.error("openrouter_not_available")
            raise RuntimeError("OpenRouter is not available")

        logger.info("openrouter_connected", model=self.model)

        # Iniciar loop de conexion
        self._running = True
        await self._connection_loop()

    async def stop(self) -> None:
        """Detener el fake node agent."""
        logger.info("fake_node_stopping", node_id=self.node_id)
        self._running = False

        # Detener heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Cancelar tareas en ejecucion
        for task in self._current_tasks.values():
            task.cancel()
        self._current_tasks.clear()

        # Cerrar WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        # Cerrar cliente OpenRouter
        await self._client.disconnect()

        logger.info("fake_node_stopped", node_id=self.node_id)

    async def _connection_loop(self) -> None:
        """Loop principal de conexion con logica de reconexion."""
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
                logger.info("reconnecting", delay=self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

    async def _connect_and_run(self) -> None:
        """Conectar al coordinator y ejecutar loop de mensajes."""
        async with websockets.connect(self.coordinator_url) as ws:
            self._ws = ws
            self._reconnect_delay = 1  # Reset delay on successful connection

            # Registrar con coordinator
            if not await self._register():
                logger.error("registration_failed")
                return

            # Iniciar heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # Loop de mensajes
            try:
                await self._message_loop()
            finally:
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()

    async def _register(self) -> bool:
        """Registrar este nodo con el coordinator."""
        if self.account_key:
            logger.info(
                "registering_fake_node_with_account_key",
                key_prefix=self.account_key[:4] if len(self.account_key) >= 4 else "???",
                model=self.model
            )
        else:
            logger.warning("registering_fake_node_without_account_key")

        # Detectar si modelo soporta vision
        supports_vision = await self._client.supports_vision()

        message = ProtocolMessage.create(
            MessageType.NODE_REGISTER,
            NodeRegisterPayload(
                node_id=self.node_id,
                public_key=node_crypto.public_key,
                account_key=self.account_key,
                lmstudio_port=0,  # No LM Studio
                model_name=f"openrouter:{self.model}",  # Prefix para identificar
                max_context=32768,
                vram_gb=self.reported_vram,
                available_hours=list(range(24)),
                gpu_name=self.gpu_name,
                gpu_vram_free=self.reported_vram,
                model_params=self.reported_params,
                model_quantization="FP16",  # OpenRouter usa modelos originales
                tokens_per_second=self.reported_tps,  # TPS bajo = penalizacion
                supports_vision=supports_vision
            )
        )

        await self._send_message(message)

        # Esperar ACK
        try:
            response = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
            msg = ProtocolMessage.from_json(response)

            if msg.type == MessageType.REGISTER_ACK:
                payload = parse_payload(msg, RegisterAckPayload)
                if payload.success:
                    node_crypto.set_coordinator_public_key(payload.coordinator_public_key)
                    logger.info(
                        "fake_node_registered",
                        node_id=self.node_id,
                        model=self.model,
                        tps=self.reported_tps
                    )
                    return True
                else:
                    logger.error("registration_rejected", message=payload.message)
        except asyncio.TimeoutError:
            logger.error("registration_timeout")

        return False

    async def _heartbeat_loop(self) -> None:
        """Enviar heartbeats periodicos."""
        while self._running and self._ws:
            try:
                message = ProtocolMessage.create(
                    MessageType.NODE_HEARTBEAT,
                    NodeHeartbeatPayload(
                        node_id=self.node_id,
                        current_load=self.current_load,  # Incluye load artificial
                        uptime_seconds=self.uptime_seconds,
                        gpu_vram_free=self.reported_vram,
                        tokens_per_second=self.reported_tps,
                        latency_avg_ms=50.0  # Latencia simulada
                    )
                )
                await self._send_message(message)

                logger.debug(
                    "heartbeat_sent",
                    load=self.current_load,
                    uptime=self.uptime_seconds
                )

                await asyncio.sleep(30)  # Heartbeat cada 30 segundos

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))
                await asyncio.sleep(5)

    async def _message_loop(self) -> None:
        """Procesar mensajes entrantes del coordinator."""
        async for message in self._ws:
            try:
                msg = ProtocolMessage.from_json(message)
                await self._handle_message(msg)
            except Exception as e:
                logger.error("message_handling_error", error=str(e))

    async def _handle_message(self, message: ProtocolMessage) -> None:
        """Manejar un mensaje del coordinator."""
        if message.type == MessageType.HEARTBEAT_ACK:
            logger.debug("heartbeat_ack_received")

        elif message.type == MessageType.TASK_ASSIGN:
            await self._handle_task_assign(message)

        elif message.type == MessageType.ERROR:
            logger.error("coordinator_error", payload=message.payload)

        else:
            logger.debug("unknown_message_type", type=message.type)

    async def _handle_task_assign(self, message: ProtocolMessage) -> None:
        """Manejar asignacion de tarea."""
        payload = parse_payload(message, TaskAssignPayload)

        logger.info(
            "task_received",
            subtask_id=payload.subtask_id,
            task_id=payload.task_id,
            streaming=payload.enable_streaming
        )

        # Ejecutar tarea en background
        task = asyncio.create_task(self._execute_task(payload))
        self._current_tasks[payload.subtask_id] = task

        task.add_done_callback(
            lambda t: self._current_tasks.pop(payload.subtask_id, None)
        )

    async def _execute_task(self, payload: TaskAssignPayload) -> None:
        """Ejecutar una tarea asignada via OpenRouter."""
        start_time = time.time()

        try:
            # Desencriptar prompt
            prompt = node_crypto.decrypt_from_coordinator(payload.encrypted_prompt)
            logger.debug("task_decrypted", subtask_id=payload.subtask_id)

            # Verificar si hay archivos (fake nodes no soportan imagenes)
            if payload.files:
                logger.warning(
                    "fake_node_received_files",
                    file_count=len(payload.files),
                    message="Fake nodes do not support images"
                )

            # Tracking para streaming
            tokens_generated = 0
            chunk_index = 0
            stream_queue: asyncio.Queue = asyncio.Queue() if payload.enable_streaming else None
            stream_task = None

            async def stream_sender():
                """Background task para enviar chunks de streaming."""
                nonlocal chunk_index
                while True:
                    try:
                        chunk_text = await asyncio.wait_for(stream_queue.get(), timeout=0.5)
                        if chunk_text is None:
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
                        chunk_index += 1
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error("stream_sender_error", error=str(e))
                        break

            # Iniciar stream sender si streaming habilitado
            if payload.enable_streaming:
                stream_task = asyncio.create_task(stream_sender())

            # Buffer para batching de tokens
            chunk_buffer = []
            last_stream_time = time.time()

            def on_token(chunk: str, count: int):
                nonlocal tokens_generated, chunk_buffer, last_stream_time
                tokens_generated = count

                if payload.enable_streaming and stream_queue:
                    chunk_buffer.append(chunk)
                    current_time = time.time()
                    if len(chunk_buffer) >= 5 or (current_time - last_stream_time) >= 0.15:
                        chunk_text = "".join(chunk_buffer)
                        chunk_buffer.clear()
                        last_stream_time = current_time
                        try:
                            stream_queue.put_nowait(chunk_text)
                        except asyncio.QueueFull:
                            pass

            # Ejecutar via OpenRouter
            logger.info(
                "executing_via_openrouter",
                subtask_id=payload.subtask_id,
                model=self.model,
                timeout=payload.timeout_seconds
            )

            response = await self._client.simple_completion_stream(
                prompt,
                timeout=float(payload.timeout_seconds),
                on_token=on_token
            )

            # Enviar chunks restantes
            if payload.enable_streaming and chunk_buffer and stream_queue:
                try:
                    stream_queue.put_nowait("".join(chunk_buffer))
                except asyncio.QueueFull:
                    pass

            # Detener stream sender
            if payload.enable_streaming and stream_queue:
                await stream_queue.put(None)
                if stream_task:
                    try:
                        await asyncio.wait_for(stream_task, timeout=5.0)
                    except asyncio.TimeoutError:
                        stream_task.cancel()

            # Calcular tiempo de ejecucion
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Encriptar respuesta
            encrypted_response = node_crypto.encrypt_for_coordinator(response)

            # Enviar resultado final
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
                tokens_generated=tokens_generated,
                model=self.model
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
                "OPENROUTER_ERROR",
                str(e)
            )

    async def _send_task_error(
        self,
        payload: TaskAssignPayload,
        error_code: str,
        error_message: str
    ) -> None:
        """Enviar mensaje de error de tarea."""
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
        """Enviar mensaje al coordinator."""
        if self._ws:
            await self._ws.send(message.to_json())


async def main():
    """Entry point para el fake node agent."""
    # Configuracion desde variables de entorno
    node_id = os.environ.get("NODE_ID", f"node-{os.getpid()}")
    model = os.environ.get("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")
    coordinator_url = os.environ.get(
        "COORDINATOR_URL",
        "ws://168.119.10.189:8000/nodes/connect"
    )
    api_key = os.environ.get("OPENROUTER_API_KEY")
    account_key = os.environ.get("IRIS_ACCOUNT_KEY")

    # Parametros de penalizacion
    reported_tps = float(os.environ.get("FAKE_NODE_TPS", "5.0"))
    artificial_load = int(os.environ.get("FAKE_NODE_ARTIFICIAL_LOAD", "3"))
    reported_vram = float(os.environ.get("FAKE_NODE_VRAM", "24.0"))
    reported_params = float(os.environ.get("FAKE_NODE_PARAMS", "70.0"))

    key_path = os.environ.get("NODE_KEY_PATH", "data/fake_node.key")

    # Validar configuracion requerida
    if not api_key:
        logger.error("openrouter_api_key_required")
        print("\n" + "="*60)
        print("ERROR: OPENROUTER_API_KEY environment variable required")
        print("="*60)
        print("\nGet your API key from: https://openrouter.ai/keys")
        print("\nThen set:")
        print('  export OPENROUTER_API_KEY="sk-or-v1-..."')
        print("="*60 + "\n")
        sys.exit(1)

    if not account_key:
        logger.error("account_key_required")
        print("\n" + "="*60)
        print("ERROR: IRIS_ACCOUNT_KEY environment variable required")
        print("="*60)
        print("\nGenerate one with: iris account generate")
        print("\nThen set:")
        print('  export IRIS_ACCOUNT_KEY="1234 5678 9012 3456"')
        print("="*60 + "\n")
        sys.exit(1)

    print("\n" + "="*60)
    print("IRIS FAKE NODE - OpenRouter Backend")
    print("="*60)
    print(f"Node ID:        {node_id}")
    print(f"Model:          {model}")
    print(f"Coordinator:    {coordinator_url}")
    print(f"Reported TPS:   {reported_tps} (low for penalty)")
    print(f"Artificial Load: {artificial_load}")
    print("="*60 + "\n")

    agent = FakeNodeAgent(
        node_id=node_id,
        model=model,
        coordinator_url=coordinator_url,
        api_key=api_key,
        account_key=account_key,
        reported_tps=reported_tps,
        artificial_load=artificial_load,
        reported_vram=reported_vram,
        reported_params=reported_params,
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
