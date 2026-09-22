"""Cross-platform clipboard helpers shared across the script tools."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


class ClipboardError(RuntimeError):
    """The requested clipboard operation could not be completed."""


def copy_linux(source: bytes | Path, mime: str = "text/plain;charset=utf-8", backend: str | None = None) -> str:
    """Copy bytes or stream a file to Linux CLIPBOARD and PRIMARY selections.

    Prefer the active display protocol. xsel supports plain text only; explicit
    backend requests never silently fall back to a different backend.
    """
    if backend:
        backend = backend.lower()
        backend = "wl-copy" if backend == "wlcopy" else backend
        if backend not in {"wl-copy", "xclip", "xsel"}:
            raise ClipboardError(f"Unknown Linux backend '{backend}'. Supported: wl-copy, xclip, xsel (plain text only).")
        candidates = [backend]
    else:
        candidates = ["wl-copy", "xclip", "xsel"] if os.environ.get("WAYLAND_DISPLAY") else ["xclip", "xsel", "wl-copy"]

    plain_text = mime.split(";", 1)[0].lower() == "text/plain"
    selected = next((item for item in candidates if (item != "xsel" or plain_text) and shutil.which(item)), None)
    if selected is None:
        raise ClipboardError("No compatible clipboard backend available. Install wl-clipboard or xclip; xsel supports plain text only.")

    for selection in ("clipboard", "primary"):
        if selected == "wl-copy":
            cmd = [selected, "--type", mime, *(["--primary"] if selection == "primary" else [])]
        elif selected == "xclip":
            cmd = [selected, "-selection", selection, "-t", mime, "-i"]
        else:
            cmd = [selected, f"--{selection}", "--input"]
        try:
            if isinstance(source, Path):
                with source.open("rb") as stream:
                    subprocess.run(cmd, stdin=stream, check=True)
            else:
                subprocess.run(cmd, input=source, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ClipboardError(f"{selected} failed copying to {selection}: {exc}") from exc
    return selected


def copy_to_all_clipboards(text: str) -> None:
    """Copy text to all available clipboards (PRIMARY and CLIPBOARD on Linux)."""
    if platform.system() == "Linux":
        copy_linux(text.encode("utf-8"))
    else:
        import pyperclip

        pyperclip.copy(text)
