import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_common import comparison_body, melody_digest, review_state
from reassess import implicit_repeat_warnings
from scan import sha
import status
from test_scan import row


class ReviewEvidenceTests(unittest.TestCase):
    def test_comparison_preserves_meter_fields_chords_and_tuplets(self):
        source = '|[M:6/8]{g}"Am"(3A.Bc [CEG]2| % note\n'
        plain = comparison_body(source)
        self.assertIn('[M:6/8]',plain)
        self.assertIn('(3A Bc [CEG]2',plain)
        self.assertNotIn('{g}',plain)
        self.assertEqual(plain.count('\n'),source.count('\n'))

    def test_tied_notes_match_a_single_sustained_note(self):
        tied = [[0,1,60,True],[1,1,60,False],[2,1,62,False]]
        sustained = [[0,2,60,False],[2,1,62,False]]
        self.assertEqual(melody_digest(tied),melody_digest(sustained))
        self.assertNotEqual(melody_digest(tied),melody_digest([[0,2,61,False],[2,1,62,False]]))

    def test_rounding_matches_javascript_at_half_a_tick(self):
        digest,count = melody_digest([[0.0625,0.0625,60,False]])
        self.assertEqual(count,1)
        self.assertEqual(digest,sha('[[63,60,63]]'))

    def test_repeat_conventions_do_not_hide_duration_errors(self):
        repeat = [dict(parser='abc2midi',message='Warning in line-char 6-12 : Assuming repeat'),
                  dict(parser='abc2abc',message='Warning : Unexpected :|2 found')]
        self.assertTrue(implicit_repeat_warnings(repeat))
        self.assertFalse(implicit_repeat_warnings(repeat+[
            dict(parser='abc2abc',message='Error : Bar 2 is 7/8 not 4/4')]))
        self.assertFalse(implicit_repeat_warnings([
            dict(parser='abc2midi',message='Process exit code 1')]))

    def test_review_expires_when_meter_changes_through_status_entry_point(self):
        source = row('|ABcd efga|')
        issue = dict(setting_id='1',category='unsupported',reason='Simple scanner limitation')
        decision = dict(setting_id='1',tune_id='1',review_state_sha256=review_state(source,[issue],{}),
            cleared_categories=['unsupported'],reason='Accepted by independent parsers',
            playback_agreement=True,original_signature_supported=True)
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            for folder in ('json','checks','changes','reports'):
                (root/folder).mkdir()
            (root/'reports/findings.jsonl').write_text(json.dumps(issue)+'\n')
            (root/'checks/reviewed-settings.json').write_text(json.dumps({'settings':[decision]}))
            def run(record):
                (root/'json/tunes.json').write_text('[\n'+json.dumps(record)+'\n]\n')
                with patch.object(status,'ROOT',root),patch('sys.argv',['status']),contextlib.redirect_stdout(io.StringIO()):
                    status.main()
                return json.loads((root/'reports/summary.json').read_text())['categories']
            result = run(source)
            self.assertEqual((result['accepted'],result['unsupported']),(1,0))
            result = run({**source,'meter':'6/8'})
            self.assertEqual((result['accepted'],result['unsupported']),(0,1))
            (root/'checks/rejected.json').write_text(json.dumps([
                dict(setting_id='1',reason='New playback evidence')]))
            result = run(source)
            self.assertEqual((result['accepted'],result['unsupported'],result['review']),(0,1,1))
            self.assertEqual(json.loads((root/'reports/findings.jsonl').read_text()),issue)
