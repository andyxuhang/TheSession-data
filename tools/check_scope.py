#!/usr/bin/env python3
"""Compare every database row with the upstream snapshot in local Git LFS."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
import subprocess

from scan import ROOT
from database_relations import verify_relations

BASE = '9106aa8e29b72c3affd954f48b259ea02a1fb418'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-db',type=Path)
    args=parser.parse_args()
    pointer=subprocess.check_output(['git','show',BASE+':thesession.db'],cwd=ROOT,text=True)
    oid=next(line.split(':',1)[1] for line in pointer.splitlines() if line.startswith('oid sha256:'))
    source=args.baseline_db or ROOT/'.git/lfs/objects'/oid[:2]/oid[2:4]/oid
    digest=hashlib.sha256()
    with source.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            digest.update(block)
    if digest.hexdigest()!=oid:
        raise ValueError('Baseline database differs from its Git LFS hash')
    patches={}
    for file in sorted((ROOT/'changes').glob('*.json')):
        for patch in json.loads(file.read_text())['corrections']:
            sid=patch['setting_id']
            old=patches.get(sid)
            if old:
                assert old['after_abc']==patch['before_abc']
                patch={**patch,'before_abc':old['before_abc']}
            patches[sid]=patch
    report={'baseline_commit':BASE,'baseline_database_sha256':oid,'tables':{}}
    def open_db(path):
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        db.row_factory=sqlite3.Row
        return db
    changed_ids=set()
    with open_db(source) as a,open_db(ROOT/'thesession.db') as b:
        schema='SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'
        before_schema=[list(row) for row in a.execute(schema)]
        after_schema=[list(row) for row in b.execute(schema)]
        relation_path=ROOT/'checks/database-relations.json'
        if relation_path.exists():
            relations=json.loads(relation_path.read_text())
            assert before_schema==relations['before_schema'], 'Unexpected upstream schema'
            assert after_schema==relations['after_schema'], 'Unrecorded schema change'
            report['schema_changes_verified']=True
            report['derived_id_tables']=verify_relations(b)
        else:
            assert before_schema==after_schema, 'Schema changed'
        for (table,) in a.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            changed=0;count=0
            for ra,rb in itertools.zip_longest(a.execute('SELECT rowid AS _rowid_,* FROM '+table+' ORDER BY rowid'),
                                             b.execute('SELECT rowid AS _rowid_,* FROM '+table+' ORDER BY rowid')):
                assert ra is not None and rb is not None, 'Row count changed'
                assert ra['_rowid_']==rb['_rowid_'], 'Source row ID changed'
                count+=1
                if tuple(ra)!=tuple(rb):
                    assert table in ('tunes','sets'), 'Unrelated table changed'
                    patch=patches[ra['setting_id']]
                    assert ra['tune_id']==patch['tune_id'] and ra['abc']==patch['before_abc'] and rb['abc']==patch['after_abc']
                    assert {k:ra[k] for k in ra.keys() if k!='abc'}=={k:rb[k] for k in rb.keys() if k!='abc'}, 'Metadata changed'
                    changed+=1
                    if table=='tunes':changed_ids.add(ra['setting_id'])
            report['tables'][table]={'rows':count,'changed_records':changed,
                                    'non_abc_fields_unchanged':True,'rowids_unchanged':True}
    assert changed_ids==set(patches), 'Correction plan and changed records differ'
    report['schema_unchanged']=before_schema==after_schema
    license_sha=subprocess.check_output(['git','hash-object','LICENSE.md'],cwd=ROOT,text=True).strip()
    assert license_sha==subprocess.check_output(['git','rev-parse',BASE+':LICENSE.md'],cwd=ROOT,text=True).strip()
    report['upstream_license_blob_sha1']=license_sha
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
