#!/usr/bin/env python3
"""Apply the reviewed, exact-source round to each matching data representation."""

import argparse
import csv
import filecmp
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ABC_VALUE = re.compile(r'("abc"\s*:\s*)("(?:[^"\\]|\\.)*")')


def read_plan(files=None):
    files = files or sorted((ROOT / "changes").glob("*.json"))
    items = [item for path in files for item in json.loads(path.read_text())["corrections"]]
    patches = {}
    for item in items:
        for side in ("before", "after"):
            actual = hashlib.sha256(item[side + "_abc"].encode()).hexdigest()
            if actual != item[side + "_sha256"]:
                raise ValueError("Correction plan content/hash mismatch")
        if "replace" in item:
            edit = item["replace"]
            if item["before_abc"].count(edit["before"]) != edit["count"]:
                raise ValueError("Unexpected number of reviewed source fragments")
            corrected = item["before_abc"].replace(edit["before"], edit["after"])
        else:
            corrected = item["before_abc"]
            boundary = len(corrected) + 1
            for edit in sorted(item["edits"], key=lambda e: (e["start"], e["end"]), reverse=True):
                start, end = edit["start"], edit["end"]
                if not 0 <= start <= end <= len(item["before_abc"]) or end > boundary:
                    raise ValueError("Invalid or overlapping source edits")
                corrected = corrected[:start] + edit["text"] + corrected[end:]
                boundary = start
        if corrected != item["after_abc"]:
            raise ValueError("Correction differs from its reviewed replacement")
        sid = item['setting_id']
        states = list(item.get('source_states', [item['before_abc']]))
        if sid in patches:
            old = patches[sid]
            if old['tune_id'] != item['tune_id'] or old['after_abc'] != item['before_abc']:
                raise ValueError('Conflicting correction history for '+sid)
            states = old['source_states'] + [old['after_abc']] + states
        patches[sid] = {**item, 'source_states':list(dict.fromkeys(states))}
    return files, patches


def replacement(row, patches, strict):
    patch = patches.get(row["setting_id"])
    if patch is None:
        return None
    if row["tune_id"] != patch["tune_id"]:
        raise ValueError("Setting/tune identity mismatch")
    if row["abc"] == patch["after_abc"]:
        return None
    if row["abc"] in patch["source_states"]:
        return patch["after_abc"]
    if strict:
        raise ValueError("Source changed since review for setting " + row["setting_id"])
    # Set entries with another text can be independent snapshots or arrangements.
    return None


class RecordLines:
    def __init__(self, stream):
        self.stream = iter(stream)
        self.consumed = []

    def __iter__(self):
        return self

    def __next__(self):
        line = next(self.stream)
        self.consumed.append(line)
        return line

    def take_record(self):
        value = "".join(self.consumed)
        self.consumed.clear()
        return value


def field_spans(record):
    positions = []
    start = 0
    index = 0
    quoted = False
    while index < len(record):
        char = record[index]
        if char == '"':
            if quoted and index + 1 < len(record) and record[index + 1] == '"':
                index += 2
                continue
            quoted = not quoted
        elif char == "," and not quoted:
            positions.append((start, index))
            start = index + 1
        index += 1
    end = len(record.rstrip("\r\n"))
    positions.append((start, end))
    return positions


def patch_csv(source, target, patches, strict):
    changed = 0
    with source.open(newline="") as stream, target.open("w", newline="") as output:
        lines = RecordLines(stream)
        reader = csv.reader(lines)
        columns = next(reader)
        output.write(lines.take_record())
        abc_index = columns.index("abc")
        for values in reader:
            record = lines.take_record()
            row = dict(zip(columns, values))
            corrected = replacement(row, patches, strict)
            if corrected is not None:
                start, end = field_spans(record)[abc_index]
                encoded = '"' + corrected.replace('"', '""') + '"'
                record = record[:start] + encoded + record[end:]
                changed += 1
            output.write(record)
    return changed


def json_records(path):
    with path.open(newline="") as stream:
        for line in stream:
            stripped = line.strip().rstrip(",")
            if not stripped or stripped in ("[", "]"):
                continue
            yield json.loads(stripped)


def patch_json(source, target, patches, strict):
    changed = 0
    with source.open(newline="") as stream, target.open("w", newline="") as output:
        for line in stream:
            stripped = line.strip().rstrip(",")
            if stripped and stripped not in ("[", "]"):
                row = json.loads(stripped)
                corrected = replacement(row, patches, strict)
                if corrected is not None:
                    matches = list(ABC_VALUE.finditer(line))
                    if len(matches) != 1:
                        raise ValueError("Expected exactly one ABC field per JSON record")
                    match = matches[0]
                    if json.loads(match[2]) != row["abc"]:
                        raise ValueError("JSON ABC token does not match its record")
                    line = line[:match.start(2)] + json.dumps(corrected, ensure_ascii=False) + line[match.end(2):]
                    changed += 1
            output.write(line)
    return changed


