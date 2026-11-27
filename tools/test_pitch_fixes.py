import unittest

from check_playback import prepare_pitch_changes
from pitch_fixes import scan_pitches
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
