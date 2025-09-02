import subprocess, sys
from typer import Typer

app = Typer()

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
            # filter binaries via git check-attr
            attr = subprocess.check_output(["git", "check-attr", "--all", "--", f], text=True)
            if "binary" not in attr and f.strip():
                print(f)
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)

def main():
    app()
