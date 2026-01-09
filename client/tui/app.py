"""
Iris Network TUI - Main Application

Futuristic Brutalist Interface inspired by:
- Blade Runner
- Neon Genesis Evangelion
- Cyberpunk aesthetics
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
from .auth import AutoAuth


class IrisTUI(App):
    """Iris Network Terminal User Interface - Brutalist Edition."""

    CSS_PATH = "styles.tcss"
    TITLE = "IRIS NETWORK"
    SUB_TITLE = "DISTRIBUTED INFERENCE SYSTEM"

    BINDINGS = [
        Binding("1", "show_tab('tab-network')", "NET", show=True),
        Binding("2", "show_tab('tab-node')", "SYS", show=True),
        Binding("3", "show_tab('tab-chat')", "COM", show=True),
        Binding("r", "refresh", "SYNC", show=True),
        Binding("q", "quit", "EXIT", show=True),
        Binding("?", "help", "HELP", show=False),
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
        self.auth = AutoAuth(coordinator_url)
        self._authenticated = False

        # Load node config
        self._load_config(config_path)

    def _load_config(self, config_path: str = None):
        """Load node configuration from YAML file."""
        # Try provided path first, then default
        paths_to_try = []
        if config_path:
            paths_to_try.append(Path(config_path).expanduser())
        paths_to_try.append(Path.home() / ".iris" / "config.yaml")

        for path in paths_to_try:
            try:
                if path.exists():
                    with open(path) as f:
                        self.node_config = yaml.safe_load(f) or {}
                        break
            except Exception:
                pass

    def compose(self) -> ComposeResult:
        """Create the TUI layout."""
        yield Header()
        with TabbedContent(initial="tab-network"):
            with TabPane("NET", id="tab-network"):
                yield NetworkScreen(id="network-screen")
            with TabPane("SYS", id="tab-node"):
                yield NodeScreen(id="node-screen")
            with TabPane("COM", id="tab-chat"):
                yield ChatScreen(id="chat-screen")
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        # Start authentication
        self._authenticate()
        # Start auto-refresh
        self.set_interval(5, self.action_refresh)
        # Initial data fetch
        self.action_refresh()

    @work(exclusive=True)
    async def _authenticate(self) -> None:
        """Perform automatic authentication."""
        success, message = await self.auth.ensure_authenticated()
        self._authenticated = success
        if success:
            self.notify(f"[#00ff41]AUTHENTICATED[/]", title="AUTH")
        else:
            self.notify(f"[#ff0000]AUTH FAILED: {message}[/]", title="AUTH")

    def action_show_tab(self, tab_id: str) -> None:
        """Switch to a specific tab."""
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id

    @work(exclusive=True)
    async def action_refresh(self) -> None:
        """Refresh all data from coordinator."""
        headers = {}
        if self.auth.token:
            headers["Authorization"] = f"Bearer {self.auth.token}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch stats
                try:
                    response = await client.get(
                        f"{self.coordinator_url}/stats",
                        headers=headers
                    )
                    if response.status_code == 200:
                        self.stats = response.json()
                except Exception:
                    pass

                # Fetch reputation/leaderboard
                try:
                    response = await client.get(
                        f"{self.coordinator_url}/reputation",
                        headers=headers
                    )
                    if response.status_code == 200:
                        self.reputation = response.json()
                except Exception:
                    pass

                # Fetch nodes (requires auth)
                try:
                    response = await client.get(
                        f"{self.coordinator_url}/nodes",
                        headers=headers
                    )
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
        """Show help notification."""
        self.notify(
            "[#ff6a00]1[/] NET  [#ff6a00]2[/] SYS  [#ff6a00]3[/] COM  "
            "[#ff6a00]R[/] SYNC  [#ff6a00]Q[/] EXIT",
            title="COMMANDS"
        )
