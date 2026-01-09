"""
Integration tests for ClubAI.

These tests verify the end-to-end flow of the system.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from shared.models import TaskMode, TaskStatus
from shared.protocol import (
    MessageType,
    ProtocolMessage,
    NodeRegisterPayload,
    TaskAssignPayload,
    TaskResultPayload,
    parse_payload,
)
from shared.crypto_utils import generate_keypair
from coordinator.database import Database
from coordinator.crypto import CoordinatorCrypto
from coordinator.node_registry import NodeRegistry
from coordinator.task_orchestrator import TaskOrchestrator
from coordinator.response_aggregator import ResponseAggregator


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


class TestUserWorkflow:
    """Tests for user registration and task submission."""

    @pytest.mark.asyncio
    async def test_user_registration(self, test_db):
        """Test user can be created in database."""
        from shared.models import generate_id
        from coordinator.auth import hash_password

        user_id = generate_id()
        password_hash = hash_password("testpassword123")

        user = await test_db.create_user(
            id=user_id,
            email="test@example.com",
            password_hash=password_hash
        )

        assert user is not None
        assert user["email"] == "test@example.com"

        # Verify can retrieve
        retrieved = await test_db.get_user_by_email("test@example.com")
        assert retrieved["id"] == user_id

    @pytest.mark.asyncio
    async def test_task_creation(self, test_db):
        """Test task can be created."""
        from shared.models import generate_id

        # Create user first
        user = await test_db.create_user(
            id=generate_id(),
            email="taskuser@example.com",
            password_hash="hash"
        )

        # Create task
        task = await test_db.create_task(
            id=generate_id(),
            user_id=user["id"],
            mode="subtasks",
            original_prompt="Test prompt"
        )

        assert task is not None
        assert task["status"] == "pending"
        assert task["original_prompt"] == "Test prompt"


class TestTaskOrchestration:
    """Tests for task orchestration flow."""

    @pytest_asyncio.fixture
    async def setup_orchestration(self, test_db, coordinator_crypto):
        """Set up orchestration environment."""
        registry = NodeRegistry()
        orchestrator = TaskOrchestrator()
        aggregator = ResponseAggregator()

        # Register a mock node
        node_keypair = generate_keypair()
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()

        register_msg = ProtocolMessage.create(
            MessageType.NODE_REGISTER,
            NodeRegisterPayload(
                node_id="test-node",
                public_key=node_keypair.public_key_b64,
                model_name="test-model",
                max_context=8192,
                vram_gb=8.0
            )
        )

        with patch('coordinator.node_registry.db', test_db), \
             patch('coordinator.node_registry.coordinator_crypto', coordinator_crypto):
            await registry.handle_register(mock_ws, register_msg)

        yield {
            "db": test_db,
            "crypto": coordinator_crypto,
            "registry": registry,
            "orchestrator": orchestrator,
            "aggregator": aggregator,
            "node_keypair": node_keypair,
            "mock_ws": mock_ws
        }

    @pytest.mark.asyncio
    async def test_task_division(self, setup_orchestration):
        """Test that tasks are divided into subtasks."""
        ctx = setup_orchestration
        orchestrator = ctx["orchestrator"]

        prompt = """Analyze the document:
