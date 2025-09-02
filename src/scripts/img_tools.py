import shutil
import subprocess
from pathlib import Path

import typer

app = typer.Typer(help="Tiny ImageMagick helpers")


def _ensure_convert():
    if not shutil.which("convert"):
        typer.echo("ImageMagick `convert` not found on PATH.", err=True)
        raise typer.Exit(2)


@app.command("2twi")
def twi(file: Path):
    _ensure_convert()
    b = file.stem
    out = Path("twi") / f"{b}.jpg"
    subprocess.run(["convert", "-resize", "66.6666666%", str(file), "-quality", "92", str(out)], check=True)
    print(out)


@app.command("2work")
def work(file: Path):
    _ensure_convert()
    b = file.stem
    out = Path("../working") / f"{b}_small.jpg"
    subprocess.run(["convert", "-resize", "50%", str(file), "-quality", "90", str(out)], check=True)
    print(out)


# expose as entry points named 2twi / 2work via wrapper functions


def cmd_2twi():
    app(prog_name="2twi")


def cmd_2work():
    app(prog_name="2work")
