"""
Agentic AI – Google Ecosystem
Entry-point for the multi-agent assistant.

Usage
-----
  # Interactive chat (default)
  python main.py

  # Single prompt (non-interactive)
  python main.py --prompt "What's on my calendar this week?"

  # Launch a specific MCP server
  python main.py mcp-server --service calendar
  python main.py mcp-server --service notes
  python main.py mcp-server --service maps
"""

from __future__ import annotations

import asyncio
import logging
import sys

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

load_dotenv()

from config.settings import settings  # noqa: E402 – after load_dotenv

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    stream=sys.stderr,
)

console = Console()


# ---------------------------------------------------------------------------
# Interactive chat loop
# ---------------------------------------------------------------------------

async def _run_chat(db_client, prompt_text: str | None, session_id: str | None) -> None:
    from agents.orchestrator import OrchestratorAgent

    async with db_client.session() as db:
        agent = OrchestratorAgent(db=db, session_id=session_id)

        if prompt_text:
            # Single-shot mode
            response = await agent.chat(prompt_text)
            console.print(Markdown(response))
            return

        # Interactive loop
        console.print(
            Panel.fit(
                "[bold green]Agentic AI – Google Ecosystem[/bold green]\n"
                "Your personal assistant for Calendar, Notes, Maps & Tasks.\n"
                "Type [bold]exit[/bold] or [bold]quit[/bold] to stop.",
                border_style="green",
            )
        )
        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Goodbye![/yellow]")
                break

            if user_input.strip().lower() in {"exit", "quit", "q"}:
                console.print("[yellow]Goodbye![/yellow]")
                break

            if not user_input.strip():
                continue

            with console.status("[bold green]Thinking…[/bold green]"):
                response = await agent.chat(user_input)

            console.print(f"\n[bold magenta]Assistant[/bold magenta]")
            console.print(Markdown(response))


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--prompt", "-p", default=None, help="Single prompt (non-interactive mode).")
@click.option("--session-id", "-s", default=None, help="Resume a previous session by ID.")
@click.pass_context
def cli(ctx: click.Context, prompt: str | None, session_id: str | None) -> None:
    """Agentic AI – Google Ecosystem personal assistant."""
    if ctx.invoked_subcommand is None:
        asyncio.run(_async_chat(prompt, session_id))


async def _async_chat(prompt: str | None, session_id: str | None) -> None:
    from database.alloydb_client import AlloyDBClient

    db_client = AlloyDBClient()
    await db_client.init()
    try:
        await _run_chat(db_client, prompt, session_id)
    finally:
        await db_client.close()


@cli.command("mcp-server")
@click.option(
    "--service",
    type=click.Choice(["calendar", "notes", "maps"], case_sensitive=False),
    required=True,
    help="Which MCP server to start.",
)
def mcp_server_cmd(service: str) -> None:
    """Launch a standalone MCP server for a specific Google service."""
    import asyncio
    from mcp.server.stdio import stdio_server

    if service == "calendar":
        from tools.calendar_tool import create_mcp_server
    elif service == "notes":
        from tools.notes_tool import create_mcp_server
    else:
        from tools.maps_tool import create_mcp_server

    server = create_mcp_server()
    console.print(f"[green]Starting {service} MCP server (stdio)…[/green]", err=True)

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
