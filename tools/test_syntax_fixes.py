import unittest

from syntax_fixes import scan_syntax
from test_scan import row


class SyntaxFixTests(unittest.TestCase):
    def score(self, bar, sid, author):
        body = f'|DEFGABcd|GABcdefg|{bar}|FGAdefga|DEFGABcd|A8|B8|C8|'
        return {**row(body,sid), 'username':author}

    def scan(self, target, witness):
        source = self.score(target,'1','source')
        versions = [source,self.score(witness,'2','first'),self.score(witness,'3','second')]
        return scan_syntax(versions,{r['setting_id']:r for r in versions})[0]

    def test_remove_a_stray_mark_with_the_same_reference_phrase(self):
        correction, = self.scan('ABcde # fga','ABcde fga')
        edit, = correction['evidence']
        self.assertEqual(edit['rule'],'orphan_symbol')
        self.assertEqual(edit['corroborating_contributors'],2)

    def test_join_a_detached_duration_if_the_reference_agrees(self):
        correction, = self.scan('ABc 2 de f/ g/ a','ABc2 de f/ g/ a')
        self.assertEqual(correction['evidence'][0]['rule'],'split_note_token')

    def test_preserve_a_meaningful_attached_octave_mark(self):
        self.assertFalse(self.scan('ABc,defga','ABcdefga'))

    def test_preserve_a_valid_tie(self):
        self.assertFalse(self.scan('A-ABcdefg','AABcdefg'))
