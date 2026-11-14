# latest

List the most recently modified files, newest at the bottom. Standalone Python 3.12+;
no packages and no other programs are required.

```sh
ln -s "$(pwd)/tools/latest/latest" ~/.local/bin/latest
```

## Use

There are no options to remember for the common cases. Say what you want in
any order:

```sh
latest                      # the 10 newest files below here
latest mp4                  # the 10 newest mp4 files
latest image build 1d       # images under build/ from the last day
latest png jpg 3            # the 3 newest png or jpg files
latest video ~/renders all  # every video, newest last
```

| Word | Meaning |
| --- | --- |
| `mp4`, `png`, `csv`, ... | file extensions, case-insensitive |
| `video`, `image`, `audio` | common extensions of that kind (also `vid`, `img`) |
| `30m`, `2h`, `1d`, `1w` | only files modified within that long (`s m h d w`) |
| `5` | how many to show; the default is 10 |
| `all` | no limit |
| `build`, `~/renders` | directories to search; the default is the current one |

In a terminal each line shows age, modification date, size and path, with the
newest file last, next to the prompt. A first line says how many older files
matched but are not shown. In a pipe the output is bare
paths in the same order, one per line, so it composes directly:

```sh
mpv "$(latest video 1)"
latest png 2h all | xargs -d '\n' nsxiv
latest mp4 -0 | xargs -0 du -ch
```

`-H` includes hidden files and directories, which are skipped by default.
`-l` keeps the detailed listing when piped. `-0` separates paths with NUL.
Ignore files such as `.gitignore` are never consulted, because generated
output usually lives in ignored directories. Directory symlinks are not followed.

A word is read as a count, an age, a known file type, an existing directory,
or else an extension, in that order. Write `./png` to mean a directory named
like a type. When nothing matches, the message states how the words were
understood (`latest: no biuld files under .`), which exposes typos. The exit
status is 1 when nothing matches and 2 for a usage error.

Tests: `uv run --no-project --with pytest pytest tools/latest/tests`.
