from __future__ import annotations

import subprocess
from importlib.metadata import entry_points

import typer

from . import __version__

app = typer.Typer(help="Utility scripts — use discrete commands directly, or `scripts run <cmd> -- …`. ")


def _available_commands() -> dict[str, str]:
    eps = entry_points(group="console_scripts")
    cmds: dict[str, str] = {}
    for ep in eps:
        # only show commands provided by this package
        if ep.name != "scripts" and isinstance(ep.value, str) and ep.value.startswith("scripts."):
            cmds[ep.name] = ep.value
    return dict(sorted(cmds.items()))


@app.command()
def list():
    """List console_scripts exposed by this package."""
    cmds = _available_commands()
    if not cmds:
        typer.echo("(no commands found)")
        raise typer.Exit(1)
    for name, target in cmds.items():
        typer.echo(f"{name:16} -> {target}")


@app.command()
def version():
    """Show scripts package version."""
    typer.echo(__version__)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(ctx: typer.Context, cmd: str):
    """Run a discrete command with its own flags: `scripts run concat -- <args>`"""
    # prefer executing the installed entry point by name (so help/exit codes match)
    args = [cmd, *ctx.args]
    try:
        code = subprocess.call(args)
    except FileNotFoundError:
        typer.echo(
            f"Command '{cmd}' not found. If it's provided by an optional extra, did you run 'uv sync --extra <name>'?",
            err=True,
        )
        raise typer.Exit(127) from None
    raise typer.Exit(code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
