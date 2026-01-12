"""
Iris Database Layer

SQLite database with async support using aiosqlite.
"""

import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
import structlog

logger = structlog.get_logger()


# SQL Schema
SCHEMA = """
-- Accounts for node operators (Mullvad-style)
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    account_key_hash TEXT UNIQUE NOT NULL,
    account_key_prefix TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active',
    total_earnings REAL DEFAULT 0.0,
    last_activity_at TIMESTAMP
);

-- Users of the club (admin only - legacy)
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    public_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    membership_status TEXT DEFAULT 'active',
    monthly_quota INTEGER DEFAULT 1000
);

-- Registered nodes
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    owner_id TEXT REFERENCES users(id),
    account_id TEXT REFERENCES accounts(id),
    public_key TEXT NOT NULL,
    model_name TEXT,
    max_context INTEGER,
    vram_gb REAL,
    lmstudio_port INTEGER DEFAULT 1234,
    reputation REAL DEFAULT 100,
    total_tasks_completed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP,
    -- Extended capabilities for intelligent task assignment
    gpu_name TEXT DEFAULT 'Unknown',
    model_params REAL DEFAULT 7.0,
    model_quantization TEXT DEFAULT 'Q4',
    tokens_per_second REAL DEFAULT 0.0,
    node_tier TEXT DEFAULT 'basic',
    supports_vision BOOLEAN DEFAULT FALSE
);

-- Node availability schedule
CREATE TABLE IF NOT EXISTS node_availability (
    node_id TEXT REFERENCES nodes(id),
    day_of_week INTEGER,
    hour_utc INTEGER,
    PRIMARY KEY (node_id, day_of_week, hour_utc)
);

-- Inference tasks
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    mode TEXT,
    difficulty TEXT DEFAULT 'simple',
    original_prompt TEXT,
    encrypted_prompt TEXT,
    status TEXT DEFAULT 'pending',
    final_response TEXT,
    has_files BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Subtasks assigned to nodes
CREATE TABLE IF NOT EXISTS subtasks (
    id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    node_id TEXT REFERENCES nodes(id),
    prompt TEXT,
    encrypted_prompt TEXT,
    response TEXT,
    encrypted_response TEXT,
    status TEXT DEFAULT 'pending',
    assigned_at TIMESTAMP,
    completed_at TIMESTAMP,
    execution_time_ms INTEGER
);

-- Reputation history
CREATE TABLE IF NOT EXISTS reputation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT REFERENCES nodes(id),
    change REAL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Monthly economic periods
CREATE TABLE IF NOT EXISTS economic_periods (
    id TEXT PRIMARY KEY,
    month TEXT,
    total_pool REAL,
    distributed BOOLEAN DEFAULT FALSE,
    distributed_at TIMESTAMP
);

-- Node earnings per period
CREATE TABLE IF NOT EXISTS node_earnings (
    period_id TEXT REFERENCES economic_periods(id),
    node_id TEXT REFERENCES nodes(id),
    reputation_snapshot REAL,
    share_percentage REAL,
    amount REAL,
    PRIMARY KEY (period_id, node_id)
);

-- Node enrollment tokens
CREATE TABLE IF NOT EXISTS node_tokens (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    used_at TIMESTAMP,
    used_by_node_id TEXT REFERENCES nodes(id),
    revoked BOOLEAN DEFAULT FALSE,
    label TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_accounts_key_hash ON accounts(account_key_hash);
CREATE INDEX IF NOT EXISTS idx_accounts_prefix ON accounts(account_key_prefix);
CREATE INDEX IF NOT EXISTS idx_nodes_account ON nodes(account_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_subtasks_task ON subtasks(task_id);
CREATE INDEX IF NOT EXISTS idx_subtasks_node ON subtasks(node_id);
CREATE INDEX IF NOT EXISTS idx_reputation_log_node ON reputation_log(node_id);
CREATE INDEX IF NOT EXISTS idx_node_tokens_hash ON node_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_node_tokens_node ON node_tokens(used_by_node_id);
"""

