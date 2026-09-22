#!/usr/bin/env python3
"""
File concatenation tool with gitignore-style patterns and config support.

Features:
- Global + project-level config (TOML)
- Gitignore-style include/exclude patterns
- Pretty tree output with statistics
- Binary file detection
- Clipboard integration
"""

import argparse
import glob as pyglob
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from shutil import which

import pathspec
from rich.console import Console
from rich.text import Text
from rich.tree import Tree
from scripts_clipboard import copy_to_all_clipboards

# =============================================================================
# CONSTANTS
# =============================================================================

FD_CANDIDATES = ["fdfind", "fd"]

DEFAULT_EXCLUDES = [
    ".git/",
    "node_modules/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "dist/",
    "build/",
    ".mypy_cache/",
    ".pytest_cache/",
    "*.pyc",
    "*.pyo",
    "*.class",
    "uv.lock",
    "package-lock.json",
    "yarn.lock",
    ".env",
    "*.env",
    "secrets.*",
    "secret.*",
    "credentials.*",
    "*.pem",
    "*.key",
    "*.crt",
    "*.p12",
    "id_rsa",
    "id_ecdsa",
    "id_ed25519",
]

TEXT_EXTS = {
    "txt",
    "log",
    "cfg",
    "conf",
    "ini",
    "toml",
    "yaml",
    "yml",
    "json",
    "jsonc",
    "csv",
    "tsv",
    "ndjson",
    "ipynb",
    "md",
    "markdown",
    "rst",
    "adoc",
    "tex",
    "bib",
    "html",
    "htm",
    "xhtml",
    "shtml",
    "xml",
    "xsd",
    "xsl",
    "xslt",
    "dtd",
    "svg",
    "css",
    "scss",
    "sass",
    "less",
    "sh",
    "bash",
    "zsh",
    "fish",
    "ps1",
    "psm1",
    "bat",
    "cmd",
    "make",
    "mk",
    "cmake",
    "gradle",
    "groovy",
    "c",
    "h",
    "cpp",
    "cc",
    "cxx",
    "hpp",
    "hh",
    "hxx",
    "m",
    "mm",
    "cs",
    "java",
    "kt",
    "kts",
    "go",
    "rs",
    "py",
    "rb",
    "php",
    "pl",
    "pm",
    "r",
    "jl",
    "swift",
    "scala",
    "clj",
    "cljs",
    "edn",
    "hs",
    "lhs",
    "ex",
    "exs",
    "erl",
    "lua",
    "ts",
    "tsx",
    "js",
    "jsx",
    "mjs",
    "cjs",
    "coffee",
    "sql",
    "dbml",
    "proto",
    "idl",
    "nix",
    "sol",
    "mdx",
    "dockerfile",
    "env",
    "tf",
    "tfvars",
    "nomad",
    "hcl",
}

TEXT_NAMES = {
    "Dockerfile",
    "Makefile",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "LICENSE",
    "README",
    "CHANGELOG",
    "AUTHORS",
    "CONTRIBUTORS",
}


# =============================================================================
# CONFIG MANAGEMENT
# =============================================================================


@dataclass
class Config:
    """Configuration for the concat tool."""

    # Pattern options
    exclude_patterns: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    use_gitignore: bool = False
    use_default_excludes: bool = True

    # Output options
    pretty: bool = False
    output_mode: str = "concat"  # "concat", "list", "tree"
    add_header: bool = True

    # File handling
    include_binary: bool = False
    encoding: str = "utf-8"
    errors: str = "replace"
    max_scan_bytes: int = 65536

    # Misc
    show_skipped: bool = False
    verbose: bool = False


CONFIG_SECTIONS = {
    "patterns": {
        "exclude": "exclude_patterns",
        "include": "include_patterns",
        "use_gitignore": "use_gitignore",
        "use_default_excludes": "use_default_excludes",
    },
    "output": {"pretty": "pretty", "mode": "output_mode", "add_header": "add_header"},
    "files": {"include_binary": "include_binary", "encoding": "encoding", "errors": "errors", "max_scan_bytes": "max_scan_bytes"},
    "misc": {"show_skipped": "show_skipped", "verbose": "verbose"},
}


