"""
Status Indicator Widget - Brutalist/Evangelion Design.

A status indicator showing connection state with
Evangelion-inspired symbols and brutalist colors.
"""

from textual.widgets import Static


class StatusIndicator(Static):
    """A status indicator with Evangelion-style symbols."""

    # Evangelion-inspired status states
    STATES = {
        "connected": ("[#00ff41 bold]▶ CONNECTED[/]", "connected"),
        "disconnected": ("[#ff0000 bold]◼ DISCONNECTED[/]", "disconnected"),
        "connecting": ("[#ffaa00 bold]◐ CONNECTING...[/]", "connecting"),
        "syncing": ("[#00ffff bold]◈ SYNCING[/]", "connecting"),
        "error": ("[#ff0000 bold]⚠ ERROR[/]", "disconnected"),
        "warning": ("[#ffaa00 bold]⚠ WARNING[/]", "connecting"),
        "active": ("[#00ff41 bold]▶ ACTIVE[/]", "connected"),
        "idle": ("[#888888 bold]◯ IDLE[/]", "disconnected"),
    }

    def __init__(self, state: str = "disconnected", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state = state
        self._update_display()

    def _update_display(self) -> None:
        """Update the display based on state."""
        text, css_class = self.STATES.get(self._state, self.STATES["disconnected"])
        self.update(text)

        # Update CSS classes
        self.remove_class("connected", "disconnected", "connecting")
        self.add_class(css_class)

    def set_state(self, state: str) -> None:
        """Set the connection state."""
        if state in self.STATES:
            self._state = state
            self._update_display()

    @property
    def state(self) -> str:
        """Get current state."""
        return self._state

    def pulse(self) -> None:
        """Create a visual pulse effect (for animations)."""
        current_text, css_class = self.STATES.get(self._state, self.STATES["disconnected"])
        # Add a brief highlight effect
        self.add_class("pulse")
        self.set_timer(0.5, lambda: self.remove_class("pulse"))
