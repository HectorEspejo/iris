"""
System Status Screen - Brutalist Design.

Displays local node status, performance metrics, and activity log
with Evangelion-inspired indicators and heavy borders.
"""

from textual.app import ComposeResult
from textual.widgets import Static, RichLog, ProgressBar
from textual.containers import Container, Horizontal, Vertical

from ..widgets import StatsCard, StatusIndicator


class NodeScreen(Container):
    """Screen showing the local node status and metrics."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._node_config = {}
        self._reputation = []

    def compose(self) -> ComposeResult:
        """Create the system status layout."""
        yield Static(" SYSTEM STATUS ", classes="section-title")

        # Connection status and node info panel
        with Container(classes="node-info-panel"):
            with Horizontal(classes="info-row"):
                yield StatusIndicator(id="conn-status")
                yield Static("", id="uptime-display", classes="info-value")

            yield Static("━" * 60, classes="info-separator")

            with Horizontal(classes="info-row"):
                yield Static("NODE ID", classes="info-label")
                yield Static("Not configured", id="node-id", classes="info-value")

            with Horizontal(classes="info-row"):
                yield Static("MODEL", classes="info-label")
                yield Static("-", id="model-name", classes="info-value")

            with Horizontal(classes="info-row"):
                yield Static("ENDPOINT", classes="info-label")
                yield Static("-", id="coordinator-url", classes="info-value")

        yield Static(" PERFORMANCE ", classes="section-title")

        with Horizontal(classes="stats-row"):
            yield StatsCard(
                "LOAD",
                "0/10",
                icon="[#ff6a00]◈[/]",
                id="perf-load"
            )
            yield StatsCard(
                "VRAM",
                "- GB",
                icon="[#00ffff]▣[/]",
                id="perf-vram"
            )
            yield StatsCard(
                "SPEED",
                "- t/s",
                icon="[#ff6a00]▸[/]",
                id="perf-speed"
            )
            yield StatsCard(
                "TASKS",
                "0",
                icon="[#00ffff]◆[/]",
                id="perf-tasks"
            )

        yield Static(" REPUTATION ", classes="section-title")

        with Container(classes="reputation-section"):
            yield Static("REPUTATION: - / 100", id="rep-text", classes="rep-text")
            yield ProgressBar(total=100, show_eta=False, id="rep-bar")
            yield Static("RANK: -", id="rank-text", classes="rep-text")

        yield Static(" ACTIVITY LOG ", classes="section-title")
        yield RichLog(id="activity-log", max_lines=50, highlight=True, markup=True)

    def on_mount(self) -> None:
        """Initialize when mounted."""
        log = self.query_one("#activity-log", RichLog)
        log.write("[#444444]▶ Waiting for node data...[/]")

    def update_data(self, config: dict, reputation: list) -> None:
        """Update the screen with node data."""
        self._node_config = config
        self._reputation = reputation

        if config:
            self._update_node_info(config)
            self._update_reputation_from_list(config.get("node_id"), reputation)
        else:
            self._show_not_configured()

    def _update_node_info(self, config: dict) -> None:
        """Update node information display."""
        try:
            # Update status
            status = self.query_one("#conn-status", StatusIndicator)
            status.set_state("connected" if config else "disconnected")

            # Update info fields
            self._update_static("#node-id", config.get("node_id", "Unknown"))

            coord_url = config.get("coordinator_url", "-")
            if len(coord_url) > 40:
                coord_url = coord_url[:37] + "..."
            self._update_static("#coordinator-url", coord_url)

            # Log the update
            log = self.query_one("#activity-log", RichLog)
            log.write(f"[#00ff41]▶ Node config loaded:[/] {config.get('node_id', 'Unknown')}")

        except Exception:
            pass

    def _update_reputation_from_list(self, node_id: str, reputation: list) -> None:
        """Find and update reputation for this node."""
        if not node_id or not reputation:
            return

        try:
            # Find this node in the reputation list
            rank = -1
            node_rep = None

            for i, node in enumerate(reputation):
                if node.get("node_id") == node_id:
                    rank = i + 1
                    node_rep = node
                    break

            if node_rep:
                rep_value = node_rep.get("reputation", 0)
                tasks = node_rep.get("tasks_completed", 0)
                model = node_rep.get("model_name", "-")

                # Update reputation display with brutalist style
                self._update_static("#rep-text", f"REPUTATION: {rep_value} / 100")
                self._update_static("#rank-text", f"RANK: #{rank:02d} OF {len(reputation)}")
                self._update_static("#model-name", model)

                # Update progress bar
                try:
                    bar = self.query_one("#rep-bar", ProgressBar)
                    bar.update(progress=min(rep_value, 100))
                except Exception:
                    pass

                # Update tasks card
                try:
                    card = self.query_one("#perf-tasks", StatsCard)
                    card.update_value(str(tasks))
                except Exception:
                    pass

                # Log reputation update
                log = self.query_one("#activity-log", RichLog)
                log.write(f"[#00ffff]▶ Reputation sync:[/] {rep_value}/100 (Rank #{rank})")

        except Exception:
            pass

    def _update_static(self, selector: str, value: str) -> None:
        """Update a static widget's content."""
        try:
            widget = self.query_one(selector, Static)
            widget.update(value)
        except Exception:
            pass

    def _show_not_configured(self) -> None:
        """Show not configured state."""
        try:
            status = self.query_one("#conn-status", StatusIndicator)
            status.set_state("disconnected")

            log = self.query_one("#activity-log", RichLog)
            log.write("[#ffaa00]⚠ No node configuration found.[/]")
            log.write("[#444444]▶ Run with --config to specify a config file.[/]")
        except Exception:
            pass

    def log_activity(self, message: str, level: str = "info") -> None:
        """Add an entry to the activity log."""
        try:
            log = self.query_one("#activity-log", RichLog)
            colors = {
                "info": "#00ffff",
                "success": "#00ff41",
                "warning": "#ffaa00",
                "error": "#ff0000"
            }
            color = colors.get(level, "#888888")
            log.write(f"[{color}]▶[/] {message}")
        except Exception:
            pass
