from __future__ import annotations

import mimetypes
import platform
import shutil
import subprocess
from pathlib import Path

import typer

app = typer.Typer(help="Copy media files to the clipboard with automatic MIME detection.")


class ClipmediaError(Exception):
    """Raised when the clipboard operation fails."""


FILE_ARGUMENT = typer.Argument(
    ...,
    exists=True,
    file_okay=True,
    dir_okay=False,
    resolve_path=True,
    readable=True,
)
MIME_OPTION = typer.Option(None, "--mime", help="Manually override the MIME type.")
BACKEND_OPTION = typer.Option(None, "--backend", help="Force a specific clipboard backend.")


def _detect_mime(path: Path) -> str:
    """Return a best-effort MIME type for the provided file."""
    file_cmd = shutil.which("file")
    if file_cmd:
        try:
            res = subprocess.run(
                [file_cmd, "--mime-type", "-b", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
            mime = res.stdout.strip()
            if mime:
                return mime
        except subprocess.CalledProcessError:
            pass

    guess, _ = mimetypes.guess_type(path.name)
    return guess or "application/octet-stream"


def _pipe_file(cmd: list[str], source: Path) -> None:
    with source.open("rb") as fh:
        subprocess.run(cmd, check=True, stdin=fh)


def _copy_linux(source: Path, mime: str, preferred: str | None) -> str:
    candidates = [preferred] if preferred else ["wl-copy", "xclip", "xsel"]
    tried: list[str] = []

    for backend in candidates:
        if not backend:
            continue

        if backend == "wl-copy":
            if shutil.which("wl-copy"):
                _pipe_file(["wl-copy", "--type", mime], source)
                _pipe_file(["wl-copy", "--primary", "--type", mime], source)
                return "wl-copy"
            tried.append("wl-copy")

        elif backend == "xclip":
            if shutil.which("xclip"):
                _pipe_file(["xclip", "-selection", "clipboard", "-t", mime, "-i"], source)
                _pipe_file(["xclip", "-selection", "primary", "-t", mime, "-i"], source)
                return "xclip"
            tried.append("xclip")

        elif backend == "xsel":
            if shutil.which("xsel"):
                _pipe_file(["xsel", "--clipboard", "--input", "--mime-type", mime], source)
                _pipe_file(["xsel", "--primary", "--input", "--mime-type", mime], source)
                return "xsel"
            tried.append("xsel")

        else:
            raise ClipmediaError(f"Unknown Linux backend '{backend}'. Supported: wl-copy, xclip, xsel.")

    if preferred:
        raise ClipmediaError(f"Requested backend '{preferred}' is unavailable. Install it and retry.")

    available = [cmd for cmd in ["wl-copy", "xclip", "xsel"] if shutil.which(cmd)]
    hint = "Install wl-clipboard or xclip." if not available else f"Available backends: {', '.join(available)}"
    raise ClipmediaError(f"No clipboard backend found. {hint}")


APPLE_TYPE_MAP = {
    "image/png": "\u00abclass PNGf\u00bb",
    "image/jpeg": "JPEG picture",
    "image/jpg": "JPEG picture",
    "image/gif": "GIF picture",
    "image/tiff": "TIFF picture",
    "image/bmp": "BMP picture",
    "application/pdf": "PDF picture",
}


def _copy_macos(source: Path, mime: str, preferred: str | None) -> str:
    backend = preferred or "osascript"
    if backend not in {"osascript", "pbcopy"}:
        raise ClipmediaError("macOS backends supported: osascript (default), pbcopy (text-only fallback).")

    resolved = source.resolve()
    escaped = str(resolved.as_posix()).replace("\\", "\\\\").replace('"', '\\"')

    if backend == "pbcopy":
        # pbcopy is text-only; warn users explicitly.
        typer.secho("Warning: pbcopy treats data as UTF-8 text; binary payloads may be mangled.", fg=typer.colors.YELLOW)
        _pipe_file(["pbcopy"], source)
        return "pbcopy"

    apple_type = APPLE_TYPE_MAP.get(mime, "data")
    script = f'set the clipboard to (read (POSIX file "{escaped}") as {apple_type})'
    subprocess.run(["osascript", "-e", script], check=True)
    return "osascript"


def _copy_windows(source: Path, mime: str, preferred: str | None) -> str:
    backend = preferred or "powershell"
    if backend != "powershell":
        raise ClipmediaError("Windows backend options are limited to 'powershell'.")

    # Use FileDrop for maximum compatibility with paste targets.
    resolved = str(source.resolve())
    ps_script = rf"""
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms
$stringCollection = New-Object System.Collections.Specialized.StringCollection
$stringCollection.Add('{resolved}') > $null
$dataObject = New-Object System.Windows.DataObject
$dataObject.SetFileDropList($stringCollection)
[System.Windows.Clipboard]::SetDataObject($dataObject, $true)
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
        check=True,
    )
    return "powershell"


BACKEND_ALIASES = {
    "wl-copy": "wl-copy",
    "wlcopy": "wl-copy",
    "xclip": "xclip",
    "xsel": "xsel",
    "osascript": "osascript",
    "pbcopy": "pbcopy",
    "powershell": "powershell",
}


def _copy_to_clipboard(source: Path, mime: str, backend: str | None) -> str:
    system = platform.system()
    normalized = None
    if backend:
        normalized = BACKEND_ALIASES.get(backend.lower())
        if not normalized:
            raise ClipmediaError(f"Unknown backend '{backend}'.")

    if system == "Linux":
        return _copy_linux(source, mime, normalized)
    if system == "Darwin":
        return _copy_macos(source, mime, normalized)
    if system == "Windows":
        return _copy_windows(source, mime, normalized)

    raise ClipmediaError(f"Unsupported platform '{system}'.")


@app.command()
def run(
    file_path: Path = FILE_ARGUMENT,
    mime: str | None = MIME_OPTION,
    backend: str | None = BACKEND_OPTION,
) -> None:
    """Copy the given media file into the system clipboard."""
    source = file_path
    detected_mime = mime or _detect_mime(source)

    try:
        backend_used = _copy_to_clipboard(source, detected_mime, backend)
    except ClipmediaError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None
    except subprocess.CalledProcessError as exc:  # pragma: no cover - dependent on system tooling
        if isinstance(exc.stderr, bytes):
            error_hint = exc.stderr.decode(errors="ignore").strip()
        elif isinstance(exc.stderr, str):
            error_hint = exc.stderr.strip()
        else:
            error_hint = str(exc)
        typer.secho(f"Clipboard command failed: {error_hint}", fg=typer.colors.RED, err=True)
        raise typer.Exit(exc.returncode or 1) from None

    typer.secho(
        f"Copied '{source.name}' ({detected_mime}) to clipboard via {backend_used}.",
        fg=typer.colors.GREEN,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
