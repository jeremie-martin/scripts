# ssh-clipboard

Copy the local text clipboard to a remote desktop:

```sh
ssh-clipboard work
ssh-clipboard user@other-host
```

Install a live link from the repository root:

```sh
ln -s "$(pwd)/tools/ssh-clipboard/ssh-clipboard" ~/.local/bin/ssh-clipboard
```

Source, README, and tests live together here. `~/.local/bin` contains only the
installed link. Source edits are live; remove the link to uninstall. For a copied
installation, use `install -m 755` instead. Keep the executable standalone: it
sends its own code to the remote host and requires no repository library there.

SSH aliases, keys, agents and interactive authentication use your normal SSH
configuration. X11 and other SSH forwarding are disabled for this connection.

Both machines need Python 3.8 or later. Linux needs `xclip` or `xsel` for X11,
or `wl-copy` and `wl-paste` (the `wl-clipboard` package) for Wayland. macOS uses
its built-in `pbcopy` and `pbpaste`. The remote SSH user must own and have access
to the desktop session. A headless host has no desktop clipboard to set.

Linux discovery uses that user's process environments, X server arguments and
desktop sockets. It ignores SSH-forwarded X displays and GNOME's private setup
display. Native Wayland is preferred when its utilities are installed; otherwise
Xwayland can provide clipboard access. Multiple detected desktops produce an
error rather than selecting one arbitrarily. For an explicit session:

```sh
ssh-clipboard work --display :0
ssh-clipboard work --display :0 --xauthority /path/on/host/to/Xauthority
ssh-clipboard work --wayland-display wayland-0
```

The implementation is sent through SSH for each invocation. It is not installed
on the remote machine. Clipboard data travels on stdin, never in command-line
arguments or temporary files. The clipboard utility retains ownership where
the window system requires it. Success means the remote clipboard was read back
and matched byte-for-byte; a digest receipt also verifies the result locally.
Another application can subsequently replace the clipboard as usual.

This is a one-shot text transfer, not clipboard synchronization. It does not
transfer images, file selections or all rich-text formats. Windows is not
supported. Restricted process visibility or unusual session layouts can require
explicit display/authentication options. Verification failure returns a nonzero
status but does not roll back the remote clipboard.

Run regression checks:

```sh
python3 -m unittest discover -s tools/ssh-clipboard/tests
```
