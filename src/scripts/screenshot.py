"""Screenshot tool — full desktop, single monitor, or interactive selection."""

from __future__ import annotations

import datetime
import io
import os
import subprocess
import tkinter as tk
from typing import Optional

import mss
import pyautogui
import typer
import base64

from PIL import Image, ImageFilter

app = typer.Typer(help="Screenshot tool with full-desktop, single-monitor, and interactive-selection modes.")

DIR_OPTION = typer.Option(None, "--dir", "-d", help="Directory to save screenshots (default: current directory).")


def _pil_to_tkphoto(image: Image.Image, master: tk.Misc | None = None) -> tk.PhotoImage:
    """Convert a PIL Image to a tkinter PhotoImage using native PNG support (Tk 8.6+).

    This avoids ImageTk which requires a C extension that breaks in isolated venvs
    due to Tcl/Tk library mismatches.
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode(), master=master)


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
    data = output.getvalue()
    try:
        process = subprocess.Popen(
            ["xclip", "-selection", "clipboard", "-t", "image/png"],
            stdin=subprocess.PIPE,
        )
        process.communicate(data)
    except Exception as e:
        typer.echo(f"Failed to copy image to clipboard: {e}")


@app.command()
def full(
    dir: Optional[str] = DIR_OPTION,
) -> None:
    """Capture the full desktop (all monitors)."""
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
    dir: Optional[str] = DIR_OPTION,
) -> None:
    """Capture a single monitor by index."""
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


class SelectionTool:
    def __init__(self, monitor: dict, original_img: Image.Image, save_dir: str | None) -> None:
        self.monitor = monitor
        self.orig_img = original_img
        self.save_dir = save_dir
        self.width = monitor["width"]
        self.height = monitor["height"]

        self.blurred_img = self.orig_img.filter(ImageFilter.GaussianBlur(radius=7))

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.width}x{self.height}+{monitor['left']}+{monitor['top']}")
        self.root.lift()
        self.root.attributes("-topmost", True)

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height, highlightthickness=0)
        self.canvas.pack()
        self.bg_photo = _pil_to_tkphoto(self.blurred_img)
        self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")

        rect_w = int(self.width * 0.25)
        rect_h = int(self.height * 0.25)
        start_x = (self.width - rect_w) // 2
        start_y = (self.height - rect_h) // 2
        self.rect = [start_x, start_y, start_x + rect_w, start_y + rect_h]
        self.rect_id = self.canvas.create_rectangle(self.rect, outline="red", width=2)
        self.clear_img_id = self.canvas.create_image(self.rect[0], self.rect[1], anchor="nw")
        self.selection_photo: tk.PhotoImage | None = None

        self.handle_size = 20
        self.handle_draw_size = self.handle_size // 2
        self.handles: dict[str, int] = {}
        self.hover_handle: str | None = None
        self.draw_handles()
        self.update_clear_area()

        self.drag_data: dict = {"action": None, "orig_x": 0, "orig_y": 0, "orig_rect": None}

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.root.bind_all("<Key>", self.on_key)
        self.root.bind_all("<Control-c>", lambda e: self.on_confirm())

        self.root.update_idletasks()
        self.root.wait_visibility(self.root)
        self.root.grab_set_global()
        self.root.after(100, self.root.focus_force)
        self.root.after(200, self.root.focus_force)

    def draw_handles(self) -> None:
        x0, y0, x1, y1 = self.rect
        corners = {
            "resize_tl": (x0, y0),
            "resize_tr": (x1, y0),
            "resize_bl": (x0, y1),
            "resize_br": (x1, y1),
        }
        for action, (cx, cy) in corners.items():
            hid = self.canvas.create_oval(
                cx - self.handle_draw_size,
                cy - self.handle_draw_size,
                cx + self.handle_draw_size,
                cy + self.handle_draw_size,
                outline="red",
                width=2,
            )
            self.handles[action] = hid

    def update_handles(self) -> None:
        x0, y0, x1, y1 = self.rect
        corners = {
            "resize_tl": (x0, y0),
            "resize_tr": (x1, y0),
            "resize_bl": (x0, y1),
            "resize_br": (x1, y1),
        }
        for action, (cx, cy) in corners.items():
            hid = self.handles[action]
            self.canvas.coords(
                hid,
                cx - self.handle_draw_size,
                cy - self.handle_draw_size,
                cx + self.handle_draw_size,
                cy + self.handle_draw_size,
            )
            if action == self.hover_handle:
                self.canvas.itemconfig(hid, fill="red", outline="red")
            else:
                self.canvas.itemconfig(hid, fill="", outline="red")

    def update_clear_area(self) -> None:
        left, top, right, bottom = self.rect
        left, top = max(0, left), max(0, top)
        right, bottom = min(self.width, right), min(self.height, bottom)
        if right <= left or bottom <= top:
            return
        cropped = self.orig_img.crop((left, top, right, bottom)).copy()
        self.selection_photo = _pil_to_tkphoto(cropped)
        self.canvas.coords(self.clear_img_id, left, top)
        self.canvas.itemconfig(self.clear_img_id, image=self.selection_photo)
        self.canvas.lift(self.rect_id)
        self.update_handles()

    def on_mouse_move(self, event: tk.Event) -> None:
        x0, y0, x1, y1 = self.rect
        corners = {
            "resize_tl": (x0, y0),
            "resize_tr": (x1, y0),
            "resize_bl": (x0, y1),
            "resize_br": (x1, y1),
        }
        closest, min_dist = None, float("inf")
        for action, (cx, cy) in corners.items():
            dist = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
            if dist < min_dist and dist <= self.handle_size:
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
            self.drag_data["orig_rect"] = self.rect.copy()
        else:
            action = "new"
            self.drag_data["orig_x"] = event.x
            self.drag_data["orig_y"] = event.y
            self.rect = [event.x, event.y, event.x, event.y]
            self.canvas.coords(self.rect_id, *self.rect)
            self.update_clear_area()
        self.drag_data["action"] = action
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y

    def on_mouse_drag(self, event: tk.Event) -> None:
        action = self.drag_data["action"]
        x0, y0, x1, y1 = self.rect
        min_size = 20
        if action == "new":
            ox, oy = self.drag_data["orig_x"], self.drag_data["orig_y"]
            self.rect = [min(ox, event.x), min(oy, event.y), max(ox, event.x), max(oy, event.y)]
        elif action == "move":
            dx = event.x - self.drag_data["x"]
            dy = event.y - self.drag_data["y"]
            ox0, oy0, ox1, oy1 = self.drag_data["orig_rect"]
            w = ox1 - ox0
            h = oy1 - oy0
            new_x0 = min(max(ox0 + dx, 0), self.width - w)
            new_y0 = min(max(oy0 + dy, 0), self.height - h)
            self.rect = [new_x0, new_y0, new_x0 + w, new_y0 + h]
        else:
            if action == "resize_tl":
                self.rect = [min(max(event.x, 0), x1 - min_size), min(max(event.y, 0), y1 - min_size), x1, y1]
            elif action == "resize_tr":
                self.rect = [x0, min(max(event.y, 0), y1 - min_size), max(min(event.x, self.width), x0 + min_size), y1]
            elif action == "resize_bl":
                self.rect = [min(max(event.x, 0), x1 - min_size), y0, x1, max(min(event.y, self.height), y0 + min_size)]
            elif action == "resize_br":
                self.rect = [x0, y0, max(min(event.x, self.width), x0 + min_size), max(min(event.y, self.height), y0 + min_size)]
        self.canvas.coords(self.rect_id, *self.rect)
        self.update_clear_area()

    def on_mouse_up(self, event: tk.Event) -> None:
        self.drag_data["action"] = None

    def on_key(self, event: tk.Event) -> None:
        if event.keysym in ("Return", "space"):
            self.on_confirm()
        elif event.keysym == "Escape":
            self.root.destroy()

    def on_confirm(self) -> None:
        left, top, right, bottom = self.rect
        cropped = self.orig_img.crop((left, top, right, bottom)).copy()
        filepath = _save_image(cropped, "selection", self.save_dir)
        _copy_to_clipboard(cropped)
        typer.echo(f"Screenshot saved as {filepath}")
        typer.echo("Screenshot copied to clipboard.")
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


@app.command()
def selection(
    dir: Optional[str] = DIR_OPTION,
) -> None:
    """Interactive selection mode — draws on the active monitor."""
    mouse_x, mouse_y = pyautogui.position()
    with mss.mss() as sct:
        monitors = sct.monitors[1:]
        active_monitor = next(
            (
                m
                for m in monitors
                if m["left"] <= mouse_x < m["left"] + m["width"] and m["top"] <= mouse_y < m["top"] + m["height"]
            ),
            monitors[0],
        )
        sct_img = sct.grab(active_monitor)
        orig_img = Image.frombytes("RGB", (sct_img.width, sct_img.height), sct_img.rgb)
    tool = SelectionTool(active_monitor, orig_img, dir)
    tool.run()


if __name__ == "__main__":
    app()
