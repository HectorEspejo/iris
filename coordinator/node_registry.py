"""
Iris Node Registry

Manages connected nodes and their status.
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from fastapi import WebSocket
import structlog

from shared.models import Node, NodeCapabilities, TaskDifficulty, NodeTier
from shared.protocol import (
    MessageType,
    ProtocolMessage,
    NodeRegisterPayload,
    NodeHeartbeatPayload,
    RegisterAckPayload,
    HeartbeatAckPayload,
    parse_payload,
)
from .database import db
from .crypto import coordinator_crypto
from .node_tokens import NodeTokenManager
from .accounts import AccountKeyGenerator

logger = structlog.get_logger()

# Constants
HEARTBEAT_TIMEOUT = timedelta(seconds=90)  # Node considered offline after this

# Tier-Difficulty matching matrix
# Maps (NodeTier, TaskDifficulty) -> score multiplier for matching
TIER_DIFFICULTY_SCORE = {
    # Basic nodes: best for simple tasks, acceptable for complex, poor for advanced
    (NodeTier.BASIC, TaskDifficulty.SIMPLE): 1.0,
    (NodeTier.BASIC, TaskDifficulty.COMPLEX): 0.6,
    (NodeTier.BASIC, TaskDifficulty.ADVANCED): 0.2,

    # Standard nodes: acceptable for simple, best for complex, acceptable for advanced
    (NodeTier.STANDARD, TaskDifficulty.SIMPLE): 0.8,
    (NodeTier.STANDARD, TaskDifficulty.COMPLEX): 1.0,
    (NodeTier.STANDARD, TaskDifficulty.ADVANCED): 0.7,

    # Premium nodes: avoid wasting on simple, good for complex, best for advanced
    (NodeTier.PREMIUM, TaskDifficulty.SIMPLE): 0.5,
    (NodeTier.PREMIUM, TaskDifficulty.COMPLEX): 0.9,
    (NodeTier.PREMIUM, TaskDifficulty.ADVANCED): 1.0,
}


@dataclass
class ConnectedNode:
    """Runtime state of a connected node."""
    node_id: str
    websocket: WebSocket
    public_key: str
    model_name: str
    max_context: int
    vram_gb: float
    current_load: int = 0
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    latency_ms: Optional[float] = None
    # Extended capabilities
    gpu_name: str = "Unknown"
    model_params: float = 7.0
    model_quantization: str = "Q4"
    tokens_per_second: float = 0.0
    node_tier: NodeTier = NodeTier.BASIC


def calculate_node_tier(
    vram_gb: float,
    model_params: float,
    tokens_per_second: float
) -> NodeTier:
    """
    Calculate node tier based on capabilities.

    Scoring:
    - VRAM (30%): 24+ GB = 30pts, 12+ GB = 20pts, 8+ GB = 10pts
    - Model params (40%): 30B+ = 40pts, 13B+ = 25pts, 7B+ = 15pts
    - Speed (30%): 50+ tps = 30pts, 20+ tps = 20pts, 10+ tps = 10pts

    Thresholds:
    - Premium: 70+ points
    - Standard: 40-69 points
    - Basic: <40 points
    """
    score = 0

    # VRAM score (0-30)
    if vram_gb >= 24:
        score += 30
    elif vram_gb >= 12:
        score += 20
    elif vram_gb >= 8:
        score += 10

    # Model params score (0-40)
    if model_params >= 30:
        score += 40
    elif model_params >= 13:
        score += 25
    elif model_params >= 7:
        score += 15
    elif model_params >= 3:
        score += 5

    # Speed score (0-30)
    if tokens_per_second >= 50:
        score += 30
    elif tokens_per_second >= 20:
        score += 20
    elif tokens_per_second >= 10:
        score += 10

    # Determine tier
    if score >= 70:
        return NodeTier.PREMIUM
    elif score >= 40:
        return NodeTier.STANDARD
    return NodeTier.BASIC


class NodeRegistry:
    """
    Manages the registry of connected nodes.

    Handles node registration, heartbeats, and selection for tasks.
    """

    def __init__(self):
        self._nodes: dict[str, ConnectedNode] = {}
        self._lock = asyncio.Lock()
        self._token_manager: Optional[NodeTokenManager] = None

    def set_token_manager(self, token_manager: NodeTokenManager) -> None:
        """Set the token manager for enrollment validation."""
        self._token_manager = token_manager

    @property
    def connected_count(self) -> int:
        """Number of currently connected nodes."""
        return len(self._nodes)

    def get_node(self, node_id: str) -> Optional[ConnectedNode]:
        """Get a connected node by ID."""
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[ConnectedNode]:
        """Get all connected nodes."""
        return list(self._nodes.values())

    def is_online(self, node_id: str) -> bool:
        """Check if a node is currently online."""
        node = self._nodes.get(node_id)
        if not node:
            return False
        return datetime.utcnow() - node.last_heartbeat < HEARTBEAT_TIMEOUT

    async def handle_register(
        self,
        websocket: WebSocket,
        message: ProtocolMessage
    ) -> Optional[str]:
        """
        Handle NODE_REGISTER message.

        Authentication priority:
        1. Account Key (Mullvad-style) - preferred
        2. Enrollment Token (deprecated, for backwards compatibility)

        Args:
            websocket: The WebSocket connection
            message: The registration message

        Returns:
            Node ID if successful, None otherwise
        """
        try:
            payload = parse_payload(message, NodeRegisterPayload)
            account_id: Optional[str] = None

            # Debug: Log what we received
            logger.info(
                "node_registration_received",
                node_id=payload.node_id,
                has_account_key=bool(payload.account_key),
                account_key_prefix=payload.account_key[:4] if payload.account_key and len(payload.account_key) >= 4 else None,
                has_enrollment_token=bool(payload.enrollment_token)
            )

            # === Account Key Authentication (Primary) ===
            if payload.account_key:
                # Validate account key format
                if not AccountKeyGenerator.validate_format(payload.account_key):
                    logger.warning(
                        "node_registration_invalid_account_key_format",
                        node_id=payload.node_id
                    )
                    ack = ProtocolMessage.create(
                        MessageType.REGISTER_ACK,
                        RegisterAckPayload(
                            success=False,
                            coordinator_public_key="",
                            message="Invalid account key format"
                        )
                    )
                    await websocket.send_text(ack.to_json())
                    return None

                # Look up account by key hash
                key_hash = AccountKeyGenerator.hash_key(payload.account_key)
                account = await db.get_account_by_key_hash(key_hash)

                if not account:
                    logger.warning(
                        "node_registration_account_not_found",
                        node_id=payload.node_id,
                        key_prefix=AccountKeyGenerator.get_prefix(payload.account_key)
                    )
                    ack = ProtocolMessage.create(
                        MessageType.REGISTER_ACK,
                        RegisterAckPayload(
                            success=False,
                            coordinator_public_key="",
                            message="Account not found. Generate an account first with: iris account generate"
                        )
                    )
                    await websocket.send_text(ack.to_json())
                    return None

                if account["status"] != "active":
                    logger.warning(
                        "node_registration_account_inactive",
                        node_id=payload.node_id,
                        status=account["status"]
                    )
                    ack = ProtocolMessage.create(
                        MessageType.REGISTER_ACK,
                        RegisterAckPayload(
                            success=False,
                            coordinator_public_key="",
                            message=f"Account is {account['status']}"
                        )
                    )
                    await websocket.send_text(ack.to_json())
                    return None

                account_id = account["id"]
                logger.info(
                    "node_authenticated_with_account",
                    node_id=payload.node_id,
                    account_prefix=account["account_key_prefix"]
                )

                # Update account activity
                await db.update_account_activity(account_id)

            # === Enrollment Token Authentication (Deprecated fallback) ===
            elif self._token_manager:
                # Check if this node was already enrolled
                is_enrolled = await self._token_manager.is_node_enrolled(payload.node_id)

                if not is_enrolled:
                    # New node - must provide valid enrollment token
                    if not payload.enrollment_token:
                        logger.warning(
                            "node_registration_no_credentials",
                            node_id=payload.node_id
                        )
                        ack = ProtocolMessage.create(
                            MessageType.REGISTER_ACK,
                            RegisterAckPayload(
                                success=False,
                                coordinator_public_key="",
                                message="Account key required. Generate an account with: iris account generate"
                            )
                        )
                        await websocket.send_text(ack.to_json())
                        return None

                    # Validate the enrollment token
                    validation = await self._token_manager.validate(payload.enrollment_token)
                    if not validation.valid:
                        logger.warning(
                            "node_registration_invalid_token",
                            node_id=payload.node_id,
                            error=validation.error
                        )
                        ack = ProtocolMessage.create(
                            MessageType.REGISTER_ACK,
                            RegisterAckPayload(
                                success=False,
                                coordinator_public_key="",
                                message=f"Invalid enrollment token: {validation.error}"
                            )
                        )
                        await websocket.send_text(ack.to_json())
                        return None

                    # Consume the token (mark as used)
                    consumed = await self._token_manager.consume(
                        payload.enrollment_token,
                        payload.node_id
                    )
                    if not consumed:
                        logger.error(
                            "node_registration_token_consume_failed",
                            node_id=payload.node_id
                        )
                        ack = ProtocolMessage.create(
                            MessageType.REGISTER_ACK,
                            RegisterAckPayload(
                                success=False,
                                coordinator_public_key="",
                                message="Failed to consume enrollment token"
                            )
                        )
                        await websocket.send_text(ack.to_json())
                        return None

                    logger.info(
                        "node_enrolled_with_token_deprecated",
                        node_id=payload.node_id,
                        token_id=validation.token_id
                    )

            async with self._lock:
                # Check if already connected (reconnection)
                if payload.node_id in self._nodes:
                    logger.info(
                        "node_reconnecting",
                        node_id=payload.node_id
                    )
                    # Update existing connection
                    self._nodes[payload.node_id].websocket = websocket

                # Calculate node tier based on capabilities
                node_tier = calculate_node_tier(
                    vram_gb=payload.vram_gb,
                    model_params=payload.model_params,
                    tokens_per_second=payload.tokens_per_second
                )

                # Create/update node in database with extended capabilities
                await db.create_node(
                    id=payload.node_id,
                    owner_id=payload.node_id,  # Legacy field
                    public_key=payload.public_key,
                    model_name=payload.model_name,
                    max_context=payload.max_context,
                    vram_gb=payload.vram_gb,
                    lmstudio_port=payload.lmstudio_port,
                    gpu_name=payload.gpu_name,
                    model_params=payload.model_params,
                    model_quantization=payload.model_quantization,
                    tokens_per_second=payload.tokens_per_second,
                    node_tier=node_tier.value
                )

                # Link node to account if authenticated via account_key
                if account_id:
                    await db.link_node_to_account(payload.node_id, account_id)

                # Add to connected nodes with extended capabilities
                self._nodes[payload.node_id] = ConnectedNode(
                    node_id=payload.node_id,
                    websocket=websocket,
                    public_key=payload.public_key,
                    model_name=payload.model_name,
                    max_context=payload.max_context,
                    vram_gb=payload.vram_gb,
                    gpu_name=payload.gpu_name,
                    model_params=payload.model_params,
                    model_quantization=payload.model_quantization,
                    tokens_per_second=payload.tokens_per_second,
                    node_tier=node_tier
                )

            # Send acknowledgment
            ack = ProtocolMessage.create(
                MessageType.REGISTER_ACK,
                RegisterAckPayload(
                    success=True,
                    coordinator_public_key=coordinator_crypto.public_key
                )
            )
            await websocket.send_text(ack.to_json())

            logger.info(
                "node_registered",
                node_id=payload.node_id,
                model=payload.model_name,
                vram=payload.vram_gb,
                gpu=payload.gpu_name,
                params_b=payload.model_params,
                tier=node_tier.value,
                account_id=account_id
            )
            return payload.node_id

        except Exception as e:
            logger.error("node_registration_failed", error=str(e))
            return None

    async def handle_heartbeat(
        self,
        node_id: str,
        message: ProtocolMessage
    ) -> bool:
        """
        Handle NODE_HEARTBEAT message.

        Args:
            node_id: The node's ID
            message: The heartbeat message

        Returns:
            True if handled successfully
        """
        try:
            payload = parse_payload(message, NodeHeartbeatPayload)

            node = self._nodes.get(node_id)
            if not node:
                logger.warning("heartbeat_unknown_node", node_id=node_id)
                return False

            # Update state
            node.last_heartbeat = datetime.utcnow()
            node.current_load = payload.current_load

            # Update database
            await db.update_node_last_seen(node_id)

            # Send acknowledgment
            ack = ProtocolMessage.create(
                MessageType.HEARTBEAT_ACK,
                HeartbeatAckPayload(success=True)
            )
            await node.websocket.send_text(ack.to_json())

            logger.debug(
                "node_heartbeat",
                node_id=node_id,
                load=payload.current_load
            )
            return True

        except Exception as e:
            logger.error("heartbeat_failed", node_id=node_id, error=str(e))
            return False

    async def handle_disconnect(self, node_id: str) -> None:
        """
        Handle node disconnection.

        Args:
            node_id: The disconnecting node's ID
        """
        async with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                logger.info("node_disconnected", node_id=node_id)

    async def select_nodes(
        self,
        n: int = 3,
        exclude: Optional[set[str]] = None
    ) -> list[ConnectedNode]:
        """
        Select nodes for a task based on reputation, load, and latency.

        Selection algorithm:
        - Weight 0.5: Reputation (higher is better)
        - Weight 0.3: Load (lower is better)
        - Weight 0.2: Latency (lower is better)
        - Add randomness to avoid always selecting the same nodes

        Args:
            n: Number of nodes to select
            exclude: Node IDs to exclude from selection

        Returns:
            List of selected nodes
        """
        exclude = exclude or set()
        available = [
            node for node in self._nodes.values()
            if node.node_id not in exclude and self.is_online(node.node_id)
        ]

        if not available:
            return []

        if len(available) <= n:
            return available

        # Get reputation scores from database
        node_reputations = {}
        for node in available:
            db_node = await db.get_node_by_id(node.node_id)
            if db_node:
                node_reputations[node.node_id] = db_node.get("reputation", 100)
            else:
                node_reputations[node.node_id] = 100

        # Calculate scores
        max_rep = max(node_reputations.values()) or 1
        max_load = max(n.current_load for n in available) or 1
        max_latency = max((n.latency_ms or 100) for n in available) or 1

        def score(node: ConnectedNode) -> float:
            rep_score = node_reputations.get(node.node_id, 100) / max_rep
            load_score = 1 - (node.current_load / max_load)
            latency_score = 1 - ((node.latency_ms or 50) / max_latency)

            # Weighted score + random factor for variety
            base_score = (
                0.5 * rep_score +
                0.3 * load_score +
                0.2 * latency_score
            )
            return base_score + random.uniform(0, 0.1)

        # Sort by score and take top n
        sorted_nodes = sorted(available, key=score, reverse=True)
        return sorted_nodes[:n]

    async def select_nodes_v2(
        self,
        difficulty: TaskDifficulty,
        n: int = 3,
        exclude: Optional[set[str]] = None
    ) -> list[ConnectedNode]:
        """
        Select nodes for a task using intelligent tier-based matching.

        New selection algorithm:
        - Weight 0.35: Tier match (how well node tier matches task difficulty)
        - Weight 0.25: Reputation (higher is better)
        - Weight 0.20: Load (lower is better)
        - Weight 0.15: Latency (lower is better)
        - Weight 0.05: Random factor for variety

        Args:
            difficulty: Task difficulty level
            n: Number of nodes to select
            exclude: Node IDs to exclude from selection

        Returns:
            List of selected nodes, best matches first
        """
        exclude = exclude or set()
        available = [
            node for node in self._nodes.values()
            if node.node_id not in exclude and self.is_online(node.node_id)
        ]

        if not available:
            logger.warning(
                "no_available_nodes",
                difficulty=difficulty.value,
                requested=n
            )
            return []

        if len(available) <= n:
            return available

        # Get reputation scores from database
        node_reputations = {}
        for node in available:
            db_node = await db.get_node_by_id(node.node_id)
            if db_node:
                node_reputations[node.node_id] = db_node.get("reputation", 100)
            else:
                node_reputations[node.node_id] = 100

        # Calculate normalization factors
        max_rep = max(node_reputations.values()) or 1
        max_load = max(node.current_load for node in available) or 1
        max_latency = max((node.latency_ms or 100) for node in available) or 1

        def score(node: ConnectedNode) -> float:
            # Tier match score (0.35 weight)
            tier_score = TIER_DIFFICULTY_SCORE.get(
                (node.node_tier, difficulty),
                0.5  # Default for unknown combinations
            )

            # Reputation score (0.25 weight)
            rep_score = node_reputations.get(node.node_id, 100) / max_rep

            # Load score - inverse (0.20 weight)
            load_score = 1 - (node.current_load / max_load) if max_load > 0 else 1

            # Latency score - inverse (0.15 weight)
            latency_score = 1 - ((node.latency_ms or 50) / max_latency) if max_latency > 0 else 0.5

            # Random factor for variety (0.05 weight)
            random_factor = random.uniform(0, 1)

            # Weighted combination
            total_score = (
                0.35 * tier_score +
                0.25 * rep_score +
                0.20 * load_score +
                0.15 * latency_score +
                0.05 * random_factor
            )

            return total_score

        # Sort by score and take top n
        sorted_nodes = sorted(available, key=score, reverse=True)
        selected = sorted_nodes[:n]

        # Log selection details
        logger.debug(
            "nodes_selected_v2",
            difficulty=difficulty.value,
            requested=n,
            selected_count=len(selected),
            selected_tiers=[node.node_tier.value for node in selected]
        )

        return selected

    async def select_fastest_basic_node(self) -> Optional[ConnectedNode]:
        """
        Select the BASIC tier node with the highest tokens_per_second.

        Used for classification mini-tasks that need quick responses.
        Prefers nodes with low current load to ensure fast response.

        Returns:
            Best BASIC node or None if no BASIC nodes available
        """
        basic_nodes = [
            node for node in self._nodes.values()
            if node.node_tier == NodeTier.BASIC
            and self.is_online(node.node_id)
            and node.current_load < 3  # Avoid overloaded nodes
        ]

        if not basic_nodes:
            logger.debug("no_basic_nodes_available_for_classification")
            return None

        # Sort by tokens_per_second (descending), then by load (ascending)
        sorted_nodes = sorted(
            basic_nodes,
            key=lambda n: (n.tokens_per_second, -n.current_load),
            reverse=True
        )

        selected = sorted_nodes[0]
        logger.debug(
            "fastest_basic_node_selected",
            node_id=selected.node_id,
            tokens_per_second=selected.tokens_per_second,
            current_load=selected.current_load
        )

        return selected

    async def send_to_node(self, node_id: str, message: ProtocolMessage) -> bool:
        """
        Send a message to a specific node.

        Args:
            node_id: Target node ID
            message: Message to send

        Returns:
            True if sent successfully
        """
        node = self._nodes.get(node_id)
        if not node:
            logger.warning("send_to_unknown_node", node_id=node_id)
            return False

        try:
            await node.websocket.send_text(message.to_json())
            return True
        except Exception as e:
            logger.error("send_to_node_failed", node_id=node_id, error=str(e))
            return False

    def increment_load(self, node_id: str) -> None:
        """Increment a node's current load."""
        if node_id in self._nodes:
            self._nodes[node_id].current_load += 1

    def decrement_load(self, node_id: str) -> None:
        """Decrement a node's current load."""
        if node_id in self._nodes:
            self._nodes[node_id].current_load = max(
                0, self._nodes[node_id].current_load - 1
            )


# Global node registry instance
node_registry = NodeRegistry()
