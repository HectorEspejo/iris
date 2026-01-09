"""
Stats Card Widget - Brutalist Design.

A card displaying a statistic with icon, value, and label
styled with heavy borders and neon colors.
"""

from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical


class StatsCard(Static):
    """A card displaying a statistic with brutalist styling."""

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
        """Create the card layout with brutalist elements."""
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

    def update_icon(self, icon: str) -> None:
        """Update the displayed icon."""
        self._icon = icon
        try:
            icon_widget = self.query_one(".card-icon", Static)
            icon_widget.update(icon)
        except Exception:
            pass

    def update_label(self, label: str) -> None:
        """Update the displayed label."""
        self._label = label
        try:
            label_widget = self.query_one(".card-label", Static)
            label_widget.update(label)
        except Exception:
            pass
