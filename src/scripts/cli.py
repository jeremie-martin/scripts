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


# Convenience nested group for Jama: forwards to discrete CLIs
jama = typer.Typer(help="Jama utilities (forwards to jamaclean, jamaconcat, …)")
app.add_typer(jama, name="jama")


def _forward(cmd: str, rest: list[str]) -> int:
    try:
        return subprocess.call([cmd, *rest])
    except FileNotFoundError:
        print(
            f"Command '{cmd}' not found. If it's provided by an optional extra, did you run 'uv sync --extra <name>'?",
            flush=True,
        )
        return 127


@jama.command("clean", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_clean(ctx: typer.Context):
    raise typer.Exit(_forward("jamaclean", ctx.args))


@jama.command("concat", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_concat(ctx: typer.Context):
    raise typer.Exit(_forward("jamaconcat", ctx.args))


@jama.command("concatfull", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_concatfull(ctx: typer.Context):
    raise typer.Exit(_forward("jamaconcatfull", ctx.args))


@jama.command("filltests", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_filltests(ctx: typer.Context):
    raise typer.Exit(_forward("jamafilltests", ctx.args))


@jama.command("notest", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_notest(ctx: typer.Context):
    raise typer.Exit(_forward("jamanotest", ctx.args))


@jama.command("tmp", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_tmp(ctx: typer.Context):
    raise typer.Exit(_forward("jamatmp", ctx.args))


@jama.command("fetch", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_fetch(ctx: typer.Context):
    """Fetch Jama items (forwards to `jama fetch`)."""
    raise typer.Exit(_forward("jama", ["fetch", *ctx.args]))


@jama.command("update", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_update(ctx: typer.Context):
    """Update Jama items (forwards to `jama update`)."""
    raise typer.Exit(_forward("jama", ["update", *ctx.args]))


@jama.command("create", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_create(ctx: typer.Context):
    """Create Jama items (forwards to `jama create`)."""
    raise typer.Exit(_forward("jama", ["create", *ctx.args]))


@jama.command("db", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def jama_db(ctx: typer.Context):
    """Manage Jama database (forwards to `jama db`)."""
    raise typer.Exit(_forward("jama", ["db", *ctx.args]))