def patch_sqlite(source, target, patches):
    if source.stat().st_size < 1000:
        raise ValueError("Materialize thesession.db with Git LFS first")
    shutil.copyfile(source, target)
    changes = {}
    with sqlite3.connect(str(target)) as db:
        db.row_factory = sqlite3.Row
        for table in ("tunes", "sets"):
            changed = 0
            rows = db.execute("SELECT rowid AS _rowid_,* FROM " + table + " WHERE setting_id IN ("+
                              ",".join("?" for _ in patches)+")", tuple(patches)).fetchall()
            if table == "tunes" and {row['setting_id'] for row in rows} != patches.keys():
                raise ValueError("Setting missing in SQLite")
            for row in rows:
                patch = patches[row["setting_id"]]
                if replacement(row, patches, table == "tunes") is None:
                    continue
                result = db.execute(
                    "UPDATE " + table + " SET abc=? WHERE rowid=?",
                    (patch["after_abc"], row["_rowid_"]),
                )
                changed += result.rowcount
            changes[table] = changed
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite quick_check failed")
        if (ROOT/'checks/database-relations.json').exists():
            from database_relations import verify_relations
            verify_relations(db)
    return changes


def record_digest(rows):
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        digest.update(json.dumps(dict(row), ensure_ascii=False, sort_keys=True).encode())
        digest.update(b"\n")
        count += 1
    return {"rows": count, "semantic_sha256": digest.hexdigest()}


def verify(paths, patches):
    results = {}
    with sqlite3.connect(paths["thesession.db"].resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        db.row_factory = sqlite3.Row
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite quick_check failed")
        if (ROOT/'checks/database-relations.json').exists():
            from database_relations import verify_relations
            results['relations'] = verify_relations(db)
        for table in ("tunes", "sets"):
            with paths["csv/" + table + ".csv"].open(newline="") as stream:
                csv_digest = record_digest(csv.DictReader(stream))
            json_digest = record_digest(json_records(paths["json/" + table + ".json"]))
            sql_digest = record_digest(db.execute("SELECT * FROM " + table + " ORDER BY rowid"))
            if csv_digest != json_digest or csv_digest != sql_digest:
                raise ValueError("Representations differ for " + table)
            results[table] = csv_digest
        selected = " WHERE setting_id IN (" + ",".join("?" for _ in patches) + ")"
        tune_rows = db.execute("SELECT * FROM tunes" + selected, tuple(patches)).fetchall()
        if {row['setting_id'] for row in tune_rows} != patches.keys():
            raise ValueError("Setting missing")
        for row in tune_rows:
            patch = patches[row["setting_id"]]
            if row["abc"] != patch["after_abc"]:
                raise ValueError("Reviewed setting is not corrected")
        for row in db.execute("SELECT * FROM sets" + selected, tuple(patches)):
            if row["abc"] in patches[row["setting_id"]]["source_states"]:
                raise ValueError("An exact matching set copy is still uncorrected")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply reviewed replacements, then verify")
    parser.add_argument("--plan", type=Path, action="append", help="Use an explicit change file (repeatable)")
    args = parser.parse_args()
    files, patches = read_plan(args.plan)
    names = ["csv/tunes.csv", "json/tunes.json", "csv/sets.csv", "json/sets.json", "thesession.db"]
    paths = {name: ROOT / name for name in names}
    if args.apply:
        with tempfile.TemporaryDirectory(prefix=".curation-", dir=ROOT) as temporary:
            stage = Path(temporary)
            staged = {name: stage / name for name in names}
            for path in staged.values():
                path.parent.mkdir(parents=True, exist_ok=True)
            changed = {}
            for table in ("tunes", "sets"):
                strict = table == "tunes"
                for extension, patcher in (("csv", patch_csv), ("json", patch_json)):
                    name = extension + "/" + table + "." + extension
                    changed[name] = patcher(paths[name], staged[name], patches, strict)
            changed["thesession.db"] = patch_sqlite(paths["thesession.db"], staged["thesession.db"], patches)
            result = verify(staged, patches)
            for name in names:
                if not filecmp.cmp(staged[name], paths[name], shallow=False):
                    staged[name].replace(paths[name])
            print(json.dumps({"updated_records": changed, "verified": result}, indent=2))
    else:
        result = verify(paths, patches)
        print(json.dumps({"verified": result, "change_files": [p.name for p in files]}, indent=2))


if __name__ == "__main__":
    main()
