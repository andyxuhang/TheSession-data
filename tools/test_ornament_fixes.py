import unittest

from ornament_fixes import scan_ornaments
from test_scan import row


class OrnamentFixTests(unittest.TestCase):
    def test_preserve_annotations_comments_and_grace_contents(self):
        text = '|"\u301cA !Coda!"{\u301cA}\u301cA2!Coda!BC| % \u301cA !Segno!\n'
        patch, = scan_ornaments([row(text)],{})[0]
        self.assertEqual(patch['after_abc'],'|"\u301cA !Coda!"{\u301cA}~A2!coda!BC| % \u301cA !Segno!\n')
        self.assertEqual(len(patch['evidence']),2)

    def test_skip_fields_and_preserve_standard_roll(self):
        self.assertFalse(scan_ornaments([row('|~ABcd efga|')],{})[0])
        self.assertFalse(scan_ornaments([row('w: ～A !Coda!\n|ABcd efga|')],{})[0])

    def test_standard_trill_and_full_word_da_capo(self):
        text = '|"!tr! !Dacapo!"{!tr!A}!tr!AB!Dacapo!cd| % !tr! !Dacapo!\n'
        patch, = scan_ornaments([row(text)],{})[0]
        self.assertEqual(patch['after_abc'],
            '|"!tr! !Dacapo!"{!tr!A}!trill!AB!dacapo!cd| % !tr! !Dacapo!\n')
        self.assertEqual({e['rule'] for e in patch['evidence']},
                         {'decoration_alias','decoration_case'})
