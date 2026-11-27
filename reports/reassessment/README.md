# Review of the remaining settings

Checked all 29,641 distinct settings in the pending categories at commit 65d541c.
The check used TradMate, abcjs 6.5.2, abc2midi 5.03 and abc2abc 2.22. The two abcmidi programs share a codebase and count as one parser family.

6,601 settings have accepted source notation. 6,492 settings leave all existing pending categories.
The source ABC is preserved. Accepted decisions record the exact source and finding state. New source text, meter, key, tune type or findings invalidate the decision.

| Category | Before | After |
|---|---:|---:|
| Needs review | 3,748 | 3,459 |
| Unsupported syntax or empty melody | 6,492 | 4,447 |
| Pickups, endings and repeats | 24,404 | 19,761 |
| Playback or parser compatibility | 3,460 | 2,045 |
| Parser-reviewed valid notation | 0 | 6,601 |

Counts overlap because a setting can have more than one observation.

## Acceptance evidence

- Source-format clearance requires working parsers, valid nonempty musical output, and no native syntax or duration errors.
- A restricted group of implicit-repeat warnings is accepted when independent base-melody playback agrees. ABC permits an omitted opening repeat, with playback restarting at the beginning or the previous repeat boundary.
- Existing internal-measure errors and rejected musical edits continue to require review.
- Playback observations are cleared when TradMate and abcjs agree on base pitches, onsets and durations. Decorations and generated accompaniment are excluded. Ties are joined, and time is rounded to 0.001 quarter notes. For written note chords, a separate comparison uses the first written pitch, matching TradMate melody handling.
- 722 accepted-format settings have remaining interpretation differences or a TradMate signature limitation. These are recorded separately in [playback-differences.csv](playback-differences.csv).
- Setting 34752 uses valid additive inline meters. The two external parser families accept it. Equivalent numeric meters produce the same base melody in TradMate, demonstrating a signature-support limitation.

The repeat and meter rules are documented in the [ABC 2.1 specification](https://abcnotation.com/wiki/abc:standard:v2.1).

## Correction search

Nine existing evidence-based correction passes were rerun. The only proposal is the previously held setting 31295. It still fails verification of the expected duration changes. The correction count remains 651 settings.

- [Correction search](correction-search.json)
- [Candidate playback check](correction-checks.json)
- [Reviewed settings and source-specific decisions](../../checks/reviewed-settings.json)
- [Accepted settings](../accepted.csv)
- [Current status](../status.md)

## Reproducing the checks

Select the union of the four pending reports from the current JSON export and retain the source hashes in input.json. Run audit_parsers.py on that selection. Run audit_tradmate.py and audit_abcjs.js with undecorated comparison bodies produced by review_common.comparison_body. Then run check_additive_meters.py, reassess.py and status.py.
The files in this directory retain the parser outputs and version metadata.
