import unittest

from missing_notes import scan_missing_notes
from test_scan import row


class MissingNoteTests(unittest.TestCase):
    def test_two_other_contributors_support_the_same_missing_note(self):
        body = '|A8|BCDEFGAB|ABcdefga|B2decdef|B8|C8|D8|E8|'
        source = row(body.replace('cdef', 'cdf', 1))
        witness = {**row(body, '2'), 'username':'first'}
        other = {**row(body, '3'), 'username':'second'}
        data = [source, witness, other]
        patches, _ = scan_missing_notes(data, {r['setting_id']:r for r in data})
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]['after_abc'], body)
        self.assertEqual(patches[0]['evidence'][0]['token'], 'e')
        other['username'] = witness['username']
        patches, _ = scan_missing_notes(data, {r['setting_id']:r for r in data})
        self.assertFalse(patches)
