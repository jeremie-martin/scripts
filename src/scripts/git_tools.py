import subprocess, sys, os
from typer import Typer

app = Typer()

def _is_binary_existing(path: str) -> bool:
    attr = subprocess.check_output(["git", "check-attr", "--all", "--", path], text=True)
    return "binary" in attr

def _is_binary_in_diff(target: str | None, path: str) -> bool:
    ref = target if target else "HEAD"
    try:
        out = subprocess.check_output(["git", "diff", "--numstat", ref, "--", path], text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return False
    # numstat: "<added>\t<removed>\t<path>"; binary -> "-\t-\t<path>"
    line = out.strip().splitlines()[0] if out.strip() else ""
    return line.startswith("-")

@app.command()
def gdiffpath(staged: bool = False, target: str = ""):
    """List relative paths of modified non-binary files."""
    try:
        if target:
            cmd = ["git", "diff", "--name-only", target] if ".." in target else ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", target]
        else:
            cmd = ["git", "diff", "--cached", "--name-only"] if staged else ["git", "diff", "HEAD", "--name-only"]
        out = subprocess.check_output(cmd, text=True)
        for f in out.split():
            if os.path.isfile(f):
                if not _is_binary_existing(f):
                    print(f)
            else:
                if not _is_binary_in_diff(target, f):
                    print(f)
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)

def main():
    app()
