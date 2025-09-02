#!/usr/bin/env python3
"""
Concatenate files (fd-powered) while excluding binary files by default.

Key behavior:
- Uses `fd`/`fdfind` for fast discovery; falls back to Python scanning.
- Excludes binary files by default via a two-stage approach:
  1) Zero-IO allowlist of common text extensions & filenames.
  2) Buffered sniff (up to --max-scan-bytes, default 65536 bytes):
     - Rejects if any NUL bytes present.
     - Rejects if decode (strict) fails with the selected --encoding (default utf-8).
     - Rejects if >30% control bytes (excluding whitespace) are found.
- Opt-in backdoor: --include-binary to include everything.
"""

import argparse
import fnmatch
import glob as pyglob
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from shutil import which

FD_CANDIDATES = ["fdfind", "fd"]  # prefer 'fdfind'

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
]

# Broad set of known-text extensions (NOT a binary blocklist!)
TEXT_EXTS = {
    # config / data
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
    # markup / docs
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
    # web / styles
    "css",
    "scss",
    "sass",
    "less",
    # scripts / shells
    "sh",
    "bash",
    "zsh",
    "fish",
    "ps1",
    "psm1",
    "bat",
    "cmd",
    # make / build
    "make",
    "mk",
    "cmake",
    "gradle",
    "groovy",
    # programming
    "c",
    "h",
    "cpp",
    "cc",
    "cxx",
    "hpp",
    "hh",
    "hxx",
    "m",
    "mm",  # Obj-C
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
    # infra
    "dockerfile",
    "env",
    "tf",
    "tfvars",
    "nomad",
    "hcl",
}

# Known text *basenames* without extensions
TEXT_NAMES = {"Dockerfile", "Makefile", ".gitignore", ".gitattributes", ".editorconfig"}


def find_fd():
    """Find available fd/fdfind command."""
    for candidate in FD_CANDIDATES:
        if which(candidate):
            return candidate
    return None


