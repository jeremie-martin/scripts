import os
import subprocess
import sys

from typer import Typer

app = Typer()


def _is_binary_existing(path: str) -> bool:
    """Return True if git attributes mark file as binary."""
    try:
        attr = subprocess.check_output(["git", "check-attr", "binary", "--", path], text=True)
    except subprocess.CalledProcessError:
        return False
    return ": binary: set" in attr


@app.command()
def gdiffpath(staged: bool = False, target: str = ""):
    """List relative paths of modified non-binary files."""
    try:
        if target:
            cmd = (
                ["git", "diff", "--name-only", target]
                if ".." in target
                else ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", target]
            )
        else:
            cmd = ["git", "diff", "--cached", "--name-only"] if staged else ["git", "diff", "HEAD", "--name-only"]
        out = subprocess.check_output(cmd, text=True)
        for f in out.split():
            if not os.path.isfile(f):
                continue
            if not _is_binary_existing(f):
                print(f)
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1) from None


def main():
    app()
