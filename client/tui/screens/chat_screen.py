"""Chat Screen."""

from textual.app import ComposeResult
from textual.widgets import Static, Button, Select, TextArea, RichLog
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual import work
import httpx
import asyncio
from pathlib import Path


class ChatScreen(Container):
    """Interactive chat interface for sending inference requests."""

    DEFAULT_CSS = """
    ChatScreen {
        layout: vertical;
        padding: 1;
    }

    #messages-container {
        height: 1fr;
        border: solid $primary;
        margin: 1;
        padding: 1;
        background: $surface-lighten-1;
    }

    .message {
        margin-bottom: 1;
        padding: 1;
        border: solid $primary-darken-1;
    }

    .user-message {
        background: $primary-darken-2;
        border-left: thick $accent;
    }

    .assistant-message {
        background: $surface-lighten-2;
        border-left: thick $success;
    }

    .message-header {
        color: $accent;
        text-style: bold;
    }

    .message-content {
        padding-top: 1;
    }

    .controls-row {
        height: auto;
        padding: 0 1;
    }

    #mode-select {
        width: 20;
    }

    #difficulty-select {
        width: 20;
        margin-left: 1;
    }

    #prompt-input {
        height: 5;
        margin: 1;
        border: solid $accent;
    }

    .button-row {
        height: auto;
        padding: 0 1;
    }

    #send-btn {
        width: 15;
    }

    #status-label {
        margin-left: 2;
        padding: 1;
        color: $text-muted;
    }

    .empty-chat {
        text-align: center;
        color: $text-muted;
        padding: 5;
    }
    """

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
        """Create the chat layout."""
        yield Static(" Iris Chat ", classes="section-title")

        # Messages area
        with VerticalScroll(id="messages-container"):
            yield Static(
                "Send a message to start chatting with Iris Network.\n\n"
                "Your prompts will be distributed across the network\n"
                "and processed by available nodes.",
                classes="empty-chat",
                id="empty-state"
            )

        # Controls
        with Horizontal(classes="controls-row"):
            yield Select(
                [("subtasks", "Subtasks"), ("consensus", "Consensus"), ("context", "Context")],
                value="subtasks",
                id="mode-select",
                prompt="Mode"
            )
            yield Select(
                [("simple", "Simple"), ("complex", "Complex"), ("advanced", "Advanced")],
                value="simple",
                id="difficulty-select",
                prompt="Difficulty"
            )

        # Input
        yield TextArea(placeholder="Enter your prompt here...", id="prompt-input")

        # Send button and status
        with Horizontal(classes="button-row"):
            yield Button("Send", id="send-btn", variant="primary")
            yield Static("Ready", id="status-label")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "send-btn":
            await self._send_message()

    @work(exclusive=True)
    async def _send_message(self) -> None:
        """Send message to the network."""
        # Get input
        input_area = self.query_one("#prompt-input", TextArea)
        prompt = input_area.text.strip()

        if not prompt:
            self._update_status("Please enter a prompt")
            return

        if not self._token:
            self._update_status("Not logged in - run: python -m client.cli login")
            self._add_system_message("You need to login first. Run: python -m client.cli login")
            return

        # Get mode and difficulty
        mode = self.query_one("#mode-select", Select).value
        difficulty = self.query_one("#difficulty-select", Select).value

        # Clear input and update status
        input_area.clear()
        self._update_status("Sending...")

        # Add user message to chat
        self._add_message("You", prompt, is_user=True)

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

                    self._update_status(f"Processing... (Task: {task_id[:8]})")

                    # Poll for result
                    result = await self._poll_for_result(client, task_id)

                    if result:
                        self._add_message("Iris", result, is_user=False)
                        self._update_status("Ready")
                    else:
                        self._add_message("Iris", "[Error: Task timed out or failed]", is_user=False)
                        self._update_status("Task failed")

                elif response.status_code == 401:
                    self._update_status("Authentication failed")
                    self._add_system_message("Session expired. Please login again.")
                else:
                    error = response.json().get("detail", "Unknown error")
                    self._update_status(f"Error: {error}")
                    self._add_system_message(f"Error: {error}")

        except httpx.TimeoutException:
            self._update_status("Request timed out")
            self._add_system_message("Request timed out. The network may be busy.")
        except Exception as e:
            self._update_status(f"Error: {str(e)[:30]}")
            self._add_system_message(f"Error: {str(e)}")

    async def _poll_for_result(self, client: httpx.AsyncClient, task_id: str, max_attempts: int = 30) -> str:
        """Poll for task completion."""
        for _ in range(max_attempts):
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

                await asyncio.sleep(2)

            except Exception:
                await asyncio.sleep(2)

        return None

    def _add_message(self, sender: str, content: str, is_user: bool = False) -> None:
        """Add a message to the chat."""
        # Hide empty state
        try:
            empty = self.query_one("#empty-state", Static)
            empty.display = False
        except Exception:
            pass

        # Create message widget
        container = self.query_one("#messages-container", VerticalScroll)

        css_class = "user-message" if is_user else "assistant-message"
        header = f"[bold]{'You' if is_user else 'Iris'}[/bold]"

        message = Static(
            f"{header}\n{content}",
            classes=f"message {css_class}"
        )

        container.mount(message)
        container.scroll_end()

        self._messages.append({"sender": sender, "content": content, "is_user": is_user})

    def _add_system_message(self, content: str) -> None:
        """Add a system message."""
        try:
            empty = self.query_one("#empty-state", Static)
            empty.display = False
        except Exception:
            pass

        container = self.query_one("#messages-container", VerticalScroll)

        message = Static(
            f"[dim italic]{content}[/]",
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
