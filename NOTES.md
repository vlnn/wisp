# Notes

## What is here

Four small modules, each with one job, so a feature lands in one of them:

| Module | Owns | Grows when |
| --- | --- | --- |
| `records` | the folder: reading, naming, keep, rename, trash | a record gets a new attribute, a new verb touches files |
| `search` | folding and word-prefix matching | matching gets smarter (tags, dates, kinds) |
| `present` | time words and Alfred rows | a row gets a new key, a new kind of row appears |
| `cli` | subcommands, the folder setting | a new subcommand, a new setting |

Alfred wiring is `workflow/info.plist`: one script filter (`l`) whose ↩ runs `keep` or `open` by the
`action` variable, ⇧↩ goes to a clipboard object, ⌥↩ to `trash`, ⌘↩ to a second, keywordless script
filter that prefills the text and runs `rename` with the `path` variable. A new key is a new
connection from the first filter; a new row action is a new `variables.action` value handled in the
↩ script.

Creation time is `st_birthtime` on macOS, `st_mtime` elsewhere (so the suite runs on Linux CI).
Tests inject `created` and `now`, which is why nothing in the package reads a clock on its own.

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

- A kind of record (`!` status, `?` question, a code span) is a property of the text, read by
  `records` from the first character and shown by `present`; the file stays the plain line.
- `sweep` is a new subcommand in `cli` that proposes moves between the log folder and an archive
  folder; `present` renders the proposal rows; `records` moves.
- `promote` is a verb in `records` with a target per kind, settings in the plist.
- Model work (tags, embeddings, digest) is a separate module that only ever runs from a `Run Script`
  object in the background and writes its answers next to the log, never into the files.

None of it requires hoard. If the folder ever wants an index, a journal and a conformance suite,
`records` is the reader a hoard kind would wrap.
