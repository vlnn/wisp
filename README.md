# wisp

One-line logs from Alfred. Type `l`, see what you logged, newest first. Type `l` and some words:
the first row logs them, the rows below are the records they match.

```
l making API v1          ↩   logged
l testing api manually   ↩   logged
l api                        Log "api"
                             testing api manually      14:31 today
                             making API v1             14:02 today
l                            everything, newest first
```

Every record is a markdown file in a folder you choose, holding the line and nothing else. When
it was logged is the file's creation time, so editing a file never moves it in the list and the
folder needs no index, no database and no sync of its own.

| Key | On a record |
| --- | --- |
| ↩ | open the file |
| ⇧↩ | copy the text |
| ⌥↩ | move the file to the Trash (Finder's, with Put Back) |
| ⌘↩ | rename: the text is prefilled, edit it, ↩ |
| ⌘C | copy the text |
| ⌘L | large type |
| ⇧ or ⌘Y | Quick Look |

Matching: every word you type must be a prefix of a word in the line; case and diacritics are
ignored. There is no cap on the number of rows.

## Install

1. Build `dist/Wisp.alfredworkflow` with `./build.sh` (or take it from Releases) and double-click it.
2. In the workflow's configuration set **Log folder**. The default is `~/log`; it is created on the
   first log.
3. Optional: a hotkey. The workflow ships a Hotkey object wired to the `l` list, meant for
   HYPER+L (⌃⌥⇧⌘L). Alfred clears hotkey combinations on import so they never clash with yours, so
   double-click the object once and press the combination you want.

Nothing to install: the bundle runs on macOS's own `/usr/bin/python3` (3.9+) with the standard
library only.

## How files are named

`reading docs` becomes `reading-docs.md`; a second `reading docs` becomes `reading-docs-2.md`. The
name is only a convenience for Finder and grep. Rename changes the text in place and then moves the
file to a name that fits, so the file keeps its creation time.

## From a terminal

```
export log_folder=~/log
uv run wisp keep "reading docs"
uv run wisp filter api | jq '.items[].title'
uv run wisp rename ~/log/reading-docs.md "reading Apache docs"
uv run wisp trash ~/log/reading-docs.md
```

`filter` and `rename-filter` print Alfred's JSON; the rest print the text they acted on.

## Development

```
uv sync
uv run pytest
uv run --isolated --python 3.9 pytest    the interpreter the workflow runs on
uv run ruff check && uv run ruff format --check
./build.sh                               → dist/Wisp.alfredworkflow
```

`NOTES.md` lists what is deliberately not here yet and where it would go.
