# Changes

## Accidentals and octaves

Corrected 19 accidentals and 2 octave errors in 18 settings of 17 tunes, along with 69 matching set entries. At least two other contributors give the same completed measure and neighboring phrases for each correction. The playback check verified 36 corrected occurrences across repeats, with the remaining pitches and all event timings preserved.

See the [before-and-after measures and references](checks/pitch-edits.json), the [playback results](checks/pitch-playback.json), and the [current review](reports/status.md).

## Bar divisions, note lengths and rhythm marks

Compared complete written phrases from the same setting and from other settings, including versions in other keys. Restored 100 missing barlines and corrected 57 misplaced-barline passages. Fixed 29 note-length passages and 2 rhythm marks. The missing-note check restored 2 notes supported by the same passage in settings from at least two other contributors.

This round corrected 190 passages in 156 settings of 139 tunes and updated 1194 matching set entries. See the [original and corrected passages](checks/matching-phrases.json), [note insertions](checks/missing-notes.json), and [review](reports/status.md). Target and source measure numbers in these files start at 1. The [final scan](checks/scan.json) found only candidates in settings already held for playback review. The checklists and report labels are in English.

## Note lengths in written repeats

Corrected 34 note lengths in 34 settings of 28 tunes. The original transcriptions contain a separate written occurrence of each corrected bar with the same surrounding phrase. Of these notes, 26 needed a longer duration and 8 a shorter one. The exports include 46 matching set entries. Two candidates in setting 32000 produced no duration change in playback and remain open.

See [the original and corrected bars](checks/parallel-lengths.json) for each comparison. Both target and reference bar numbers in this file start at 1. The [current report](reports/status.md) covers 384 fixes in 345 settings and lists 3,893 settings for review.

## Note lengths in matching phrases

Corrected 22 duration suffixes in 21 settings of 16 tunes and updated 126 matching set entries. Each corrected bar matches another upstream setting with the same key, meter and surrounding phrase. All 22 edits passed the individual and combined playback checks. See [the changed bars and their references](checks/phrase-lengths.json).

## Missing barlines

Restored 19 missing dividers in 15 settings and 45 matching set entries. Each change splits a double-length measure into two full measures. Seven have the exact two-bar phrase in sequence in another setting of the tune. All 19 preserved the original pitches and timing individually and together within each setting. Three other proposed dividers changed a pitch and remain open. See the [individual checks](checks/barlines.json) and [current list](reports/status.md).

After the barline changes, the cumulative count was 328 fixes across 290 settings and 253 tunes.

## Earlier notation fixes

The automated pass fixes 303 places in 269 settings across 233 tunes:

- 210 missing barlines;
- 4 misplaced barlines;
- 70 single-character note-length errors;
- 19 stray control characters outside comments and annotations.

Each musical change has a complete-bar witness from the same tune and key. A note-length change also needs a matching adjacent phrase. Playback comparisons keep pitches, ties and rests unchanged and allow only the expected duration changes. Three proposals did not pass that comparison and remain in the issue list. Two scan passes found supported changes; a third found no further acceptable changes.

Together with the initial fixes below, the total at that revision was 309 places in 275 settings across 238 tunes. All three export formats are updated, including exact matching copies embedded in sets. No notes or rests are added and the contributor metadata is retained.

See [the current issue list](reports/status.md), [the changes](changes/notation-fixes.json), [playback checks](checks/notation-playback.json), and [data checks](checks/data.json). The entries below describe the earlier six-setting change and its original checks.

## Initial fixes

