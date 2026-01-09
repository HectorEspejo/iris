"""
Tests for node connection and registration.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from shared.protocol import (
    MessageType,
    ProtocolMessage,
    NodeRegisterPayload,
    NodeHeartbeatPayload,
    RegisterAckPayload,
    parse_payload,
)
from shared.crypto_utils import generate_keypair
from coordinator.database import Database
from coordinator.node_registry import NodeRegistry, ConnectedNode
from coordinator.crypto import CoordinatorCrypto


@pytest_asyncio.fixture
async def test_db():
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(db_path=str(Path(tmpdir) / "test.db"))
        await db.connect()
        yield db
        await db.disconnect()


@pytest.fixture
def coordinator_crypto():
    """Create coordinator crypto with temp key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        crypto = CoordinatorCrypto(key_path=str(Path(tmpdir) / "coord.key"))
        crypto.initialize()
        yield crypto


@pytest.fixture
def node_keypair():
    """Generate a node keypair."""
    return generate_keypair()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestNodeRegistry:
    """Tests for NodeRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a fresh NodeRegistry."""
        return NodeRegistry()

    def test_initial_state(self, registry):
        """Test registry starts empty."""
        assert registry.connected_count == 0
        assert registry.get_all_nodes() == []

    def test_get_nonexistent_node(self, registry):
        """Test getting a non-existent node returns None."""
        assert registry.get_node("nonexistent") is None

    def test_is_online_nonexistent(self, registry):
        """Test is_online for non-existent node."""
        assert not registry.is_online("nonexistent")


class TestNodeRegistration:
    """Tests for node registration flow."""

    @pytest_asyncio.fixture
    async def setup_registry(self, test_db, coordinator_crypto):
        """Set up registry with mocked dependencies."""
        registry = NodeRegistry()

        # Patch global instances
        with patch('coordinator.node_registry.db', test_db), \
             patch('coordinator.node_registry.coordinator_crypto', coordinator_crypto):
            yield registry, test_db, coordinator_crypto

    @pytest.mark.asyncio
    async def test_successful_registration(self, setup_registry, mock_websocket, node_keypair):
        """Test successful node registration."""
        registry, db, crypto = setup_registry

        # Create registration message
        register_msg = ProtocolMessage.create(
            MessageType.NODE_REGISTER,
            NodeRegisterPayload(
                node_id="test-node-123",
                public_key=node_keypair.public_key_b64,
                lmstudio_port=1234,
                model_name="llama-3.2",
                max_context=8192,
                vram_gb=8.0
            )
        )

        # Handle registration
        with patch('coordinator.node_registry.db', db), \
             patch('coordinator.node_registry.coordinator_crypto', crypto):
            node_id = await registry.handle_register(mock_websocket, register_msg)

        assert node_id == "test-node-123"
        assert registry.connected_count == 1
        assert registry.is_online("test-node-123")

        # Check ACK was sent
        mock_websocket.send_text.assert_called_once()
        sent_msg = ProtocolMessage.from_json(mock_websocket.send_text.call_args[0][0])
        assert sent_msg.type == MessageType.REGISTER_ACK

    @pytest.mark.asyncio
    async def test_registration_creates_db_record(self, setup_registry, mock_websocket, node_keypair):
        """Test that registration creates database record."""
        registry, db, crypto = setup_registry

        register_msg = ProtocolMessage.create(
            MessageType.NODE_REGISTER,
            NodeRegisterPayload(
                node_id="db-test-node",
                public_key=node_keypair.public_key_b64,
                model_name="test-model",
                max_context=4096,
                vram_gb=4.0
            )
        )

        with patch('coordinator.node_registry.db', db), \
             patch('coordinator.node_registry.coordinator_crypto', crypto):
            await registry.handle_register(mock_websocket, register_msg)

        # Check database
        db_node = await db.get_node_by_id("db-test-node")
        assert db_node is not None
        assert db_node["model_name"] == "test-model"


