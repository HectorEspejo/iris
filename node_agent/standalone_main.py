#!/usr/bin/env python3
"""
Iris Node Agent - Standalone Entry Point

This is the entry point for the PyInstaller-built executable.
It handles configuration loading from YAML files and provides a CLI interface.

Usage:
    iris-node --config config.yaml
    iris-node --enrollment-token "iris_v1.xxx" --lmstudio-url "http://localhost:1234/v1"
"""

import argparse
import asyncio
import os
import socket
import sys
import time
from pathlib import Path
from typing import Optional

# Handle PyInstaller frozen environment
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    BASE_DIR = Path(sys._MEIPASS)
    sys.path.insert(0, str(BASE_DIR))
else:
    # Running as script
    BASE_DIR = Path(__file__).parent.parent
    sys.path.insert(0, str(BASE_DIR))

# Now import the main module
from node_agent.main import NodeAgent

VERSION = "1.0.0"
DEFAULT_COORDINATOR = "ws://168.119.10.189:8000/nodes/connect"
DEFAULT_LMSTUDIO = "http://localhost:1234/v1"


def load_config(config_path: Path) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Dictionary with configuration values
    """
    try:
        import yaml
    except ImportError:
        print("Error: PyYAML is required for config file support")
        print("Install with: pip install pyyaml")
        sys.exit(1)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}

    return config


def generate_node_id() -> str:
    """Generate a default node ID based on hostname and timestamp."""
    hostname = socket.gethostname().lower().replace('.', '-')[:20]
    timestamp = int(time.time()) % 100000
    return f"node-{hostname}-{timestamp}"


def print_banner():
    """Print the startup banner."""
    banner = f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║              Iris Node Agent v{VERSION}                     ║
    ║         Distributed AI Inference Network                  ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description='Iris Node Agent - Distributed AI Inference',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with config file
  iris-node --config ~/.iris/config.yaml

  # Start with command line arguments
  iris-node --enrollment-token "iris_v1.xxx" --node-id "my-node"

  # Use custom LM Studio URL
  iris-node --config config.yaml --lmstudio-url "http://192.168.1.100:1234/v1"

Environment Variables:
  NODE_ID           - Unique node identifier
  COORDINATOR_URL   - Coordinator WebSocket URL
  LMSTUDIO_URL      - LM Studio API URL
  ENROLLMENT_TOKEN  - Enrollment token for registration
  NODE_KEY_PATH     - Path to store encryption keys
        """
    )

    parser.add_argument(
        '--config', '-c',
        type=Path,
        help='Path to YAML configuration file'
    )
    parser.add_argument(
        '--node-id',
        help='Unique node identifier (auto-generated if not provided)'
    )
    parser.add_argument(
        '--coordinator-url',
        help=f'Coordinator WebSocket URL (default: {DEFAULT_COORDINATOR})'
    )
    parser.add_argument(
        '--lmstudio-url',
        default=DEFAULT_LMSTUDIO,
        help=f'LM Studio API URL (default: {DEFAULT_LMSTUDIO})'
    )
    parser.add_argument(
        '--enrollment-token',
        help='Enrollment token for first-time registration'
    )
    parser.add_argument(
        '--data-dir',
        type=Path,
        help='Directory for data storage (default: ~/.iris/data)'
    )
    parser.add_argument(
        '--version', '-v',
        action='version',
        version=f'Iris Node Agent {VERSION}'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress banner output'
    )

    args = parser.parse_args()

    # Load config file if provided
    config = {}
    if args.config:
        try:
            config = load_config(args.config)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error reading config file: {e}")
            sys.exit(1)

    # Resolve configuration with priority: CLI args > Config file > Env vars > Defaults
    node_id = (
        args.node_id or
        config.get('node_id') or
        os.environ.get('NODE_ID') or
        generate_node_id()
    )

    coordinator_url = (
        args.coordinator_url or
        config.get('coordinator_url') or
        os.environ.get('COORDINATOR_URL') or
        DEFAULT_COORDINATOR
    )

    lmstudio_url = (
        args.lmstudio_url or
        config.get('lmstudio_url') or
        os.environ.get('LMSTUDIO_URL') or
        DEFAULT_LMSTUDIO
    )

    enrollment_token = (
        args.enrollment_token or
        config.get('enrollment_token') or
        os.environ.get('ENROLLMENT_TOKEN')
    )

    # Resolve data directory
    default_data_dir = Path.home() / '.iris' / 'data'
    data_dir = (
        args.data_dir or
        Path(config.get('data_dir', str(default_data_dir)))
    )

    # Ensure data directory exists
    data_dir.mkdir(parents=True, exist_ok=True)
    key_path = data_dir / 'node.key'

    # Print banner unless quiet mode
    if not args.quiet:
        print_banner()

    # Print configuration
    print(f"  Node ID:        {node_id}")
    print(f"  Coordinator:    {coordinator_url}")
    print(f"  LM Studio:      {lmstudio_url}")
    print(f"  Data Dir:       {data_dir}")
    print(f"  Token:          {'Provided' if enrollment_token else 'Not provided'}")
    print()

    # Warn if no enrollment token
    if not enrollment_token:
        print("  Warning: No enrollment token provided.")
        print("           This node will fail to register if not previously enrolled.")
        print()

    # Create and run agent
    agent = NodeAgent(
        node_id=node_id,
        coordinator_url=coordinator_url,
        lmstudio_url=lmstudio_url,
        key_path=str(key_path),
        enrollment_token=enrollment_token
    )

    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print("\n  Shutting down...")
    except Exception as e:
        print(f"\n  Error: {e}")
        sys.exit(1)
    finally:
        asyncio.run(agent.stop())

    print("  Node agent stopped.")


if __name__ == '__main__':
    main()
