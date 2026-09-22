import os
import subprocess
import sys

from typer import Typer

app = Typer()


@app.command()
def gdiffpath(staged: bool = False, target: str = ""):
    """List relative paths of modified non-binary files."""
    try:
        root = os.fsdecode(subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).rstrip(b"\n"))
        if target:
            cmd = (
                ["git", "-C", root, "diff", target]
                if ".." in target
                else ["git", "-C", root, "diff-tree", "--root", "--no-commit-id", "-r", target]
            )
        else:
            cmd = ["git", "-C", root, "diff", "--cached" if staged else "HEAD"]
        out = subprocess.check_output([*cmd, "--numstat", "--no-renames", "-z", "--"])
        for record in out.split(b"\0"):
            if not record:
                continue
            added, removed, raw_path = record.split(b"\t", 2)
            path = os.path.join(root, os.fsdecode(raw_path))
            if added != b"-" and removed != b"-" and os.path.isfile(path):
                print(os.path.relpath(path))
    except (OSError, subprocess.CalledProcessError) as e:
        print(e, file=sys.stderr)
        raise SystemExit(1) from None


def main():
    app()
