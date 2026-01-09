"""
Communications Screen - Brutalist Design.

Interactive chat interface for sending inference requests
with a terminal-style, cyberpunk aesthetic.
"""

from textual.app import ComposeResult
from textual.widgets import Static, Button, Select, TextArea
from textual.containers import Container, Horizontal, VerticalScroll
from textual import work
import httpx
import asyncio
from pathlib import Path


class ChatScreen(Container):
    """Interactive chat interface for sending inference requests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._messages = []
        self._token = None
        self._coordinator_url = "http://168.119.10.189:8000"
        self._load_token()

    def _load_token(self) -> None:
        """Load auth token from file."""
        try:
            token_path = Path.home() / ".iris" / "token"
            if token_path.exists():
                self._token = token_path.read_text().strip()
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        """Create the communications layout."""
        yield Static(" COMMUNICATIONS ", classes="section-title")

        # Messages area with brutalist container
        with VerticalScroll(id="messages-container"):
            yield Static(
                "[#444444]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n\n"
                "[#ff6a00]▌IRIS NETWORK COMMUNICATIONS TERMINAL▐[/]\n\n"
                "[#888888]Send a message to initiate distributed inference.\n"
                "Your prompts will be processed across the network.[/]\n\n"
                "[#444444]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]",
                classes="empty-chat",
                id="empty-state"
            )

        # Controls with brutalist styling
        with Horizontal(classes="controls-row"):
            yield Static("[#ff6a00]MODE[/]", classes="control-label")
            yield Select(
                [("SUBTASKS", "subtasks"), ("CONSENSUS", "consensus"), ("CONTEXT", "context")],
                value="subtasks",
                id="mode-select",
                prompt="MODE"
            )
            yield Static("[#00ffff]DIFF[/]", classes="control-label")
            yield Select(
                [("SIMPLE", "simple"), ("COMPLEX", "complex"), ("ADVANCED", "advanced")],
                value="simple",
                id="difficulty-select",
                prompt="DIFFICULTY"
            )

        # Input area
        yield TextArea(placeholder="> Enter command...", id="prompt-input")

        # Send button and status
        with Horizontal(classes="button-row"):
            yield Button("▶ TRANSMIT", id="send-btn", variant="primary")
            yield Static("[#00ffff]● READY[/]", id="status-label")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "send-btn":
            self._send_message()

    @work(exclusive=True)
    async def _send_message(self) -> None:
        """Send message to the network."""
        # Get input
        input_area = self.query_one("#prompt-input", TextArea)
        prompt = input_area.text.strip()

        if not prompt:
            self._update_status("[#ffaa00]⚠ ENTER PROMPT[/]")
            return

        if not self._token:
            self._update_status("[#ff0000]◼ NOT AUTHENTICATED[/]")
            self._add_system_message("Authentication required. Restarting TUI...")
            return

        # Get mode and difficulty
        mode = self.query_one("#mode-select", Select).value
        difficulty = self.query_one("#difficulty-select", Select).value

        # Clear input and update status
        input_area.clear()
        self._update_status("[#ffaa00]◐ TRANSMITTING...[/]")

        # Add user message to chat
        self._add_message("USER", prompt, is_user=True)

        try:
            # Send request
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._coordinator_url}/inference",
                    json={
                        "prompt": prompt,
                        "mode": mode,
                        "difficulty": difficulty
                    },
                    headers={"Authorization": f"Bearer {self._token}"}
                )

                if response.status_code == 200:
                    data = response.json()
                    task_id = data.get("task_id")

                    self._update_status(f"[#00ffff]◐ PROCESSING {task_id[:8]}[/]")

                    # Poll for result
                    result = await self._poll_for_result(client, task_id)

                    if result:
                        self._add_message("IRIS", result, is_user=False)
                        self._update_status("[#00ff41]▶ COMPLETE[/]")
                    else:
                        self._add_message("IRIS", "[#ff0000]ERROR: Task timeout or failure[/]", is_user=False)
                        self._update_status("[#ff0000]◼ FAILED[/]")

                elif response.status_code == 401:
                    self._update_status("[#ff0000]◼ AUTH EXPIRED[/]")
                    self._add_system_message("Session expired. Restart TUI to re-authenticate.")
                else:
                    error = response.json().get("detail", "Unknown error")
                    self._update_status(f"[#ff0000]◼ ERROR[/]")
                    self._add_system_message(f"Error: {error}")

        except httpx.TimeoutException:
            self._update_status("[#ff0000]◼ TIMEOUT[/]")
            self._add_system_message("Request timed out. Network may be busy.")
        except Exception as e:
            self._update_status("[#ff0000]◼ ERROR[/]")
            self._add_system_message(f"Error: {str(e)[:50]}")

    async def _poll_for_result(self, client: httpx.AsyncClient, task_id: str, max_attempts: int = 30) -> str:
        """Poll for task completion."""
        for attempt in range(max_attempts):
            try:
                response = await client.get(
                    f"{self._coordinator_url}/inference/{task_id}",
                    headers={"Authorization": f"Bearer {self._token}"}
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")

                    if status == "completed":
                        return data.get("final_response", "No response")
                    elif status in ("failed", "partial"):
                        return None

                    # Update status with progress indicator
                    dots = "." * ((attempt % 3) + 1)
                    self._update_status(f"[#00ffff]◐ PROCESSING{dots}[/]")

                await asyncio.sleep(2)

            except Exception:
                await asyncio.sleep(2)

        return None

    def _add_message(self, sender: str, content: str, is_user: bool = False) -> None:
        """Add a message to the chat with brutalist styling."""
        # Hide empty state
        try:
            empty = self.query_one("#empty-state", Static)
            empty.display = False
        except Exception:
            pass

        # Create message widget
        container = self.query_one("#messages-container", VerticalScroll)

        css_class = "user-message" if is_user else "assistant-message"

        # Brutalist message format
        if is_user:
            header = f"[#ff6a00 bold]▌{sender}▐[/]"
        else:
            header = f"[#00ffff bold]▌{sender}▐[/]"

        message = Static(
            f"{header}\n{content}",
            classes=f"message {css_class}"
        )

        container.mount(message)
        container.scroll_end()

        self._messages.append({"sender": sender, "content": content, "is_user": is_user})

    def _add_system_message(self, content: str) -> None:
        """Add a system message with warning styling."""
        try:
            empty = self.query_one("#empty-state", Static)
            empty.display = False
        except Exception:
            pass

        container = self.query_one("#messages-container", VerticalScroll)

        message = Static(
            f"[#ffaa00]▌SYSTEM▐[/] [#888888]{content}[/]",
            classes="message"
        )

        container.mount(message)
        container.scroll_end()

    def _update_status(self, status: str) -> None:
        """Update status label."""
        try:
            label = self.query_one("#status-label", Static)
            label.update(status)
        except Exception:
            pass
