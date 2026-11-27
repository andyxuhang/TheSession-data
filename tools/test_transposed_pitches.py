import unittest

from transposed_pitches import scan_transposed_pitches
from test_scan import row


class TransposedPitchTests(unittest.TestCase):
    def settings(self):
        return [
            row('|DEFGABcd|DEFGABcd|EFGAB=cde|DEFGABcd|DEFGABcd|A8|B8|C8|','1'),
            {**row('|GABcdefg|GABcdefg|ABcdefga|GABcdefg|GABcdefg|d8|e8|f8|','2'),
             'username':'first','mode':'Gmajor'},
            {**row('|CDEFGABc|CDEFGABc|DEFGABcd|CDEFGABc|CDEFGABc|G8|A8|B8|','3'),
             'username':'second','mode':'Cmajor'},
        ]

    def scan(self, entries):
        return scan_transposed_pitches(entries,{r['setting_id']:r for r in entries})[0]

    def test_cross_check_an_accidental_two_independent_keys(self):
        data = self.settings()
        patch, = self.scan(data)
        evidence, = patch['evidence']
        self.assertEqual((evidence['before_midi'],evidence['after_midi']),(72,73))
        self.assertEqual(evidence['transposed_references'],['2','3'])

    def test_competing_context_blocks_new_pitch(self):
        data = self.settings()
        conflict = {**data[1],'setting_id':'4','username':'different',
                    'abc':data[1]['abc'].replace('ABcdefga','ABcde=fga')}
        self.assertFalse(self.scan([*data, conflict]))