def sh_quote(s: str) -> str:
    if all(c.isalnum() or c in "._-/:=+" for c in s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


def run_fd(base_args, paths, add_default_pattern=False, verbose=False):
    """
    If add_default_pattern=True, inject default regex '.*' so 'paths' are search roots.
    """
    if not paths:
        return []

    cmd = base_args[:]
    if add_default_pattern:
        cmd.append(".*")  # explicit PATTERN so following args are PATHS

    cmd += ["--print0"] + paths
    if verbose:
        print("FD CMD:", " ".join(map(sh_quote, cmd)), file=sys.stderr)

    try:
        out = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
    except Exception as e:
        if verbose:
            print(f"fd invocation failed: {e}", file=sys.stderr)
        return None

    data = out.stdout.decode("utf-8", errors="replace")
    return [p for p in data.split("\0") if p]


def gather_with_fd(inputs, excludes, use_gitignore, verbose=False):
    fd = find_fd()
    if not fd:
        return None  # signal to fall back

    base = [fd, "--type", "f", "--color", "never", "--hidden"]
    if not use_gitignore:
        base += ["--no-ignore"]
    for pat in excludes:
        base += ["-E", pat]

    files = set()
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

    # explicit files
    for f in files_given:
        files.add(os.path.abspath(f))

    # directories: add explicit pattern '.*' so paths are treated as roots
    if dirs:
        found = run_fd(base, dirs, add_default_pattern=True, verbose=verbose)
        if found is None:
            return None
        for p in found:
            files.add(os.path.abspath(p))

    # globs: pattern-first form with -g; search from '.'
    for g in globs:
        args = base[:] + ["-g", g]  # -g supplies the pattern already
        found = run_fd(args, ["."], add_default_pattern=False, verbose=verbose)
        if found is None:
            return None
        for p in found:
            files.add(os.path.abspath(p))

    return sorted(files)


def is_excluded(path, patterns):
    rel = os.path.relpath(path)
    abs_ = os.path.abspath(path)
    for pat in patterns:
        if pat.endswith("/"):
            folder = pat[:-1]
            parts = Path(rel).parts
            if folder in parts:
                return True
        if (
            fnmatch.fnmatch(rel, pat)
            or fnmatch.fnmatch(os.path.basename(rel), pat)
            or fnmatch.fnmatch(abs_, pat)
        ):
            return True
    return False


def gather_fallback(inputs, excludes, verbose=False):
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
            if os.path.isfile(p) and not is_excluded(p, excludes):
                files.add(os.path.abspath(p))
    return sorted(files)


def _looks_text_by_name(path: str) -> bool:
    base = os.path.basename(path)
    if base in TEXT_NAMES:
        return True
    ext = os.path.splitext(base)[1].lower().lstrip(".")
    if ext in TEXT_EXTS:
        return True
    return False


def _control_ratio(sample: bytes) -> float:
    """
    Compute ratio of control bytes excluding common whitespace.
    """
    if not sample:
        return 0.0
    controls = 0
    for b in sample:
        if b in (9, 10, 13):  # \t, \n, \r
            continue
        if b < 32 or b == 127:
            controls += 1
    return controls / len(sample)


def is_probably_text(
    path: str, encoding: str = "utf-8", max_bytes: int = 65536
) -> bool:
    """
    Fast text-vs-binary sniffing.
    - Trusts filename/extension allowlist to avoid I/O for common text.
    - Otherwise reads up to max_bytes and applies:
        * NUL byte check
        * strict decode with provided encoding
        * control-character ratio threshold
    """
    try:
        if _looks_text_by_name(path):
            return True

        with open(path, "rb") as f:
            sample = f.read(max_bytes)

        if not sample:
            return True  # empty files: treat as text

        if b"\x00" in sample:
            return False

        # Strict decode with user-selected encoding; if it fails, likely binary.
        try:
            sample.decode(encoding, errors="strict")
        except Exception:
            # Many true binaries will fail here; if it's simply non-UTF8 text and
            # the user didn't pass the right --encoding, they can override.
            return False

        # Guardrail for unusual encodings that still decode: control char ratio
        if _control_ratio(sample) > 0.30:
            return False

        return True
    except Exception:
        # On any unexpected error during sniffing, err on the side of "not text".
        return False


def filter_text_files(
    file_paths,
    include_binary: bool,
    encoding: str,
    max_scan_bytes: int,
    show_skipped: bool,
) -> list:
    if include_binary:
        return file_paths
    kept = []
    for fp in file_paths:
        if is_probably_text(fp, encoding=encoding, max_bytes=max_scan_bytes):
            kept.append(fp)
        else:
            if show_skipped:
                print(f"[skip binary] {os.path.relpath(fp)}", file=sys.stderr)
    return kept


def concatenate(
    file_paths,
    output_buffer,
    print_paths=True,
    add_header=True,
    encoding="utf-8",
    errors="replace",
):
    seen = set()
    for fp in file_paths:
        rel = os.path.relpath(fp)
        if rel in seen:
            continue
        seen.add(rel)

        # print path listing to STDOUT (like before)
        if print_paths:
            print(rel)

        if not os.path.isfile(fp):
            print(f"Error: '{rel}' is not a regular file", file=sys.stderr)
            continue

        if add_header:
            print(f"{rel}:", file=output_buffer)
        try:
            with open(fp, "r", encoding=encoding, errors=errors) as f:
                output_buffer.write(f.read())
        except Exception as e:
            print(f"Error reading '{rel}': {e}", file=sys.stderr)

        print("", file=output_buffer)  # blank line between files


def main():
    parser = argparse.ArgumentParser(description="Concatenate files (fd-powered).")
    parser.add_argument(
        "-t",
        "--terminal",
        action="store_true",
        help="Print to terminal instead of copying to clipboard",
    )
    parser.add_argument(
        "-g",
        "--gitignore",
        action="store_true",
        help="Respect .gitignore/.fdignore (default off)",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        action="append",
        default=[],
        help="Extra excludes (wildcards or dirs); repeatable",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Disable built-in default excludes",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Do not print 'path:' header before file contents",
    )
    parser.add_argument(
        "--encoding", default="utf-8", help="File encoding (default: utf-8)"
    )
    parser.add_argument(
        "--errors",
        default="replace",
        help="Decode errors policy: strict|ignore|replace",
    )
    parser.add_argument(
        "--include-binary",
        action="store_true",
        help="Include binary files (disable binary auto-exclusion)",
    )
    parser.add_argument(
        "--max-scan-bytes",
        type=int,
        default=65536,
        help="Max bytes to sniff per file when detecting binaries (default: 65536)",
    )
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="Log skipped binary files to stderr",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose (shows fd command)"
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Files, directories, or globs. If empty, reads from stdin.",
    )
    args = parser.parse_args()

    inputs = (
        args.files
        if args.files
        else [line.strip() for line in sys.stdin if line.strip()]
        if not sys.stdin.isatty()
        else []
    )
    if not inputs:
        print(
            "No inputs given. Provide files/dirs/globs or pipe a list on stdin.",
            file=sys.stderr,
        )
        sys.exit(1)

    excludes = (
        [] if args.no_default_excludes else list(DEFAULT_EXCLUDES)
    ) + args.exclude

    # Try fd; fall back if unavailable or if call failed
    files = gather_with_fd(inputs, excludes, args.gitignore, verbose=args.verbose)
    if files is None:
        if args.verbose:
            print(
                "fdfind/fd not found — falling back to Python scanning.",
                file=sys.stderr,
            )
        files = gather_fallback(inputs, excludes, verbose=args.verbose)

    if not files:
        print("No matching files.", file=sys.stderr)
        sys.exit(2)

    # Binary exclusion happens here (post-discovery, pre-concatenation)
    files = filter_text_files(
        files,
        include_binary=args.include_binary,
        encoding=args.encoding,
        max_scan_bytes=args.max_scan_bytes,
        show_skipped=args.show_skipped,
    )

    if not files:
        print(
            "No text files to process (all were binary or excluded).", file=sys.stderr
        )
        sys.exit(3)

    if args.terminal:
        buf = StringIO()
        concatenate(
            files,
            buf,
            print_paths=True,
            add_header=not args.no_header,
            encoding=args.encoding,
            errors=args.errors,
        )
        out = buf.getvalue()
        buf.close()
        print(out, end="")
    else:
        buf = StringIO()
        concatenate(
            files,
            buf,
            print_paths=True,
            add_header=not args.no_header,
            encoding=args.encoding,
            errors=args.errors,
        )
        out = buf.getvalue()
        buf.close()
        try:
            import pyperclip

            pyperclip.copy(out)
            print("Output copied to clipboard.", file=sys.stderr)
        except Exception as e:
            print(
                f"Clipboard copy failed ({e}). Falling back to terminal output.",
                file=sys.stderr,
            )
            print(out, end="")


if __name__ == "__main__":
    main()
