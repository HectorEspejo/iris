"""
Iris Account Service

Business logic for Mullvad-style account management.
"""

from typing import Optional
import uuid
import structlog

from .database import db
from .accounts import AccountKeyGenerator
from shared.models import (
    Account,
    AccountStatus,
    AccountCreateResponse,
    AccountInfo,
    AccountWithNodes,
    Node,
)

logger = structlog.get_logger()


class AccountService:
    """
    Service for managing Mullvad-style accounts.

    Handles account creation, verification, and node linking.
    """

    async def create_account(self) -> AccountCreateResponse:
        """
        Create a new account with a generated Account Key.

        Returns:
            AccountCreateResponse with the full key (shown only once!)
        """
        # Generate account key
        account_key = AccountKeyGenerator.generate()
        account_key_hash = AccountKeyGenerator.hash_key(account_key)
        account_key_prefix = AccountKeyGenerator.get_prefix(account_key)
        account_id = str(uuid.uuid4())

        # Create in database
        account_data = await db.create_account(
            id=account_id,
            account_key_hash=account_key_hash,
            account_key_prefix=account_key_prefix
        )

        logger.info(
            "account_created",
            account_id=account_id,
            prefix=account_key_prefix
        )

        account = Account(
            id=account_data["id"],
            account_key_prefix=account_data["account_key_prefix"],
            status=AccountStatus(account_data["status"]),
            total_earnings=account_data["total_earnings"],
            created_at=account_data["created_at"],
            last_activity_at=account_data.get("last_activity_at")
        )

        return AccountCreateResponse(
            account_key=account_key,  # Only shown once!
            account=account
        )

    async def verify_account(self, account_key: str) -> Optional[Account]:
        """
        Verify an account key and return the account if valid.

        Args:
            account_key: The account key to verify

        Returns:
            Account if valid, None otherwise
        """
        if not AccountKeyGenerator.validate_format(account_key):
            logger.warning("invalid_account_key_format")
            return None

        key_hash = AccountKeyGenerator.hash_key(account_key)
        account_data = await db.get_account_by_key_hash(key_hash)

        if not account_data:
            logger.warning(
                "account_not_found",
                prefix=AccountKeyGenerator.get_prefix(account_key)
            )
            return None

        if account_data["status"] != "active":
            logger.warning(
                "account_not_active",
                status=account_data["status"],
                prefix=account_data["account_key_prefix"]
            )
            return None

        # Update last activity
        await db.update_account_activity(account_data["id"])

        return Account(
            id=account_data["id"],
            account_key_prefix=account_data["account_key_prefix"],
            status=AccountStatus(account_data["status"]),
            total_earnings=account_data["total_earnings"],
            created_at=account_data["created_at"],
            last_activity_at=account_data.get("last_activity_at")
        )

    async def get_account_by_key(self, account_key: str) -> Optional[AccountInfo]:
        """
        Get account information by account key.

        Args:
            account_key: The account key

        Returns:
            AccountInfo with node count, or None if not found
        """
        account = await self.verify_account(account_key)
        if not account:
            return None

        node_count = await db.get_account_node_count(account.id)

        return AccountInfo(
            id=account.id,
            account_key_prefix=account.account_key_prefix,
            status=account.status,
            total_earnings=account.total_earnings,
            node_count=node_count,
            created_at=account.created_at,
            last_activity_at=account.last_activity_at
        )

    async def get_account_with_nodes(
        self,
        account_key: str
    ) -> Optional[AccountWithNodes]:
        """
        Get account with all its linked nodes.

        Args:
            account_key: The account key

        Returns:
            AccountWithNodes or None if not found
        """
        account = await self.verify_account(account_key)
        if not account:
            return None

        nodes_data = await db.get_account_nodes(account.id)
        nodes = []
        total_reputation = 0.0

        for node_data in nodes_data:
            # Build Node object (simplified - capabilities not stored separately)
            from shared.models import NodeCapabilities
            capabilities = NodeCapabilities(
                lmstudio_port=node_data.get("lmstudio_port", 1234),
                model_name=node_data.get("model_name", "unknown"),
                max_context=node_data.get("max_context", 8192),
                vram_gb=node_data.get("vram_gb", 8.0),
                gpu_name=node_data.get("gpu_name", "Unknown"),
                model_params=node_data.get("model_params", 7.0),
                model_quantization=node_data.get("model_quantization", "Q4"),
                tokens_per_second=node_data.get("tokens_per_second", 0.0)
            )

            node = Node(
                id=node_data["id"],
                public_key=node_data["public_key"],
                capabilities=capabilities,
                owner_id=node_data.get("owner_id"),
                account_id=node_data.get("account_id"),
                reputation=node_data.get("reputation", 100.0),
                total_tasks_completed=node_data.get("total_tasks_completed", 0),
                created_at=node_data["created_at"],
                last_seen_at=node_data.get("last_seen_at")
            )
            nodes.append(node)
            total_reputation += node.reputation

        return AccountWithNodes(
            account=account,
            nodes=nodes,
            total_reputation=total_reputation
        )

    async def get_account_nodes(self, account_key: str) -> Optional[list[dict]]:
        """
        Get all nodes for an account (simplified dict format).

        Args:
            account_key: The account key

        Returns:
            List of node dicts or None if account not found
        """
        account = await self.verify_account(account_key)
        if not account:
            return None

        return await db.get_account_nodes(account.id)

    async def suspend_account(self, account_id: str) -> bool:
        """
        Suspend an account.

        Args:
            account_id: The account ID to suspend

        Returns:
            True if successful
        """
        await db.update_account_status(account_id, "suspended")
        logger.info("account_suspended", account_id=account_id)
        return True

    async def reactivate_account(self, account_id: str) -> bool:
        """
        Reactivate a suspended account.

        Args:
            account_id: The account ID to reactivate

        Returns:
            True if successful
        """
        await db.update_account_status(account_id, "active")
        logger.info("account_reactivated", account_id=account_id)
        return True

    async def get_all_accounts(self) -> list[AccountInfo]:
        """
        Get all accounts (admin function).

        Returns:
            List of AccountInfo objects
        """
        accounts_data = await db.get_all_accounts()
        accounts = []

        for acc_data in accounts_data:
            node_count = await db.get_account_node_count(acc_data["id"])
            accounts.append(AccountInfo(
                id=acc_data["id"],
                account_key_prefix=acc_data["account_key_prefix"],
                status=AccountStatus(acc_data["status"]),
                total_earnings=acc_data["total_earnings"],
                node_count=node_count,
                created_at=acc_data["created_at"],
                last_activity_at=acc_data.get("last_activity_at")
            ))

        return accounts


# Global service instance
account_service = AccountService()
