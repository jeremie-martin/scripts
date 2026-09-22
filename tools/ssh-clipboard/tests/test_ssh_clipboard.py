"""Regression checks that do not change any desktop clipboard."""

import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader("clipboard", str(Path(__file__).parents[1] / "ssh-clipboard"))
spec = importlib.util.spec_from_loader(loader.name, loader)
clipboard = importlib.util.module_from_spec(spec)
loader.exec_module(clipboard)


def options(**kwargs):
    result = dict(display=None, wayland_display=None, xauthority=None)
    result.update(kwargs)
    return SimpleNamespace(**result)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(clipboard.sys, "platform", "linux"),
            patch.object(clipboard.Path, "glob", return_value=[]),
            patch.dict(clipboard.os.environ, {"DISPLAY": "localhost:12.0", "XAUTHORITY": "/wrong/auth", "WAYLAND_DISPLAY": "wrong-socket"}),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_one_desktop_replaces_ssh_environment(self):
        with patch.object(clipboard, "x_displays", return_value={":4": {"/desktop/auth"}}):
            kind, env, label = clipboard.remote_session(options())
        self.assertEqual((kind, label), ("x11", ":4"))
        self.assertEqual(env["XAUTHORITY"], "/desktop/auth")
        self.assertNotIn("WAYLAND_DISPLAY", env)

    def test_multiple_desktops_require_selection(self):
        with (
            patch.object(clipboard, "x_displays", return_value={":0": {""}, ":2": {""}}),
            self.assertRaisesRegex(clipboard.ClipboardError, "Multiple desktops"),
        ):
            clipboard.remote_session(options())

    def test_explicit_display_and_auth(self):
        with patch.object(clipboard, "x_displays", return_value={":0": {"/a", "/b"}}):
            _, env, _ = clipboard.remote_session(options(display=":0", xauthority="/chosen"))
        self.assertEqual(env["XAUTHORITY"], "/chosen")

    def test_ambiguous_auth_fails(self):
        with (
            patch.object(clipboard, "x_displays", return_value={":0": {"/a", "/b"}}),
            self.assertRaisesRegex(clipboard.ClipboardError, "Multiple X authority"),
        ):
            clipboard.remote_session(options())

    def test_headless_fails(self):
        with patch.object(clipboard, "x_displays", return_value={}), self.assertRaisesRegex(clipboard.ClipboardError, "No desktop"):
            clipboard.remote_session(options())

    def test_forwarded_override_rejected(self):
        with (
            patch.object(clipboard, "x_displays", return_value={}),
            self.assertRaisesRegex(clipboard.ClipboardError, "local display"),
        ):
            clipboard.remote_session(options(display="localhost:12.0"))

    def test_native_wayland(self):
        socket = SimpleNamespace(name="wayland-0", is_socket=lambda: True)
        with (
            patch.object(clipboard, "x_displays", return_value={}),
            patch.object(clipboard.Path, "glob", return_value=[socket]),
            patch.object(clipboard, "installed", return_value=True),
        ):
            kind, env, _ = clipboard.remote_session(options())
        self.assertEqual(kind, "wayland")
        self.assertEqual(env["WAYLAND_DISPLAY"], "wayland-0")
        self.assertNotIn("DISPLAY", env)


class DiscoveryTests(unittest.TestCase):
    def test_gnome_setup_and_forwarded_displays_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            for pid, display in enumerate((":0", ":1", "localhost:12.0"), 1):
                entry = proc / str(pid)
                entry.mkdir()
                entry.joinpath("environ").write_bytes(f"DISPLAY={display}\0GNOME_SETUP_DISPLAY=:1\0".encode())
                entry.joinpath("cmdline").write_bytes(b"/usr/bin/app\0")
            with patch.object(clipboard.Path, "exists", return_value=True):
                self.assertEqual(clipboard.x_displays(proc), {":0": {""}})


class VerificationTests(unittest.TestCase):
    def test_exact_bytes_including_empty_and_trailing_newlines(self):
        import hashlib
        import io
        import json

        for data in (b"", "café\n\n".encode()):
            with (
                self.subTest(data=data),
                patch.object(clipboard.sys, "argv", ["ssh-clipboard", "--receive"]),
                patch.object(clipboard.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(data))),
                patch.object(clipboard.sys, "stdout", new_callable=io.StringIO) as output,
                patch.object(clipboard, "remote_session", return_value=("x11", {}, ":0")),
                patch.object(clipboard, "backend", return_value=(["read"], ["write"])),
                patch.object(clipboard, "run_clipboard", side_effect=[None, data]) as run,
            ):
                clipboard.main()
                self.assertEqual(run.call_args_list[0].args, (["write"], {}, data))
                self.assertEqual(json.loads(output.getvalue())["sha256"], hashlib.sha256(data).hexdigest())

    def test_remote_mismatch_is_an_error(self):
        import io

        with (
            patch.object(clipboard.sys, "argv", ["ssh-clipboard", "--receive"]),
            patch.object(clipboard.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"expected\n"))),
            patch.object(clipboard, "remote_session", return_value=("x11", {}, ":0")),
            patch.object(clipboard, "backend", return_value=(["read"], ["write"])),
            patch.object(clipboard, "run_clipboard", side_effect=[None, b"wrong"]),
            self.assertRaisesRegex(clipboard.ClipboardError, "did not match"),
        ):
            clipboard.main()

    def test_utility_failure_propagates(self):
        with self.assertRaisesRegex(clipboard.ClipboardError, "failed"):
            clipboard.run_clipboard(["sh", "-c", "exit 7"], clipboard.os.environ.copy(), b"text")


if __name__ == "__main__":
    unittest.main()