# Migration queries for existing databases
MIGRATIONS = [
    # Add extended node capabilities columns
    "ALTER TABLE nodes ADD COLUMN gpu_name TEXT DEFAULT 'Unknown'",
    "ALTER TABLE nodes ADD COLUMN model_params REAL DEFAULT 7.0",
    "ALTER TABLE nodes ADD COLUMN model_quantization TEXT DEFAULT 'Q4'",
    "ALTER TABLE nodes ADD COLUMN tokens_per_second REAL DEFAULT 0.0",
    "ALTER TABLE nodes ADD COLUMN node_tier TEXT DEFAULT 'basic'",
    # Add difficulty column to tasks
    "ALTER TABLE tasks ADD COLUMN difficulty TEXT DEFAULT 'simple'",
    # Add indexes for new columns (after columns exist)
    "CREATE INDEX IF NOT EXISTS idx_tasks_difficulty ON tasks(difficulty)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_tier ON nodes(node_tier)",
    # Add node_tokens table for enrollment system
    """CREATE TABLE IF NOT EXISTS node_tokens (
        id TEXT PRIMARY KEY,
        token_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        used_at TIMESTAMP,
        used_by_node_id TEXT REFERENCES nodes(id),
        revoked BOOLEAN DEFAULT FALSE,
        label TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_node_tokens_hash ON node_tokens(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_node_tokens_node ON node_tokens(used_by_node_id)",
    # Add accounts table (Mullvad-style account keys)
    """CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY,
        account_key_hash TEXT UNIQUE NOT NULL,
        account_key_prefix TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active',
        total_earnings REAL DEFAULT 0.0,
        last_activity_at TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_accounts_key_hash ON accounts(account_key_hash)",
    "CREATE INDEX IF NOT EXISTS idx_accounts_prefix ON accounts(account_key_prefix)",
    # Add account_id to nodes table
    "ALTER TABLE nodes ADD COLUMN account_id TEXT REFERENCES accounts(id)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_account ON nodes(account_id)",
    # Add has_files column to tasks for multimodal support
    "ALTER TABLE tasks ADD COLUMN has_files BOOLEAN DEFAULT FALSE",
    # Add supports_vision column to nodes for multimodal models
    "ALTER TABLE nodes ADD COLUMN supports_vision BOOLEAN DEFAULT FALSE",
]


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: str = "data/iris.db"):
        self.db_path = Path(db_path)
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Initialize database connection and create tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()

        # Run migrations for existing databases
        await self._run_migrations()

        logger.info("database_connected", path=str(self.db_path))

    async def _run_migrations(self) -> None:
        """Run database migrations for schema updates."""
        for migration in MIGRATIONS:
            try:
                await self._connection.execute(migration)
                await self._connection.commit()
            except Exception:
                # Column probably already exists, ignore
                pass

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("database_disconnected")

    @property
    def conn(self) -> aiosqlite.Connection:
        """Get the database connection."""
        if not self._connection:
            raise RuntimeError("Database not connected")
        return self._connection

    # =========================================================================
    # User Operations
    # =========================================================================

    async def create_user(
        self,
        id: str,
        email: str,
        password_hash: str,
        public_key: Optional[str] = None
    ) -> dict[str, Any]:
        """Create a new user."""
        await self.conn.execute(
            """
            INSERT INTO users (id, email, password_hash, public_key)
            VALUES (?, ?, ?, ?)
            """,
            (id, email, password_hash, public_key)
        )
        await self.conn.commit()
        return await self.get_user_by_id(id)

    async def get_user_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        """Get user by ID."""
        async with self.conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        """Get user by email."""
        async with self.conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_user_public_key(self, user_id: str, public_key: str) -> None:
        """Update user's public key."""
        await self.conn.execute(
            "UPDATE users SET public_key = ? WHERE id = ?",
            (public_key, user_id)
        )
        await self.conn.commit()

    # =========================================================================
    # Node Operations
    # =========================================================================

    async def create_node(
        self,
        id: str,
        owner_id: str,
        public_key: str,
        model_name: str,
        max_context: int,
        vram_gb: float,
        lmstudio_port: int = 1234,
        gpu_name: str = "Unknown",
        model_params: float = 7.0,
        model_quantization: str = "Q4",
        tokens_per_second: float = 0.0,
        node_tier: str = "basic",
        supports_vision: bool = False
    ) -> dict[str, Any]:
        """Create or update a node."""
        await self.conn.execute(
            """
            INSERT INTO nodes (
                id, owner_id, public_key, model_name, max_context, vram_gb,
                lmstudio_port, last_seen_at, gpu_name, model_params,
                model_quantization, tokens_per_second, node_tier, supports_vision
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                public_key = excluded.public_key,
                model_name = excluded.model_name,
                max_context = excluded.max_context,
                vram_gb = excluded.vram_gb,
                lmstudio_port = excluded.lmstudio_port,
                last_seen_at = excluded.last_seen_at,
                gpu_name = excluded.gpu_name,
                model_params = excluded.model_params,
                model_quantization = excluded.model_quantization,
                tokens_per_second = excluded.tokens_per_second,
                node_tier = excluded.node_tier,
                supports_vision = excluded.supports_vision
            """,
            (id, owner_id, public_key, model_name, max_context, vram_gb,
             lmstudio_port, datetime.utcnow(), gpu_name, model_params,
             model_quantization, tokens_per_second, node_tier, supports_vision)
        )
        await self.conn.commit()
        return await self.get_node_by_id(id)

    async def get_node_by_id(self, node_id: str) -> Optional[dict[str, Any]]:
        """Get node by ID."""
        async with self.conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_nodes_by_owner(self, owner_id: str) -> list[dict[str, Any]]:
        """Get all nodes owned by a user."""
        async with self.conn.execute(
            "SELECT * FROM nodes WHERE owner_id = ?", (owner_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_nodes(self) -> list[dict[str, Any]]:
        """Get all registered nodes."""
        async with self.conn.execute(
            "SELECT * FROM nodes ORDER BY reputation DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_node_last_seen(self, node_id: str) -> None:
        """Update node's last seen timestamp."""
        await self.conn.execute(
            "UPDATE nodes SET last_seen_at = ? WHERE id = ?",
            (datetime.utcnow(), node_id)
        )
        await self.conn.commit()

    async def update_node_reputation(self, node_id: str, reputation: float) -> None:
        """Update node's reputation score."""
        await self.conn.execute(
            "UPDATE nodes SET reputation = ? WHERE id = ?",
            (reputation, node_id)
        )
        await self.conn.commit()

    async def increment_node_tasks(self, node_id: str) -> None:
        """Increment node's completed task count."""
        await self.conn.execute(
            "UPDATE nodes SET total_tasks_completed = total_tasks_completed + 1 WHERE id = ?",
            (node_id,)
        )
        await self.conn.commit()

    async def update_node_capabilities(
        self,
        node_id: str,
        tokens_per_second: Optional[float] = None,
        node_tier: Optional[str] = None
    ) -> None:
        """Update node's extended capabilities."""
        updates = []
        params = []

        if tokens_per_second is not None:
            updates.append("tokens_per_second = ?")
            params.append(tokens_per_second)

        if node_tier is not None:
            updates.append("node_tier = ?")
            params.append(node_tier)

        if updates:
            params.append(node_id)
            await self.conn.execute(
                f"UPDATE nodes SET {', '.join(updates)} WHERE id = ?",
                tuple(params)
            )
            await self.conn.commit()

    async def get_nodes_by_tier(self, tier: str) -> list[dict[str, Any]]:
        """Get all nodes of a specific tier."""
        async with self.conn.execute(
            "SELECT * FROM nodes WHERE node_tier = ? ORDER BY reputation DESC",
            (tier,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_vision_capable_nodes(self) -> list[dict[str, Any]]:
        """Get all nodes that support vision/image processing."""
        async with self.conn.execute(
            "SELECT * FROM nodes WHERE supports_vision = TRUE ORDER BY reputation DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # =========================================================================
    # Task Operations
    # =========================================================================

    async def create_task(
        self,
        id: str,
        user_id: str,
        mode: str,
        original_prompt: str,
        encrypted_prompt: Optional[str] = None,
        difficulty: str = "simple",
        has_files: bool = False
    ) -> dict[str, Any]:
        """Create a new task."""
        await self.conn.execute(
            """
            INSERT INTO tasks (id, user_id, mode, difficulty, original_prompt, encrypted_prompt, has_files)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, user_id, mode, difficulty, original_prompt, encrypted_prompt, has_files)
        )
        await self.conn.commit()
        return await self.get_task_by_id(id)

    async def get_task_by_id(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get task by ID."""
        async with self.conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_tasks_by_user(
        self,
        user_id: str,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get tasks for a user."""
        async with self.conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        final_response: Optional[str] = None
    ) -> None:
        """Update task status and optionally set response."""
        if final_response is not None:
            await self.conn.execute(
                """
                UPDATE tasks
                SET status = ?, final_response = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, final_response, datetime.utcnow(), task_id)
            )
        else:
            await self.conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (status, task_id)
            )
        await self.conn.commit()

    async def get_recent_tasks(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get most recent tasks across all users."""
        async with self.conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # =========================================================================
    # Subtask Operations
    # =========================================================================

    async def create_subtask(
        self,
        id: str,
        task_id: str,
        prompt: str,
        encrypted_prompt: Optional[str] = None
    ) -> dict[str, Any]:
        """Create a new subtask."""
        await self.conn.execute(
            """
            INSERT INTO subtasks (id, task_id, prompt, encrypted_prompt)
            VALUES (?, ?, ?, ?)
            """,
            (id, task_id, prompt, encrypted_prompt)
        )
        await self.conn.commit()
        return await self.get_subtask_by_id(id)

    async def get_subtask_by_id(self, subtask_id: str) -> Optional[dict[str, Any]]:
        """Get subtask by ID."""
        async with self.conn.execute(
            "SELECT * FROM subtasks WHERE id = ?", (subtask_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_subtasks_by_task(self, task_id: str) -> list[dict[str, Any]]:
        """Get all subtasks for a task."""
        async with self.conn.execute(
            "SELECT * FROM subtasks WHERE task_id = ?", (task_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def assign_subtask(self, subtask_id: str, node_id: str, encrypted_prompt: str) -> None:
        """Assign a subtask to a node."""
        await self.conn.execute(
            """
            UPDATE subtasks
            SET node_id = ?, encrypted_prompt = ?, status = 'assigned', assigned_at = ?
            WHERE id = ?
            """,
            (node_id, encrypted_prompt, datetime.utcnow(), subtask_id)
        )
        await self.conn.commit()

    async def complete_subtask(
        self,
        subtask_id: str,
        response: str,
        encrypted_response: str,
        execution_time_ms: int
    ) -> None:
        """Mark a subtask as completed."""
        await self.conn.execute(
            """
            UPDATE subtasks
            SET response = ?, encrypted_response = ?, status = 'completed',
                completed_at = ?, execution_time_ms = ?
            WHERE id = ?
            """,
            (response, encrypted_response, datetime.utcnow(), execution_time_ms, subtask_id)
        )
        await self.conn.commit()

    async def fail_subtask(self, subtask_id: str, status: str = "failed") -> None:
        """Mark a subtask as failed or timeout."""
        await self.conn.execute(
            "UPDATE subtasks SET status = ?, completed_at = ? WHERE id = ?",
            (status, datetime.utcnow(), subtask_id)
        )
        await self.conn.commit()

    # =========================================================================
    # Reputation Log Operations
    # =========================================================================

    async def log_reputation_change(
        self,
        node_id: str,
        change: float,
        reason: str
    ) -> None:
        """Log a reputation change."""
        await self.conn.execute(
            """
            INSERT INTO reputation_log (node_id, change, reason)
            VALUES (?, ?, ?)
            """,
            (node_id, change, reason)
        )
        await self.conn.commit()

    async def get_reputation_history(
        self,
        node_id: str,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get reputation history for a node."""
        async with self.conn.execute(
            """
            SELECT * FROM reputation_log
            WHERE node_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (node_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # =========================================================================
    # Economic Operations
    # =========================================================================

    async def create_economic_period(
        self,
        id: str,
        month: str,
        total_pool: float
    ) -> dict[str, Any]:
        """Create a new economic period."""
        await self.conn.execute(
            """
            INSERT INTO economic_periods (id, month, total_pool)
            VALUES (?, ?, ?)
            """,
            (id, month, total_pool)
        )
        await self.conn.commit()
        async with self.conn.execute(
            "SELECT * FROM economic_periods WHERE id = ?", (id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row)

    async def get_economic_period(self, month: str) -> Optional[dict[str, Any]]:
        """Get economic period by month."""
        async with self.conn.execute(
            "SELECT * FROM economic_periods WHERE month = ?", (month,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def record_node_earning(
        self,
        period_id: str,
        node_id: str,
        reputation_snapshot: float,
        share_percentage: float,
        amount: float
    ) -> None:
        """Record earnings for a node in a period."""
        await self.conn.execute(
            """
            INSERT INTO node_earnings (period_id, node_id, reputation_snapshot, share_percentage, amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            (period_id, node_id, reputation_snapshot, share_percentage, amount)
        )
        await self.conn.commit()

    async def mark_period_distributed(self, period_id: str) -> None:
        """Mark an economic period as distributed."""
        await self.conn.execute(
            "UPDATE economic_periods SET distributed = TRUE, distributed_at = ? WHERE id = ?",
            (datetime.utcnow(), period_id)
        )
        await self.conn.commit()

    # =========================================================================
    # Account Operations (Mullvad-style)
    # =========================================================================

    async def create_account(
        self,
        id: str,
        account_key_hash: str,
        account_key_prefix: str
    ) -> dict[str, Any]:
        """Create a new account."""
        await self.conn.execute(
            """
            INSERT INTO accounts (id, account_key_hash, account_key_prefix)
            VALUES (?, ?, ?)
            """,
            (id, account_key_hash, account_key_prefix)
        )
        await self.conn.commit()
        return await self.get_account_by_id(id)

    async def get_account_by_id(self, account_id: str) -> Optional[dict[str, Any]]:
        """Get account by ID."""
        async with self.conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_account_by_key_hash(self, key_hash: str) -> Optional[dict[str, Any]]:
        """Get account by account key hash."""
        async with self.conn.execute(
            "SELECT * FROM accounts WHERE account_key_hash = ?", (key_hash,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_account_nodes(self, account_id: str) -> list[dict[str, Any]]:
        """Get all nodes belonging to an account."""
        async with self.conn.execute(
            "SELECT * FROM nodes WHERE account_id = ? ORDER BY created_at DESC",
            (account_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_account_node_count(self, account_id: str) -> int:
        """Get count of nodes for an account."""
        async with self.conn.execute(
            "SELECT COUNT(*) as count FROM nodes WHERE account_id = ?",
            (account_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"]

    async def update_account_status(self, account_id: str, status: str) -> None:
        """Update account status."""
        await self.conn.execute(
            "UPDATE accounts SET status = ? WHERE id = ?",
            (status, account_id)
        )
        await self.conn.commit()

    async def update_account_activity(self, account_id: str) -> None:
        """Update account's last activity timestamp."""
        await self.conn.execute(
            "UPDATE accounts SET last_activity_at = ? WHERE id = ?",
            (datetime.utcnow(), account_id)
        )
        await self.conn.commit()

    async def update_account_earnings(
        self,
        account_id: str,
        amount: float
    ) -> None:
        """Add to account's total earnings."""
        await self.conn.execute(
            "UPDATE accounts SET total_earnings = total_earnings + ? WHERE id = ?",
            (amount, account_id)
        )
        await self.conn.commit()

    async def get_all_accounts(self) -> list[dict[str, Any]]:
        """Get all accounts."""
        async with self.conn.execute(
            "SELECT * FROM accounts ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def link_node_to_account(self, node_id: str, account_id: str) -> None:
        """Link a node to an account."""
        await self.conn.execute(
            "UPDATE nodes SET account_id = ? WHERE id = ?",
            (account_id, node_id)
        )
        await self.conn.commit()

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_stats(self) -> dict[str, Any]:
        """Get overall statistics."""
        async with self.conn.execute("SELECT COUNT(*) as count FROM users") as cursor:
            users_count = (await cursor.fetchone())["count"]

        async with self.conn.execute("SELECT COUNT(*) as count FROM nodes") as cursor:
            nodes_count = (await cursor.fetchone())["count"]

        async with self.conn.execute(
            "SELECT COUNT(*) as count FROM tasks WHERE DATE(created_at) = DATE('now')"
        ) as cursor:
            tasks_today = (await cursor.fetchone())["count"]

        async with self.conn.execute("SELECT COUNT(*) as count FROM tasks") as cursor:
            total_tasks = (await cursor.fetchone())["count"]

        return {
            "total_users": users_count,
            "total_nodes": nodes_count,
            "tasks_today": tasks_today,
            "total_tasks": total_tasks
        }


# Global database instance
db = Database()
