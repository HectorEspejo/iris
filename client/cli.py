"""
Iris Command Line Interface

CLI for interacting with the Iris distributed inference network.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.markdown import Markdown

from shared.models import TaskMode, TaskStatus, TaskDifficulty
from .sdk import IrisClient, IrisError, AuthenticationError, APIError

# Initialize Typer app
app = typer.Typer(
    name="iris",
    help="Iris - Distributed AI Inference Network CLI",
    add_completion=False
)

# Rich console for pretty output
console = Console()

# Default configuration
DEFAULT_URL = "http://168.119.10.189:8000"


def get_client(url: str = DEFAULT_URL) -> IrisClient:
    """Create a client instance."""
    return IrisClient(base_url=url)


def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# =============================================================================
# Authentication Commands
# =============================================================================

@app.command()
def register(
    email: str = typer.Option(..., "--email", "-e", help="Email address"),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True, help="Password"),
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """Register a new user account."""
    async def _register():
        async with get_client(url) as client:
            try:
                result = await client.register(email, password)
                console.print(f"[green]✓ Registered successfully![/green]")
                console.print(f"  User ID: {result['id']}")
                console.print(f"  Email: {result['email']}")
                console.print("\nRun [bold]iris login[/bold] to authenticate.")
            except APIError as e:
                console.print(f"[red]✗ Registration failed: {e}[/red]")
                raise typer.Exit(1)

    run_async(_register())


@app.command()
def login(
    email: str = typer.Option(..., "--email", "-e", help="Email address"),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True, help="Password"),
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """Login to your Iris account."""
    async def _login():
        async with get_client(url) as client:
            try:
                await client.login(email, password)
                console.print(f"[green]✓ Logged in successfully![/green]")

                # Show account info
                info = await client.get_me()
                console.print(f"  Welcome, {info['email']}")
                console.print(f"  Tasks completed: {info.get('total_tasks', 0)}")
            except AuthenticationError as e:
                console.print(f"[red]✗ Login failed: {e}[/red]")
                raise typer.Exit(1)

    run_async(_login())


@app.command()
def logout():
    """Logout and clear saved credentials."""
    async def _logout():
        async with get_client() as client:
            await client.logout()
            console.print("[green]✓ Logged out successfully![/green]")

    run_async(_logout())


# =============================================================================
# Account Commands (Mullvad-style)
# =============================================================================

# Create account subcommand group
account_app = typer.Typer(help="Manage your Iris account (Mullvad-style)")
app.add_typer(account_app, name="account")


@account_app.command("generate")
def account_generate(
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """
    Generate a new account key.

    This will create a new account and display your unique 16-digit account key.
    IMPORTANT: Save this key! It will only be shown once.
    """
    import httpx

    async def _generate():
        async with httpx.AsyncClient(base_url=url, timeout=30.0) as client:
            try:
                response = await client.post("/accounts/generate")
                response.raise_for_status()
                data = response.json()

                account_key = data["account_key"]
                account = data["account"]

                # Display the key prominently
                console.print()
                console.print(Panel(
                    f"[bold yellow]{account_key}[/bold yellow]",
                    title="[green]Your Account Key[/green]",
                    subtitle="[red]Save this now![/red]",
                    border_style="green",
                    padding=(1, 4)
                ))

                console.print()
                console.print("[bold red]⚠ IMPORTANT: Save this key in a safe place![/bold red]")
                console.print("[red]This is the ONLY time it will be shown.[/red]")
                console.print()
                console.print("[dim]Account details:[/dim]")
                console.print(f"  [dim]Account ID:[/dim] {account['id'][:8]}...")
                console.print(f"  [dim]Status:[/dim] {account['status']}")
                console.print()
                console.print("[bold]To start a node, set this environment variable:[/bold]")
                console.print(f'  [cyan]export IRIS_ACCOUNT_KEY="{account_key}"[/cyan]')
                console.print()

            except httpx.HTTPStatusError as e:
                console.print(f"[red]✗ Failed to generate account: {e.response.text}[/red]")
                raise typer.Exit(1)
            except Exception as e:
                console.print(f"[red]✗ Error: {e}[/red]")
                raise typer.Exit(1)

    run_async(_generate())


@account_app.command("info")
def account_info(
    account_key: str = typer.Option(..., "--key", "-k", help="Your account key"),
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """Show account information."""
    import httpx

    async def _info():
        async with httpx.AsyncClient(base_url=url, timeout=30.0) as client:
            try:
                response = await client.get(
                    "/accounts/me",
                    params={"account_key": account_key}
                )
                response.raise_for_status()
                info = response.json()

                # Mask the key for display
                key_display = account_key[:4] + " **** **** ****"

                console.print()
                console.print(Panel(
                    f"[bold]Account: {key_display}[/bold]",
                    border_style="blue"
                ))

                console.print(f"  Status: [green]{info['status']}[/green]")
                console.print(f"  Nodes: {info['node_count']}")
                console.print(f"  Total Earnings: {info['total_earnings']:.2f} credits")
                console.print(f"  Created: {info['created_at'][:19]}")
                if info.get('last_activity_at'):
                    console.print(f"  Last Activity: {info['last_activity_at'][:19]}")
                console.print()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    console.print("[red]✗ Invalid or inactive account key[/red]")
                else:
                    console.print(f"[red]✗ Error: {e.response.text}[/red]")
                raise typer.Exit(1)
            except Exception as e:
                console.print(f"[red]✗ Error: {e}[/red]")
                raise typer.Exit(1)

    run_async(_info())


@account_app.command("nodes")
def account_nodes(
    account_key: str = typer.Option(..., "--key", "-k", help="Your account key"),
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """List all nodes linked to your account."""
    import httpx

    async def _nodes():
        async with httpx.AsyncClient(base_url=url, timeout=30.0) as client:
            try:
                response = await client.get(
                    "/accounts/nodes",
                    params={"account_key": account_key}
                )
                response.raise_for_status()
                nodes_list = response.json()

                if not nodes_list:
                    console.print("[yellow]No nodes linked to this account yet.[/yellow]")
                    console.print()
                    console.print("To link a node, start it with:")
                    console.print(f'  [cyan]export IRIS_ACCOUNT_KEY="{account_key[:4]} **** **** ****"[/cyan]')
                    console.print("  [cyan]python -m node_agent.main[/cyan]")
                    return

                # Mask the key for display
                key_display = account_key[:4] + " **** **** ****"

                table = Table(title=f"Nodes for Account {key_display}")
                table.add_column("Node ID", style="cyan")
                table.add_column("GPU")
                table.add_column("Model")
                table.add_column("Tier")
                table.add_column("Tasks")
                table.add_column("Reputation", justify="right")

                # Tier colors
                tier_colors = {
                    "premium": "gold1",
                    "standard": "grey70",
                    "basic": "grey50"
                }

                for node in nodes_list:
                    tier = node.get("node_tier", "basic")
                    tier_color = tier_colors.get(tier, "white")

                    table.add_row(
                        node["id"][:16] + "...",
                        node.get("gpu_name", "Unknown")[:15],
                        node.get("model_name", "?")[:15],
                        f"[{tier_color}]{tier.capitalize()}[/{tier_color}]",
                        str(node.get("total_tasks_completed", 0)),
                        f"{node.get('reputation', 100):.1f}"
                    )

                console.print(table)
                console.print(f"\n[dim]Total: {len(nodes_list)} node(s)[/dim]")

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    console.print("[red]✗ Invalid or inactive account key[/red]")
                else:
                    console.print(f"[red]✗ Error: {e.response.text}[/red]")
                raise typer.Exit(1)
            except Exception as e:
                console.print(f"[red]✗ Error: {e}[/red]")
                raise typer.Exit(1)

    run_async(_nodes())


@account_app.command("verify")
def account_verify(
    account_key: str = typer.Option(..., "--key", "-k", help="Account key to verify"),
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """Verify that an account key is valid."""
    import httpx

    async def _verify():
        async with httpx.AsyncClient(base_url=url, timeout=30.0) as client:
            try:
                response = await client.post(
                    "/accounts/verify",
                    json={"account_key": account_key}
                )
                response.raise_for_status()
                info = response.json()

                key_display = account_key[:4] + " **** **** ****"
                console.print(f"[green]✓ Account key {key_display} is valid![/green]")
                console.print(f"  Status: {info['status']}")
                console.print(f"  Nodes: {info['node_count']}")

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    console.print("[red]✗ Invalid or inactive account key[/red]")
                else:
                    console.print(f"[red]✗ Verification failed: {e.response.text}[/red]")
                raise typer.Exit(1)
            except Exception as e:
                console.print(f"[red]✗ Error: {e}[/red]")
                raise typer.Exit(1)

    run_async(_verify())


# =============================================================================
# Inference Commands
# =============================================================================

@app.command()
def ask(
    prompt: str = typer.Argument(None, help="The prompt to send"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read prompt from file"),
    mode: str = typer.Option("subtasks", "--mode", "-m", help="Task mode: subtasks, consensus, context"),
    difficulty: Optional[str] = typer.Option(None, "--difficulty", "-d", help="Task difficulty: simple, complex, advanced (auto-detected if not set)"),
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Don't wait for response")
):
    """Send an inference request to the network."""
    # Get prompt
    if file:
        if not file.exists():
            console.print(f"[red]✗ File not found: {file}[/red]")
            raise typer.Exit(1)
        prompt = file.read_text()
    elif prompt is None:
        console.print("[red]✗ Please provide a prompt or use --file[/red]")
        raise typer.Exit(1)

    # Parse mode
    try:
        task_mode = TaskMode(mode)
    except ValueError:
        console.print(f"[red]✗ Invalid mode: {mode}[/red]")
        console.print("Valid modes: subtasks, consensus, context")
        raise typer.Exit(1)

    # Parse difficulty (optional)
    task_difficulty = None
    if difficulty:
        try:
            task_difficulty = TaskDifficulty(difficulty.lower())
        except ValueError:
            console.print(f"[red]✗ Invalid difficulty: {difficulty}[/red]")
            console.print("Valid difficulties: simple, complex, advanced")
            raise typer.Exit(1)

    async def _ask():
        async with get_client(url) as client:
            if not client.is_authenticated:
                console.print("[red]✗ Not logged in. Run 'iris login' first.[/red]")
                raise typer.Exit(1)

            try:
                if no_wait:
                    task_id = await client.ask_async(prompt, task_mode)
                    console.print(f"[green]✓ Task submitted![/green]")
                    console.print(f"  Task ID: {task_id}")
                    console.print(f"\nCheck status with: iris status {task_id}")
                else:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console
                    ) as progress:
                        progress.add_task("Processing request...", total=None)
                        response = await client.ask(prompt, task_mode)

                    # Display response
                    console.print()
                    console.print(Panel(
                        Markdown(response),
                        title="Response",
                        border_style="green"
                    ))

            except APIError as e:
                console.print(f"[red]✗ Request failed: {e}[/red]")
                raise typer.Exit(1)

    run_async(_ask())


@app.command()
def status(
    task_id: str = typer.Argument(..., help="Task ID to check"),
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """Check the status of a task."""
    async def _status():
        async with get_client(url) as client:
            if not client.is_authenticated:
                console.print("[red]✗ Not logged in. Run 'iris login' first.[/red]")
                raise typer.Exit(1)

            try:
                task = await client.get_task_status(task_id)

                # Status color
                status_colors = {
                    "pending": "yellow",
                    "processing": "blue",
                    "completed": "green",
                    "failed": "red",
                    "partial": "orange3"
                }
                color = status_colors.get(task["status"], "white")

                console.print(f"\n[bold]Task Status[/bold]")
                console.print(f"  ID: {task['task_id']}")
                console.print(f"  Status: [{color}]{task['status']}[/{color}]")
                console.print(f"  Subtasks: {task['subtasks_completed']}/{task['subtasks_total']}")
                console.print(f"  Created: {task['created_at']}")

                if task.get("completed_at"):
                    console.print(f"  Completed: {task['completed_at']}")

                if task.get("response"):
                    console.print()
                    console.print(Panel(
                        Markdown(task["response"]),
                        title="Response",
                        border_style="green"
                    ))

            except APIError as e:
                console.print(f"[red]✗ Failed to get status: {e}[/red]")
                raise typer.Exit(1)

    run_async(_status())


# =============================================================================
# Information Commands
# =============================================================================

@app.command()
def nodes(
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """List active nodes in the network."""
    async def _nodes():
        async with get_client(url) as client:
            if not client.is_authenticated:
                console.print("[red]✗ Not logged in. Run 'iris login' first.[/red]")
                raise typer.Exit(1)

            try:
                node_list = await client.get_nodes()

                if not node_list:
                    console.print("[yellow]No nodes currently online.[/yellow]")
                    return

                table = Table(title="Active Nodes")
                table.add_column("Node ID", style="cyan")
                table.add_column("Tier")
                table.add_column("GPU")
                table.add_column("Model")
                table.add_column("VRAM")
                table.add_column("Load")

                # Tier colors
                tier_colors = {
                    "premium": "gold1",
                    "standard": "grey70",
                    "basic": "grey50"
                }

                for node in node_list:
                    tier = node.get("node_tier", "basic")
                    tier_color = tier_colors.get(tier, "white")
                    model_info = node.get("model_name", "unknown")[:15]
                    params = node.get("model_params", 7)

                    table.add_row(
                        node["node_id"][:12] + "...",
                        f"[{tier_color}]{tier.capitalize()}[/{tier_color}]",
                        node.get("gpu_name", "Unknown")[:15],
                        f"{model_info} ({params}B)",
                        f"{node.get('vram_gb', '?')} GB",
                        str(node.get("current_load", 0))
                    )

                console.print(table)
                console.print(f"\n[dim]Total: {len(node_list)} nodes[/dim]")

            except APIError as e:
                console.print(f"[red]✗ Failed to get nodes: {e}[/red]")
                raise typer.Exit(1)

    run_async(_nodes())


@app.command()
def reputation(
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """Show node reputation leaderboard."""
    async def _reputation():
        async with get_client(url) as client:
            try:
                leaderboard = await client.get_reputation()

                if not leaderboard:
                    console.print("[yellow]No nodes registered yet.[/yellow]")
                    return

                table = Table(title="Reputation Leaderboard")
                table.add_column("#", style="dim")
                table.add_column("Node ID", style="cyan")
                table.add_column("Model")
                table.add_column("Reputation", justify="right")
                table.add_column("Tasks", justify="right")
                table.add_column("Status")

                for i, node in enumerate(leaderboard, 1):
                    status = "[green]●[/green]" if node.get("is_online") else "[red]○[/red]"
                    table.add_row(
                        str(i),
                        node["node_id"][:12] + "...",
                        node.get("model_name", "unknown"),
                        f"{node.get('reputation', 0):.1f}",
                        str(node.get("tasks_completed", 0)),
                        status
                    )

                console.print(table)

            except APIError as e:
                console.print(f"[red]✗ Failed to get leaderboard: {e}[/red]")
                raise typer.Exit(1)

    run_async(_reputation())


@app.command()
def stats(
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """Show network statistics."""
    async def _stats():
        async with get_client(url) as client:
            try:
                network_stats = await client.get_stats()

                console.print("\n[bold]Network Statistics[/bold]")
                console.print(f"  Nodes Online: {network_stats.get('nodes_online', 0)}")
                console.print(f"  Total Nodes: {network_stats.get('total_nodes', 0)}")
                console.print(f"  Total Users: {network_stats.get('total_users', 0)}")
                console.print(f"  Tasks Today: {network_stats.get('tasks_today', 0)}")
                console.print(f"  Total Tasks: {network_stats.get('total_tasks', 0)}")

            except APIError as e:
                console.print(f"[red]✗ Failed to get stats: {e}[/red]")
                raise typer.Exit(1)

    run_async(_stats())


@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of tasks to show"),
    url: str = typer.Option(DEFAULT_URL, "--url", "-u", help="Coordinator URL")
):
    """Show your task history."""
    async def _history():
        async with get_client(url) as client:
            if not client.is_authenticated:
                console.print("[red]✗ Not logged in. Run 'iris login' first.[/red]")
                raise typer.Exit(1)

            try:
                tasks = await client.get_history(limit)

                if not tasks:
                    console.print("[yellow]No tasks found.[/yellow]")
                    return

                table = Table(title="Task History")
                table.add_column("ID", style="cyan")
                table.add_column("Status")
                table.add_column("Mode")
                table.add_column("Created")
                table.add_column("Prompt", max_width=40)

                status_colors = {
                    "pending": "yellow",
                    "processing": "blue",
                    "completed": "green",
                    "failed": "red",
                    "partial": "orange3"
                }

                for task in tasks:
                    status = task.get("status", "unknown")
                    color = status_colors.get(status, "white")
                    prompt = task.get("original_prompt", "")[:40]
                    if len(task.get("original_prompt", "")) > 40:
                        prompt += "..."

                    table.add_row(
                        task["id"][:8] + "...",
                        f"[{color}]{status}[/{color}]",
                        task.get("mode", "?"),
                        task.get("created_at", "")[:19],
                        prompt
                    )

                console.print(table)

            except APIError as e:
                console.print(f"[red]✗ Failed to get history: {e}[/red]")
                raise typer.Exit(1)

    run_async(_history())


# =============================================================================
# TUI Command
# =============================================================================

@app.command()
def tui(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Node config file path"),
    url: str = typer.Option("http://168.119.10.189:8000", "--url", "-u", help="Coordinator URL")
):
    """Launch interactive TUI dashboard."""
    try:
        from client.tui import IrisTUI
        tui_app = IrisTUI(config_path=config, coordinator_url=url)
        tui_app.run()
    except ImportError:
        console.print("[red]TUI requires textual library. Install with:[/red]")
        console.print("  pip install textual")
        raise typer.Exit(1)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
