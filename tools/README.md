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
