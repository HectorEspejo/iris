"""
Network Dashboard Screen - Brutalist Design.

Displays network statistics, active nodes, and reputation leaderboard
with a futuristic brutalist aesthetic.
"""

from textual.app import ComposeResult
from textual.widgets import Static, DataTable
from textual.containers import Container, Horizontal, Vertical, VerticalScroll

from ..widgets import StatsCard


class NetworkScreen(Container):
    """Dashboard showing network statistics and node information."""

    def compose(self) -> ComposeResult:
        """Create the network dashboard layout."""
        yield Static(" NETWORK OVERVIEW ", classes="section-title")

        with Horizontal(classes="stats-row"):
            yield StatsCard(
                "ONLINE",
                "0",
                icon="[#ff6a00]◉[/]",
                id="stat-nodes"
            )
            yield StatsCard(
                "TODAY",
                "0",
                icon="[#00ffff]▤[/]",
                id="stat-today"
            )
            yield StatsCard(
                "TOTAL",
                "0",
                icon="[#ff6a00]Σ[/]",
                id="stat-total"
            )
            yield StatsCard(
                "USERS",
                "0",
                icon="[#00ffff]◎[/]",
                id="stat-users"
            )

        yield Static(" ACTIVE NODES ", classes="section-title")
        yield DataTable(id="nodes-table")

        yield Static(" LEADERBOARD ", classes="section-title")
        yield DataTable(id="leaderboard-table")

    def on_mount(self) -> None:
        """Initialize tables when mounted."""
        # Setup nodes table
        nodes_table = self.query_one("#nodes-table", DataTable)
        nodes_table.add_columns("NODE ID", "TIER", "MODEL", "LOAD", "STATUS")
        nodes_table.cursor_type = "row"

        # Setup leaderboard table
        leaderboard = self.query_one("#leaderboard-table", DataTable)
        leaderboard.add_columns("RANK", "NODE ID", "REP", "TASKS")
        leaderboard.cursor_type = "row"

    def update_data(self, stats: dict, reputation: list, nodes: list) -> None:
        """Update the screen with new data."""
        # Update stats cards
        if stats:
            self._update_card("stat-nodes", str(stats.get("nodes_online", 0)))
            self._update_card("stat-today", str(stats.get("tasks_today", 0)))
            self._update_card("stat-total", str(stats.get("total_tasks", 0)))
            self._update_card("stat-users", str(stats.get("total_users", 0)))

        # Update nodes table
        self._update_nodes_table(nodes if nodes else [])

        # Update leaderboard
        self._update_leaderboard(reputation if reputation else [])

    def _update_card(self, card_id: str, value: str) -> None:
        """Update a stats card value."""
        try:
            card = self.query_one(f"#{card_id}", StatsCard)
            card.update_value(value)
        except Exception:
            pass

    def _update_nodes_table(self, nodes: list) -> None:
        """Update the active nodes table."""
        try:
            table = self.query_one("#nodes-table", DataTable)
            table.clear()

            for node in nodes[:10]:  # Show top 10
                node_id = node.get("node_id", "Unknown")[:20]
                tier = node.get("node_tier", "BASIC")
                model = node.get("model_name", "Unknown")[:15]
                load = f"{node.get('current_load', 0)}/10"
                is_online = node.get("is_online", True)

                # Format status with Evangelion-style indicator
                status = "[#00ff41]▶ ON[/]" if is_online else "[#ff0000]◼ OFF[/]"

                # Color tier with brutalist style
                tier_display = self._format_tier(tier)

                table.add_row(node_id, tier_display, model, load, status)

        except Exception:
            pass

    def _update_leaderboard(self, reputation: list) -> None:
        """Update the reputation leaderboard."""
        try:
            table = self.query_one("#leaderboard-table", DataTable)
            table.clear()

            # Brutalist rank indicators
            ranks = ["[#ff6a00]#01[/]", "[#00ffff]#02[/]", "[#ff0055]#03[/]"]

            for i, node in enumerate(reputation[:10]):  # Show top 10
                rank = ranks[i] if i < 3 else f"#{i + 1:02d}"
                node_id = node.get("node_id", "Unknown")[:20]
                rep = node.get("reputation", 0)
                tasks = node.get("tasks_completed", 0)

                # Create mini progress bar for reputation
                bar_filled = int(rep / 100 * 10)
                bar_empty = 10 - bar_filled
                rep_bar = f"[#ff6a00]{'▓' * bar_filled}[/][#444444]{'░' * bar_empty}[/] {rep}"

                table.add_row(rank, node_id, rep_bar, str(tasks))

        except Exception:
            pass

    def _format_tier(self, tier: str) -> str:
        """Format tier with brutalist colors."""
        colors = {
            "PREMIUM": "[#ff6a00 bold]▌PREMIUM▐[/]",
            "STANDARD": "[#00ffff]▌STANDARD▐[/]",
            "BASIC": "[#666666]▌BASIC▐[/]",
        }
        return colors.get(tier.upper(), f"▌{tier}▐")