Reviewed on 27 November 2026 by andyxuhang. The upstream baseline is commit `9106aa8e29b72c3affd954f48b259ea02a1fb418` from [adactio/TheSession-data](https://github.com/adactio/TheSession-data).

The first change contains six setting corrections across five tunes. Each replacement is limited to a specific source fragment and source-content hash. Original tune IDs, setting IDs, contributor names, dates, composers and other metadata are retained in the data exports. The complete original and corrected ABC for each setting are recorded in [initial-fixes.json](changes/initial-fixes.json).

| Tune | Setting | Correction and evidence |
|---|---|---|
| The Plane Tree | [26073](https://thesession.org/tunes/4990#setting26073) | Move the barline in `cde dcB AGA\|B3` to give `cde dcB\|AGA B3`. This changes a 9+3 grouping of eighth notes into two complete 6/8 bars without changing any notes or durations. |
| The Fox On The Prowl | [13420](https://thesession.org/tunes/501#setting13420) | Move `BAFA defab\|faf e3 A` to `BAFA defa\|bfaf e3 A`. This produces 8+8 eighth-note units in place of 9+7. |
| The Fox On The Prowl | [13421](https://thesession.org/tunes/501#setting13421) | The same misplaced barline occurs with a final lowercase `a`. Apply the same divider adjustment and retain that pitch. |
| The Flower Of The Flock | [13579](https://thesession.org/tunes/585#setting13579) | Insert the missing divider in `A~E3DEGA BGBd`, giving `A~E3\|DEGA BGBd`. The two resulting bars each contain the correct written duration for 4/4. The existing triplet and ornament are retained. |
| O'Connor's | [25362](https://thesession.org/tunes/2097#setting25362) | Change `af fe/f` to `af fe/f/`. The first bar of the same B part explicitly gives the latter rhythm. Restoring the final slash removes the surplus sixteenth note. |
| Mairi's Wedding | [1797](https://thesession.org/tunes/706#setting1797) | Change `BA Bd2` to `BA Bd`. The former contains five eighth-note units in 2/4. The complete, otherwise matching `BA Bd` occurs in the A part of this setting. |

## Public-page review

The current ABC and comments were inspected on the linked pages before this round. The Plane Tree page displayed 13 comments, The Fox On The Prowl 20, The Flower Of The Flock 13, O'Connor's 13 and Mairi's Wedding 45. These counts document the review coverage at that time.

Mairi's Wedding already has a [2011 comment about incorrect rhythm](https://thesession.org/tunes/706#comment576068) and a [2012 clean-ABC contribution](https://thesession.org/tunes/706#comment628208). Those comments do not explicitly identify this particular `d2`. The proposed correction also has the same-setting parallel-bar evidence described above.

For The Fox On The Prowl, the [subsequent ABC repost](https://thesession.org/tunes/501#comment318354) still contains the misplaced divider. The reviewed comments on the other selected pages did not explicitly locate the corresponding fragment. This curation is an independent proposal; it is not an assertion that the original contributors or The Session have endorsed it.

## Reproduction and checks

Materialize the data tracked by Git LFS, then run the standard-library Python tool from the repository root.

```bash
git lfs pull
python3 tools/apply.py --apply
python3 tools/apply.py
```

The application command accepts a reviewed original or an already corrected setting. An unexpected source edit causes it to stop for review. Files are staged and checked before replacement, and a rerun can finish a partially applied round. Set entries are updated only when both their IDs and their embedded ABC exactly match the reviewed original. Independent set arrangements with different text are retained.

The checker compares every record across the CSV, JSON and SQLite representations of both tunes and sets. It also checks SQLite integrity and matching set copies. The [initial results](checks/initial-data.json) recorded six changed tune rows and 33 matching set copies; all 55,838 settings and 337,510 set entries remained present. Those are the results at the initial commit, before the later notation fixes. A separate comparison with the original SQLite database checked every row of every table and verified that all non-ABC fields and the schema were unchanged; see [initial scope check](checks/initial-scope.json).

[Playback validation](checks/initial-playback.json) uses the unmodified TradMate parser at commit `823fbf4cb5941394d86b5dd476ba46cc6e891f47`, with automatic repairs disabled and neutral asset paths. All six settings retain their pitch and tie sequence. The four barline corrections retain every event's start time and duration. For the two duration corrections, only the reviewed note's duration changes, once on each of two repeat passes; total duration changes by the expected amount. This is a parser-level comparison, not a listening review or proof that all other bars in these settings are error-free.

To reproduce those checks with a local TradMate checkout containing the pinned commit and a standalone Dart SDK:

```bash
python3 tools/check_playback.py --tradmate-repo /path/to/TradMate --dart /path/to/dart
```

Application-specific adjustments for continuous playback between a final bar and an opening pickup are outside the source-correction round. Speculative missing notes or rests require further musical evidence.

## Licensing and attribution

Contains information from [The Session](https://thesession.org/), made available under the [Open Database License](https://opendatacommons.org/licenses/odbl/1-0/). The complete upstream [LICENSE.md](LICENSE.md), including its separate content terms, is retained. This fork continues to distribute the database under ODbL 1.0 and preserves the upstream content terms. Its public files and correction manifest provide the modified data and the complete record of this round's alterations.
