"""Cross-platform clipboard helpers shared across the script tools."""

from __future__ import annotations

import platform
import shutil
import subprocess


def _copy_to_linux_clipboard(text: str) -> None:
    """Copy text to Linux PRIMARY and CLIPBOARD selections."""
    if shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        subprocess.run(["xclip", "-selection", "primary"], input=text.encode(), check=True)
    elif shutil.which("xsel"):
        subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode(), check=True)
        subprocess.run(["xsel", "--primary", "--input"], input=text.encode(), check=True)
    elif shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=text.encode(), check=True)
        subprocess.run(["wl-copy", "--primary"], input=text.encode(), check=True)
    else:
        raise RuntimeError("No Linux clipboard backend found (xclip, xsel, or wl-copy)")


def copy_to_all_clipboards(text: str) -> None:
    """Copy text to all available clipboards (PRIMARY and CLIPBOARD on Linux)."""
    if platform.system() == "Linux":
        _copy_to_linux_clipboard(text)
    else:
        import pyperclip

        pyperclip.copy(text)
