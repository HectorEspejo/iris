"""Stats Card Widget."""

from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical


class StatsCard(Static):
    """A card displaying a statistic with icon, value, and label."""

    DEFAULT_CSS = """
    StatsCard {
        width: 1fr;
        height: 7;
        border: solid $primary;
        padding: 1 2;
        margin: 0 1;
        background: $surface-lighten-1;
        layout: vertical;
    }

    StatsCard .card-icon {
        text-align: center;
        color: $accent;
        height: 1;
    }

    StatsCard .card-value {
        text-align: center;
        text-style: bold;
        color: $text;
        height: 2;
        content-align: center middle;
    }

    StatsCard .card-label {
        text-align: center;
        color: $text-muted;
        height: 1;
    }
    """

    def __init__(
        self,
        label: str,
        value: str = "0",
        icon: str = "",
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self._label = label
        self._value = value
        self._icon = icon

    def compose(self) -> ComposeResult:
        """Create the card layout."""
        yield Static(self._icon, classes="card-icon")
        yield Static(self._value, classes="card-value", id=f"{self.id}-value" if self.id else None)
        yield Static(self._label, classes="card-label")

    def update_value(self, value: str) -> None:
        """Update the displayed value."""
        self._value = value
        try:
            value_widget = self.query_one(".card-value", Static)
            value_widget.update(value)
        except Exception:
            pass