class TestHeartbeat:
    """Tests for heartbeat handling."""

    @pytest_asyncio.fixture
    async def registered_node(self, test_db, coordinator_crypto, node_keypair):
        """Set up a registered node."""
        registry = NodeRegistry()
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()

        register_msg = ProtocolMessage.create(
            MessageType.NODE_REGISTER,
            NodeRegisterPayload(
                node_id="heartbeat-test-node",
                public_key=node_keypair.public_key_b64,
                model_name="test-model",
                max_context=8192,
                vram_gb=8.0
            )
        )

        with patch('coordinator.node_registry.db', test_db), \
             patch('coordinator.node_registry.coordinator_crypto', coordinator_crypto):
            await registry.handle_register(mock_ws, register_msg)
            yield registry, test_db, mock_ws

    @pytest.mark.asyncio
    async def test_heartbeat_updates_last_seen(self, registered_node):
        """Test that heartbeat updates last seen time."""
        registry, db, mock_ws = registered_node

        heartbeat_msg = ProtocolMessage.create(
            MessageType.NODE_HEARTBEAT,
            NodeHeartbeatPayload(
                node_id="heartbeat-test-node",
                current_load=2,
                uptime_seconds=3600
            )
        )

        node_before = registry.get_node("heartbeat-test-node")
        old_heartbeat = node_before.last_heartbeat

        await asyncio.sleep(0.01)  # Small delay

        with patch('coordinator.node_registry.db', db):
            await registry.handle_heartbeat("heartbeat-test-node", heartbeat_msg)

        node_after = registry.get_node("heartbeat-test-node")
        assert node_after.last_heartbeat > old_heartbeat

    @pytest.mark.asyncio
    async def test_heartbeat_updates_load(self, registered_node):
        """Test that heartbeat updates current load."""
        registry, db, mock_ws = registered_node

        heartbeat_msg = ProtocolMessage.create(
            MessageType.NODE_HEARTBEAT,
            NodeHeartbeatPayload(
                node_id="heartbeat-test-node",
                current_load=5,
                uptime_seconds=7200
            )
        )

        with patch('coordinator.node_registry.db', db):
            await registry.handle_heartbeat("heartbeat-test-node", heartbeat_msg)

        node = registry.get_node("heartbeat-test-node")
        assert node.current_load == 5


class TestNodeDisconnection:
    """Tests for node disconnection."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_node(self, test_db, coordinator_crypto, node_keypair):
        """Test that disconnection removes node from registry."""
        registry = NodeRegistry()
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()

        register_msg = ProtocolMessage.create(
            MessageType.NODE_REGISTER,
            NodeRegisterPayload(
                node_id="disconnect-test",
                public_key=node_keypair.public_key_b64,
                model_name="test",
                max_context=8192,
                vram_gb=8.0
            )
        )

        with patch('coordinator.node_registry.db', test_db), \
             patch('coordinator.node_registry.coordinator_crypto', coordinator_crypto):
            await registry.handle_register(mock_ws, register_msg)
            assert registry.connected_count == 1

            await registry.handle_disconnect("disconnect-test")

        assert registry.connected_count == 0
        assert not registry.is_online("disconnect-test")


class TestNodeSelection:
    """Tests for node selection algorithm."""

    @pytest_asyncio.fixture
    async def registry_with_nodes(self, test_db, coordinator_crypto):
        """Set up registry with multiple nodes."""
        registry = NodeRegistry()

        # Create multiple nodes with different reputations
        for i, rep in enumerate([150, 100, 80], 1):
            kp = generate_keypair()
            mock_ws = AsyncMock()
            mock_ws.send_text = AsyncMock()

            register_msg = ProtocolMessage.create(
                MessageType.NODE_REGISTER,
                NodeRegisterPayload(
                    node_id=f"select-node-{i}",
                    public_key=kp.public_key_b64,
                    model_name="test",
                    max_context=8192,
                    vram_gb=8.0
                )
            )

            with patch('coordinator.node_registry.db', test_db), \
                 patch('coordinator.node_registry.coordinator_crypto', coordinator_crypto):
                await registry.handle_register(mock_ws, register_msg)

            # Set reputation
            await test_db.update_node_reputation(f"select-node-{i}", rep)

        yield registry, test_db

    @pytest.mark.asyncio
    async def test_select_nodes_returns_requested_count(self, registry_with_nodes):
        """Test that select_nodes returns correct number."""
        registry, db = registry_with_nodes

        with patch('coordinator.node_registry.db', db):
            selected = await registry.select_nodes(n=2)

        assert len(selected) == 2

    @pytest.mark.asyncio
    async def test_select_nodes_excludes_specified(self, registry_with_nodes):
        """Test that select_nodes excludes specified nodes."""
        registry, db = registry_with_nodes

        with patch('coordinator.node_registry.db', db):
            selected = await registry.select_nodes(n=2, exclude={"select-node-1"})

        node_ids = [n.node_id for n in selected]
        assert "select-node-1" not in node_ids

    @pytest.mark.asyncio
    async def test_select_nodes_empty_when_all_excluded(self, registry_with_nodes):
        """Test select_nodes returns empty when all excluded."""
        registry, db = registry_with_nodes

        exclude_all = {"select-node-1", "select-node-2", "select-node-3"}
        with patch('coordinator.node_registry.db', db):
            selected = await registry.select_nodes(n=2, exclude=exclude_all)

        assert len(selected) == 0
