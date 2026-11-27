import unittest

from check_playback import prepare_reference_duration
from reference_lengths import scan_reference_lengths
from test_scan import row


class ReferenceLengthTests(unittest.TestCase):
    def scan(self, original, reference):
        data = [original,reference]
        return scan_reference_lengths(data,{r['setting_id']:r for r in data})[0]

    def test_detached_duration_has_a_proven_playback_change(self):
        left = '|DEFGABcd|GABcdefg|'
        right = '|FGAdefga|DEFGABcd|A8|B8|C8|'
        source = row(left+'ABc 2 de f/ g/ a'+right,'1')
        reference = {**row(left+'ABc2 de f/ g/ a'+right,'2'),'username':'reference'}
        patch, = self.scan(source,reference)
        edit, = patch['evidence']
        self.assertEqual(edit['rule'],'split_note_token')
        proof = prepare_reference_duration(patch,edit)
        self.assertEqual((proof['before'],proof['after']),(0.5,1.0))

    def test_transposed_measure_with_matching_extended_phrase(self):
        source = row('|DEFGABcd|DEFGABcd|EFGABc2de|DEFGABcd|DEFGABcd|A8|B8|C8|','1')
        reference = {**row('|GABcdefg|GABcdefg|ABcdefga|GABcdefg|GABcdefg|d8|e8|f8|','2'),
                     'username':'reference','mode':'Gmajor'}
        patch, = self.scan(source,reference)
        edit, = patch['evidence']
        self.assertEqual(edit['transposed_references'],['2'])
        self.assertEqual(patch['after_abc'],source['abc'].replace('c2de','cde'))

    def test_different_repeat_mark_rejects_the_reading(self):
        body = '|DEFGABcd|GABcdefg|ABcde2fga:|FGAdefga|DEFGABcd|A8|B8|C8|'
        source = row(body,'1')
        other = body.replace('e2f','ef').replace(':|','|')
        reference = {**row(other,'2'),'username':'reference'}
        self.assertFalse(self.scan(source,reference))
