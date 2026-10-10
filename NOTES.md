# Notes

## What is here

Eight small modules, each with one job, so a feature lands in one of them:

| Module | Owns | Grows when |
| --- | --- | --- |
| `records` | the folder: reading, naming, kinds, keep, rename, mark, trash | a record gets a new attribute, a new verb touches files |
| `search` | folding, word-prefix matching, the kind axis of a query | matching gets smarter (tags, dates) |
| `present` | time words and Alfred rows | a row gets a new key, a new kind of row appears |
| `macos` | Finder trash and notifications | another osascript call is needed |
| `oracle` | the model: evidence, prompt, request, streaming, answers on disk, which backend | a new question shape, a different budget |
| `apple` | the on-device model: Swift helper source, compile, run | the Swift side changes |
| `view` | the Text View protocol: a job's files, the JSON for each state | the view shows something new |
| `cli` | subcommands, the folder setting | a new subcommand, a new setting |

Alfred wiring is `workflow/info.plist`: one script filter (`l`) whose ↩ runs `keep` or `open` by the
`action` variable, ⇧↩ passes a conditional (`action` equal to `mark` goes to the ↩ script, anything
else to a clipboard object), ⌥↩ to `trash`, ⌘↩ to a second, keywordless script
filter that prefills the text and runs `rename` with the `path` variable, and ⌃↩ to a third,
keywordless script filter (`menu`) whose rows carry the same `action` values; its ↩ passes a
conditional that sends `rename`, `copy` and `trash` to the objects the modifier keys use and
everything else to the ↩ script. A new row action is a new `variables.action` value handled in
the ↩ script, and a new line in `present.menu`; a new key is a new connection from the first
filter. Esc in the menu closes Alfred rather than going back to the list. ↩ passes a conditional
first: `action` equal to `ask` goes to the Text View (script file `view` at the bundle root), anything
else to the ↩ script. 
The Text View runs `wisp view <question>` with no `job` variable, which starts `wisp ask --job
<folder>` detached and returns a rerun of 0.2 s; each rerun reads the job folder (`partial.md`,
`done`, `error`) and renders it. The job folder is under Alfred's cache folder, so Alfred may clear
it; nothing is saved until ⌥↩ in the finished view runs `wisp keep-answer "$question" "$1"` (the
question travels back as a variable, the answer is the view's output) and opens the file it printed. If the view ever comes up empty on ↩, check the
conditional in the editor reads *action is equal to ask*: that match mode is the one number in the
plist written from memory.

The **Apple Intelligence** checkbox arrives as `oracle_apple` (`1` or `0`); when on, `oracle.server`
returns `oracle.APPLE`, a `Server` with `apple=True` and no URL, and the server fields are not read.

`apple.swift` compiles with `swiftc -O -parse-as-library` into `<data>/bin/wisp-apple` the first time
it is needed, and again whenever the shipped source is newer than the binary. It takes the system
instructions as its argument and the prompt on stdin, prints the answer, and exits 2 with a message
when Apple Intelligence is not available. Nothing in the suite runs it; the shell contract is what
the tests pin down.

Creation time is `st_birthtime` on macOS, `st_mtime` elsewhere (so the suite runs on Linux CI); the
time a record last changed is `st_mtime` everywhere, and is what a done task reports as the time it
was finished. Tests inject `created`, `changed` and `now`, which is why nothing in the package reads
a clock on its own.

## Kinds

A kind is the first character of the line when a space follows it: `.` task, `*` done, `!` note,
anything else a plain log. `records.parse` is the one place that knows this; `Record.kind` and
`Record.line` read through it, `compose` writes it back, and `keep` and `rename` normalise the
spacing. `mark` flips `.` and `*` by rewriting the first line and nothing else, so the body and the
birth time survive and `st_mtime` becomes the done time. The sigils are not word characters, so the
slug ignores them and marking never moves a file.

The query carries the same sigil as a filter on kind (`search.query`), with the words matched
against `Record.line`; no sigil means every kind. The oracle spells kinds out as `TODO`, `DONE
<time>` and `NOTE` because a small model follows a word over 1 200 lines better than a dot.

`!` is a kind here, not a flag, so an important task has no spelling yet. If one is ever wanted,
the choice is between a second sigil position (`!. `) and making `!` orthogonal to the others;
`parse` is the only function that would change.

## Deliberately not here

- **Caching.** The folder is read in full on every keystroke. At ten lines a day that is under
  100 ms for two or three years. Then a snapshot file next to the log (refreshed when the folder
  changes) goes in `records.read_folder`, and nothing else changes.
- **Year folders.** Alfred's own list gets slow somewhere past 15 000 rows. When that day comes,
  `2026/`, `2027/` under the log folder, and bare `l` shows the current year unless a word is typed.
- **Notifications.** Keep, rename and trash print one line and show nothing; the next `l` has the
  result on top. A notification object on the `keep` output is one connection away.
- **Undo.** Trash goes to Finder's Trash, so Put Back is the undo. If a journal is ever wanted,
  `records` is where moves would be recorded.

## Where the earlier design goes

The design discussed before this was built (statuses, questions, snippets, sweep, promote, a local
model for tags, like and digests) is all compatible with the current files:

- Kinds are in (`.`, `*`, `!`); a `?` question kind cannot use `?` at the filter level, which is
  the ask mode, and a code span would be read by `records` the same way as the sigils.
- `sweep` is a new subcommand in `cli` that proposes moves between the log folder and an archive
  folder; `present` renders the proposal rows; `records` moves. Done tasks are the first thing it
  would propose.
- `promote` is a verb in `records` with a target per kind, settings in the plist.
- Model work beyond `l ?` (tags, embeddings, digest) extends `oracle`; it only ever runs from a
  `Run Script` object, never on a keystroke, and writes next to the log, never into the files.
  `digest` is `ask` with a fixed question over one day; `like` needs an embeddings endpoint and a
  vector file, the one piece of state the current design has no home for yet.

None of it requires hoard. If the folder ever wants an index, a journal and a conformance suite,
`records` is the reader a hoard kind would wrap.
