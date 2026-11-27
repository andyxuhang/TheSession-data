import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from check_playback import prepare_pitch_changes
from pitch_fixes import scan_pitches
from scan import ROOT
from test_scan import row


class PitchFixTests(unittest.TestCase):
    def score(self, measure, sid, username):
        body = f'|ABcdefga|GABcdefg|{measure}|FGAdefga|DEFGABcd|A8|B8|C8|'
        return {**row(body,sid), 'username':username}

    def scan(self, target, proposed):
        source = self.score(target,'1','first')
        refs = [self.score(proposed,'2','second'), self.score(proposed,'3','third')]
        settings = [source,*refs]
        return scan_pitches(settings,{r['setting_id']:r for r in settings})[0]

    def test_isolated_natural_sign(self):
        patch, = self.scan('ABcdEfga','AB=cdEfga')
        change, = patch['evidence']
        self.assertEqual((change['rule'],change['before_midi'],change['after_midi']),
                         ('accidental_typo',73,72))
        playback, = prepare_pitch_changes(patch,'Dmajor')
        self.assertEqual((playback['old_token'],playback['new_token']),('c','=c'))

    def test_accidental_carry_must_not_change_a_second_note(self):
        self.assertFalse(self.scan('ABcdcFga','AB=cdcFga'))

    def test_a_redundant_accidental_is_not_a_pitch_error(self):
        self.assertFalse(self.scan('ABcdEfga','AB^cdEfga'))

    def test_octave_jump_in_the_middle_of_a_run(self):
        patch, = self.scan('ABcDefga','ABcdefga')
        self.assertEqual(patch['evidence'][0]['rule'],'octave_typo')

    def test_independent_agreement_on_the_original_blocks_the_edit(self):
        settings = [self.score('ABcdEfga','1','first'), self.score('AB=cdEfga','2','second'),
                    self.score('AB=cdEfga','3','third'), self.score('ABcdEfga','4','fourth')]
        result, _ = scan_pitches(settings,{r['setting_id']:r for r in settings})
        self.assertFalse(result)

    def test_isolated_octave_with_one_extended_witness(self):
        source = self.score('ABcDefga','1','first')
        witness = self.score('ABcdefga','2','second')
        settings = [source,witness]
        result, _ = scan_pitches(settings,{r['setting_id']:r for r in settings})
        self.assertEqual(result[0]['evidence'][0]['rule'],'octave_typo')
        witness['abc'] = witness['abc'].replace('|ABcdefga|GAB', '|aBcdefga|GAB',1)
        witness['abc'] = witness['abc'].replace('|DEFGABcd|','|DEFGABce|')
        result, _ = scan_pitches(settings,{r['setting_id']:r for r in settings})
        self.assertFalse(result)

    def test_change_to_different_letter_requires_an_isolated_jump(self):
        patch, = self.scan('ABcCefga','ABcdefga')
        self.assertEqual(patch['evidence'][0]['rule'],'note_typo')
        self.assertFalse(self.scan('ABcgefga','ABcdefga'))

    def test_abcjs_maps_written_offsets_after_crlf_and_unicode(self):
        node = shutil.which('node')
        abcjs = ROOT.parent.parent/'third_party/abcjs/abcjs-basic-min.js'
        if not node or not abcjs.is_file():
            self.skipTest('Node and the vendored TradMate abcjs are required')
        prefix = '% \U0001f3b5\r\n'
        before = prefix + '|ABcdefga|\r\n|ABcdEfga|FGAdefga|'
        after = before.replace('ABcdEfga','AB=cdEfga')
        patch = {**row(before), 'before_abc':before, 'after_abc':after,
                 'evidence':[{'rule':'accidental_typo','bar':2,'note':3,'before_midi':73,'after_midi':72}]}
        patch['pitch_changes'] = prepare_pitch_changes(patch,'Dmajor')
        with tempfile.TemporaryDirectory() as work:
            source = Path(work)/'input.json'
            source.write_text(json.dumps([patch]))
            result = subprocess.check_output(
                [node,str(ROOT/'tools/check_abcjs_pitches.js'),str(abcjs),str(source)],text=True)
        check, = json.loads(result)['results']
        self.assertTrue(check['passed'],check)
        self.assertEqual(check['changed_played_pitches'],1)
