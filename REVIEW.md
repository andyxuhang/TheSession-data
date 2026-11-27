# First curation round

Reviewed on 27 November 2026 by andyxuhang. The upstream baseline is commit `9106aa8e29b72c3affd954f48b259ea02a1fb418` from [adactio/TheSession-data](https://github.com/adactio/TheSession-data).

This round contains six setting corrections across five tunes. Each replacement is limited to a specific source fragment and source-content hash. Original tune IDs, setting IDs, contributor names, dates, composers and other metadata are retained in the data exports. The complete original and corrected ABC for each setting are recorded in [round-001.json](corrections/round-001.json).

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
python3 tools/apply_corrections.py --apply
python3 tools/apply_corrections.py
```

The application command accepts a reviewed original or an already corrected setting. An unexpected source edit causes it to stop for review. Files are staged and checked before replacement, and a rerun can finish a partially applied round. Set entries are updated only when both their IDs and their embedded ABC exactly match the reviewed original. Independent set arrangements with different text are retained.

The checker compares every record across the CSV, JSON and SQLite representations of both tunes and sets. It also checks SQLite integrity, the six corrected settings and matching set copies. Results are stored in [round-001-validation.json](corrections/round-001-validation.json). All 55,838 settings and 337,510 set entries remain present. Exactly six tune rows and 33 matching set copies changed. A separate comparison with the original SQLite database checks every row of every table and verifies that all non-ABC fields and the schema are unchanged; see [scope validation](corrections/round-001-scope-validation.json).

[Playback validation](corrections/round-001-playback-validation.json) uses the unmodified TradMate parser at commit `823fbf4cb5941394d86b5dd476ba46cc6e891f47`, with automatic repairs disabled and neutral asset paths. All six settings retain their pitch and tie sequence. The four barline corrections retain every event's start time and duration. For the two duration corrections, only the reviewed note's duration changes, once on each of two repeat passes; total duration changes by the expected amount. This is a parser-level comparison, not a listening review or proof that all other bars in these settings are error-free.

To reproduce those checks with a local TradMate checkout containing the pinned commit and a standalone Dart SDK:

```bash
python3 tools/verify_playback.py --tradmate-repo /path/to/TradMate --dart /path/to/dart
```

Application-specific adjustments for continuous playback between a final bar and an opening pickup are outside the source-correction round. Speculative missing notes or rests require further musical evidence.

## Licensing and attribution

Contains information from [The Session](https://thesession.org/), made available under the [Open Database License](https://opendatacommons.org/licenses/odbl/1-0/). The complete upstream [LICENSE.md](LICENSE.md), including its separate content terms, is retained. This fork continues to distribute the database under ODbL 1.0 and preserves the upstream content terms. Its public files and correction manifest provide the modified data and the complete record of this round's alterations.
