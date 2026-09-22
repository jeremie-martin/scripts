from __future__ import annotations

import sys
from importlib.metadata import EntryPoint, distribution

import typer

from . import __version__

app = typer.Typer(help="Utility scripts — use discrete commands directly, or `scripts run <cmd> -- …`. ")


def _available_commands() -> dict[str, EntryPoint]:
    """Use this distribution's entry points as the single command registry."""
    return {ep.name: ep for ep in distribution("scripts").entry_points if ep.group == "console_scripts" and ep.name != "scripts"}


@app.command()
def list():
    """List console_scripts exposed by this package."""
    cmds = _available_commands()
    if not cmds:
        typer.echo("(no commands found)")
        raise typer.Exit(1)
    for name, entry in sorted(cmds.items()):
        typer.echo(f"{name:16} -> {entry.value}")


@app.command()
def version():
    """Show scripts package version."""
    typer.echo(__version__)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(ctx: typer.Context, cmd: str):
    """Run a discrete command with its own flags: `scripts run concat -- <args>`"""
    entry = _available_commands().get(cmd)
    if entry is None:
        typer.echo(f"Unknown scripts command: {cmd}. Use 'scripts list' to see available commands.", err=True)
        raise typer.Exit(2)
    argv = sys.argv
    try:
        sys.argv = [cmd, *ctx.args]
        result = entry.load()()
    finally:
        sys.argv = argv
    raise typer.Exit(result or 0)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
