import importlib
import json
from pathlib import Path
import tempfile
import unittest

from scan import sha

apply = importlib.import_module('apply')


def patch(before, after):
    return {'setting_id':'1','tune_id':'1','before_abc':before,'after_abc':after,
            'before_sha256':sha(before),'after_sha256':sha(after),
            'replace':{'before':before,'after':after,'count':1}}


class ApplicationTests(unittest.TestCase):
    def load(self, changes):
        with tempfile.TemporaryDirectory() as directory:
            files=[]
            for i, item in enumerate(changes):
                path=Path(directory)/f'{i}.json'
                path.write_text(json.dumps({'corrections':[item]}))
                files.append(path)
            return apply.read_plan(files)[1]

    def test_hash_guard(self):
        p=patch('AB2','AB');p['before_abc']='AC2'
        with self.assertRaises(ValueError):self.load([p])

    def test_source_change_stops_application(self):
        patches=self.load([patch('AB2','AB')])
        with self.assertRaises(ValueError):
            apply.replacement({'setting_id':'1','tune_id':'1','abc':'AC'},patches,True)

    def test_different_set_arrangement_is_retained(self):
        patches=self.load([patch('AB2','AB')])
        self.assertIsNone(apply.replacement({'setting_id':'1','tune_id':'1','abc':'AC'},patches,False))

    def test_already_applied_is_unchanged(self):
        patches=self.load([patch('AB2','AB')])
        self.assertIsNone(apply.replacement({'setting_id':'1','tune_id':'1','abc':'AB'},patches,True))

    def test_intermediate_history_can_be_completed(self):
        patches=self.load([patch('AB2','AB'),patch('AB','A|B')])
        for source in ('AB2','AB'):
            self.assertEqual(apply.replacement({'setting_id':'1','tune_id':'1','abc':source},patches,True),'A|B')

    def test_conflicting_history_is_rejected(self):
        with self.assertRaises(ValueError):self.load([patch('AB2','AB'),patch('AC','A|C')])

    def test_overlapping_offsets_are_rejected(self):
        p=patch('ABC','AB');del p['replace']
        p['edits']=[{'start':0,'end':2,'text':'A'},{'start':1,'end':3,'text':'B'}]
        with self.assertRaises(ValueError):self.load([p])


if __name__=='__main__':
    unittest.main()
