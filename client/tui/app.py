"""
Iris Network TUI - Main Application
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static
from textual.binding import Binding
from textual.containers import Container
from textual import work
import httpx
import yaml
from pathlib import Path

from .screens import NodeScreen, NetworkScreen, ChatScreen


class IrisTUI(App):
    """Iris Network Terminal User Interface."""

    CSS_PATH = "styles.tcss"
    TITLE = "Iris Network"
    SUB_TITLE = "Distributed AI Inference"

    BINDINGS = [
        Binding("1", "show_tab('tab-node')", "Node", show=True),
        Binding("2", "show_tab('tab-network')", "Network", show=True),
        Binding("3", "show_tab('tab-chat')", "Chat", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=False),
    ]

    def __init__(
        self,
        config_path: str = None,
        coordinator_url: str = "http://168.119.10.189:8000"
    ):
        super().__init__()
        self.config_path = config_path
        self.coordinator_url = coordinator_url
        self.node_config = {}
        self.stats = {}
        self.nodes = []
        self.reputation = []

        # Load node config if provided
        if config_path:
            self._load_config(config_path)

    def _load_config(self, config_path: str):
        """Load node configuration from YAML file."""
        try:
            path = Path(config_path).expanduser()
            if path.exists():
                with open(path) as f:
                    self.node_config = yaml.safe_load(f) or {}
        except Exception as e:
            self.log.error(f"Failed to load config: {e}")

    def compose(self) -> ComposeResult:
        """Create the TUI layout."""
        yield Header()
        with TabbedContent(initial="tab-network"):
            with TabPane("Network", id="tab-network"):
                yield NetworkScreen(id="network-screen")
            with TabPane("Node", id="tab-node"):
                yield NodeScreen(id="node-screen")
            with TabPane("Chat", id="tab-chat"):
                yield ChatScreen(id="chat-screen")
        yield Footer()

    async def on_mount(self) -> None:
        """Called when app is mounted."""
        # Start auto-refresh
        self.set_interval(5, self.action_refresh)
        # Initial data fetch
        await self.action_refresh()

    def action_show_tab(self, tab_id: str) -> None:
        """Switch to a specific tab."""
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id

    @work(exclusive=True)
    async def action_refresh(self) -> None:
        """Refresh all data from coordinator."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch stats
                try:
                    response = await client.get(f"{self.coordinator_url}/stats")
                    if response.status_code == 200:
                        self.stats = response.json()
                except Exception:
                    pass

                # Fetch reputation/leaderboard
                try:
                    response = await client.get(f"{self.coordinator_url}/reputation")
                    if response.status_code == 200:
                        self.reputation = response.json()
                except Exception:
                    pass

                # Fetch nodes (may require auth)
                try:
                    response = await client.get(f"{self.coordinator_url}/nodes")
                    if response.status_code == 200:
                        self.nodes = response.json()
                except Exception:
                    pass

            # Update screens
            self._update_screens()

        except Exception as e:
            self.log.error(f"Refresh failed: {e}")

    def _update_screens(self) -> None:
        """Update all screens with new data."""
        # Update network screen
        try:
            network_screen = self.query_one("#network-screen", NetworkScreen)
            network_screen.update_data(self.stats, self.reputation, self.nodes)
        except Exception:
            pass

        # Update node screen
        try:
            node_screen = self.query_one("#node-screen", NodeScreen)
            node_screen.update_data(self.node_config, self.reputation)
        except Exception:
            pass

    def action_help(self) -> None:
        """Show help."""
        self.notify(
            "Keys: [1] Node [2] Network [3] Chat [R] Refresh [Q] Quit",
            title="Help"
        )
