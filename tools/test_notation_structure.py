import unittest

from notation_structure import accidental_reset, scan_structures, unmatched_slurs
from test_scan import row


class NotationStructureTests(unittest.TestCase):
    def test_redundant_barline_by_section_boundary(self):
        original = '|DEFGABcd||GABc|defg|FGAdefga|DEFGABcd|A8|B8|'
        witness = original.replace('GABc|defg', 'GABc defg')
        rows = [row(original, '1'), {**row(witness, '2'), 'username': 'witness'}]
        proposals, counts = scan_structures(rows, {r['setting_id']:r for r in rows})
        proposal, = proposals
        self.assertEqual(counts, {'redundant_barline': 1})
        self.assertEqual(proposal['after_abc'], witness)

    def test_slurs_ignore_annotations_grace_notes_and_tuplets(self):
        text = '|"(C"{AB}(3DEF (AB)cd|ABc)d| % stray ( here'
        at, = unmatched_slurs(text)
        self.assertEqual(text[at-1:at+2], 'c)d')

    def test_barline_returns_to_the_key_signature(self):
        before = 'A2^CDEFG Bcdefgab'
        after = 'A2^CDEFG| Bcdefgab'
        reset = accidental_reset(before, after, 'Cmajor')
        self.assertIsNotNone(reset)
        self.assertEqual((reset['old_midi'], reset['new_midi'], reset['token']), (73, 72, 'c'))

    def test_reject_barlines_that_change_two_pitches(self):
        before = 'A2^CDEFG Bccdefga'
        self.assertIsNone(accidental_reset(before,'A2^CDEFG| Bccdefga','Cmajor'))
