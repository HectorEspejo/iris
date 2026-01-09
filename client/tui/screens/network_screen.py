"""Network Dashboard Screen."""

from textual.app import ComposeResult
from textual.widgets import Static, DataTable
from textual.containers import Container, Horizontal, Vertical, VerticalScroll

from ..widgets import StatsCard


class NetworkScreen(Container):
    """Dashboard showing network statistics and node information."""

    DEFAULT_CSS = """
    NetworkScreen {
        layout: vertical;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the network dashboard layout."""
        yield Static(" Network Overview ", classes="section-title")

        with Horizontal(classes="stats-row"):
            yield StatsCard("Nodes Online", "0", icon="[bold cyan]Nodes[/]", id="stat-nodes")
            yield StatsCard("Tasks Today", "0", icon="[bold green]Today[/]", id="stat-today")
            yield StatsCard("Total Tasks", "0", icon="[bold blue]Total[/]", id="stat-total")
            yield StatsCard("Users", "0", icon="[bold magenta]Users[/]", id="stat-users")

        yield Static(" Active Nodes ", classes="section-title")
        yield DataTable(id="nodes-table")

        yield Static(" Reputation Leaderboard ", classes="section-title")
        yield DataTable(id="leaderboard-table")

    def on_mount(self) -> None:
        """Initialize tables when mounted."""
        # Setup nodes table
        nodes_table = self.query_one("#nodes-table", DataTable)
        nodes_table.add_columns("Node ID", "Tier", "Model", "Load", "Status")

        # Setup leaderboard table
        leaderboard = self.query_one("#leaderboard-table", DataTable)
        leaderboard.add_columns("Rank", "Node ID", "Reputation", "Tasks")

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
                status = "[green]Online[/]" if node.get("is_online", True) else "[red]Offline[/]"

                # Color tier
                tier_display = self._format_tier(tier)

                table.add_row(node_id, tier_display, model, load, status)

        except Exception:
            pass

    def _update_leaderboard(self, reputation: list) -> None:
        """Update the reputation leaderboard."""
        try:
            table = self.query_one("#leaderboard-table", DataTable)
            table.clear()

            medals = ["[yellow]1[/]", "[white]2[/]", "[#cd7f32]3[/]"]

            for i, node in enumerate(reputation[:10]):  # Show top 10
                rank = medals[i] if i < 3 else str(i + 1)
                node_id = node.get("node_id", "Unknown")[:25]
                rep = str(node.get("reputation", 0))
                tasks = str(node.get("tasks_completed", 0))

                table.add_row(rank, node_id, rep, tasks)

        except Exception:
            pass

    def _format_tier(self, tier: str) -> str:
        """Format tier with color."""
        colors = {
            "PREMIUM": "[bold #ffd700]PREMIUM[/]",
            "STANDARD": "[#c0c0c0]STANDARD[/]",
            "BASIC": "[#cd7f32]BASIC[/]",
        }
        return colors.get(tier.upper(), tier)
