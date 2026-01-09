"""Status Indicator Widget."""

from textual.widgets import Static


class StatusIndicator(Static):
    """A status indicator showing connection state."""

    DEFAULT_CSS = """
    StatusIndicator {
        width: auto;
        height: 1;
        padding: 0 1;
    }

    StatusIndicator.connected {
        color: $success;
    }

    StatusIndicator.disconnected {
        color: $error;
    }

    StatusIndicator.connecting {
        color: $warning;
    }
    """

    STATES = {
        "connected": ("● CONNECTED", "connected"),
        "disconnected": ("○ DISCONNECTED", "disconnected"),
        "connecting": ("◐ CONNECTING...", "connecting"),
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
