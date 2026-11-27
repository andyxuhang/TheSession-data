# Data tools

The scanner and data checks use the Python standard library. The playback check additionally needs a standalone Dart SDK and a local TradMate Git checkout containing commit `823fbf4cb5941394d86b5dd476ba46cc6e891f47`. It extracts only that parser's dependencies into a temporary directory, without modifying them or the TradMate checkout. Git LFS must have materialized `thesession.db` and `json/sets.json`.

## Find and apply fixes

```bash
python3 tools/fix_notation.py --tradmate-repo /path/to/TradMate --dart /path/to/dart --apply
```

Without `--apply`, the command saves proposals and results under `reports/`; use `--output /some/path` to choose another directory. It does not change exports or submit anything online. With `--apply`, accepted changes are recorded in `changes/notation-fixes.json`, checked and applied to CSV, JSON and SQLite, then listed under `reports/`. Existing original ABC is retained on subsequent runs.

The scanner uses exact fractions. Missing or shifted barlines require complete matching measures from the same tune, meter and key. Length corrections are restricted to one character and require a unique full-measure witness plus a matching adjacent measure. A missing triplet marker requires a matching complete phrase. Control characters are removed only outside annotations and comments. Unsupported syntax, repeat-boundary durations, guessed pitches, rest padding and inferred meters are excluded from automatic editing.

Each proposed setting is compiled before and after with automatic repair disabled and a neutral asset path. The checker compares every event's pitch, rest/tie state, start time and duration. Barlines must preserve all timings. Rhythm changes must match the independently calculated written-note changes. Some original duration errors are already normalized internally by the parser; those cases are marked explicitly in the results. A rejected setting remains unchanged. The scanner repeats until no further proposals pass, and the combined change is checked again before application.

These checks establish consistency with the stated rules, not the composer's intent. They cannot identify a wrong pitch that happens to fill a bar, reconstruct missing notes, or settle an unusual meter or deliberate variation. The report keeps such questions separate from applied fixes. New upstream ABC must match the recorded source text; a changed target setting stops the application for review.

## Barline fixes

Add `--barlines` to the scan command to process missing and misplaced dividers. It tests each location independently with the playback parser, combines the passing edits within each setting, and tests that version again. The original setting must already have at least six full bars and at least three quarters of its bars must fit the meter. A plain divider can move in either direction. When the left bar is short, or the setting falls outside the usual dance-meter checks, both corrected measures must already appear in sequence elsewhere in the same tune, meter and key. Witness locations in the change file are pairs of setting ID and zero-based written bar index.

## Note lengths

Use `--lengths` with `tools/fix_notation.py` to look for an incorrect duration digit or slash in an internal bar. A reference must be a different setting of the same tune, type, meter and key whose ABC is identical to the upstream snapshot. The complete corrected bar must match its written notes, rhythm marks and ornaments (apart from spacing). The comparison requires a matching neighbor or four matching notes on either side. Competing rhythms in the matching context leave the bar for review.

The tool checks every proposed suffix change alone, then checks the combined changes. A single edit must produce the expected audible duration change on a changed ABC token. The scanner records the reference setting and bar in the change file.

Use `--parallel-lengths` to check a written repetition in the same setting, including settings with no other transcriptions. The target is an internal bar between two plain dividers, surrounded by full bars. Its reference must be a full bar in the original upstream text, at least three written bars away. Neighbor comparisons stay on the same side of repeat or section boundaries. A full opening or closing bar can serve as a reference from the side with a matching phrase. Repeats produced by playback do not count as written evidence.

## Compare whole phrases

Run `tools/fix_notation.py --phrases` with the same compiler options. The scanner compares an irregular passage of up to four written measures with the original transcriptions of the same tune. An exact match in note order and timing can support new measure divisions. A matching passage can also establish one or two duration suffixes or a rhythm mark. The scanner requires a full matching neighbor, and uses both neighbors for less literal matches, multi-note timing changes and transposed versions. A line break within a double-length measure can support a missing divider when a complete half matches an adjacent written phrase. Each corrected passage and its references are recorded in [matching-phrases.json](../checks/matching-phrases.json).

Run `--missing-notes` to check short interior measures for an omitted note. The entire reconstructed measure and both neighbors must match original transcriptions from at least two other contributors. Playback must contain the inserted note where the original sequence is short and preserve the pitches, rests, ties and durations of the original events.

The reports count distinct settings. When an upstream setting appears in separate rows for different composers, the tools compare the ABC once and apply the same reviewed correction to each matching row. Composer fields are preserved.

## Accidentals and octaves

Run `tools/fix_notation.py --pitches` with the compiler options above. The pass looks in full measures between ordinary barlines. It compares the corrected measure and both neighbors with original transcriptions of the same tune. A fourth matching measure or a separate written repetition can provide additional corroboration.

An accidental correction needs either two other contributors and a fourth matching measure, or a written repetition and an independent contributor. An isolated octave jump may be corroborated by a fourth matching measure in another contributor's transcription. A change to a different note letter requires an isolated jump, a fourth matching measure and at least two other contributors. A conflicting transcription with the same surrounding passage leaves the pitch for review.

The scanner resolves accidentals across each measure and allows one sounding pitch change per correction. New pitch edits are checked in TradMate and the vendored abcjs, using Node for the latter. Both must preserve timing and agree on the expected played changes. The abcjs check also matches the exact written locations. See [pitch edits](../checks/pitch-edits.json) for the original and corrected measures and the reference setting and measure numbers.

## Other checks

```bash
python3 tools/apply.py
python3 tools/check_playback.py --tradmate-repo /path/to/TradMate --dart /path/to/dart
python3 tools/check_scope.py
python3 -m unittest discover -s tools -p 'test_*.py'
```

`apply.py --apply` applies all recorded change files; the default only checks the current exports. CSV and JSON are edited only inside the affected ABC fields. Set copies must match the reviewed ABC exactly; different arrangements are retained. SQLite schema and metadata are unchanged. Files are staged and cross-checked before replacement. The operation is repeatable; rerunning after a partial filesystem replacement completes the same changes.

`check_scope.py` compares every row of every table to the original upstream database. It expects that baseline's LFS object to be available locally, or accepts `--baseline-db /path/to/original/thesession.db`. It also verifies the baseline SHA-256 and unchanged license. This extra check does not download the baseline.

`scan.py --output /some/path` runs the fraction-based scanner alone. `status.py --findings /path/to/findings.jsonl` rebuilds the classified CSV lists from the current database exports and scan findings. `checks/previous-flags.json` retains the earlier parser's observations; a flag is used only while its source-body hash still matches. Those observations are not treated as proof of a source error.

The data paths (`csv/tunes.csv`, `json/tunes.json`, `thesession.db` and the set exports) follow the upstream layout. Source licenses and attribution remain in `LICENSE.md` and the exported records.
