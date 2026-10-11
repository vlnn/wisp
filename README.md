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
| ↩ | a menu of what this record can do, the usual thing on the first row: *Open* for a log, *Finish* for a task, *Decide* for a question, *Reopen* for a done or decided one, then Open, Rename, Copy, Trash. ↩ again runs it; type to narrow. On a question what you type is the answer: the first row reads *Decide "question \| answer"* and ↩ settles it, while the other rows stay put |
| ⇧↩ | copy the text; on a task, finish it; on a question, open the answer field (and on a settled one, reopen it) |
| ⌥↩ | move the file to the Trash (Finder's, with Put Back) |
| ⌘↩ | rename: the text is prefilled, edit it, ↩ |
| ⌘C | copy the text |
| ⌘L | large type |
| ⇧ or ⌘Y | Quick Look |

Matching: every word you type must be a prefix of a word in the line; case and diacritics are
ignored. There is no cap on the number of rows.

## Tasks, notes, questions, decisions

A line is a plain log unless it starts with a sigil:

```
l . fix the build            Task "fix the build"      ↩ keeps `. fix the build`
l ! keys are in 1password    Note "keys are in 1password"
l ? postgres or sqlite       Question "postgres or sqlite"
l = postgres | two writers   Decision "postgres | two writers"
l .                          open tasks, newest first
l . build                    open tasks about build
l *                          done tasks: "done 16:40 today · 09:12 today"
l ?                          open questions
l =                          decisions: "decided Tue 7 Oct 11:02 · Mon 6 Oct 16:30"
l !                          notes
```

⇧↩ (or ↩ ↩, *Finish*) on a task turns `. fix the build` into `* fix the build` in place; the file keeps its creation
time and its name, and the time it was marked is the file's modification time, so a done task
knows both when it was written and when it was finished. ⇧↩ again reopens it. A question is settled with
its resolution: ↩ on it, type the answer, ↩ again, and `? why is the sky green` turns into
`= why is the sky green | it is blue` in place, so the question and what came of it stay on
one line (⇧↩ opens the same answer field). *Reopen* makes it a question again without losing the answer, and a second *Decide*
appends another ` | …`. A decision can also be logged directly with `=`. `.` and `*` need a space after them, so
`.gitignore moved` and `*args again` stay plain logs; `?`, `!` and `=` never start a word, so
`?will it work` is the same question as `? will it work`. Words without a sigil
match every kind, so `l build` finds the task too.

The sigils are deliberately the bullet journal's: `.` a task, `*` crossed out, `!` worth
remembering, with `?` and `=` for the thing a work log is worst at answering months later, why.
Each kind has its own dot in the list: green for a log, terracotta for a note, and for the kinds
that get settled a ring while they are open and a filled dot once they are: ochre for a task,
blue for a question. Under `ask`, the *Ask* row wears the open question's ring and kept
answers the decision's dot. The colours are the top of `workflow/icons.py`;
`uv run python workflow/icons.py` redraws them.

## Install

1. Build `dist/Wisp.alfredworkflow` with `./build.sh` (or take it from Releases) and double-click it.
2. In the workflow's configuration set **Log folder**. The default is `~/log`; it is created on the
   first log.
3. Optional: hotkeys. The workflow ships two Hotkey objects, one wired to the `l` list and meant
   for HYPER+L (⌃⌥⇧⌘L), one wired to `ask` and meant for HYPER+/ (⌃⌥⇧⌘/). Alfred clears hotkey
   combinations on import so they never clash with yours, so double-click each object once and
   press the combination you want.

Nothing to install: the bundle runs on macOS's own `/usr/bin/python3` (3.9+) with the standard
library only.

## Ask the log: `ask`

Pick a model in the workflow configuration, one of:

- **Model server**: the URL of [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server`,
  or anything else that answers OpenAI-style `/v1/chat/completions`, e.g. `http://127.0.0.1:8080`;
- **Apple Intelligence**: a checkbox for Apple's on-device model (macOS 26 or later, an
  Apple-silicon Mac with Apple Intelligence turned on, and the Command Line Tools for a one-time
  compile of a small Swift helper into the workflow's data folder). While it is ticked the server
  fields are ignored.

Until one of them is set, `ask` only tells you to set it.

```
ask today summary            Ask "today summary"   ↩ asks the model about 1 240 lines
ask what did I do with api   Ask "what did I do with api"   ↩ asks the model about 1 240 lines, 23 matching
                             testing api manually      14:31 today
                             making API v1             14:02 today
ask                          the whole log, newest first
```

Under the **Ask** row the list is exactly what `l` would show for the same words, same dots and
same keys, so you can see what the model has to go on before you ask.

↩ on **Ask** opens a text view inside Alfred and the answer streams into it as the model writes. In the view, ↩ copies the answer and ⌥↩ keeps it as a file
and opens it; Esc closes the view and the answer is gone unless you kept it. Kept answers are
markdown files (question on the first line, answer below) in Alfred's data folder for the
workflow, opened as they are kept; they are not listed in Alfred.

The model sees each line as `YYYY-MM-DD HH:MM  text`; the other kinds carry a word before the
text, `TODO`, `QUESTION`, `NOTE`, or `DONE` and `DECIDED` with the time they were settled, so "what
is still open?", "what did I finish this week?" and "why postgres?" are questions it can answer. The question goes with the log, newest
line first, cut at about 12 000 characters for a server and
6 000 for the Apple model, whose context window is 4 096 tokens. The lines the question's words
match (the rows listed under **Ask**) always go, however old they are; the rest of the budget is
filled with the newest lines, so "what did I do with api" still works once the log has outgrown
the budget. The **Ask** row says how many lines that is and how many of them the words match. The model only ever runs when you press ↩ on **Ask**, never while you type. On a server,
pick an instruct model rather than a thinking one — the workflow asks the template not to think,
which Qwen3-style models honour, and hides a `<think>` block if one comes back anyway. **Model**
names the alias when the server serves several; **Model server API key** is sent as a bearer token.

`wisp ask --dry-run "today summary"` prints exactly what the model would be sent;
`wisp ask --keep "today summary"` saves the answer the way ⌥↩ does.

## How files are named

`reading docs` becomes `reading-docs.md`; a second `reading docs` becomes `reading-docs-2.md`; the
sigil never reaches the name, so `. fix the build` is `fix-the-build.md`. The
name is only a convenience for Finder and grep. Rename changes the text in place and then moves the
file to a name that fits, so the file keeps its creation time.

## From a terminal

```
export log_folder=~/log
uv run wisp keep "reading docs"
uv run wisp filter api | jq '.items[].title'
uv run wisp rename ~/log/reading-docs.md "reading Apache docs"
uv run wisp trash ~/log/reading-docs.md
uv run wisp keep ". fix the build"
uv run wisp mark ~/log/fix-the-build.md      → * fix the build (and back again)
uv run wisp decide ~/log/why-the-sky.md "it is blue"   → = why the sky … | it is blue
uv run wisp menu ~/log/fix-the-build.md      the ↩ menu, as Alfred's JSON
oracle_url=http://127.0.0.1:8080 uv run wisp ask "today summary"
```

`oracle_url`, `oracle_model` and `oracle_key` configure the model the way the panel does;
`alfred_workflow_data` is where kept answers go (default `~/Library/Application Support/wisp`).

`wisp check` prints the resolved settings: the log folder and how many records it holds, the data
and jobs folders, and whether the model server answers (or what the Apple helper still needs).

`filter`, `ask-filter`, `rename-filter`, `menu` and `view` print Alfred's JSON, `mark` and `decide` print the new line, `ask` prints the answer (`ask --keep` and
`keep-answer "<question>" "<answer>"` save it and print the file's path), the rest print the text
they acted on. `wisp act <action> <arg>` is what Alfred's ↩ runs: `keep`, `mark`, `open`, `copy` or `trash`,
each also a subcommand of its own. `wisp ask --job <folder> "…"` is what the text view runs in the
background: progress goes to that folder instead of notifications.

## Development

```
make test                                pytest
make lint                                ruff check and format, mypy
make build                               → dist/Wisp.alfredworkflow
uv run --isolated --python 3.9 pytest    the interpreter the workflow runs on
```

The bundle's version is `git describe --tags` at build time, so a tagged build shows `0.1.0` in
Alfred and a build from main shows `0.1.0-7-gabc1234`; the `version` in `workflow/info.plist` is
only what an untagged checkout falls back to.
CI runs the tests and lint on Python 3.9 and 3.13, builds the bundle on macOS and publishes it: every
push to `main` updates the `latest` pre-release, a `v*` tag makes a release with notes. To cut one:

```
git tag v0.1.0 && git push origin v0.1.0
```

`NOTES.md` lists what is deliberately not here yet and where it would go.
