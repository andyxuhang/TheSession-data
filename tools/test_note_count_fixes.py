import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from check_playback import prepare_note_count
from note_count_fixes import scan_note_counts
from scan import ROOT
from test_scan import row


class NoteCountTests(unittest.TestCase):
    def score(self, bar, sid, username):
        body = f'|ABcdefga|GABcdefg|{bar}|FGAdefga|DEFGABcd|A8|B8|C8|'
        return {**row(body,sid), 'username':username}

    def scan(self, settings):
        return scan_note_counts(settings,{r['setting_id']:r for r in settings})[0]

    def test_restore_one_note_with_matching_longer_phrase(self):
        target = self.score('ABcdfga','1','first')
        reference = self.score('ABcdefga','2','second')
        patch, = self.scan([target,reference])
        evidence, = patch['evidence']
        self.assertEqual(patch['after_abc'],reference['abc'])
        playback = prepare_note_count(patch,evidence)
        self.assertEqual((playback['direction'],playback['token'],playback['midi']),(1,'e',76))

    def test_remove_one_of_two_identical_adjacent_notes(self):
        target = self.score('ABccdefga','1','first')
        reference = self.score('ABcdefga','2','second')
        patch, = self.scan([target,reference])
        evidence, = patch['evidence']
        self.assertEqual(patch['after_abc'],reference['abc'])
        playback = prepare_note_count(patch,evidence)
        self.assertEqual((playback['direction'],playback['token'],playback['midi']),(-1,'c',73))
        self.assertEqual(len(playback['positions']),2)

    def test_competing_duration_reading_blocks_note_insertion(self):
        target = self.score('ABcdfga','1','first')
        reference = self.score('ABcdefga','2','second')
        alternative = self.score('ABcd2fga','3','third')
        self.assertFalse(self.scan([target,reference,alternative]))

    def test_reject_an_offset_that_does_not_name_the_changed_note(self):
        target = self.score('ABcdfga','1','first')
        reference = self.score('ABcdefga','2','second')
        patch, = self.scan([target,reference])
        evidence, = patch['evidence']
        with self.assertRaises(ValueError):
            prepare_note_count(patch,{**evidence,'possible_offsets':[0]})

    def test_restore_degree_from_a_transposed_reference(self):
        source = row('|DEFGABcd|DEFGABcd|EFGABde|DEFGABcd|DEFGABcd|A8|B8|C8|','1')
        reference = {**row('|GABcdefg|GABcdefg|ABcdefga|GABcdefg|GABcdefg|d8|e8|f8|','2'),
                     'username':'reference','mode':'Gmajor'}
        patch, = self.scan([source,reference])
        edit, = patch['evidence']
        self.assertEqual(edit['transposed_references'],['2'])
        self.assertEqual(patch['after_abc'],source['abc'].replace('ABde','ABcde'))

    def test_source_positions_disambiguate_consecutive_identical_notes(self):
        node = shutil.which('node')
        abcjs = ROOT.parent.parent/'third_party/abcjs/abcjs-basic-min.js'
        if not node or not abcjs.is_file():
            self.skipTest('Node and the vendored TradMate abcjs are required')
        patch = {**row('|A ABBBcd|'), 'before_abc':'|A ABBBcd|', 'after_abc':'|AA ABBBcd|',
                 'pitch_changes':[]}
        evidence = {'note_count_change':1, 'bar':1, 'before':'A ABBBcd', 'after':'AA ABBBcd',
                    'token':'A', 'midi':69, 'duration_eighths':'1', 'possible_offsets':[0,1]}
        patch['insertion'] = prepare_note_count(patch,evidence)
        with tempfile.TemporaryDirectory() as work:
            source = Path(work)/'input.json'
            source.write_text(json.dumps([patch]))
            out = subprocess.check_output(
                [node,str(ROOT/'tools/check_abcjs_pitches.js'),str(abcjs),str(source)],text=True)
        check, = json.loads(out)['results']
        self.assertTrue(check['passed'],check)
        self.assertEqual(check['changed_note_occurrences'],1)
