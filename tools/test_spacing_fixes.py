import unittest

from spacing_fixes import scan_spacing
from test_scan import row


class SpacingFixTests(unittest.TestCase):
    def test_keep_annotation_and_comment_contents(self):
        text = '|"D\u00a0major"{A\u200eB}DE\u00a0FG| % label\u200e\n'
        patch, = scan_spacing([row(text)],{})[0]
        self.assertEqual(patch['after_abc'],'|"D\u00a0major"{A\u200eB}DE FG| % label\u200e\n')
        self.assertEqual(len(patch['evidence']),1)

    def test_remove_formatting_marks_without_replacing_note_text(self):
        text = '|A\u200e2Bcd\u00a0efg|'
        patch, = scan_spacing([row(text)],{})[0]
        self.assertEqual(patch['before_abc'],text)
        self.assertEqual(patch['after_abc'],'|A2Bcd efg|')
        self.assertEqual([ev['codepoint'] for ev in patch['evidence']],['U+200E','U+00A0'])

    def test_plain_score_has_no_changes(self):
        self.assertFalse(scan_spacing([row('|ABcd efga|')],{})[0])
