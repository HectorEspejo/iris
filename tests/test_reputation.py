"""
Tests for reputation system.
"""

import pytest
import pytest_asyncio
import tempfile
from pathlib import Path

from shared.models import ReputationChangeReason
from coordinator.database import Database
from coordinator.reputation import (
    ReputationSystem,
    INITIAL_REPUTATION,
    MIN_REPUTATION,
    TASK_COMPLETED_POINTS,
    TASK_FAST_BONUS,
    TASK_TIMEOUT_PENALTY,
    TASK_INVALID_PENALTY,
)


@pytest_asyncio.fixture
async def test_db():
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(db_path=str(Path(tmpdir) / "test.db"))
        await db.connect()
        yield db
        await db.disconnect()


@pytest_asyncio.fixture
async def reputation_system(test_db):
    """Create reputation system with test database."""
    # Monkey-patch the global db
    import coordinator.reputation as rep_module
    import coordinator.database as db_module

    original_db = db_module.db
    db_module.db = test_db
    rep_module.db = test_db

    system = ReputationSystem()
    yield system

    # Restore original
    db_module.db = original_db


@pytest_asyncio.fixture
async def test_node(test_db):
    """Create a test node."""
    node = await test_db.create_node(
        id="test-node-1",
        owner_id="test-owner",
        public_key="test-pubkey",
        model_name="test-model",
        max_context=8192,
        vram_gb=8.0
    )
    return node


class TestReputationSystem:
    """Tests for reputation system."""

    @pytest.mark.asyncio
    async def test_initial_reputation(self, reputation_system, test_node):
        """Test that nodes start with initial reputation."""
        rep = await reputation_system.get_reputation(test_node["id"])
        assert rep == INITIAL_REPUTATION

    @pytest.mark.asyncio
    async def test_task_completed_adds_points(self, reputation_system, test_node):
        """Test that completing a task adds points."""
        initial = await reputation_system.get_reputation(test_node["id"])

        # Complete a task (not fast)
        new_rep = await reputation_system.record_task_completed(
            test_node["id"],
            execution_time_ms=50000  # 50 seconds, not fast
        )

        assert new_rep == initial + TASK_COMPLETED_POINTS

    @pytest.mark.asyncio
    async def test_fast_completion_bonus(self, reputation_system, test_node):
        """Test that fast completion gets bonus points."""
        initial = await reputation_system.get_reputation(test_node["id"])

        # Complete a task fast
        new_rep = await reputation_system.record_task_completed(
            test_node["id"],
            execution_time_ms=10000  # 10 seconds, fast
        )

        expected = initial + TASK_COMPLETED_POINTS + TASK_FAST_BONUS
        assert new_rep == expected

    @pytest.mark.asyncio
    async def test_timeout_penalty(self, reputation_system, test_node):
        """Test that timeout reduces reputation."""
        initial = await reputation_system.get_reputation(test_node["id"])

        new_rep = await reputation_system.record_task_timeout(test_node["id"])

        assert new_rep == initial + TASK_TIMEOUT_PENALTY

    @pytest.mark.asyncio
    async def test_invalid_response_penalty(self, reputation_system, test_node):
        """Test that invalid response heavily penalizes."""
        initial = await reputation_system.get_reputation(test_node["id"])

        new_rep = await reputation_system.record_task_failed(
            test_node["id"],
            error_code="INVALID_RESPONSE"
        )

        assert new_rep == initial + TASK_INVALID_PENALTY

    @pytest.mark.asyncio
    async def test_reputation_minimum(self, reputation_system, test_node, test_db):
        """Test that reputation cannot go below minimum."""
        # Set reputation to just above minimum
        await test_db.update_node_reputation(test_node["id"], MIN_REPUTATION + 5)

        # Apply heavy penalty
        new_rep = await reputation_system.record_task_failed(
            test_node["id"],
            error_code="INVALID_RESPONSE"
        )

        assert new_rep == MIN_REPUTATION

    @pytest.mark.asyncio
    async def test_weekly_decay(self, reputation_system, test_node, test_db):
        """Test weekly decay reduces reputation."""
        await test_db.update_node_reputation(test_node["id"], 200.0)

        results = await reputation_system.apply_weekly_decay()

        assert test_node["id"] in results
        assert results[test_node["id"]] < 200.0
        assert results[test_node["id"]] == 200.0 * 0.99  # 1% decay

    @pytest.mark.asyncio
    async def test_weekly_decay_respects_minimum(self, reputation_system, test_node, test_db):
        """Test weekly decay doesn't go below minimum."""
        await test_db.update_node_reputation(test_node["id"], MIN_REPUTATION)

        results = await reputation_system.apply_weekly_decay()

        # Node at minimum shouldn't be in results (no change)
        # or should be at minimum
        if test_node["id"] in results:
            assert results[test_node["id"]] >= MIN_REPUTATION

    @pytest.mark.asyncio
    async def test_leaderboard(self, reputation_system, test_db):
        """Test leaderboard returns nodes sorted by reputation."""
        # Create multiple nodes with different reputations
        await test_db.create_node(
            id="node-high",
            owner_id="owner",
            public_key="key1",
            model_name="model",
            max_context=8192,
            vram_gb=8.0
        )
        await test_db.update_node_reputation("node-high", 200.0)

        await test_db.create_node(
            id="node-low",
            owner_id="owner",
            public_key="key2",
            model_name="model",
            max_context=8192,
            vram_gb=8.0
        )
        await test_db.update_node_reputation("node-low", 50.0)

        leaderboard = await reputation_system.get_leaderboard(limit=10)

        assert len(leaderboard) >= 2
        # Should be sorted by reputation descending
        reps = [entry["reputation"] for entry in leaderboard]
        assert reps == sorted(reps, reverse=True)

    @pytest.mark.asyncio
    async def test_reputation_history(self, reputation_system, test_node):
        """Test reputation history is recorded."""
        # Make some changes
        await reputation_system.record_task_completed(test_node["id"], 50000)
        await reputation_system.record_task_timeout(test_node["id"])

        history = await reputation_system.get_node_history(test_node["id"])

        assert len(history) >= 2
        # Most recent first
        assert history[0]["change"] == TASK_TIMEOUT_PENALTY


class TestReputationCalculations:
    """Tests for reputation calculations."""

    @pytest.mark.asyncio
    async def test_multiple_completions(self, reputation_system, test_node):
        """Test multiple task completions accumulate."""
        initial = await reputation_system.get_reputation(test_node["id"])

        # Complete 3 tasks
        for _ in range(3):
            await reputation_system.record_task_completed(test_node["id"], 50000)

        final = await reputation_system.get_reputation(test_node["id"])
        assert final == initial + (TASK_COMPLETED_POINTS * 3)

    @pytest.mark.asyncio
    async def test_mixed_events(self, reputation_system, test_node):
        """Test mixed success and failure events."""
        initial = await reputation_system.get_reputation(test_node["id"])

        # 2 successes, 1 timeout
        await reputation_system.record_task_completed(test_node["id"], 50000)
        await reputation_system.record_task_completed(test_node["id"], 50000)
        await reputation_system.record_task_timeout(test_node["id"])

        final = await reputation_system.get_reputation(test_node["id"])
        expected = initial + (TASK_COMPLETED_POINTS * 2) + TASK_TIMEOUT_PENALTY
        assert final == expected