def load_toml_config(path: Path) -> dict:
    """Read only explicitly configured fields; defaults belong to Config."""
    if not path.exists():
        return {}
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        unknown = data.keys() - CONFIG_SECTIONS.keys()
        if unknown:
            raise ValueError(f"unknown sections: {', '.join(sorted(unknown))}")
        values = {}
        defaults = Config()
        for section, names in CONFIG_SECTIONS.items():
            for key, value in data.get(section, {}).items():
                if key not in names:
                    raise ValueError(f"unknown setting {section}.{key}")
                name = names[key]
                expected = type(getattr(defaults, name))
                if type(value) is not expected or (expected is list and any(not isinstance(item, str) for item in value)):
                    raise ValueError(f"invalid value for {section}.{key}")
                values[name] = value
        if values.get("output_mode", "concat") not in {"concat", "list", "tree"}:
            raise ValueError("output.mode must be concat, list, or tree")
        if values.get("max_scan_bytes", 65536) <= 0:
            raise ValueError("files.max_scan_bytes must be positive")
        return values
    except (OSError, ValueError, AttributeError) as exc:
        raise ValueError(f"Failed to load config from {path}: {exc}") from exc


def find_global_config() -> dict:
    """Find and load global config from ~/.config/concat/config.toml"""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    global_config_path = config_home / "concat" / "config.toml"
    return load_toml_config(global_config_path)


def find_project_config(start_dir: Path | None = None) -> dict:
    """Walk up from start_dir to find project-level .concatconfig or .concat.toml"""
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    while True:
        # Try both .concatconfig and .concat.toml
        for name in [".concatconfig", ".concat.toml"]:
            config_path = current / name
            if config_path.exists():
                return load_toml_config(config_path)

        # Stop at filesystem root
        parent = current.parent
        if parent == current:
            break
        current = parent

    return {}


def load_config() -> Config:
    """Apply global then project settings; pattern lists are additive."""
    values = {}
    for layer in (find_global_config(), find_project_config()):
        for name, value in layer.items():
            values[name] = [*values.get(name, []), *value] if isinstance(value, list) else value
    return Config(**values)


# =============================================================================
# PATTERN MATCHING (GITIGNORE-STYLE)
# =============================================================================


class PatternMatcher:
    """Match all paths relative to one explicit base using gitignore syntax."""

    def __init__(self, patterns: list[str], base_dir: str | None = None):
        self.base_dir = Path(base_dir or Path.cwd()).absolute()
        self.spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def matches(self, path: str) -> bool:
        relative = os.path.relpath(path, self.base_dir)
        return self.spec.match_file(Path(relative).as_posix())


# =============================================================================
# FILE DISCOVERY
# =============================================================================


def find_fd():
    """Find available fd/fdfind command."""
    for candidate in FD_CANDIDATES:
        if which(candidate):
            return candidate
    return None


