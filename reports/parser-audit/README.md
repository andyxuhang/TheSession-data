# Additional ABC parser review

Checked 55,821 distinct settings at commit f321390.
Used abc2midi 5.03 (check-only mode), abc2abc 2.22, and abcjs 6.5.2. Each setting was checked independently.
abc2midi and abc2abc share the abcmidi codebase. abcjs provides the independent parser comparison.
The ABC body was preserved. Every parser received explicit meter, key and L:1/8 headers.

| Parser | Settings with diagnostics | Absent from previous findings |
|---|---:|---:|
| abc2midi | 13,037 | 2,724 |
| abc2abc | 25,803 | 3,209 |
| abcjs | 1,646 | 132 |

The combined review contains 27,264 settings. Of these, 3,804 were absent from the current findings.jsonl.
These are diagnostic counts, not confirmed error counts. A setting can appear under several categories.
Short measures, incomplete repeats, unsupported decorations and engraving limitations require musical or specification review.

| Diagnostic category | Settings | Absent from previous findings |
|---|---:|---:|
| Measure duration | 21,854 | 90 |
| Repeat or ending structure | 7,684 | 3,216 |
| Parser process or exception | 4,096 | 1,022 |
| Ignored or unsupported character | 923 | 40 |
| Chord or annotation syntax | 886 | 218 |
| Note syntax | 752 | 165 |
| Other diagnostic | 588 | 88 |
| Decoration compatibility | 543 | 11 |
| Tie target | 389 | 60 |
| Barline compatibility | 376 | 71 |
| Broken rhythm | 316 | 18 |
| Grace-note syntax | 272 | 22 |
| Display duration | 234 | 30 |
| Tuplet notation | 104 | 4 |
| Unclosed chord annotation | 9 | 1 |

## Newly confirmed annotation defects

abcjs and abc2midi both report unclosed quoted annotations in the following settings. The intended annotation boundaries still need reference checking.

| Setting | Tune | Source |
|---|---|---|
| 15843 | 2576 | [Original](https://thesession.org/tunes/2576#setting15843) |

## Additional examples

- Settings 20630, 20632, 20633 and 20640 contain the form (3). abcjs reports the closing parenthesis as an ignored character. abc2midi accepts this form, so the intended slur or tuplet notation needs checking.
- Setting 37512 contains an incomplete explicit tuplet field. abcjs expects a number after the colon. abc2midi emits no diagnostic for this case.
- Unknown bar symbols and unrepresentable display durations can reflect parser behavior. The original ABC and musical phrase must be checked before changing notes or repeats.

## Files

- [All flagged settings](settings.csv), including source links and previous-review coverage.
- [Machine-readable summary](summary.json).
- [abc2midi and abc2abc diagnostics](native-diagnostics.jsonl).
- [abcjs diagnostics](abcjs-diagnostics.jsonl).
- [Native parser versions and input hash](native-summary.json).

Run from the data fork, with the TradMate checkout two directories above it.

```bash
python3 tools/audit_parsers.py --output reports/parser-audit
node tools/audit_abcjs.js ../../third_party/abcjs/abcjs-basic-min.js json/tunes.json reports/parser-audit/abcjs-diagnostics.jsonl 2> reports/parser-audit/abcjs-progress.jsonl
python3 tools/summarize_parsers.py
```

No score corrections were applied during this audit.
