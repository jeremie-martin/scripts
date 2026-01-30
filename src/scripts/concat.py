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
import fnmatch
import glob as pyglob
import os
import subprocess
import sys
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from shutil import which

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from scripts.jama.common import copy_to_all_clipboards

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

try:
    import pathspec
except ImportError:
    pathspec = None

try:
    from rich.console import Console
    from rich.text import Text
    from rich.tree import Tree
except ImportError:
    Console = Tree = Text = None


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

    def merge(self, other: "Config") -> "Config":
        """Merge another config into this one (other takes precedence for non-default values)."""
        merged = Config()

        # Merge lists (combine them)
        merged.exclude_patterns = self.exclude_patterns + other.exclude_patterns
        merged.include_patterns = self.include_patterns + other.include_patterns

        # For boolean/scalar values, prefer 'other' if it differs from default
        default = Config()

        merged.use_gitignore = other.use_gitignore if other.use_gitignore != default.use_gitignore else self.use_gitignore
        merged.use_default_excludes = (
            other.use_default_excludes if other.use_default_excludes != default.use_default_excludes else self.use_default_excludes
        )
        merged.pretty = other.pretty if other.pretty != default.pretty else self.pretty
        merged.output_mode = other.output_mode if other.output_mode != default.output_mode else self.output_mode
        merged.add_header = other.add_header if other.add_header != default.add_header else self.add_header
        merged.include_binary = other.include_binary if other.include_binary != default.include_binary else self.include_binary
        merged.encoding = other.encoding if other.encoding != default.encoding else self.encoding
        merged.errors = other.errors if other.errors != default.errors else self.errors
        merged.max_scan_bytes = other.max_scan_bytes if other.max_scan_bytes != default.max_scan_bytes else self.max_scan_bytes
        merged.show_skipped = other.show_skipped if other.show_skipped != default.show_skipped else self.show_skipped
        merged.verbose = other.verbose if other.verbose != default.verbose else self.verbose

        return merged


def load_toml_config(path: Path) -> Config | None:
    """Load configuration from a TOML file."""
    if not tomllib:
        return None

    if not path.exists():
        return None

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)

        # Map TOML to Config
        config = Config()

        if "patterns" in data:
            config.exclude_patterns = data["patterns"].get("exclude", [])
            config.include_patterns = data["patterns"].get("include", [])
            config.use_gitignore = data["patterns"].get("use_gitignore", False)
            config.use_default_excludes = data["patterns"].get("use_default_excludes", True)

        if "output" in data:
            config.pretty = data["output"].get("pretty", False)
            config.output_mode = data["output"].get("mode", "concat")
            config.add_header = data["output"].get("add_header", True)

        if "files" in data:
            config.include_binary = data["files"].get("include_binary", False)
            config.encoding = data["files"].get("encoding", "utf-8")
            config.errors = data["files"].get("errors", "replace")
            config.max_scan_bytes = data["files"].get("max_scan_bytes", 65536)

        if "misc" in data:
            config.show_skipped = data["misc"].get("show_skipped", False)
            config.verbose = data["misc"].get("verbose", False)

        return config
    except Exception as e:
        print(f"Warning: Failed to load config from {path}: {e}", file=sys.stderr)
        return None


def find_global_config() -> Config | None:
    """Find and load global config from ~/.config/concat/config.toml"""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    global_config_path = config_home / "concat" / "config.toml"
    return load_toml_config(global_config_path)


def find_project_config(start_dir: Path = None) -> Config | None:
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

    return None


def load_config() -> Config:
    """Load configuration from global and project configs, merging them."""
    config = Config()

    # Load global config
    global_config = find_global_config()
    if global_config:
        config = config.merge(global_config)

    # Load project config (takes precedence)
    project_config = find_project_config()
    if project_config:
        config = config.merge(project_config)

    return config


# =============================================================================
# PATTERN MATCHING (GITIGNORE-STYLE)
# =============================================================================


