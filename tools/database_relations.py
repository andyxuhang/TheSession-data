#!/usr/bin/env python3
"""Build unique ID parents while preserving the original seven data tables."""

import argparse
import csv
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from apply import json_records, record_digest
from scan import ROOT, sha


TABLES = ('aliases','events','recordings','sessions','sets','tune_popularity','tunes')
PARENTS = {
    'tune_ids':'CREATE TABLE tune_ids (tune_id TEXT PRIMARY KEY NOT NULL)',
    'setting_ids':'''CREATE TABLE setting_ids (
        setting_id TEXT PRIMARY KEY NOT NULL,
        tune_id TEXT NOT NULL REFERENCES tune_ids(tune_id),
        UNIQUE(setting_id,tune_id))''',
}
TRIGGERS = {
    'recordings_tune_insert':'''CREATE TRIGGER recordings_tune_insert BEFORE INSERT ON recordings
        WHEN NEW.tune_id IS NOT NULL AND NEW.tune_id <> ''
        AND NOT EXISTS (SELECT 1 FROM tune_ids WHERE tune_id=NEW.tune_id)
        BEGIN SELECT RAISE(ABORT,'Unknown recording tune_id'); END''',
    'recordings_tune_update':'''CREATE TRIGGER recordings_tune_update BEFORE UPDATE OF tune_id ON recordings
        WHEN NEW.tune_id IS NOT NULL AND NEW.tune_id <> ''
        AND NOT EXISTS (SELECT 1 FROM tune_ids WHERE tune_id=NEW.tune_id)
        BEGIN SELECT RAISE(ABORT,'Unknown recording tune_id'); END''',
    'tune_ids_recordings_delete':'''CREATE TRIGGER tune_ids_recordings_delete BEFORE DELETE ON tune_ids
        WHEN EXISTS (SELECT 1 FROM recordings WHERE tune_id=OLD.tune_id AND tune_id <> '')
        BEGIN SELECT RAISE(ABORT,'Tune is referenced by recordings'); END''',
    'tune_ids_recordings_update':'''CREATE TRIGGER tune_ids_recordings_update BEFORE UPDATE OF tune_id ON tune_ids
        WHEN NEW.tune_id <> OLD.tune_id
        AND EXISTS (SELECT 1 FROM recordings WHERE tune_id=OLD.tune_id AND tune_id <> '')
        BEGIN SELECT RAISE(ABORT,'Tune is referenced by recordings'); END''',
}


def schema_rows(db):
    return [list(row) for row in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]


def open_database(path):
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    db.row_factory = sqlite3.Row
    return db


def parent_rows(db):
    evidence = json.loads((ROOT/'checks/relations-source-evidence.json').read_text())
    tunes = {row[0] for row in db.execute('SELECT DISTINCT tune_id FROM tunes')}
    for item in evidence['verified_empty_tunes']:
        if item['settings_count'] != 0 or item['http_status'] != 200:
            raise ValueError('Unverified tune identity')
        tunes.add(item['tune_id'])
    settings = {}
    for sid,tid in db.execute('SELECT DISTINCT setting_id,tune_id FROM tunes'):
        if sid in settings and settings[sid] != tid:
            raise ValueError('A setting references multiple tune identities')
        settings[sid]=tid
    return {
        'tune_ids':[dict(tune_id=tid) for tid in sorted(tunes,key=int)],
        'setting_ids':[dict(setting_id=sid,tune_id=settings[sid]) for sid in sorted(settings,key=int)],
    }


