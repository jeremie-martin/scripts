# scripts-clipboard

Shared desktop clipboard transport. This library provides no commands and creates
no shared runtime environment. Each consuming tool installs it in its own environment.

Consumers declare a normal scripts-clipboard dependency and an editable relative
path in tool.uv.sources. uv uses that path when installing from the source checkout.
Wheels contain the dependency name, not a checkout path: supply this library's wheel
alongside consumer wheels when installing from artifacts.

API: copy_linux(bytes_or_path, mime, backend) returns the selected backend;
copy_to_all_clipboards(text) copies text; ClipboardError identifies transport failure.
Linux backend selection prefers Wayland when WAYLAND_DISPLAY is set. Both CLIPBOARD
and PRIMARY are copied. xsel supports text/plain only. Non-Linux text uses pyperclip.

From the repository root:

```sh
uv run --project packages/clipboard --locked pytest packages/clipboard/tests
uv build packages/clipboard
```

ssh-clipboard deliberately remains independent: it transmits its standard-library
implementation to the remote host, where this library is not installed.
