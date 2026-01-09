"""
Iris Economics Module

Manages the economic pool and distribution of earnings to nodes.
"""

from datetime import datetime
from typing import Optional
import structlog

from shared.models import generate_id
from .database import db

logger = structlog.get_logger()


class EconomicsManager:
    """
    Manages the club's economic model.

    Key functions:
    - Track monthly pools
    - Calculate share distribution based on reputation
    - Record earnings for nodes
    """

    async def create_period(
        self,
        month: str,
        total_pool: float
    ) -> dict:
        """
        Create a new economic period.

        Args:
            month: Month string (format: "2025-01")
            total_pool: Total amount to distribute

        Returns:
            Created period record
        """
        # Check if period already exists
        existing = await db.get_economic_period(month)
        if existing:
            logger.warning("period_already_exists", month=month)
            return existing

        period = await db.create_economic_period(
            id=generate_id(),
            month=month,
            total_pool=total_pool
        )

        logger.info(
            "economic_period_created",
            month=month,
            total_pool=total_pool
        )

        return period

    async def calculate_shares(
        self,
        month: str
    ) -> dict[str, dict]:
        """
        Calculate share distribution for a period.

        Distribution is proportional to reputation:
        - Node share = (node_reputation / total_reputation) * pool

        Args:
            month: Month to calculate for

        Returns:
            Dictionary mapping node_id to earnings info
        """
        period = await db.get_economic_period(month)
        if not period:
            raise ValueError(f"No economic period found for {month}")

        if period["distributed"]:
            logger.warning("period_already_distributed", month=month)
            return {}

        total_pool = period["total_pool"]

        # Get all nodes with positive reputation
        nodes = await db.get_all_nodes()
        eligible_nodes = [
            n for n in nodes
            if n.get("reputation", 0) > 0
        ]

        if not eligible_nodes:
            logger.warning("no_eligible_nodes", month=month)
            return {}

        # Calculate total reputation
        total_reputation = sum(
            n.get("reputation", 0) for n in eligible_nodes
        )

        if total_reputation <= 0:
            return {}

        # Calculate shares
        shares = {}
        for node in eligible_nodes:
            node_id = node["id"]
            reputation = node.get("reputation", 0)
            share_percentage = reputation / total_reputation
            amount = share_percentage * total_pool

            shares[node_id] = {
                "node_id": node_id,
                "reputation_snapshot": reputation,
                "share_percentage": share_percentage * 100,  # as percentage
                "amount": round(amount, 2)
            }

        logger.info(
            "shares_calculated",
            month=month,
            total_pool=total_pool,
            nodes=len(shares),
            total_reputation=total_reputation
        )

        return shares

    async def distribute(self, month: str) -> dict[str, dict]:
        """
        Distribute earnings for a period.

        This records earnings and marks the period as distributed.

        Args:
            month: Month to distribute

        Returns:
            Distribution results
        """
        period = await db.get_economic_period(month)
        if not period:
            raise ValueError(f"No economic period found for {month}")

        if period["distributed"]:
            raise ValueError(f"Period {month} already distributed")

        # Calculate shares
        shares = await self.calculate_shares(month)

        if not shares:
            logger.warning("no_shares_to_distribute", month=month)
            return {}

        # Record earnings
        period_id = period["id"]
        for node_id, share_info in shares.items():
            await db.record_node_earning(
                period_id=period_id,
                node_id=node_id,
                reputation_snapshot=share_info["reputation_snapshot"],
                share_percentage=share_info["share_percentage"],
                amount=share_info["amount"]
            )

        # Mark period as distributed
        await db.mark_period_distributed(period_id)

        logger.info(
            "period_distributed",
            month=month,
            period_id=period_id,
            nodes=len(shares),
            total_distributed=sum(s["amount"] for s in shares.values())
        )

        return shares

    async def get_node_earnings(
        self,
        node_id: str,
        limit: int = 12
    ) -> list[dict]:
        """
        Get earnings history for a node.

        Args:
            node_id: Node ID
            limit: Maximum periods to return

        Returns:
            List of earning records
        """
        async with db.conn.execute(
            """
            SELECT ne.*, ep.month
            FROM node_earnings ne
            JOIN economic_periods ep ON ne.period_id = ep.id
            WHERE ne.node_id = ?
            ORDER BY ep.month DESC
            LIMIT ?
            """,
            (node_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_total_earnings(self, node_id: str) -> float:
        """Get total lifetime earnings for a node."""
        async with db.conn.execute(
            "SELECT SUM(amount) as total FROM node_earnings WHERE node_id = ?",
            (node_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["total"] or 0.0

    async def get_period_summary(self, month: str) -> Optional[dict]:
        """
        Get summary for an economic period.

        Args:
            month: Month to summarize

        Returns:
            Period summary or None
        """
        period = await db.get_economic_period(month)
        if not period:
            return None

        # Get earnings for this period
        async with db.conn.execute(
            """
            SELECT COUNT(*) as nodes, SUM(amount) as distributed
            FROM node_earnings
            WHERE period_id = ?
            """,
            (period["id"],)
        ) as cursor:
            row = await cursor.fetchone()

        return {
            "month": month,
            "total_pool": period["total_pool"],
            "distributed": period["distributed"],
            "distributed_at": period.get("distributed_at"),
            "nodes_paid": row["nodes"] or 0,
            "amount_distributed": row["distributed"] or 0.0
        }

    async def preview_distribution(self, total_pool: float) -> list[dict]:
        """
        Preview how a pool would be distributed with current reputations.

        Args:
            total_pool: Hypothetical pool amount

        Returns:
            List of projected earnings per node
        """
        nodes = await db.get_all_nodes()
        eligible = [n for n in nodes if n.get("reputation", 0) > 0]

        if not eligible:
            return []

        total_rep = sum(n.get("reputation", 0) for n in eligible)

        preview = []
        for node in eligible:
            rep = node.get("reputation", 0)
            share = rep / total_rep if total_rep > 0 else 0
            preview.append({
                "node_id": node["id"],
                "model_name": node.get("model_name", "unknown"),
                "reputation": rep,
                "share_percentage": round(share * 100, 2),
                "projected_amount": round(share * total_pool, 2)
            })

        # Sort by projected amount
        preview.sort(key=lambda x: x["projected_amount"], reverse=True)

        return preview


# Global economics manager instance
economics_manager = EconomicsManager()