def verify_relations(db):
    expected = parent_rows(db)
    for name,records in expected.items():
        if record_digest(db.execute('SELECT * FROM '+name+' ORDER BY rowid')) != record_digest(records):
            raise ValueError('Derived ID parent differs from its source: '+name)
    problems = list(db.execute('PRAGMA foreign_key_check'))
    if problems:
        raise ValueError('Foreign-key violations: '+str(len(problems)))
    missing = db.execute("""SELECT count(*) FROM recordings r
        LEFT JOIN tune_ids t ON r.tune_id=t.tune_id
        WHERE r.tune_id IS NOT NULL AND r.tune_id<>'' AND t.tune_id IS NULL""").fetchone()[0]
    if missing:
        raise ValueError('Unresolved recording tune references')
    trigger_names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    if not set(TRIGGERS) <= trigger_names:
        raise ValueError('Optional recording-reference guards are missing')
    return dict(tune_ids=len(expected['tune_ids']),setting_ids=len(expected['setting_ids']),
                foreign_key_violations=0,unresolved_recording_references=0)


def helper_exports_match(expected):
    for table,records in expected.items():
        csv_path,json_path = ROOT/'csv'/f'{table}.csv',ROOT/'json'/f'{table}.json'
        if not csv_path.exists() or not json_path.exists():
            return False
        with csv_path.open(newline='') as stream:
            if record_digest(csv.DictReader(stream)) != record_digest(records):
                return False
        if record_digest(json_records(json_path)) != record_digest(records):
            return False
    return True


def geojson_name_edits(db):
    path = ROOT/'json/sessions.geojson'
    text = path.read_text()
    document = json.loads(text)
    by_coordinate = {}
    for row in db.execute('SELECT id,name,longitude,latitude FROM sessions'):
        key = (float(row['longitude']),float(row['latitude']))
        by_coordinate.setdefault(key,[]).append(dict(row))
    names = list(re.finditer(r'"name"\s*:\s*("(?:[^"\\]|\\.)*")',text))
    if len(names)!=len(document['features']):
        raise ValueError('Unexpected GeoJSON name layout')
    edits = []
    for i,feature in enumerate(document['features']):
        rows = by_coordinate.get(tuple(feature['geometry']['coordinates']),[])
        canonical = {row['name'] for row in rows}
        current = feature['properties']['name']
        if current in canonical or len(canonical)!=1:
            continue
        corrected = next(iter(canonical))
        if current != corrected.replace('"',''):
            continue
        token = names[i]
        if json.loads(token[1]) != current:
            raise ValueError('GeoJSON feature offset differs')
        edits.append(dict(feature_index=i,session_ids=sorted(row['id'] for row in rows),
                          before=current,after=corrected,start=token.start(1),end=token.end(1)))
    after = text
    for edit in reversed(edits):
        after = after[:edit['start']]+json.dumps(edit['after'],ensure_ascii=False)+after[edit['end']:]
    expected = json.loads(text)
    for edit in edits:
        expected['features'][edit['feature_index']]['properties']['name']=edit['after']
    if json.loads(after)!=expected:
        raise ValueError('Unexpected GeoJSON changes')
    return after,edits


def fixed_schema(sql,table):
    if table=='recordings':
        return sql.replace(' REFERENCES [tunes]([tune_id])','')
    sql = sql.replace('REFERENCES [tunes]([tune_id])','REFERENCES [tune_ids]([tune_id])')
    sql = sql.replace('REFERENCES [tunes]([setting_id])','REFERENCES [setting_ids]([setting_id])')
    if table in ('tunes','sets'):
        at = sql.rfind(')')
        sql = sql[:at]+',\n FOREIGN KEY(setting_id,tune_id) REFERENCES setting_ids(setting_id,tune_id)\n'+sql[at:]
    return sql


def write_parent_exports(stage,parents):
    for table,records in parents.items():
        csv_path,json_path = stage/'csv'/f'{table}.csv',stage/'json'/f'{table}.json'
        csv_path.parent.mkdir(parents=True,exist_ok=True)
        json_path.parent.mkdir(parents=True,exist_ok=True)
        with csv_path.open('w',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=list(records[0]),lineterminator='\n')
            writer.writeheader()
            writer.writerows(records)
        json_path.write_text('[\n'+',\n'.join(json.dumps(row) for row in records)+'\n]\n')


