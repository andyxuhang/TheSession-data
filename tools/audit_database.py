#!/usr/bin/env python3
"""Audit all SQLite tables, CSV/JSON exports, references and map features."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from apply import json_records, record_digest
from database_relations import TABLES, open_database, verify_relations
from scan import ROOT


def normalized(records):
    for row in records:
        yield {key:'' if value is None else str(value) for key,value in dict(row).items()}


def csv_rows(path):
    with path.open(newline='',encoding='utf-8-sig') as stream:
        yield from csv.DictReader(stream)


def row_counts(records):
    return Counter(json.dumps(row,sort_keys=True,ensure_ascii=False) for row in normalized(records))


def audit(output):
    output.mkdir(parents=True,exist_ok=True)
    findings = []
    with open_database(ROOT/'thesession.db') as db:
        integrity = [row[0] for row in db.execute('PRAGMA integrity_check')]
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        exports = {}
        for table in tables:
            csv_path,json_path = ROOT/'csv'/f'{table}.csv',ROOT/'json'/f'{table}.json'
            columns = [row[1] for row in db.execute('PRAGMA table_info('+table+')')]
            if not csv_path.exists() or not json_path.exists():
                exports[table]=dict(missing_exports=True)
                continue
            with csv_path.open(newline='',encoding='utf-8-sig') as stream:
                csv_columns=csv.DictReader(stream).fieldnames
            first=next(json_records(json_path),{})
            digests = {
                'csv':record_digest(normalized(csv_rows(csv_path))),
                'json':record_digest(normalized(json_records(json_path))),
                'sqlite':record_digest(normalized(db.execute('SELECT * FROM '+table+' ORDER BY rowid'))),
            }
            ordered_equal = len({json.dumps(value,sort_keys=True) for value in digests.values()})==1
            logical_equal = ordered_equal
            if not ordered_equal:
                counts = row_counts(db.execute('SELECT * FROM '+table))
                logical_equal = counts==row_counts(csv_rows(csv_path))==row_counts(json_records(json_path))
            exports[table]=dict(rows=digests['sqlite']['rows'],columns=columns,
                headers_equal=set(columns)==set(csv_columns)==set(first),
                ordered_equal=ordered_equal,logical_equal=logical_equal,digests=digests)
        tunes = {row[0] for row in db.execute('SELECT DISTINCT tune_id FROM tunes')}
        parents = {row[0] for row in db.execute('SELECT tune_id FROM tune_ids')} if 'tune_ids' in tables else tunes
        settings = defaultdict(set)
        setting_variants = defaultdict(list)
        for row in db.execute('SELECT rowid,* FROM tunes'):
            settings[row['setting_id']].add(row['tune_id'])
            setting_variants[row['setting_id']].append(dict(row))
        for table in ('aliases','tune_popularity','recordings','sets'):
            for row in db.execute('SELECT rowid,* FROM '+table):
                tid=row['tune_id']
                if tid and tid not in parents:
                    findings.append(dict(kind='missing_tune_parent',table=table,rowid=row['rowid'],tune_id=tid))
                if table=='sets':
                    sid=row['setting_id']
                    if sid not in settings:
                        findings.append(dict(kind='missing_setting_parent',table=table,rowid=row['rowid'],
                                             tuneset=row['tuneset'],setting_id=sid))
                    elif tid not in settings[sid]:
                        findings.append(dict(kind='setting_tune_mismatch',table=table,rowid=row['rowid'],
                                             tuneset=row['tuneset'],setting_id=sid,tune_id=tid))
        identity_conflicts = []
        for sid,versions in setting_variants.items():
            comparable={json.dumps({k:v for k,v in row.items() if k not in ('rowid','composer')},sort_keys=True)
                        for row in versions}
            if len(comparable)>1:
                identity_conflicts.append(dict(setting_id=sid,rowids=[r['rowid'] for r in versions]))
        copy_fields = ('name','type','meter','mode','abc')
        copy_differences = []
        for row in db.execute('SELECT rowid,* FROM sets ORDER BY rowid'):
            versions = setting_variants.get(row['setting_id'],[])
            if versions:
                different = [field for field in copy_fields if row[field]!=versions[0][field]]
                if different:
                    copy_differences.append(dict(rowid=row['rowid'],tuneset=row['tuneset'],
                        setting_id=row['setting_id'],fields=different))
        keys = dict(events=('id',),sessions=('id',),aliases=('tune_id','alias'),
                    tune_popularity=('tune_id',),recordings=('id','track','number'),
                    sets=('tuneset','settingorder','setting_id'))
        duplicate_keys = {}
        for table,columns in keys.items():
            query='SELECT count(*) AS n FROM '+table+' GROUP BY '+','.join(columns)+' HAVING count(*)>1'
            duplicates=[row[0] for row in db.execute(query)]
            duplicate_keys[table]=dict(key=columns,duplicate_groups=len(duplicates),rows=sum(duplicates))
        set_positions = defaultdict(list)
        set_orders = defaultdict(set)
        set_owners = defaultdict(set)
        for row in db.execute('SELECT rowid,tuneset,settingorder,tune_id,setting_id,member_id FROM sets ORDER BY rowid'):
            set_positions[row['tuneset'],row['settingorder']].append(dict(row))
            set_orders[row['tuneset']].add(int(row['settingorder']))
            set_owners[row['tuneset']].add(row['member_id'])
        collisions = [rows for rows in set_positions.values() if len(rows)>1]
        position_rows = []
        for group in collisions:
            for row in group:
                position_rows.append({**row,'entries_at_position':len(group),
                    'source_url':f"https://thesession.org/members/{row['member_id']}/sets/{row['tuneset']}"})
        gaps = []
        for sid,positions in set_orders.items():
            ordered=sorted(positions)
            missing=sorted(set(range(ordered[0],ordered[-1]+1))-positions)
            if missing:
                gaps.append(dict(tuneset=sid,positions=ordered,missing_values=missing))
        external_members = [dict(member_id=row[0],set_count=row[1],
            source_url=f'https://thesession.org/members/{row[0]}')
            for row in db.execute('SELECT member_id,count(DISTINCT tuneset) FROM sets GROUP BY member_id')]
        try:
            foreign_check=[list(row) for row in db.execute('PRAGMA foreign_key_check')]
        except sqlite3.OperationalError as error:
            foreign_check=str(error)
        derived=verify_relations(db) if 'tune_ids' in tables else None
        session_points=defaultdict(list)
        for row in db.execute('SELECT id,name,longitude,latitude FROM sessions'):
            if row['longitude'] and row['latitude']:
                key=(row['name'],Decimal(row['longitude']),Decimal(row['latitude']))
                session_points[key].append(row['id'])
        geo=json.loads((ROOT/'json/sessions.geojson').read_text())
        actual=Counter()
        geometry_conflicts=[]
        for i,feature in enumerate(geo['features']):
            name=feature['properties']['name']
            lon,lat=map(lambda value:Decimal(str(value)),feature['geometry']['coordinates'])
            actual[name,lon,lat]+=1
            prop=feature['properties']
            if (lon,lat)!=(Decimal(str(prop['longitude'])),Decimal(str(prop['latitude']))):
                geometry_conflicts.append(i)
        expected=Counter({key:1 for key in session_points})
        missing_map=[dict(session_ids=session_points[key],count=count) for key,count in (expected-actual).items()]
        extra_map=sum((actual-expected).values())
        result=dict(integrity_check=integrity,tables=exports,
            all_exports_equal=all(row.get('logical_equal') and row.get('headers_equal') for row in exports.values()),
            foreign_key_check=foreign_check,derived_id_verification=derived,
            missing_or_mismatched_references=len(findings),setting_identity_conflicts=identity_conflicts,
            set_copy_comparison=dict(rows_checked=db.execute('SELECT count(*) FROM sets').fetchone()[0],
                fields=copy_fields,differing_rows=len(copy_differences)),
            duplicate_record_keys=duplicate_keys,
            composer_join_extra_rows=sum(len(v)-1 for v in setting_variants.values()),
            optional_unlinked_recordings=db.execute("SELECT count(*) FROM recordings WHERE tune_id='' OR tune_id IS NULL").fetchone()[0],
            external_reference_limits=dict(member_table_exported=False,
                distinct_set_member_ids=len(external_members),website_existence_checked=False),
            set_position_observations=dict(shared_values=len(collisions),rows=len(position_rows),
                affected_sets=len({group[0]['tuneset'] for group in collisions}),gaps=gaps,
                owner_conflicts=[sid for sid,owners in set_owners.items() if len(owners)>1]),
            geojson=dict(features=len(geo['features']),unique_session_locations=len(expected),
                shared_locations=sum(len(ids)>1 for ids in session_points.values()),
                missing_points=missing_map,extra_points=extra_map,geometry_property_conflicts=geometry_conflicts))
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    with (output/'reference-problems.jsonl').open('w') as stream:
        for row in findings:
            stream.write(json.dumps(row)+'\n')
    with (output/'set-copy-differences.jsonl').open('w') as stream:
        for row in copy_differences:
            stream.write(json.dumps(row)+'\n')
    with (output/'external-members.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['member_id','set_count','source_url'],lineterminator='\n')
        writer.writeheader()
        writer.writerows(external_members)
    with (output/'set-position-observations.csv').open('w',newline='') as stream:
        columns=['rowid','tuneset','settingorder','tune_id','setting_id','member_id','entries_at_position','source_url']
        writer=csv.DictWriter(stream,fieldnames=columns,lineterminator='\n')
        writer.writeheader()
        writer.writerows(position_rows)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/database-integrity')
    args=parser.parse_args()
    result=audit(args.output)
    print(json.dumps({key:value for key,value in result.items() if key!='tables'},indent=2))
    if (result['integrity_check']!=['ok'] or not result['all_exports_equal']
        or result['foreign_key_check'] or result['missing_or_mismatched_references']
        or result['setting_identity_conflicts']
        or any(row['duplicate_groups'] for row in result['duplicate_record_keys'].values())
        or result['geojson']['missing_points'] or result['geojson']['extra_points']
        or result['geojson']['geometry_property_conflicts']):
        raise SystemExit('Unresolved integrity errors; see the audit report')


if __name__=='__main__':
    main()
