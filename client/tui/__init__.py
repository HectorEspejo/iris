"""
Iris Network TUI - Interactive Terminal User Interface

Usage:
    python -m client.tui
    python -m client.cli tui
"""

from .app import IrisTUI

__all__ = ["IrisTUI", "main"]


def main():
    """Entry point for the TUI."""
    import argparse
    parser = argparse.ArgumentParser(description="Iris Network TUI")
    parser.add_argument("--config", "-c", help="Config file path")
    parser.add_argument("--coordinator", help="Coordinator URL",
                        default="http://168.119.10.189:8000")
    args = parser.parse_args()

    app = IrisTUI(config_path=args.config, coordinator_url=args.coordinator)
    app.run()


if __name__ == "__main__":
    main()