def sh_quote(s: str) -> str:
    """Simple shell quoting for display."""
    if all(c.isalnum() or c in "._-/:=+" for c in s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


def run_fd(base_args, paths, add_default_pattern=False, verbose=False):
    """Run fd command and return results."""
    if not paths:
        return []

    cmd = base_args[:]
    if add_default_pattern:
        cmd.append(".*")

    cmd += ["--print0", *paths]
    if verbose:
        print("FD CMD:", " ".join(map(sh_quote, cmd)), file=sys.stderr)

    try:
        out = subprocess.run(cmd, capture_output=True, check=False)
    except OSError as e:
        if verbose:
            print(f"fd invocation failed: {e}", file=sys.stderr)
        return None

    if out.returncode:
        raise RuntimeError(f"fd failed: {out.stderr.decode(errors='replace').strip()}")
    data = out.stdout.decode("utf-8", errors="replace")
    return [p for p in data.split("\0") if p]


def gather_with_fd(inputs, excludes, use_gitignore, verbose=False):
    """Gather files using fd/fdfind."""
    fd = find_fd()
    if not fd:
        return None

    base = [fd, "--type", "f", "--color", "never", "--hidden"]
    if not use_gitignore:
        base += ["--no-ignore"]
    for pat in excludes:
        base += ["-E", pat]

    files = set()
    exclude_matcher = PatternMatcher(excludes) if excludes else None
    dirs, globs, files_given = [], [], []

    for it in inputs:
        it = it.strip()
        if not it:
            continue
        if os.path.isfile(it):
            files_given.append(os.path.abspath(it))
        elif os.path.isdir(it):
            dirs.append(it)
        else:
            globs.append(it)

    # Explicit files
    for f in files_given:
        if exclude_matcher and exclude_matcher.matches(f):
            continue
        files.add(os.path.abspath(f))

    # Directories
    if dirs:
        found = run_fd(base, dirs, add_default_pattern=True, verbose=verbose)
        if found is None:
            return None
        for p in found:
            files.add(os.path.abspath(p))

    # Globs
    for g in globs:
        args = [*base[:], "-g", g]
        found = run_fd(args, ["."], add_default_pattern=False, verbose=verbose)
        if found is None:
            return None
        for p in found:
            files.add(os.path.abspath(p))

    return sorted(files)


def gather_fallback(inputs, exclude_matcher: PatternMatcher, verbose=False):
    """Fallback file gathering using Python's os.walk."""
    files = set()

    for it in inputs:
        it = it.strip()
        if not it:
            continue

        candidates = []
        if os.path.isdir(it):
            for root, _, fs in os.walk(it):
                for f in fs:
                    candidates.append(os.path.join(root, f))
        else:
            candidates.extend(pyglob.glob(it, recursive=True))

        for p in candidates:
            if os.path.isfile(p) and not exclude_matcher.matches(p):
                files.add(os.path.abspath(p))

    return sorted(files)


# =============================================================================
# BINARY DETECTION
# =============================================================================


def _looks_text_by_name(path: str) -> bool:
    """Check if file looks like text based on name/extension."""
    base = os.path.basename(path)
    if base in TEXT_NAMES:
        return True
    ext = os.path.splitext(base)[1].lower().lstrip(".")
    return ext in TEXT_EXTS


def _control_ratio(sample: bytes) -> float:
    """Compute ratio of control bytes excluding whitespace."""
    if not sample:
        return 0.0
    controls = sum(1 for b in sample if b not in (9, 10, 13) and (b < 32 or b == 127))
    return controls / len(sample)


def is_probably_text(path: str, encoding: str = "utf-8", max_bytes: int = 65536) -> bool:
    """Determine if file is probably text."""
    try:
        if _looks_text_by_name(path):
            return True

        with open(path, "rb") as f:
            sample = f.read(max_bytes)

        if not sample:
            return True

        if b"\x00" in sample:
            return False

        try:
            sample.decode(encoding, errors="strict")
        except Exception:
            return False

        return _control_ratio(sample) <= 0.3
    except Exception:
        return False


def filter_text_files(file_paths, config: Config) -> list[str]:
    """Filter out binary files based on config."""
    if config.include_binary:
        return file_paths

    kept = []
    for fp in file_paths:
        if is_probably_text(fp, encoding=config.encoding, max_bytes=config.max_scan_bytes):
            kept.append(fp)
        elif config.show_skipped:
            print(f"[skip binary] {os.path.relpath(fp)}", file=sys.stderr)

    return kept


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================


def count_lines(path: str, encoding: str = "utf-8", errors: str = "replace") -> int:
    """Count lines in a file."""
    try:
        with open(path, encoding=encoding, errors=errors) as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def count_chars(path: str, encoding: str = "utf-8", errors: str = "replace") -> int:
    """Count characters in a file."""
    try:
        with open(path, encoding=encoding, errors=errors) as f:
            return len(f.read())
    except Exception:
        return 0


def format_tree_output(files: list[str], config: Config):
    """Format output as a pretty tree with statistics."""
    from rich import box
    from rich.columns import Columns
    from rich.console import Group
    from rich.panel import Panel

    console = Console()

    file_stats = {}
    for fp in files:
        try:
            with open(fp, encoding=config.encoding, errors=config.errors) as stream:
                lines = chars = 0
                for line in stream:
                    lines += 1
                    chars += len(line)
            file_stats[fp] = {"lines": lines, "chars": chars}
        except (OSError, UnicodeError) as exc:
            print(f"Cannot read {fp}: {exc}", file=sys.stderr)
            file_stats[fp] = {"lines": 0, "chars": 0}
    total_lines = sum(stats["lines"] for stats in file_stats.values())
    total_chars = sum(stats["chars"] for stats in file_stats.values())

    root = Tree(Text(".", style="bold blue"))
    directories = {(): root}
    for fp in sorted(files):
        parts = Path(os.path.relpath(fp)).parts
        for depth in range(1, len(parts)):
            key = parts[:depth]
            if key not in directories:
                directories[key] = directories[key[:-1]].add(Text(parts[depth - 1] + "/", style="bold blue"))
        stats = file_stats[fp]
        pct = stats["chars"] / total_chars * 100 if total_chars else 0
        label = Text(parts[-1])
        label.append(f"    {stats['lines']:,}L  ", style="dim yellow")
        label.append(f"{stats['chars']:,}C  ", style="dim green")
        label.append(f"{pct:.1f}%", style="bold magenta")
        directories[parts[:-1]].add(label)

    # Build top contributors panel
    top_contributors = []
    if len(files) > 0:
        # Sort files by character count (descending)
        sorted_files = sorted([(fp, file_stats[fp]["lines"], file_stats[fp]["chars"]) for fp in files], key=lambda x: x[2], reverse=True)[
            :10
        ]

        top_contributors.append(Text(f"Top {min(10, len(files))} Contributors", style="bold cyan"))
        top_contributors.append(Text())  # Empty line

        # Find max path length for alignment
        max_path_len = max(len(os.path.relpath(fp)) for fp, _, _ in sorted_files)

        # Create a table-like display
        for fp, lines, chars in sorted_files:
            rel_path = os.path.relpath(fp)
            pct = (chars / total_chars * 100) if total_chars > 0 else 0

            # Format with minimal spacing
            path_display = Text(f"{rel_path}", style="white")
            padding = " " * (max_path_len - len(rel_path) + 2)
            path_display.append(padding)
            path_display.append(f"{lines:>6,}L  ", style="dim yellow")
            path_display.append(f"{chars:>9,}C  ", style="dim green")
            path_display.append(f"{pct:>5.1f}%", style="bold magenta")
            top_contributors.append(path_display)

    # Create contributors panel
    contributors_group = Group(*top_contributors)
    contributors_panel = Panel(contributors_group, box=box.ROUNDED, border_style="dim", padding=(0, 1))

    # Try to display side-by-side if terminal is wide enough
    terminal_width = console.width

    # Estimate tree width by rendering it
    with console.capture() as capture:
        console.print(root)
    tree_output = capture.get()
    tree_width = max(len(line) for line in tree_output.splitlines()) if tree_output else 0

    # Minimum width needed for contributors (roughly 45-50 chars)
    min_contributors_width = 50

    if terminal_width >= tree_width + min_contributors_width + 5:
        # Wide enough - display side by side
        console.print(Columns([root, contributors_panel], equal=False, expand=False))
    else:
        # Not enough space - display vertically
        console.print(root)
        console.print()
        console.print(contributors_panel)

    console.print(f"\n[bold green]TOTAL:[/bold green] {total_lines:,}L  {total_chars:,}C  in {len(files)} files")


def format_list_output(files: list[str], config: Config):
    """Format output as a simple list with stats."""
    if config.pretty and (Console and Text):
        # Use rich for pretty list output with colors
        console = Console()
        total_lines = 0
        total_chars = 0

        # First pass: calculate totals and find max path length
        file_stats = []
        max_path_len = 0
        for fp in files:
            lines = count_lines(fp, config.encoding, config.errors)
            chars = count_chars(fp, config.encoding, config.errors)
            total_lines += lines
            total_chars += chars
            rel = os.path.relpath(fp)
            max_path_len = max(max_path_len, len(rel))
            file_stats.append((rel, lines, chars))

        # Second pass: display with colors and alignment
        for rel, lines, chars in file_stats:
            pct = (chars / total_chars * 100) if total_chars > 0 else 0

            # Format with colors like tree view
            line_display = Text(rel, style="white")
            padding = " " * (max_path_len - len(rel) + 2)
            line_display.append(padding)
            line_display.append(f"{lines:>6,}L  ", style="dim yellow")
            line_display.append(f"{chars:>9,}C  ", style="dim green")
            line_display.append(f"{pct:>5.1f}%", style="bold magenta")
            console.print(line_display)

        console.print(f"\n[bold green]TOTAL:[/bold green] {total_lines:,}L  {total_chars:,}C  in {len(files)} files")
    else:
        # Plain output without rich
        total_lines = 0
        total_chars = 0

        # First pass: calculate totals
        file_stats = []
        for fp in files:
            lines = count_lines(fp, config.encoding, config.errors)
            chars = count_chars(fp, config.encoding, config.errors)
            total_lines += lines
            total_chars += chars
            file_stats.append((fp, lines, chars))

        # Second pass: display
        for fp, lines, chars in file_stats:
            rel = os.path.relpath(fp)
            pct = (chars / total_chars * 100) if total_chars > 0 else 0

            if config.pretty:
                print(f"{rel}  {lines:>6,}L  {chars:>9,}C  {pct:>5.1f}%")
            else:
                print(rel)

        if config.pretty:
            print(f"\nTOTAL: {total_lines:,}L  {total_chars:,}C  in {len(files)} files")


def concatenate_files(files: list[str], config: Config) -> str:
    """Concatenate files into a single string."""
    output = StringIO()
    seen = set()

    for fp in files:
        rel = os.path.relpath(fp)
        if rel in seen:
            continue
        seen.add(rel)

        if not os.path.isfile(fp):
            print(f"Error: '{rel}' is not a regular file", file=sys.stderr)
            continue

        if config.add_header:
            print(f"{rel}:", file=output)

        try:
            with open(fp, encoding=config.encoding, errors=config.errors) as f:
                output.write(f.read())
        except Exception as e:
            print(f"Error reading '{rel}': {e}", file=sys.stderr)

        print("", file=output)

    result = output.getvalue()
    output.close()
    return result


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Concatenate files with gitignore-style patterns and config support.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s src/                        # Concatenate all files in src/
  %(prog)s --pretty src/               # Show tree view with stats
  %(prog)s -e "*.txt" "*.log" .        # Exclude multiple patterns
  %(prog)s -e file1 file2 -e "*.tmp" . # Mix single and multiple -e flags
  %(prog)s --terminal src/             # Print to terminal instead of clipboard

Config files:
  Global: ~/.config/concat/config.toml
  Project: .concatconfig or .concat.toml (searched upward from cwd)
        """,
    )

    # Input/Output
    parser.add_argument(
        "files",
        nargs="*",
        help="Files, directories, or globs. If empty, reads from stdin.",
    )
    parser.add_argument(
        "-t",
        "--terminal",
        action="store_true",
        help="Print to terminal instead of clipboard",
    )
    parser.add_argument(
        "-p",
        "--pretty",
        action="store_true",
        help="Pretty tree output with statistics",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List files only (no concatenation)",
    )

    # Pattern options
    parser.add_argument(
        "-e",
        "--exclude",
        action="extend",
        nargs="+",
        default=[],
        help="Exclude patterns (gitignore-style); can specify multiple patterns",
    )
    parser.add_argument(
        "-i",
        "--include",
        action="extend",
        nargs="+",
        default=[],
        help="Include patterns (gitignore-style); can specify multiple patterns",
    )
    parser.add_argument(
        "-g",
        "--gitignore",
        action="store_true",
        help="Respect .gitignore/.fdignore",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Disable built-in default excludes",
    )

    # File handling
    parser.add_argument(
        "--include-binary",
        action="store_true",
        help="Include binary files",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        help="File encoding (default: utf-8)",
    )
    parser.add_argument(
        "--errors",
        default=None,
        help="Decode errors policy: strict|ignore|replace",
    )

    # Output options
    parser.add_argument(
        "-n",
        "--no-header",
        "--no-filename",
        action="store_true",
        help="Don't print 'path:' header before file contents",
    )

    # Misc
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="Log skipped binary files to stderr",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Load config from files
    try:
        config = load_config()
    except ValueError as exc:
        parser.error(str(exc))

    # Override config with CLI arguments
    if args.exclude:
        config.exclude_patterns.extend(args.exclude)
    if args.include:
        config.include_patterns.extend(args.include)
    if args.gitignore:
        config.use_gitignore = True
    if args.no_default_excludes:
        config.use_default_excludes = False
    if args.include_binary:
        config.include_binary = True
    if args.encoding:
        config.encoding = args.encoding
    if args.errors:
        config.errors = args.errors
    if args.no_header:
        config.add_header = False
    if args.show_skipped:
        config.show_skipped = True
    if args.verbose:
        config.verbose = True
    if args.pretty:
        config.pretty = True
        config.output_mode = "tree"
    if args.list:
        config.output_mode = "list"

    # Get inputs
    inputs = args.files if args.files else ([line.strip() for line in sys.stdin if line.strip()] if not sys.stdin.isatty() else [])

    if not inputs:
        print("No inputs given. Provide files/dirs/globs or pipe a list on stdin.", file=sys.stderr)
        sys.exit(1)

    # Build exclude patterns
    exclude_patterns = []
    if config.use_default_excludes:
        exclude_patterns.extend(DEFAULT_EXCLUDES)
    exclude_patterns.extend(config.exclude_patterns)

    # Discover files
    try:
        files = gather_with_fd(inputs, exclude_patterns, config.use_gitignore, verbose=config.verbose)
    except RuntimeError as exc:
        parser.error(str(exc))

    if files is None:
        if config.use_gitignore:
            parser.error("--gitignore requires fd or fdfind; refusing to scan without ignore rules")
        if config.verbose:
            print("fd not found — falling back to Python scanning.", file=sys.stderr)
        exclude_matcher = PatternMatcher(exclude_patterns)
        files = gather_fallback(inputs, exclude_matcher, verbose=config.verbose)

    if not files:
        print("No matching files.", file=sys.stderr)
        sys.exit(2)

    # Apply include patterns (if any)
    if config.include_patterns:
        include_matcher = PatternMatcher(config.include_patterns)
        files = [f for f in files if include_matcher.matches(f)]

    # Filter binary files
    files = filter_text_files(files, config)

    if not files:
        print("No text files to process.", file=sys.stderr)
        sys.exit(3)

    # Output based on mode
    if config.output_mode == "tree":
        # Show pretty tree in terminal
        format_tree_output(files, config)

        # But still copy concatenated content to clipboard (unless --terminal)
        if not args.terminal:
            content = concatenate_files(files, config)

            try:
                copy_to_all_clipboards(content)
                print("\n✓ Concatenated content copied to clipboard.", file=sys.stderr)
            except Exception as e:
                print(f"\nClipboard copy failed ({e}).", file=sys.stderr)
    elif config.output_mode == "list" or args.list:
        format_list_output(files, config)
    else:
        # Concatenation mode
        content = concatenate_files(files, config)

        if args.terminal:
            print(content, end="")
        else:
            try:
                copy_to_all_clipboards(content)
                print("Output copied to clipboard.", file=sys.stderr)
            except Exception as e:
                print(f"Clipboard copy failed ({e}). Falling back to terminal.", file=sys.stderr)
                print(content, end="")


if __name__ == "__main__":
    main()
