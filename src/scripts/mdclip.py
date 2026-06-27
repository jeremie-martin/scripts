from __future__ import annotations

import html
import platform
import re
import shutil
import subprocess
from pathlib import Path

import pyperclip
import typer
from bs4 import BeautifulSoup, Tag
from markdown_it import MarkdownIt

app = typer.Typer(help="Render a Markdown file to styled HTML and copy it to the clipboard.")


class MdclipError(Exception):
    """Raised when the clipboard operation fails."""


FILE_ARGUMENT = typer.Argument(
    ...,
    exists=True,
    file_okay=True,
    dir_okay=False,
    resolve_path=True,
    readable=True,
    help="Markdown file to render and copy.",
)
BACKEND_OPTION = typer.Option(None, "--backend", help="Force a specific clipboard backend.")
TITLE_OPTION = typer.Option(None, "--title", help="Override the HTML document title.")
PRINT_HTML_OPTION = typer.Option(False, "--print-html", help="Print the generated HTML instead of copying it.")

HTML_MIME = "text/html"
LINUX_BACKENDS = ("wl-copy", "xclip", "xsel")
BACKEND_ALIASES = {
    **{backend: backend for backend in LINUX_BACKENDS},
    "wlcopy": "wl-copy",
}
MARKDOWN_RENDERER = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
PLAIN_TEXT_DOUBLE_BREAK_TAGS = ("p", "div", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6")
PLAIN_TEXT_SINGLE_BREAK_TAGS = ("li", "tr")

ROOT_STYLE = (
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;"
    "font-size:15px;"
    "line-height:1.6;"
    "color:#24292f;"
    "background:#ffffff;"
)
TAG_STYLES: dict[str, str] = {
    "h1": "margin:0 0 16px;font-size:2em;font-weight:600;line-height:1.25;border-bottom:1px solid #d8dee4;padding-bottom:0.3em;",
    "h2": "margin:24px 0 16px;font-size:1.5em;font-weight:600;line-height:1.25;border-bottom:1px solid #d8dee4;padding-bottom:0.3em;",
    "h3": "margin:24px 0 16px;font-size:1.25em;font-weight:600;line-height:1.25;",
    "h4": "margin:24px 0 16px;font-size:1em;font-weight:600;line-height:1.25;",
    "h5": "margin:24px 0 16px;font-size:0.875em;font-weight:600;line-height:1.25;",
    "h6": "margin:24px 0 16px;font-size:0.85em;font-weight:600;line-height:1.25;color:#57606a;",
    "p": "margin:0 0 16px;",
    "ul": "margin:0 0 16px;padding-left:2em;",
    "ol": "margin:0 0 16px;padding-left:2em;",
    "li": "margin:0.25em 0;",
    "blockquote": "margin:0 0 16px;padding:0 1em;color:#57606a;border-left:0.25em solid #d0d7de;",
    "pre": (
        "margin:0 0 16px;"
        "padding:16px;"
        "overflow:auto;"
        "font-size:0.9em;"
        "line-height:1.45;"
        "background:#f6f8fa;"
        "border:1px solid #d0d7de;"
        "border-radius:6px;"
        "font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;"
    ),
    "table": "margin:0 0 16px;border-collapse:collapse;display:block;max-width:100%;overflow:auto;",
    "thead": "background:#f6f8fa;",
    "th": "padding:6px 13px;border:1px solid #d0d7de;font-weight:600;text-align:left;",
    "td": "padding:6px 13px;border:1px solid #d0d7de;",
    "hr": "height:0;margin:24px 0;border:0;border-top:1px solid #d8dee4;",
    "a": "color:#0969da;text-decoration:none;",
    "img": "max-width:100%;height:auto;",
}
INLINE_CODE_STYLE = (
    "padding:0.2em 0.4em;"
    "margin:0;"
    "font-size:85%;"
    "background:#f6f8fa;"
    "border-radius:6px;"
    "font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;"
)
BLOCK_CODE_STYLE = "padding:0;background:transparent;border-radius:0;font-size:inherit;"


def _merge_style(tag: Tag, style: str) -> None:
    existing = tag.get("style", "").strip()
    tag["style"] = f"{existing};{style}" if existing else style


def _list_item_prefix(tag: Tag) -> str:
    parent = tag.parent
    if not isinstance(parent, Tag) or parent.name != "ol":
        return "- "

    siblings = [child for child in parent.children if isinstance(child, Tag) and child.name == "li"]
    return f"{siblings.index(tag) + 1}. "


def _render_plain_text(wrapper: Tag) -> str:
    for list_item in wrapper.find_all("li"):
        list_item.insert(0, _list_item_prefix(list_item))

    for tag_name in PLAIN_TEXT_SINGLE_BREAK_TAGS:
        for tag in wrapper.find_all(tag_name):
            tag.insert_after("\n")

    for tag_name in PLAIN_TEXT_DOUBLE_BREAK_TAGS:
        for tag in wrapper.find_all(tag_name):
            tag.insert_after("\n\n")

    plain_text = wrapper.get_text()
    plain_text = re.sub(r"[ \t]+\n", "\n", plain_text)
    return re.sub(r"\n{3,}", "\n\n", plain_text).strip()


def _render_clipboard_payload(markdown_text: str, title: str) -> tuple[str, str]:
    soup = BeautifulSoup(MARKDOWN_RENDERER.render(markdown_text), "html.parser")

    for tag in soup.find_all(True):
        name = tag.name.lower()
        if name in TAG_STYLES:
            _merge_style(tag, TAG_STYLES[name])

        if name == "code":
            if tag.parent and tag.parent.name == "pre":
                _merge_style(tag, BLOCK_CODE_STYLE)
            else:
                _merge_style(tag, INLINE_CODE_STYLE)

    wrapper = BeautifulSoup("", "html.parser").new_tag("div")
    wrapper["style"] = ROOT_STYLE

    for element in list(soup.contents):
        wrapper.append(element)

    styled_fragment = str(wrapper)
    plain_text = _render_plain_text(wrapper)
    html_document = _build_html_document(styled_fragment, title)
    return html_document, plain_text


def _build_html_document(fragment: str, title: str) -> str:
    return (
        "<!DOCTYPE html>"
        "<html>"
        "<head>"
        '<meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        "</head>"
        "<body>"
        "<!--StartFragment-->"
        f"{fragment}"
        "<!--EndFragment-->"
        "</body>"
        "</html>"
    )


def _pipe_text(cmd: list[str], content: str) -> None:
    subprocess.run(cmd, check=True, input=content.encode("utf-8"))


def _copy_linux(html: str, preferred: str | None) -> str:
    candidates = [preferred] if preferred else list(LINUX_BACKENDS)

    for backend in candidates:
        if not backend:
            continue

        if backend == "wl-copy":
            if shutil.which("wl-copy"):
                _pipe_text(["wl-copy", "--type", HTML_MIME], html)
                _pipe_text(["wl-copy", "--primary", "--type", HTML_MIME], html)
                return "wl-copy"

        elif backend == "xclip":
            if shutil.which("xclip"):
                _pipe_text(["xclip", "-selection", "clipboard", "-t", HTML_MIME, "-i"], html)
                _pipe_text(["xclip", "-selection", "primary", "-t", HTML_MIME, "-i"], html)
                return "xclip"

        elif backend == "xsel":
            if shutil.which("xsel"):
                _pipe_text(["xsel", "--clipboard", "--input", "--mime-type", HTML_MIME], html)
                _pipe_text(["xsel", "--primary", "--input", "--mime-type", HTML_MIME], html)
                return "xsel"

        else:
            raise MdclipError(f"Unknown Linux backend '{backend}'. Supported: wl-copy, xclip, xsel.")

    if preferred:
        raise MdclipError(f"Requested backend '{preferred}' is unavailable. Install it and retry.")

    available = [cmd for cmd in LINUX_BACKENDS if shutil.which(cmd)]
    hint = "Install wl-clipboard or xclip." if not available else f"Available backends: {', '.join(available)}"
    raise MdclipError(f"No clipboard backend found. {hint}")


def _copy_html_to_clipboard(html: str, plain_text: str, backend: str | None) -> str:
    system = platform.system()
    normalized = None
    if backend:
        normalized = BACKEND_ALIASES.get(backend.lower())
        if not normalized:
            raise MdclipError(f"Unknown backend '{backend}'.")

    if system == "Linux":
        return _copy_linux(html, normalized)
    if normalized:
        raise MdclipError("Backend selection is only supported on Linux rich-clipboard backends.")

    pyperclip.copy(plain_text)
    return "pyperclip (plain text fallback)"


@app.command()
def run(
    file_path: Path = FILE_ARGUMENT,
    backend: str | None = BACKEND_OPTION,
    title: str | None = TITLE_OPTION,
    print_html: bool = PRINT_HTML_OPTION,
) -> None:
    """Copy a rendered Markdown preview to the clipboard."""
    markdown_text = file_path.read_text(encoding="utf-8")
    resolved_title = title or file_path.stem
    html_document, plain_text = _render_clipboard_payload(markdown_text, resolved_title)

    if print_html:
        typer.echo(html_document)
        raise typer.Exit()

    try:
        backend_used = _copy_html_to_clipboard(html_document, plain_text, backend)
    except MdclipError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None
    except pyperclip.PyperclipException as exc:
        typer.secho(f"Clipboard fallback failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None
    except subprocess.CalledProcessError as exc:  # pragma: no cover - dependent on system tooling
        error_hint = exc.stderr.decode(errors="ignore").strip() if isinstance(exc.stderr, bytes) else str(exc)
        typer.secho(f"Clipboard command failed: {error_hint or exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(exc.returncode or 1) from None

    message = f"Copied '{file_path.name}' as rendered HTML via {backend_used}."
    if "fallback" in backend_used:
        message += " Rich HTML clipboard support is currently implemented on Linux backends only."
    typer.secho(message, fg=typer.colors.GREEN)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