1. Extract main themes
2. Identify stakeholders
3. List conclusions"""

        subtasks = orchestrator._divide_into_subtasks(prompt)

        assert len(subtasks) == 3

    @pytest.mark.asyncio
    async def test_response_aggregation_subtasks(self, setup_orchestration):
        """Test response aggregation for subtask mode."""
        ctx = setup_orchestration
        db = ctx["db"]
        aggregator = ctx["aggregator"]

        from shared.models import generate_id

        # Create user
        user = await db.create_user(
            id=generate_id(),
            email="agg@example.com",
            password_hash="hash"
        )

        # Create task
        task_id = generate_id()
        await db.create_task(
            id=task_id,
            user_id=user["id"],
            mode="subtasks",
            original_prompt="Extract themes and conclusions"
        )

        # Create completed subtasks
        subtask1_id = generate_id()
        await db.create_subtask(
            id=subtask1_id,
            task_id=task_id,
            prompt="Extract themes"
        )
        await db.complete_subtask(
            subtask1_id,
            response="The main themes are A and B.",
            encrypted_response="enc",
            execution_time_ms=1000
        )

        subtask2_id = generate_id()
        await db.create_subtask(
            id=subtask2_id,
            task_id=task_id,
            prompt="Extract conclusions"
        )
        await db.complete_subtask(
            subtask2_id,
            response="The conclusions are X and Y.",
            encrypted_response="enc",
            execution_time_ms=1500
        )

        # Aggregate
        result = await aggregator.aggregate(
            task_id=task_id,
            mode=TaskMode.SUBTASKS,
            original_prompt="Extract themes and conclusions"
        )

        assert "themes are A and B" in result
        assert "conclusions are X and Y" in result


class TestCryptoIntegration:
    """Tests for cryptographic operations in context."""

    @pytest.mark.asyncio
    async def test_coordinator_node_encryption(self, coordinator_crypto):
        """Test encryption between coordinator and node."""
        node_keypair = generate_keypair()

        # Coordinator encrypts for node
        original = "Secret task prompt"
        encrypted = coordinator_crypto.encrypt_for_node(
            node_keypair.public_key_b64,
            original
        )

        # Node decrypts
        from shared.crypto_utils import decrypt_from_sender
        decrypted = decrypt_from_sender(
            node_keypair,
            coordinator_crypto.public_key,
            encrypted
        )

        assert decrypted == original

    @pytest.mark.asyncio
    async def test_node_coordinator_encryption(self, coordinator_crypto):
        """Test encryption from node to coordinator."""
        node_keypair = generate_keypair()

        # Node encrypts for coordinator
        from shared.crypto_utils import encrypt_for_recipient
        original = "Task result"
        encrypted = encrypt_for_recipient(
            node_keypair,
            coordinator_crypto.public_key,
            original
        )

        # Coordinator decrypts
        decrypted = coordinator_crypto.decrypt_from_node(
            node_keypair.public_key_b64,
            encrypted
        )

        assert decrypted == original


class TestEconomics:
    """Tests for economic calculations."""

    @pytest.mark.asyncio
    async def test_share_calculation(self, test_db):
        """Test economic share calculation."""
        from coordinator.economics import EconomicsManager
        from shared.models import generate_id

        manager = EconomicsManager()

        # Create nodes with different reputations
        await test_db.create_node(
            id="econ-node-1",
            owner_id="owner1",
            public_key="key1",
            model_name="model",
            max_context=8192,
            vram_gb=8.0
        )
        await test_db.update_node_reputation("econ-node-1", 100)

        await test_db.create_node(
            id="econ-node-2",
            owner_id="owner2",
            public_key="key2",
            model_name="model",
            max_context=8192,
            vram_gb=8.0
        )
        await test_db.update_node_reputation("econ-node-2", 200)

        # Create period
        await test_db.create_economic_period(
            id=generate_id(),
            month="2025-01",
            total_pool=1000.0
        )

        # Calculate shares
        with patch('coordinator.economics.db', test_db):
            shares = await manager.calculate_shares("2025-01")

        # Node 2 has 2x reputation, should get 2x share
        assert shares["econ-node-2"]["amount"] > shares["econ-node-1"]["amount"]

        # Total should equal pool
        total = sum(s["amount"] for s in shares.values())
        assert abs(total - 1000.0) < 0.01


class TestProtocolMessages:
    """Tests for protocol message handling."""

    def test_register_message_roundtrip(self):
        """Test NODE_REGISTER message serialization."""
        payload = NodeRegisterPayload(
            node_id="test-123",
            public_key="pubkey123",
            model_name="llama",
            max_context=8192,
            vram_gb=16.0
        )

        msg = ProtocolMessage.create(MessageType.NODE_REGISTER, payload)
        json_str = msg.to_json()

        # Parse back
        parsed = ProtocolMessage.from_json(json_str)
        parsed_payload = parse_payload(parsed, NodeRegisterPayload)

        assert parsed_payload.node_id == "test-123"
        assert parsed_payload.model_name == "llama"

    def test_task_assign_message(self):
        """Test TASK_ASSIGN message."""
        payload = TaskAssignPayload(
            subtask_id="subtask-1",
            task_id="task-1",
            encrypted_prompt="base64encrypted...",
            timeout_seconds=60
        )

        msg = ProtocolMessage.create(MessageType.TASK_ASSIGN, payload)
        json_str = msg.to_json()

        parsed = ProtocolMessage.from_json(json_str)
        assert parsed.type == MessageType.TASK_ASSIGN

    def test_task_result_message(self):
        """Test TASK_RESULT message."""
        payload = TaskResultPayload(
            subtask_id="subtask-1",
            task_id="task-1",
            encrypted_response="base64response...",
            execution_time_ms=1500
        )

        msg = ProtocolMessage.create(MessageType.TASK_RESULT, payload)
        json_str = msg.to_json()

        parsed = ProtocolMessage.from_json(json_str)
        parsed_payload = parse_payload(parsed, TaskResultPayload)

        assert parsed_payload.execution_time_ms == 1500


class TestDatabaseOperations:
    """Tests for database operations."""

    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self, test_db):
        """Test complete task lifecycle in database."""
        from shared.models import generate_id

        # Create user
        user = await test_db.create_user(
            id=generate_id(),
            email="lifecycle@example.com",
            password_hash="hash"
        )

        # Create task
        task_id = generate_id()
        task = await test_db.create_task(
            id=task_id,
            user_id=user["id"],
            mode="subtasks",
            original_prompt="Test"
        )
        assert task["status"] == "pending"

        # Update to processing
        await test_db.update_task_status(task_id, "processing")
        task = await test_db.get_task_by_id(task_id)
        assert task["status"] == "processing"

        # Complete with response
        await test_db.update_task_status(
            task_id,
            "completed",
            final_response="Done!"
        )
        task = await test_db.get_task_by_id(task_id)
        assert task["status"] == "completed"
        assert task["final_response"] == "Done!"
        assert task["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_subtask_workflow(self, test_db):
        """Test subtask creation and completion."""
        from shared.models import generate_id

        # Create user and task
        user = await test_db.create_user(
            id=generate_id(),
            email="subtask@example.com",
            password_hash="hash"
        )

        task_id = generate_id()
        await test_db.create_task(
            id=task_id,
            user_id=user["id"],
            mode="subtasks",
            original_prompt="Parent task"
        )

        # Create subtask
        subtask_id = generate_id()
        subtask = await test_db.create_subtask(
            id=subtask_id,
            task_id=task_id,
            prompt="Subtask prompt"
        )
        assert subtask["status"] == "pending"

        # Assign to node
        await test_db.assign_subtask(subtask_id, "node-1", "encrypted")
        subtask = await test_db.get_subtask_by_id(subtask_id)
        assert subtask["status"] == "assigned"
        assert subtask["node_id"] == "node-1"

        # Complete
        await test_db.complete_subtask(
            subtask_id,
            response="Result",
            encrypted_response="enc-result",
            execution_time_ms=500
        )
        subtask = await test_db.get_subtask_by_id(subtask_id)
        assert subtask["status"] == "completed"
        assert subtask["execution_time_ms"] == 500
