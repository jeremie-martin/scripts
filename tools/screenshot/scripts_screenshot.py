"""Screenshot tool — full desktop, single monitor, or interactive selection."""

from __future__ import annotations

import datetime
import io
import json
import os
import subprocess
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import typer

if TYPE_CHECKING:
    import tkinter as tk

    from PIL import Image

from scripts_clipboard import ClipboardError, copy_linux, copy_to_all_clipboards

app = typer.Typer(help="Screenshot tool with full-desktop, single-monitor, and interactive-selection modes.")

DIR_OPTION = typer.Option(None, "--dir", "-d", help="Directory to save screenshots (default: current directory).")

_STATE_FILE = os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
    "screenshot-tool",
    "last_selection.json",
)


def _monitor_key(monitor: dict) -> str:
    """A stable identity for a monitor, based on its geometry."""
    return f"{monitor['left']},{monitor['top']},{monitor['width']},{monitor['height']}"


def _load_state() -> dict:
    try:
        with open(_STATE_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _load_last_rect(monitor: dict) -> list[int] | None:
    """Return this monitor's last selection rect if it still fits."""
    rect = _load_state().get(_monitor_key(monitor))
    width, height = monitor["width"], monitor["height"]
    if (
        isinstance(rect, list)
        and len(rect) == 4
        and all(isinstance(v, int) for v in rect)
        and 0 <= rect[0] < rect[2] <= width
        and 0 <= rect[1] < rect[3] <= height
    ):
        return rect
    return None


def _save_last_rect(monitor: dict, rect: list[int]) -> None:
    """Persist this monitor's selection rect for the next run; failures are non-fatal."""
    try:
        state = _load_state()
        state[_monitor_key(monitor)] = [int(v) for v in rect]
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump(state, f)
    except OSError:
        pass


def _pil_to_tkphoto(image: Image.Image, master: tk.Misc | None = None) -> tk.PhotoImage:
    """Convert a PIL Image to a tkinter PhotoImage using PPM (Tk 8.6+).

    PPM is uncompressed and natively decoded by Tk's C layer — no PNG
    compression overhead and no base64 encoding needed.
    """
    import tkinter as tk

    buf = io.BytesIO()
    image.save(buf, format="PPM")
    return tk.PhotoImage(data=buf.getvalue(), master=master)


def _save_image(img: Image.Image, prefix: str = "screenshot", directory: str | None = None) -> str:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{prefix}_{timestamp}.png"
    if directory:
        os.makedirs(directory, exist_ok=True)
        filepath = os.path.join(directory, filename)
    else:
        filepath = filename
    img.save(filepath)
    return filepath


def _copy_to_clipboard(img: Image.Image) -> None:
    output = io.BytesIO()
    img.save(output, format="PNG")
    try:
        copy_linux(output.getvalue(), "image/png")
    except ClipboardError as e:
        typer.echo(f"Failed to copy image to clipboard: {e}", err=True)
        raise typer.Exit(1) from e


def _copy_text_to_clipboard(text: str) -> None:
    """Copy text to PRIMARY and CLIPBOARD via the shared helper (xclip/xsel/wl-copy)."""
    try:
        copy_to_all_clipboards(text)
    except Exception as e:
        typer.echo(f"Failed to copy text to clipboard: {e}", err=True)
        raise typer.Exit(1) from e


def _run_ocr(image_path: str, max_new_tokens: int = 4096) -> str:
    """Run LightOnOCR on a saved image and return extracted text."""
    try:
        import torch
        from transformers import LightOnOcrForConditionalGeneration, LightOnOcrProcessor
    except ImportError:
        typer.echo("OCR needs the 'ocr' extra. Reinstall with: uv tool install --editable 'tools/screenshot[ocr]'")
        raise typer.Exit(code=1) from None

    model_id = "lightonai/LightOnOCR-2-1B"
    use_cuda = torch.cuda.is_available()
    device = "cuda" if use_cuda else "cpu"
    dtype = torch.bfloat16 if use_cuda else torch.float32

    typer.echo("Loading OCR model...")
    model = LightOnOcrForConditionalGeneration.from_pretrained(model_id, torch_dtype=dtype).to(device)
    processor = LightOnOcrProcessor.from_pretrained(model_id)

    conversation = [{"role": "user", "content": [{"type": "image", "url": image_path}]}]
    inputs = processor.apply_chat_template(conversation, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt")
    inputs = {k: (v.to(device=device, dtype=dtype) if v.is_floating_point() else v.to(device)) for k, v in inputs.items()}

    typer.echo("Running OCR...")
    output_ids = model.generate(**inputs, max_new_tokens=max_new_tokens)
    generated_ids = output_ids[0, inputs["input_ids"].shape[1] :]
    return processor.decode(generated_ids, skip_special_tokens=True).strip()


def _notify(summary: str, body: str = "") -> None:
    with suppress(FileNotFoundError):
        subprocess.Popen(["notify-send", "-a", "screenshot", summary, body])


@app.command()
def full(
    dir: str | None = DIR_OPTION,
) -> None:
    """Capture the full desktop (all monitors)."""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", (sct_img.width, sct_img.height), sct_img.rgb)
    filepath = _save_image(img, "full_desktop", dir)
    typer.echo(f"Screenshot saved as {filepath}")
    _copy_to_clipboard(img)
    typer.echo("Screenshot copied to clipboard.")


@app.command()
def monitor(
    index: int = typer.Argument(..., help="Monitor index (starting at 1)."),
    dir: str | None = DIR_OPTION,
) -> None:
    """Capture a single monitor by index."""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        monitors = sct.monitors
        if index < 1 or index >= len(monitors):
            typer.echo(f"Invalid monitor index. Available monitors: {len(monitors) - 1}")
            raise typer.Exit(code=1)
        mon = monitors[index]
        sct_img = sct.grab(mon)
        img = Image.frombytes("RGB", (sct_img.width, sct_img.height), sct_img.rgb)
    filepath = _save_image(img, f"monitor{index}", dir)
    typer.echo(f"Screenshot saved as {filepath}")
    _copy_to_clipboard(img)
    typer.echo("Screenshot copied to clipboard.")


@dataclass
class _DragState:
    action: str | None = None
    start_x: int = 0
    start_y: int = 0
    x: int = 0
    y: int = 0
    orig_rect: list[int] = field(default_factory=list)


class SelectionTool:
    _HANDLE_RADIUS = 10
    _HANDLE_HIT_SIZE = 20
    _MIN_SELECTION = 20
    _DEFAULT_RATIO = 0.25
    _OUTLINE_COLOR = "red"
    _OUTLINE_WIDTH = 2
    _BLUR_RADIUS = 7

    def __init__(self, monitor: dict, original_img: Image.Image, save_dir: str | None) -> None:
        import tkinter as tk
        from tkinter import font as tkfont

        from PIL import ImageFilter

        self.monitor = monitor
        self.orig_img = original_img
        self.save_dir = save_dir
        self.width = monitor["width"]
        self.height = monitor["height"]

        # Prepare images BEFORE creating the window
        blurred_img = self.orig_img.filter(ImageFilter.GaussianBlur(radius=self._BLUR_RADIUS))

        # Create window but keep it hidden until fully set up
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.width}x{self.height}+{monitor['left']}+{monitor['top']}")

        # Convert images to Tk format (needs a Tk root to exist)
        self.bg_photo = _pil_to_tkphoto(blurred_img, master=self.root)
        self.orig_photo = _pil_to_tkphoto(self.orig_img, master=self.root)
        del blurred_img  # free ~24MB

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height, highlightthickness=0)
        self.canvas.pack()
        self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")

        last_rect = _load_last_rect(self.monitor)
        if last_rect is not None:
            self.rect = last_rect
        else:
            rect_w = int(self.width * self._DEFAULT_RATIO)
            rect_h = int(self.height * self._DEFAULT_RATIO)
            start_x = (self.width - rect_w) // 2
            start_y = (self.height - rect_h) // 2
            self.rect = [start_x, start_y, start_x + rect_w, start_y + rect_h]
        self.rect_id = self.canvas.create_rectangle(self.rect, outline=self._OUTLINE_COLOR, width=self._OUTLINE_WIDTH)
        self.clear_img_id = self.canvas.create_image(self.rect[0], self.rect[1], anchor="nw")
        self.selection_photo: tk.PhotoImage | None = None

        self.handles: dict[str, int] = {}
        self.hover_handle: str | None = None
        self.draw_handles()

        # Live dimensions readout (white text on a dark backing for legibility).
        # Scale the font to the monitor height so it stays readable on 4K/HiDPI.
        # A negative size is interpreted by Tk as pixels (DPI-independent).
        self._label_font_px = max(12, round(self.height / 90))
        base_family = tkfont.nametofont("TkDefaultFont", root=self.root).actual("family")
        self._label_font = tkfont.Font(root=self.root, family=base_family, size=-self._label_font_px)
        self.size_bg_id = self.canvas.create_rectangle(0, 0, 0, 0, fill="black", outline="")
        self.size_text_id = self.canvas.create_text(0, 0, anchor="nw", fill="white", font=self._label_font, text="")

        self.update_clear_area()

        self.drag = _DragState()

        # Held-arrow-key state for smooth, multi-key, accelerating nudges.
        self._arrow_held: set[str] = set()
        self._arrow_release_jobs: dict[str, str] = {}
        self._arrow_tick_job: str | None = None
        self._arrow_accel = 0
        self._arrow_shift = False
        self._arrow_ctrl = False

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.root.bind_all("<Key>", self.on_key)
        self.root.bind_all("<Control-c>", lambda e: self.on_confirm())
        for key in self._ARROW_DELTAS:
            self.root.bind_all(f"<KeyPress-{key}>", self.on_arrow_press)
            self.root.bind_all(f"<KeyRelease-{key}>", self.on_arrow_release)

        # Show window now that everything is ready — no grey flash
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.update_idletasks()
        self.root.wait_visibility(self.root)
        self.root.grab_set_global()
        self.root.after(100, self.root.focus_force)
        self.root.after(200, self.root.focus_force)

    def _handle_positions(self) -> dict[str, tuple[int, int]]:
        x0, y0, x1, y1 = self.rect
        mx, my = (x0 + x1) // 2, (y0 + y1) // 2
        return {
            "resize_tl": (x0, y0),
            "resize_tr": (x1, y0),
            "resize_bl": (x0, y1),
            "resize_br": (x1, y1),
            "resize_t": (mx, y0),
            "resize_b": (mx, y1),
            "resize_l": (x0, my),
            "resize_r": (x1, my),
        }

    def draw_handles(self) -> None:
        r = self._HANDLE_RADIUS
        for action, (cx, cy) in self._handle_positions().items():
            hid = self.canvas.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline=self._OUTLINE_COLOR,
                width=self._OUTLINE_WIDTH,
            )
            self.handles[action] = hid

    def update_handles(self) -> None:
        r = self._HANDLE_RADIUS
        for action, (cx, cy) in self._handle_positions().items():
            hid = self.handles[action]
            self.canvas.coords(hid, cx - r, cy - r, cx + r, cy + r)
            if action == self.hover_handle:
                self.canvas.itemconfig(hid, fill=self._OUTLINE_COLOR, outline=self._OUTLINE_COLOR)
            else:
                self.canvas.itemconfig(hid, fill="", outline=self._OUTLINE_COLOR)

    def update_clear_area(self) -> None:
        import tkinter as tk

        left, top, right, bottom = self.rect
        left, top = max(0, left), max(0, top)
        right, bottom = min(self.width, right), min(self.height, bottom)
        w, h = right - left, bottom - top
        if w <= 0 or h <= 0:
            return
        # Use Tk-native photo copy instead of PIL crop → encode per frame
        self.selection_photo = tk.PhotoImage(width=w, height=h, master=self.root)
        self.selection_photo.tk.call(
            self.selection_photo,
            "copy",
            self.orig_photo,
            "-from",
            left,
            top,
            right,
            bottom,
            "-to",
            0,
            0,
        )
        self.canvas.coords(self.clear_img_id, left, top)
        self.canvas.itemconfig(self.clear_img_id, image=self.selection_photo)
        self.canvas.lift(self.rect_id)
        self.update_handles()
        self.update_size_label(w, h)

    def _refresh(self) -> None:
        """Re-sync the rectangle outline and clear area to the current rect."""
        self.canvas.coords(self.rect_id, *self.rect)
        self.update_clear_area()

    def update_size_label(self, w: int, h: int) -> None:
        """Show the live WxH of the selection just above its top-left corner."""
        left, top = self.rect[0], self.rect[1]
        pad = max(4, self._label_font_px // 3)
        approx_h = self._label_font_px + pad * 2
        self.canvas.itemconfig(self.size_text_id, text=f"{w} × {h}")  # noqa: RUF001 (display glyph)
        # Place above the box; flip to inside-below when too close to the top edge.
        text_y = top - pad if top - approx_h >= 0 else top + pad
        self.canvas.coords(self.size_text_id, left + pad, text_y)
        self.canvas.itemconfig(self.size_text_id, anchor="sw" if text_y < top else "nw")
        bbox = self.canvas.bbox(self.size_text_id)
        if bbox:
            x0, y0, x1, y1 = bbox
            self.canvas.coords(self.size_bg_id, x0 - pad, y0 - 1, x1 + pad, y1 + 1)
        self.canvas.lift(self.size_bg_id)
        self.canvas.lift(self.size_text_id)

    def on_mouse_move(self, event: tk.Event) -> None:
        closest, min_dist = None, float("inf")
        for action, (cx, cy) in self._handle_positions().items():
            dist = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
            if dist < min_dist and dist <= self._HANDLE_HIT_SIZE:
                min_dist, closest = dist, action
        if closest != self.hover_handle:
            self.hover_handle = closest
            self.update_handles()

    def on_mouse_down(self, event: tk.Event) -> None:
        x0, y0, x1, y1 = self.rect
        ctrl = (event.state & 0x4) != 0
        if self.hover_handle:
            action = self.hover_handle
        elif ctrl and x0 <= event.x <= x1 and y0 <= event.y <= y1:
            action = "move"
            self.drag.orig_rect = self.rect.copy()
        else:
            action = "new"
            self.drag.start_x = event.x
            self.drag.start_y = event.y
            self.rect = [event.x, event.y, event.x, event.y]
            self._refresh()
        self.drag.action = action
        self.drag.x = event.x
        self.drag.y = event.y

    def on_mouse_drag(self, event: tk.Event) -> None:
        action = self.drag.action
        x0, y0, x1, y1 = self.rect
        ms = self._MIN_SELECTION
        if action == "new":
            ox, oy = self.drag.start_x, self.drag.start_y
            self.rect = [min(ox, event.x), min(oy, event.y), max(ox, event.x), max(oy, event.y)]
        elif action == "move":
            dx = event.x - self.drag.x
            dy = event.y - self.drag.y
            ox0, oy0, ox1, oy1 = self.drag.orig_rect
            w = ox1 - ox0
            h = oy1 - oy0
            new_x0 = min(max(ox0 + dx, 0), self.width - w)
            new_y0 = min(max(oy0 + dy, 0), self.height - h)
            self.rect = [new_x0, new_y0, new_x0 + w, new_y0 + h]
        else:
            if action == "resize_tl":
                self.rect = [min(max(event.x, 0), x1 - ms), min(max(event.y, 0), y1 - ms), x1, y1]
            elif action == "resize_tr":
                self.rect = [x0, min(max(event.y, 0), y1 - ms), max(min(event.x, self.width), x0 + ms), y1]
            elif action == "resize_bl":
                self.rect = [min(max(event.x, 0), x1 - ms), y0, x1, max(min(event.y, self.height), y0 + ms)]
            elif action == "resize_br":
                self.rect = [x0, y0, max(min(event.x, self.width), x0 + ms), max(min(event.y, self.height), y0 + ms)]
            elif action == "resize_t":
                self.rect = [x0, min(max(event.y, 0), y1 - ms), x1, y1]
            elif action == "resize_b":
                self.rect = [x0, y0, x1, max(min(event.y, self.height), y0 + ms)]
            elif action == "resize_l":
                self.rect = [min(max(event.x, 0), x1 - ms), y0, x1, y1]
            elif action == "resize_r":
                self.rect = [x0, y0, max(min(event.x, self.width), x0 + ms), y1]
        self._refresh()

    def on_mouse_up(self, event: tk.Event) -> None:
        self.drag.action = None

    _ARROW_DELTAS: ClassVar[dict[str, tuple[int, int]]] = {
        "Left": (-1, 0),
        "Right": (1, 0),
        "Up": (0, -1),
        "Down": (0, 1),
    }
    _ARROW_TICK_MS = 16  # ~60fps motion while keys are held
    _ARROW_MAX_STEP = 30  # px per tick cap (before the Shift multiplier)
    _ARROW_SHIFT_MULT = 6  # Shift → jump straight to fast

    def on_key(self, event: tk.Event) -> None:
        if event.keysym in ("Return", "space"):
            self.on_confirm()
        elif event.keysym == "o":
            self.on_ocr()
        elif event.keysym == "Escape":
            self.root.destroy()

    def on_arrow_press(self, event: tk.Event) -> None:
        key = event.keysym
        # A Release immediately followed by a Press of the same key is X11
        # auto-repeat, not a real key-up — cancel the pending release.
        job = self._arrow_release_jobs.pop(key, None)
        if job is not None:
            self.root.after_cancel(job)
        self._arrow_held.add(key)
        self._arrow_shift = (event.state & 0x1) != 0
        self._arrow_ctrl = (event.state & 0x4) != 0
        if self._arrow_tick_job is None:
            self._arrow_accel = 0
            self._arrow_tick()

    def on_arrow_release(self, event: tk.Event) -> None:
        # Defer removal so an auto-repeat Press (already queued) can cancel it.
        key = event.keysym
        self._arrow_release_jobs[key] = self.root.after_idle(self._finalize_arrow_release, key)

    def _finalize_arrow_release(self, key: str) -> None:
        self._arrow_release_jobs.pop(key, None)
        self._arrow_held.discard(key)

    def _arrow_tick(self) -> None:
        if not self._arrow_held:
            self._arrow_tick_job = None
            self._arrow_accel = 0
            return
        self._arrow_accel += 1
        step = min(1 + self._arrow_accel // 3, self._ARROW_MAX_STEP)  # ramp up while held
        if self._arrow_shift:
            step *= self._ARROW_SHIFT_MULT
        dx = dy = 0
        for key in self._arrow_held:
            sx, sy = self._ARROW_DELTAS[key]
            dx += sx * step
            dy += sy * step
        if dx or dy:
            self._nudge(dx, dy, self._arrow_ctrl)
        self._arrow_tick_job = self.root.after(self._ARROW_TICK_MS, self._arrow_tick)

    def _nudge(self, dx: int, dy: int, resize: bool) -> None:
        x0, y0, x1, y1 = self.rect
        ms = self._MIN_SELECTION
        if resize:
            # Resize the bottom-right edge, clamped to the monitor and min size.
            x1 = min(max(x1 + dx, x0 + ms), self.width)
            y1 = min(max(y1 + dy, y0 + ms), self.height)
            self.rect = [x0, y0, x1, y1]
        else:
            # Move the whole box, preserving size, clamped on-screen.
            w, h = x1 - x0, y1 - y0
            nx0 = min(max(x0 + dx, 0), self.width - w)
            ny0 = min(max(y0 + dy, 0), self.height - h)
            self.rect = [nx0, ny0, nx0 + w, ny0 + h]
        self._refresh()

    def on_confirm(self) -> None:
        _save_last_rect(self.monitor, self.rect)
        left, top, right, bottom = self.rect
        cropped = self.orig_img.crop((left, top, right, bottom)).copy()
        filepath = _save_image(cropped, "selection", self.save_dir)
        _copy_to_clipboard(cropped)
        typer.echo(f"Screenshot saved as {filepath}")
        typer.echo("Screenshot copied to clipboard.")
        self.root.destroy()
        _notify("Screenshot copied to clipboard", filepath)

    def on_ocr(self) -> None:
        _save_last_rect(self.monitor, self.rect)
        _notify("OCR started", "Loading model...")
        left, top, right, bottom = self.rect
        cropped = self.orig_img.crop((left, top, right, bottom)).copy()
        filepath = _save_image(cropped, "selection", self.save_dir)
        typer.echo(f"Screenshot saved as {filepath}")
        self.root.destroy()
        try:
            text = _run_ocr(filepath)
        except (typer.Exit, SystemExit):
            return
        typer.echo(f"OCR result:\n{text}")
        _copy_text_to_clipboard(text)
        typer.echo("OCR text copied to clipboard (primary + clipboard).")
        _notify("OCR text copied to clipboard")

    def run(self) -> None:
        self.root.mainloop()


@app.command()
def selection(
    dir: str | None = DIR_OPTION,
) -> None:
    """Interactive selection mode — draws on the active monitor."""
    import mss
    import pyautogui
    from PIL import Image

    mouse_x, mouse_y = pyautogui.position()
    with mss.mss() as sct:
        monitors = sct.monitors[1:]
        active_monitor = next(
            (m for m in monitors if m["left"] <= mouse_x < m["left"] + m["width"] and m["top"] <= mouse_y < m["top"] + m["height"]),
            monitors[0],
        )
        sct_img = sct.grab(active_monitor)
        orig_img = Image.frombytes("RGB", (sct_img.width, sct_img.height), sct_img.rgb)
    tool = SelectionTool(active_monitor, orig_img, dir)
    tool.run()


@app.callback(invoke_without_command=True)
def _legacy_mode(
    ctx: typer.Context,
    mode: str | None = typer.Option(None, "--mode", hidden=True),
    monitor_idx: int | None = typer.Option(None, "--monitor", hidden=True),
    dir: str | None = DIR_OPTION,
) -> None:
    """Backward-compatible --mode flag."""
    if ctx.invoked_subcommand is not None or mode is None:
        return
    if mode == "full":
        full(dir=dir)
    elif mode == "monitor":
        if monitor_idx is None:
            typer.echo("Please specify --monitor index for single monitor mode.")
            raise typer.Exit(code=1)
        monitor(index=monitor_idx, dir=dir)
    elif mode == "selection":
        selection(dir=dir)
    else:
        typer.echo(f"Unknown mode: {mode}")
        raise typer.Exit(code=1)


def main() -> None:
    try:
        app()
    except ModuleNotFoundError as exc:
        if exc.name not in {"mss", "PIL", "pyautogui", "tkinter", "_tkinter"}:
            raise
        typer.echo(
            "Screenshot capture needs its Python dependencies (uv tool install --editable tools/screenshot) and system Tk support.",
            err=True,
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
