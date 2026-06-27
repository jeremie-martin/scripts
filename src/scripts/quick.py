from __future__ import annotations

import subprocess
from pathlib import Path

import typer

app = typer.Typer(
    add_completion=False,
    help="Scaffold a throwaway project under ~/prog/quick/. Plain positional args, no wizard.",
)

BASE_DIR = Path.home() / "prog" / "quick"
TYPES = ("python", "node", "cpp", "empty")

GITIGNORE = {
    "python": "__pycache__/\n*.pyc\n.venv/\n.env\ndist/\n*.egg-info/\n",
    "node": "node_modules/\ndist/\n*.log\n.env\n",
    "cpp": "build/\n*.o\n*.out\n",
    "empty": ".env\n",
}

NAME_ARGUMENT = typer.Argument("scratch", help="Project name (becomes the directory name).")
TYPE_ARGUMENT = typer.Argument("empty", help=f"Project flavour: {', '.join(TYPES)}.")
BASE_OPTION = typer.Option(BASE_DIR, "--base", help="Parent directory to create the project in.")
GIT_OPTION = typer.Option(True, "--git/--no-git", help="Initialise a git repository.")
FORCE_OPTION = typer.Option(False, "--force", "-f", help="Reuse the directory if it already exists.")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _scaffold_python(dest: Path, name: str) -> None:
    # uv is the project's standard toolchain; let it lay out the project offline.
    subprocess.run(["uv", "init", "--name", name, str(dest)], check=True)


def _scaffold_node(dest: Path, name: str) -> None:
    _write(
        dest / "package.json",
        f'{{\n  "name": "{name}",\n  "version": "0.1.0",\n  "type": "module",\n'
        '  "scripts": {\n'
        '    "dev": "tsx src/index.ts",\n'
        '    "build": "tsc"\n'
        "  }\n}\n",
    )
    _write(
        dest / "tsconfig.json",
        '{\n  "compilerOptions": {\n'
        '    "target": "ES2022",\n'
        '    "module": "ESNext",\n'
        '    "moduleResolution": "bundler",\n'
        '    "strict": true,\n'
        '    "outDir": "dist",\n'
        '    "esModuleInterop": true,\n'
        '    "skipLibCheck": true\n'
        '  },\n  "include": ["src"]\n}\n',
    )
    _write(dest / "src" / "index.ts", 'console.log("hello from ' + name + '");\n')


def _scaffold_cpp(dest: Path, name: str) -> None:
    _write(
        dest / "CMakeLists.txt",
        f"cmake_minimum_required(VERSION 3.20)\nproject({name} CXX)\n\n"
        "set(CMAKE_CXX_STANDARD 20)\nset(CMAKE_CXX_STANDARD_REQUIRED ON)\n\n"
        f"add_executable({name} src/main.cpp)\n",
    )
    _write(
        dest / "src" / "main.cpp",
        '#include <iostream>\n\nint main() {\n'
        f'    std::cout << "hello from {name}" << std::endl;\n'
        "    return 0;\n}\n",
    )


SCAFFOLDS = {
    "python": _scaffold_python,
    "node": _scaffold_node,
    "cpp": _scaffold_cpp,
    "empty": lambda dest, name: None,
}


@app.command()
def run(
    name: str = NAME_ARGUMENT,
    type: str = TYPE_ARGUMENT,
    base: Path = BASE_OPTION,
    git: bool = GIT_OPTION,
    force: bool = FORCE_OPTION,
) -> None:
    """Create a new project skeleton and print its path."""
    flavour = type.lower()
    if flavour not in TYPES:
        typer.echo(f"Unknown type '{type}'. Choose one of: {', '.join(TYPES)}.", err=True)
        raise typer.Exit(2)

    dest = (base.expanduser() / name).resolve()
    if dest.exists() and not force:
        typer.echo(f"Refusing to overwrite existing directory: {dest} (use --force)", err=True)
        raise typer.Exit(1)
    dest.mkdir(parents=True, exist_ok=True)

    try:
        SCAFFOLDS[flavour](dest, name)
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Scaffold step failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    # README + .gitignore unless the scaffolder already supplied them (uv writes a README).
    readme = dest / "README.md"
    if not readme.exists():
        _write(readme, f"# {name}\n")
    gitignore = dest / ".gitignore"
    if not gitignore.exists():
        _write(gitignore, GITIGNORE[flavour])

    if git and not (dest / ".git").exists():
        subprocess.run(["git", "init", "-q", str(dest)], check=False)

    typer.echo(f"Created {flavour} project at {dest}", err=True)
    # Bare path on stdout so it's usable in a subshell, e.g. cd "$(quick foo)".
    typer.echo(str(dest))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
