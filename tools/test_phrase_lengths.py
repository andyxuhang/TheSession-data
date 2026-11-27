import unittest

from phrase_lengths import scan_lengths
from test_scan import row


class PhraseLengthTests(unittest.TestCase):
    def setUp(self):
        self.source = row("|A8|BCDEFGAB|ABcde2fga|B2decdef|B8|C8|D8|E8|")
        self.witness = row("|G8|BCDEFGAB|ABcdefga|B2decdef|F8|C8|D8|E8|", "2")

    def scan(self, *references, upstream=None):
        data = [self.source, *references]
        return scan_lengths(data, upstream or {r['setting_id']:r for r in data})

    def test_matching_phrase_points_to_one_suffix(self):
        result = self.scan(self.witness)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['after_abc'], self.source['abc'].replace('e2f','ef'))
        self.assertEqual(result[0]['evidence'][0]['witnesses'], [('2',2)])

    def test_conflicting_full_rhythms_are_left_for_review(self):
        alternative = {**self.witness, 'setting_id':'3',
                       'abc':self.witness['abc'].replace('ABcdefga','ABcde2f/g/a')}
        self.assertFalse(self.scan(self.witness, alternative))

    def test_edited_reference_is_not_upstream_evidence(self):
        original = {**self.witness, 'abc':self.witness['abc'].replace('ABcdefga','ABcde2fga')}
        self.assertFalse(self.scan(self.witness, upstream={'1':self.source,'2':original}))

    def test_boundary_or_different_key_is_not_a_witness(self):
        self.assertFalse(self.scan({**self.witness, 'mode':'Gmajor'}))
        self.assertFalse(self.scan({**self.witness, 'abc':self.witness['abc'].replace('|ABcdefga','|:ABcdefga')}))

    def parallel(self, body):
        setting = row(body)
        return scan_lengths([setting], {'1': setting}, parallel=True)

    def test_parallel_phrase_at_opening(self):
        body = "|:ABcdefga|B2decdef|C8|D8|G8|ABcde2fga|B2decdef|E8|"
        patches = self.parallel(body)
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]['after_abc'], body.replace('e2f', 'ef'))
        self.assertEqual(patches[0]['evidence'][0]['witnesses'], [('1', 0)])

    def test_parallel_phrase_needs_context_on_same_side_of_repeat(self):
        self.assertFalse(self.parallel("|ABcdefga:|B2decdef|C8|D8|G8|ABcde2fga|B2decdef|E8|"))

    def test_overlapping_written_phrases_do_not_count(self):
        self.assertFalse(self.parallel("|A8|BCDEFGAB|ABcdefga|BCDEFGAB|ABcde2fga|B2decdef|C8|D8|"))

    def test_two_distinct_rhythms_in_parallel_phrases(self):
        self.assertFalse(self.parallel("|:ABcdefga|B2decdef|C8|D8|G8|ABcde2fga|B2decdef|E8|ABcde2f/g/a|B2decdef|"))
