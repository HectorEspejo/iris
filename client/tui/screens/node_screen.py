"""Node Status Screen."""

from textual.app import ComposeResult
from textual.widgets import Static, DataTable, RichLog, ProgressBar
from textual.containers import Container, Horizontal, Vertical

from ..widgets import StatsCard, StatusIndicator


class NodeScreen(Container):
    """Screen showing the local node status and metrics."""

    DEFAULT_CSS = """
    NodeScreen {
        layout: vertical;
        padding: 1;
    }

    .node-info-panel {
        height: auto;
        border: solid $primary;
        padding: 1 2;
        margin: 1;
        background: $surface-lighten-1;
    }

    .info-row {
        height: 1;
    }

    .info-label {
        width: 18;
        color: $text-muted;
    }

    .info-value {
        width: 1fr;
        text-style: bold;
    }

    .reputation-section {
        height: auto;
        padding: 1;
        margin: 1;
    }

    .rep-bar-container {
        height: 1;
        margin: 0 1;
    }

    .rep-text {
        text-align: center;
        padding: 1;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._node_config = {}
        self._reputation = []

    def compose(self) -> ComposeResult:
        """Create the node status layout."""
        yield Static(" Node Status ", classes="section-title")

        # Connection status and node info
        with Container(classes="node-info-panel"):
            with Horizontal(classes="info-row"):
                yield StatusIndicator(id="conn-status")

            with Horizontal(classes="info-row"):
                yield Static("Node ID:", classes="info-label")
                yield Static("Not configured", id="node-id", classes="info-value")

            with Horizontal(classes="info-row"):
                yield Static("Model:", classes="info-label")
                yield Static("-", id="model-name", classes="info-value")

            with Horizontal(classes="info-row"):
                yield Static("Coordinator:", classes="info-label")
                yield Static("-", id="coordinator-url", classes="info-value")

            with Horizontal(classes="info-row"):
                yield Static("LM Studio:", classes="info-label")
                yield Static("-", id="lmstudio-url", classes="info-value")

        yield Static(" Performance ", classes="section-title")

        with Horizontal(classes="stats-row"):
            yield StatsCard("Load", "0/10", icon="[cyan]Load[/]", id="perf-load")
            yield StatsCard("VRAM", "- GB", icon="[green]VRAM[/]", id="perf-vram")
            yield StatsCard("Speed", "- t/s", icon="[blue]Speed[/]", id="perf-speed")
            yield StatsCard("Tasks", "0", icon="[magenta]Tasks[/]", id="perf-tasks")

        yield Static(" Reputation ", classes="section-title")

        with Container(classes="reputation-section"):
            yield Static("Reputation: - / 100", id="rep-text", classes="rep-text")
            yield ProgressBar(total=100, show_eta=False, id="rep-bar")
            yield Static("Rank: -", id="rank-text", classes="rep-text")

        yield Static(" Activity Log ", classes="section-title")
        yield RichLog(id="activity-log", max_lines=50, highlight=True, markup=True)

    def on_mount(self) -> None:
        """Initialize when mounted."""
        log = self.query_one("#activity-log", RichLog)
        log.write("[dim]Waiting for node data...[/]")

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
            self._update_static("#coordinator-url", config.get("coordinator_url", "-")[:40])
            self._update_static("#lmstudio-url", config.get("lmstudio_url", "-"))

            # Log the update
            log = self.query_one("#activity-log", RichLog)
            log.write(f"[green]Node config loaded:[/] {config.get('node_id', 'Unknown')}")

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

                # Update reputation display
                self._update_static("#rep-text", f"Reputation: {rep_value} / 100")
                self._update_static("#rank-text", f"Rank: #{rank} of {len(reputation)}")
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
            log.write("[yellow]No node configuration found.[/]")
            log.write("[dim]Run with --config to specify a config file.[/]")
        except Exception:
            pass
