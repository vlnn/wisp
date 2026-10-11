# Notes

## What is here

Eight small modules, each with one job, so a feature lands in one of them:

| Module | Owns | Grows when |
| --- | --- | --- |
| `records` | the folder: reading, naming, kinds, keep, rename, mark, trash | a record gets a new attribute, a new verb touches files |
| `search` | folding, word-prefix matching, the kind axis of a query | matching gets smarter (tags, dates) |
| `present` | time words, Alfred rows, the icon per kind | a row gets a new key, a new kind of row appears |
| `macos` | Finder trash and notifications | another osascript call is needed |
| `oracle` | the model: evidence, prompt, request, streaming, answers on disk, which backend | a new question shape, a different budget |
| `apple` | the on-device model: Swift helper source, compile, run | the Swift side changes |
| `view` | the Text View protocol: a job's files, the JSON for each state | the view shows something new |
| `cli` | subcommands, the folder setting | a new subcommand, a new setting |

Alfred wiring is `workflow/info.plist`: two script filters, `l` for the log and `ask` for the model,
each with a hotkey object; `ask` lists the same log rows under its own, so it has the same four
connections as `l`. The plist only routes to Alfred's own objects; every side effect is `wisp act "$action" "$1"`,
which dispatches through `cli.ACTIONS` (`keep`, `mark`, `open`, `copy`, `trash`). Both ↩ into one
conditional on the `action` variable: `ask` goes to the Text View (script file `view` at the bundle
root), `menu` to a keywordless script filter (`menu`) that lists what the record can do, else `act`.
The menu's rows carry the same `action` values the modifier keys use, and its ↩ passes a second
conditional that sends `rename` to the rename filter, `decide` straight to the `decide` script, else
`act`. On a question the menu is the answer field: what is typed is not a filter but the resolution,
the first row is `present.decide_row` with it, and Open, Rename, Copy and Trash stay listed
underneath. From the list, ⇧↩ passes a conditional too (`menu` for a question, since the menu is its
answer field, else `act` for `mark` or `copy`), ⌥↩ goes straight to `act` (`trash`), ⌘↩ to a
keywordless script filter that prefills the text and runs `rename` with the `path` variable. A new
action is a line in `present.menu`, a `variables.action` value and an entry in `cli.ACTIONS`; the
plist changes only when the action needs an Alfred object. A new shortcut is a connection from the
first filter. Esc in the menu closes Alfred rather than going back to the list; ⌃↩ is not used because
Alfred reserves it for the default fallback search.

