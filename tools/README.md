# Data tools

The scanner and data checks use the Python standard library. The playback check additionally needs a standalone Dart SDK and a local TradMate Git checkout containing commit `823fbf4cb5941394d86b5dd476ba46cc6e891f47`. It extracts only that parser's dependencies into a temporary directory, without modifying them or the TradMate checkout. Git LFS must have materialized `thesession.db` and `json/sets.json`.

## Find and apply fixes

```bash
python3 tools/fix_notation.py --tradmate-repo /path/to/TradMate --dart /path/to/dart --apply
```

Without `--apply`, the command saves proposals and results under `reports/`; use `--output /some/path` to choose another directory. It does not change exports or submit anything online. With `--apply`, accepted changes are recorded in `changes/notation-fixes.json`, checked and applied to CSV, JSON and SQLite, then listed under `reports/`. Existing original ABC is retained on subsequent runs.

The scanner uses exact fractions. Missing or shifted barlines require complete matching measures from the same tune, meter and key. Length corrections are restricted to one character and require a unique full-measure witness plus a matching adjacent measure. A missing triplet marker requires a matching complete phrase. Control characters are removed only outside annotations and comments. Unsupported syntax, repeat-boundary durations, guessed pitches, rest padding and inferred meters are excluded from automatic editing.

Each proposed setting is compiled before and after with automatic repair disabled and a neutral asset path. The checker compares every event's pitch, rest/tie state, start time and duration. Barlines must preserve all timings. Rhythm changes must match the independently calculated written-note changes. Some original duration errors are already normalized internally by the parser; those cases are marked explicitly in the results. A rejected setting remains unchanged. The scanner repeats until no further proposals pass, and the combined change is checked again before application.

Timing checks cover measure structure. The pitch and note-count passes below require their own matching passages and playback checks. Unusual meters and possible variants remain in the review report. The original ABC is checked against the correction plan before any replacement is applied.

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

Run `--transposed-pitches` to compare relative pitches and written scale degrees across keys in the same mode. Each change needs matching adjacent measures, a fourth matching measure and agreement from at least two other contributors.

The scanner resolves accidentals across each measure and allows one sounding pitch change per correction. New pitch edits are checked in TradMate and the vendored abcjs, using Node for the latter. Both must preserve timing and agree on the expected played changes. The abcjs check also matches the exact written locations. See [pitch edits](../checks/pitch-edits.json) for the original and corrected measures and the reference setting and measure numbers.

## Local notation syntax

Run `tools/fix_notation.py --syntax` to check isolated notation symbols, split note tokens and invalid ties between different pitches. A correction needs a matching complete measure and matching adjacent measures. Support comes from independent contributors, a longer matching phrase, or a separate written repetition. Both playback engines must preserve the sounding pitches, note count and timing. The abcjs check also checks for new notation warnings. The [notation syntax edits](../checks/syntax-edits.json) record the exact changes and reference measures.

## Omitted and surplus notes

Run `tools/fix_notation.py --note-counts` for a measure whose duration differs from a complete reference by exactly one note. Both neighbors must match, and the candidate and reference must have the same adjacent repeat or section marks. The complete corrected measure must match the written reference. Independent contributors, a longer matching phrase, or another written occurrence provide corroboration. A transposed reference for an omitted note must also match an additional measure in the same mode. A competing reading that resolves the duration by keeping the original notes blocks the change.

Each accepted patch inserts or removes a single whole note token. TradMate and abcjs check the agreed pitch and duration at every played occurrence and follow all remaining notes after the expected timing shift. The abcjs note-count check follows the written melody with generated backing chords disabled. Source chord annotations remain in the ABC. The [written-note edits](../checks/written-note-edits.json) identify the exact tokens and reference measures.

## Reference durations at section boundaries

Run `tools/fix_notation.py --reference-lengths` to compare an irregular measure with the same written passage in another setting or elsewhere in the tune. The target and reference share both neighboring measures and the same repeat or section markers. Transposed references need the same mode, scale degrees and rhythm around the target, with an additional matching measure. A separated duration suffix can qualify when joining it produces the exact reference and both playback engines confirm the resulting change.

The [rhythm edits](../checks/written-rhythm-edits.json) record the original and expected duration, exact written position and source measures. The checks follow every remaining note after accounting for the expected timing shift. If TradMate already interprets the written note at the corrected duration, its full playback must remain stable, its isolated measure must confirm the corrected duration, and abcjs must confirm the expected change in the full score.

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