class PatternMatcher:
    """Handles gitignore-style pattern matching."""

    def __init__(self, patterns: list[str], base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.patterns = patterns

        if pathspec:
            # Use pathspec for proper gitignore semantics
            self.spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        else:
            # Fallback to simple fnmatch
            self.spec = None

    def matches(self, path: str) -> bool:
        """Check if path matches any pattern."""
        if self.spec:
            # pathspec handles relative paths properly
            try:
                rel_path = Path(path).relative_to(self.base_dir)
            except ValueError:
                rel_path = Path(path)
            return self.spec.match_file(str(rel_path))
        else:
            # Fallback matching
            return self._fallback_match(path)

    def _fallback_match(self, path: str) -> bool:
        """Simple fnmatch-based fallback when pathspec unavailable."""
        rel = os.path.relpath(path)
        abs_path = os.path.abspath(path)
        basename = os.path.basename(path)

        for pat in self.patterns:
            # Negation patterns (not perfect, but reasonable)
            if pat.startswith("!"):
                continue  # Skip negations in fallback mode

            # Directory patterns
            if pat.endswith("/"):
                folder = pat[:-1]
                if folder in Path(rel).parts:
                    return True

            # Standard glob matching
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(basename, pat) or fnmatch.fnmatch(abs_path, pat):
                return True

        return False


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
    except Exception as e:
        if verbose:
            print(f"fd invocation failed: {e}", file=sys.stderr)
        return None

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
    if not (Console and Tree):
        # Fallback to simple list if rich not available
        print("(Rich library not available, falling back to list view)", file=sys.stderr)
        format_list_output(files, config)
        return

    from rich import box
    from rich.columns import Columns
    from rich.console import Group
    from rich.panel import Panel

    console = Console()

    # Build tree structure
    tree_data = {}
    total_lines = 0
    total_chars = 0
    file_stats = {}  # Store stats for percentage calculation

    # First pass: collect stats and find max filename length per directory
    for fp in files:
        rel_path = Path(os.path.relpath(fp))
        parts = rel_path.parts

        line_count = count_lines(fp, config.encoding, config.errors)
        char_count = count_chars(fp, config.encoding, config.errors)
        total_lines += line_count
        total_chars += char_count
        file_stats[fp] = {"lines": line_count, "chars": char_count}

        current = tree_data
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Leaf (file)
                current[part] = {"_type": "file", "_lines": line_count, "_chars": char_count, "_path": fp}
            else:
                # Directory
                if part not in current:
                    current[part] = {"_type": "dir"}
                current = current[part]

    # Render tree with percentages
    def build_tree(node_dict, parent_tree=None):
        # Filter out metadata keys and sort: directories first, then files
        items = [(k, v) for k, v in node_dict.items() if not k.startswith("_")]
        items.sort(key=lambda x: (x[1].get("_type") == "file", x[0]))

        # Find max name length in this directory
        max_name_len = max((len(k) for k, v in items if v.get("_type") == "file"), default=0)

        for name, data in items:
            if data.get("_type") == "file":
                lines = data.get("_lines", 0)
                chars = data.get("_chars", 0)
                pct = (chars / total_chars * 100) if total_chars > 0 else 0

                # Create label with padding to align stats in this directory
                label = Text(name)
                # Pad to max length + some extra spacing
                padding_needed = max_name_len - len(name) + 4
                label.append(" " * padding_needed)
                label.append(f"{lines:>6,}L  ", style="dim yellow")
                label.append(f"{chars:>9,}C  ", style="dim green")
                label.append(f"{pct:>5.1f}%", style="bold magenta")
                if parent_tree:
                    parent_tree.add(label)
            else:
                # It's a directory (either explicit _type="dir" or just a dict)
                if parent_tree:
                    subtree = parent_tree.add(f"[bold blue]{name}/[/bold blue]")
                else:
                    subtree = Tree(f"[bold blue]{name}/[/bold blue]")
                build_tree(data, subtree)
                if parent_tree is None:
                    return subtree

    # Start from root
    if len(tree_data) == 1:
        root_name = list(tree_data.keys())[0]
        root = Tree(f"[bold blue]{root_name}/[/bold blue]")
        build_tree(tree_data[root_name], root)
    else:
        root = Tree("[bold blue].[/bold blue]")
        build_tree(tree_data, root)

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

        # Print path to stdout (for list mode)
        print(rel)

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
        "--no-header",
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
    config = load_config()

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
    files = gather_with_fd(inputs, exclude_patterns, config.use_gitignore, verbose=config.verbose)

    if files is None:
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
    if config.output_mode == "tree" and config.pretty:
        # Show pretty tree in terminal
        format_tree_output(files, config)

        # But still copy concatenated content to clipboard (unless --terminal)
        if not args.terminal:
            # Suppress the file listing during concatenation for clipboard
            import io

            old_stdout = sys.stdout
            sys.stdout = io.StringIO()  # Suppress file listing
            content = concatenate_files(files, config)
            sys.stdout = old_stdout

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
