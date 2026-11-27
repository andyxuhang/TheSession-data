# Database and export integrity

Checked the full repository database against all nine CSV and nine JSON table exports, plus the session GeoJSON. The original seven tables contain 650,105 rows. Including the two new ID tables, all 729,126 rows agree across SQLite, CSV and JSON, including multiplicity and row order.

## Repairs

The original SQLite foreign keys pointed at non-unique tune and setting columns. Multiple transcriptions per tune and composer joins make those columns unsuitable parent keys; SQLite rejected its own foreign-key check with a schema mismatch.

Added `tune_ids` (23,200 unique tune identities) and `setting_ids` (55,821 unique setting identities), with matching CSV and JSON exports. Foreign keys now reference those unique parents. Composite setting/tune references also prevent a valid setting ID from being assigned to the wrong tune. All original source-table values and row IDs were preserved during this structural repair. The separately recorded notation changes remain the only edits to the seven source tables.

Tune [6692](https://thesession.org/tunes/6692) has eleven references: one alias, one popularity row and nine recording entries. Its official API confirms the tune exists but currently has no settings. It therefore belongs in the tune identity table without an invented ABC transcription. The [source evidence](../../checks/relations-source-evidence.json) records the API URL, response hash and verification date, 2026-11-28.

The 63,623 recording entries with an empty optional tune reference retain their original values. Triggers enforce nonempty recording references and protect referenced parent IDs. Other foreign keys use SQLite's normal enforcement; writers must enable `PRAGMA foreign_keys=ON` on their connections.

Restored omitted double quotes in two GeoJSON venue names (session IDs 9603 and 7650), using the matching coordinates and the names shared by SQLite, CSV and JSON. No map coordinates or other feature properties changed. The map's 2,194 locations represent all 2,195 session rows: two entries share one identical name and location.

## Final results

| Check | Result |
| --- | --- |
| SQLite physical integrity | Pass |
| All table exports, headers, values and record counts | Match |
| SQLite foreign-key violations | 0 |
| Missing or mismatched tune/setting references | 0 |
| Conflicting setting identities | 0 |
| Duplicate record keys checked by the audit | 0 |
| Set copies checked against their setting's name, type, meter, mode and ABC | All 337,510 match |
| Missing or extra map locations | 0 |
| Map geometry/property coordinate differences | 0 |

Seventeen additional tune rows come from composer joins. Their non-composer fields agree, and their credits are retained.

## Ordering observations requiring review

There are 1,664 shared `settingorder` values across 1,660 sets, involving 3,937 entries. The [complete list](set-position-observations.csv) includes row IDs, set IDs, setting IDs and official source links. These are observations, not confirmed invalid references: the source does not declare this field unique or contiguous. No set entry was removed or renumbered.

[Set 63950](https://thesession.org/members/163594/sets/63950) has positions 1 and 3, leaving a numeric gap at 2. Its entries still reference valid settings (5696 and 29187). The audit cannot establish whether an entry was removed or whether the exported position is stale.

As a checked example, the official [set 353](https://thesession.org/members/81825/sets/353) contains all five exported settings, in source-row order 284, 322, 3434, 970 and 2050, while the exported position values are 1, 2, 2, 3 and 4. This supports retaining the entries; it does not establish the author's intended numbering for every affected set. Determining a new order requires additional authoritative evidence.

## Evidence and repeatable checks

The repository does not export a member table. Its 11,734 distinct set-owner IDs therefore cannot be checked against a local parent table, and their current website existence was not verified individually. The [external member list](external-members.csv) provides every ID and source link. This is a coverage limit, not a finding that those members are missing. Contributor usernames, artist names and other free-text credits likewise have no separately exported identity table. The zero unresolved-reference result applies to the tune and setting relationships represented by this dataset.

- [Machine-readable results](summary.json)
- [Unresolved reference findings](reference-problems.jsonl) (empty after repair)
- [Set copy differences](set-copy-differences.jsonl) (empty)
- [Schema and exact preservation checks](../../checks/database-relations.json)
- [Full upstream scope comparison](../../checks/scope.json)
- [Byte-identical schema repair reapplication](../../checks/database-relations-reapply.json)

```bash
python3 tools/database_relations.py
python3 tools/audit_database.py
python3 tools/check_scope.py
```

`database_relations.py --apply` performs the recorded schema and GeoJSON repair when needed. A second run makes no changes. The integrity audit exits unsuccessfully on broken references, mismatched exports or other structural failures and retains its findings. Ordering observations remain available for review without blocking the structural checks.
