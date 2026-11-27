import unittest

from parser_syntax import annotation_reference, scan_parser_syntax
from test_scan import row


class ParserSyntaxTests(unittest.TestCase):
    def test_keep_a_tuplet_inside_a_balanced_slur(self):
        proposals,_ = scan_parser_syntax([row('|((3ABC DEF)|')],{})
        self.assertFalse(proposals)

    def test_only_remove_an_unmatched_tuplet_closer(self):
        source = row('|"label (3)"{abc}(3)ABC DEF|')
        proposal, = scan_parser_syntax([source],{})[0]
        self.assertEqual(proposal['after_abc'],'|"label (3)"{abc}(3ABC DEF|')

    def test_preserve_optional_tuplet_fields(self):
        self.assertFalse(scan_parser_syntax([row('|(3::2AB CDEF|')],{})[0])
        proposal, = scan_parser_syntax([row('|(3:ABC DEF|')],{})[0]
        self.assertEqual(proposal['after_abc'],'|(3ABC DEF|')

    def test_numeric_annotation_reference_keeps_every_note(self):
        proposal, = scan_parser_syntax([row('|"1\r\n"ABC DEF|"2\n"GAB cde|')],{})[0]
        self.assertEqual(proposal['after_abc'],'|"^1"ABC DEF|"^2"GAB cde|')
        self.assertEqual(annotation_reference(proposal),'|ABC DEF|GAB cde|')
        with self.assertRaises(ValueError):
            annotation_reference({**proposal,'after_abc':proposal['after_abc'].replace('ABC','ABD')})