The Text View runs `wisp view <question>` with no `job` variable, which starts `wisp ask --job
<folder>` detached and returns a rerun of 0.2 s; each rerun reads the job folder (`partial.md`,
`done`, `error`) and renders it. The folder is stamped (`started`) before the process is launched;
a job with no stamp, or with neither `done` nor `error` after `view.GIVE_UP` seconds, is shown as a
failure rather than polled forever. The job folder is under Alfred's cache folder, so Alfred may clear
it; nothing is saved until ⌥↩ in the finished view runs `wisp keep-answer "$question" "$1"` (the
question travels back as a variable, the answer is the view's output) and opens the file it printed.
A finished view also carries `thread`, its own job folder; ⌘↩ opens the keywordless `ask-more`
filter, whose row is the `ask` action with `thread` set, so the view starts `wisp ask --job <new>
--thread <old>`. Each job writes `thread.json`, its predecessor's turns plus its own
(`view.Job.remember`), and `oracle.prompt` replays them: the log goes with the first question,
then assistant and user turns alternate, and the turns' length comes off the evidence budget. If the view ever comes up empty on ↩, check the
conditional in the editor reads *action is equal to ask*: that match mode is the one number in the
plist written from memory.

The **Apple Intelligence** checkbox arrives as `oracle_apple` (`1` or `0`); when on, `oracle.backend`
returns an `oracle.Apple` and the server fields are not read, otherwise an `oracle.Llama` or `None`.
Both carry a `budget` and answer `respond(messages, on_text)`, and every failure comes back as one
`oracle.ModelError` whose message is what the user sees.

`apple.swift` compiles with `swiftc -O -parse-as-library` into `<data>/bin/wisp-apple` the first time
it is needed, and again whenever the shipped source is newer than the binary. It takes the system
instructions as its argument and the prompt on stdin, prints each snapshot of the answer as one JSON
string per line (`apple.snapshots` reads them, the last is the answer), and exits 2 with a message
when Apple Intelligence is not available. Nothing in the suite runs it; the shell contract is what
the tests pin down.

Creation time is `st_birthtime` on macOS, `st_mtime` elsewhere (so the suite runs on Linux CI); the
time a record last changed is `st_mtime` everywhere, and is what a done task reports as the time it
was finished. Both come from one `stat` in `records.file_stamps`, the `stamps` callable tests inject
along with `now`; the only places that read a clock are the defaults in `cli.run` and the job id
in `view.job_id`. A `Record` holds its `kind` and `line` as read; `text` is composed from them.

## Kinds

A kind is the first character of the line: `.` task, `*` done, `?` question, `=` decision, `!`
note, anything else a plain log. `.` and `*` count only when a space follows them, since they
start file names and globs; `?`, `!` and `=` count on their own (`records.TIGHT`). `records.parse` is the one place that knows this; `Record.kind` and
`Record.line` read through it, `compose` writes it back, and `keep` and `rename` normalise the
spacing. `mark` flips `.` and `*`, and `=` back to `?`, by rewriting the first line and nothing else, so the
body and the birth time survive and `st_mtime` becomes the time it was settled. `decide` is the
only way forward from `?`: it appends ` | <resolution>` (`records.RESOLVED`) and sets `=`, so a
reopened and re-decided question carries every resolution it ever had. The sigils are not word characters, so the
slug ignores them and marking never moves a file.

The query carries the same sigil as a filter on kind (`search.query`), with the words matched
against `Record.line`; no sigil means every kind. The first word that reads as a day (`search.days`:
`today`, `yesterday`, a weekday, `YYYY-MM-DD`, `YYYY-MM`) becomes `Query.span` and is taken out of
the words; `search.in_scope` is kind and span, `search.wanted` adds the words. `oracle.evidence`
uses the same query: the scope bounds what can go to the model; the words single lines out within
it (`oracle.single_out`: every word, else any word of three letters or more that is not filler) and
then only those go, headed with the terms; only when no word matches do the newest lines in scope
fill the budget. The oracle spells kinds out as `TODO`, `DONE
<time>` and `NOTE` because a small model follows a word over 1 200 lines better than a dot.

Alfred colours nothing in a row but the icon, so a kind's colour is a PNG in `workflow/icons/`,
drawn by `workflow/icons.py` with the standard library (a ring while open, a disc once settled).
`Kind.icon` is `icons/<name>.png` relative to the bundle, which is where `build.sh` copies the folder.

A kind is one line of `records.Kind`: its sigil, the word `l` offers it with (`Kind.offer`) and the
word the model sees (`Kind.tag`). What stays outside the enum is the state machine (`FLIPPED`,
`SETTLED`, `present.SETTLE`), since that relates kinds to each other. `present.Row` is Alfred's row
as a `TypedDict`, so mypy catches a misspelt key; `oracle.Backend` is a `Protocol`, so a third model
only needs `budget`, `respond` and `check`, and a branch in `oracle.backend`.

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

- Kinds are in (`.`, `*`, `?`, `=`, `!`); the ask mode moved to its own `ask` keyword to free `?`.
  A code span would be read by `records` the same way as the sigils.
- `sweep` is a new subcommand in `cli` that proposes moves between the log folder and an archive
  folder; `present` renders the proposal rows; `records` moves. Done tasks are the first thing it
  would propose.
- `promote` is a verb in `records` with a target per kind, settings in the plist.
- Model work beyond `ask` (tags, embeddings, digest) extends `oracle`; it only ever runs from a
  `Run Script` object, never on a keystroke, and writes next to the log, never into the files.
  `digest` is `ask` with a fixed question over one day; `like` needs an embeddings endpoint and a
  vector file, the one piece of state the current design has no home for yet.

None of it requires hoard. If the folder ever wants an index, a journal and a conformance suite,
`records` is the reader a hoard kind would wrap.
