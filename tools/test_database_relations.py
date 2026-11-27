import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import database_relations as relations


class DatabaseRelationTests(unittest.TestCase):
    def database(self):
        db=sqlite3.connect(':memory:')
        db.execute('PRAGMA foreign_keys=ON')
        for sql in relations.PARENTS.values():
            db.execute(sql)
        db.execute("INSERT INTO tune_ids VALUES ('1')")
        db.execute("INSERT INTO tune_ids VALUES ('2')")
        db.execute("INSERT INTO setting_ids VALUES ('10','1')")
        db.execute('CREATE TABLE recordings (tune_id TEXT)')
        for sql in relations.TRIGGERS.values():
            db.execute(sql)
        return db

    def test_optional_recording_refs_and_parent_protection(self):
        with self.database() as db:
            db.executemany('INSERT INTO recordings VALUES (?)',[('',),(None,),('1',)])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO recordings VALUES ('999')")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE recordings SET tune_id='999' WHERE tune_id='1'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM tune_ids WHERE tune_id='1'")
            self.assertEqual(db.execute('SELECT count(*) FROM recordings').fetchone()[0],3)

    def test_setting_and_tune_must_form_a_valid_pair(self):
        with self.database() as db:
            db.execute('''CREATE TABLE sets (setting_id TEXT,tune_id TEXT,
                FOREIGN KEY(setting_id,tune_id) REFERENCES setting_ids(setting_id,tune_id))''')
            db.execute("INSERT INTO sets VALUES ('10','1')")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO sets VALUES ('10','2')")

    def test_geojson_name_fix_preserves_geometry(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            (root/'json').mkdir()
            document=dict(type='FeatureCollection',features=[dict(type='Feature',
                geometry=dict(type='Point',coordinates=[1.5,2.5]),
                properties=dict(name='The Venue',longitude=1.5,latitude=2.5))])
            (root/'json/sessions.geojson').write_text(json.dumps(document))
            with sqlite3.connect(':memory:') as db:
                db.row_factory=sqlite3.Row
                db.execute('CREATE TABLE sessions (id TEXT,name TEXT,longitude TEXT,latitude TEXT)')
                db.execute('INSERT INTO sessions VALUES (?,?,?,?)',('1','The "Venue"','1.5','2.5'))
                with patch.object(relations,'ROOT',root):
                    text,edits=relations.geojson_name_edits(db)
            self.assertEqual(len(edits),1)
            corrected=json.loads(text)
            self.assertEqual(corrected['features'][0]['geometry'],document['features'][0]['geometry'])
            self.assertEqual(corrected['features'][0]['properties']['name'],'The "Venue"')

    def test_publish_rolls_back_a_partial_failure(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            stage=root/'stage'
            stage.mkdir()
            for name in ('one','two'):
                (root/name).write_text('old '+name)
                (stage/name).write_text('new '+name)
            real_replace=relations.os.replace
            count=0
            def replace(source,target):
                nonlocal count
                count+=1
                if count==2:
                    raise OSError('Simulated publication failure')
                return real_replace(source,target)
            with patch.object(relations,'ROOT',root),patch.object(relations.os,'replace',replace):
                with self.assertRaises(OSError):
                    relations.publish(stage,['one','two'])
            self.assertEqual((root/'one').read_text(),'old one')
            self.assertEqual((root/'two').read_text(),'old two')
