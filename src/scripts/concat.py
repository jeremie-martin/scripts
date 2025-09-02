#!/usr/bin/env python3
"""
Script to concatenate files based on patterns.
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
    ".next/",
    ".nuxt/",
    "build/",
    ".cache/",
    "target/",
    "*.log",
    "*.tmp",
    "*.swp",
    "*.swo",
    "*~",
]


def find_fd():
    """Find available fd/fdfind command."""
    for candidate in FD_CANDIDATES:
        if which(candidate):
            return candidate
    return None


def run_fd(pattern, path=".", excludes=None, fd_cmd=None):
    """Run fd command to find files."""
    if not fd_cmd:
        fd_cmd = find_fd()
        if not fd_cmd:
            return []

    cmd = [fd_cmd, "--type", "f", "--glob", pattern]
    if excludes:
        for exclude in excludes:
            cmd.extend(["--exclude", exclude])

    cmd.append(path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        return []


def find_files_with_fd(pattern, path=".", excludes=None):
    """Find files using fd."""
    fd_cmd = find_fd()
    if fd_cmd:
        return run_fd(pattern, path, excludes, fd_cmd)
    else:
        # Fallback to glob
        return find_files_with_glob(pattern, path, excludes)


def find_files_with_glob(pattern, path=".", excludes=None):
    """Find files using glob."""
    if excludes is None:
        excludes = []

    all_files = []
    for root, dirs, files in os.walk(path):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(os.path.join(root, d), exc) for exc in excludes)]

        for file in files:
            if fnmatch.fnmatch(file, pattern):
                # Check if file path matches any exclude pattern
                full_path = os.path.join(root, file)
                if not any(fnmatch.fnmatch(full_path, exc) for exc in excludes):
                    all_files.append(full_path)

    return all_files


def find_files(pattern, path=".", excludes=None, use_fd=True):
    """Find files using fd if available, otherwise glob."""
    if use_fd and find_fd():
        return find_files_with_fd(pattern, path, excludes)
    else:
        return find_files_with_glob(pattern, path, excludes)


def concatenate_files(files, output_file, separator="\n"):
    """Concatenate files into output file."""
    with open(output_file, 'w', encoding='utf-8') as outfile:
        for i, file_path in enumerate(files):
            if i > 0:
                outfile.write(separator)

            try:
                with open(file_path, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    outfile.write(content)
            except UnicodeDecodeError:
                # Try with different encoding
                try:
                    with open(file_path, 'r', encoding='latin-1') as infile:
                        content = infile.read()
                        outfile.write(content)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error reading {file_path}: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Concatenate files matching a pattern into a single output file."
    )
    parser.add_argument(
        "pattern",
        help="File pattern to match (e.g., '*.py', '*.txt')"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output file path"
    )
    parser.add_argument(
        "-p", "--path",
        default=".",
        help="Search path (default: current directory)"
    )
    parser.add_argument(
        "--no-fd",
        action="store_true",
        help="Don't use fd/fdfind even if available"
    )
    parser.add_argument(
        "--exclude",
        action="append",
        help="Exclude pattern (can be used multiple times)"
    )
    parser.add_argument(
        "--separator",
        default="\n",
        help="Separator between files (default: newline)"
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list files that would be concatenated"
    )

    args = parser.parse_args()

    # Combine default and user excludes
    excludes = DEFAULT_EXCLUDES + (args.exclude or [])

    # Find files
    files = find_files(args.pattern, args.path, excludes, not args.no_fd)

    if not files:
        print(f"No files found matching pattern '{args.pattern}' in '{args.path}'", file=sys.stderr)
        return 1

    # Sort files for consistent output
    files.sort()

    if args.list_only:
        print("Files that would be concatenated:")
        for file in files:
            print(f"  {file}")
        print(f"\nTotal: {len(files)} files")
        return 0

    # Concatenate files
    try:
        concatenate_files(files, args.output, args.separator)
        print(f"Successfully concatenated {len(files)} files into '{args.output}'")
        return 0
    except Exception as e:
        print(f"Error concatenating files: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
