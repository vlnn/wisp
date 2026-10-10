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

## Ask the log: `l ?`

Pick a model in the workflow configuration, one of:

- **Model server**: the URL of [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server`,
  or anything else that answers OpenAI-style `/v1/chat/completions`, e.g. `http://127.0.0.1:8080`;
- **Apple Intelligence**: a checkbox for Apple's on-device model (macOS 26 or later, an
  Apple-silicon Mac with Apple Intelligence turned on, and the Command Line Tools for a one-time
  compile of a small Swift helper into the workflow's data folder). While it is ticked the server
  fields are ignored.

Until one of them is set, `l ?` only tells you to set it.

```
l ? today summary            Ask "today summary"   ↩ asks the model about 1 240 lines
l ? what did I do with api   …
l ?                          every earlier answer, newest first
```

↩ on **Ask** opens a text view inside Alfred and the answer streams into it as the model writes
(the Apple model answers in one go). In the view, ↩ copies the answer and ⌥↩ keeps it as a file
and opens it; Esc closes the view and the answer is gone unless you kept it. Kept answers are
markdown files (question on the first line, answer below) in Alfred's data folder for the
workflow; `l ?` lists them like log lines: ↩ opens, ⇧↩ copies the answer, ⌥↩ trashes it.

The question goes with the log, newest line first, cut at about 12 000 characters for a server and
6 000 for the Apple model, whose context window is 4 096 tokens; the **Ask** row says how many lines
that is. The model only ever runs when you press ↩ on **Ask**, never while you type. On a server,
pick an instruct model rather than a thinking one — the workflow asks the template not to think,
which Qwen3-style models honour, and hides a `<think>` block if one comes back anyway. **Model**
names the alias when the server serves several; **Model server API key** is sent as a bearer token.

`wisp ask --dry-run "today summary"` prints exactly what the model would be sent;
`wisp ask --keep "today summary"` saves the answer the way ⌥↩ does.

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
oracle_url=http://127.0.0.1:8080 uv run wisp ask "today summary"
```

`oracle_url`, `oracle_model` and `oracle_key` configure the model the way the panel does;
`alfred_workflow_data` is where kept answers go (default `~/Library/Application Support/wisp`).

`filter`, `rename-filter` and `view` print Alfred's JSON, `ask` prints the answer (`ask --keep` and
`keep-answer "<question>" "<answer>"` save it and print the file's path), the rest print the text
they acted on. `wisp ask --job <folder> "…"` is what the text view runs in the background: progress
goes to that folder instead of notifications.

## Development

```
make test                                pytest
make lint                                ruff check and format
make build                               → dist/Wisp.alfredworkflow
uv run --isolated --python 3.9 pytest    the interpreter the workflow runs on
```

CI runs the tests and lint on Python 3.9 and 3.13, builds the bundle on macOS and publishes it: every
push to `main` updates the `latest` pre-release, a `v*` tag makes a release with notes. To cut one:

```
git tag v0.1.0 && git push origin v0.1.0
```

`NOTES.md` lists what is deliberately not here yet and where it would go.