def publish(stage,names):
    backups = stage/'backups'
    backups.mkdir()
    published = []
    try:
        for index,name in enumerate(names):
            target = ROOT/name
            backup = backups/str(index)
            if target.exists():
                os.link(target,backup)
            target.parent.mkdir(parents=True,exist_ok=True)
            os.replace(stage/name,target)
            published.append((target,backup))
    except BaseException:
        for target,backup in reversed(published):
            if backup.exists():
                os.replace(backup,target)
            else:
                target.unlink()
        raise


def repair():
    manifest_path = ROOT/'checks/database-relations.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    with open_database(ROOT/'thesession.db') as source:
        parents = parent_rows(source)
        geo_text,geo_edits = geojson_name_edits(source)
        if previous and schema_rows(source)==previous['after_schema']:
            try:
                verification = verify_relations(source)
                if helper_exports_match(parents) and not geo_edits:
                    return dict(changed=False,verification=verification)
            except ValueError:
                pass
        current_schema = schema_rows(source)
        if previous and current_schema not in (previous['before_schema'],previous['after_schema']):
            raise ValueError('Unrecognized schema change')
        before_schema = previous['before_schema'] if previous else current_schema
        if any(row[0]!='table' for row in before_schema):
            raise ValueError('Source schema contains objects requiring separate preservation')
        original_sql = {row[1]:row[3] for row in before_schema if row[0]=='table'}
        if set(original_sql)!=set(TABLES):
            raise ValueError('Unexpected source tables')
        before_data = {table:record_digest(source.execute('SELECT * FROM '+table+' ORDER BY rowid'))
                       for table in TABLES}
        with tempfile.TemporaryDirectory(prefix='.relations-',dir=ROOT) as temporary:
            stage = Path(temporary)
            with sqlite3.connect(stage/'thesession.db') as destination:
                destination.row_factory=sqlite3.Row
                destination.execute('PRAGMA foreign_keys=ON')
                for sql in PARENTS.values():
                    destination.execute(sql)
                for table,records in parents.items():
                    columns=list(records[0])
                    destination.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in columns)+')',
                        [tuple(row[c] for c in columns) for row in records])
                for table in TABLES:
                    destination.execute(fixed_schema(original_sql[table],table))
                    columns=[r[1] for r in source.execute('PRAGMA table_info('+table+')')]
                    names='rowid,'+','.join('"'+c+'"' for c in columns)
                    query='INSERT INTO '+table+' ('+names+') VALUES ('+','.join('?' for _ in range(len(columns)+1))+')'
                    destination.executemany(query,source.execute('SELECT '+names+' FROM '+table+' ORDER BY rowid'))
                for sql in TRIGGERS.values():
                    destination.execute(sql)
                for table in TABLES:
                    if record_digest(destination.execute('SELECT * FROM '+table+' ORDER BY rowid'))!=before_data[table]:
                        raise ValueError('Source data changed during schema repair: '+table)
                verification=verify_relations(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise ValueError('SQLite integrity check failed')
                after_schema=schema_rows(destination)
            destination.close()
            write_parent_exports(stage,parents)
            names=[f'{folder}/{table}.{suffix}' for table in parents
                   for folder,suffix in (('csv','csv'),('json','json'))]
            if geo_edits:
                (stage/'json/sessions.geojson').write_text(geo_text)
                names.append('json/sessions.geojson')
            manifest=dict(before_schema=before_schema,after_schema=after_schema,
                          source_tables_preserved=before_data,verification=verification,
                          geojson_name_edits=(previous.get('geojson_name_edits',[]) if previous else [])+geo_edits)
            (stage/'checks').mkdir()
            (stage/'checks/database-relations.json').write_text(json.dumps(manifest,indent=2)+'\n')
            names.extend(['checks/database-relations.json','thesession.db'])
            publish(stage,names)
    return dict(changed=True,verification=verification,geojson_names_corrected=len(geo_edits))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.apply:
        result=repair()
    else:
        with open_database(ROOT/'thesession.db') as db:
            result=verify_relations(db)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
