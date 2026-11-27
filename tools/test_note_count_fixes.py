import unittest

from check_playback import prepare_note_count
from note_count_fixes import scan_note_counts
from test_scan import row


class NoteCountTests(unittest.TestCase):
    def score(self, bar, sid, username):
        body = f'|ABcdefga|GABcdefg|{bar}|FGAdefga|DEFGABcd|A8|B8|C8|'
        return {**row(body,sid), 'username':username}

    def scan(self, settings):
        return scan_note_counts(settings,{r['setting_id']:r for r in settings})[0]

    def test_restore_one_note_with_matching_longer_phrase(self):
        target = self.score('ABcdfga','1','first')
        reference = self.score('ABcdefga','2','second')
        patch, = self.scan([target,reference])
        evidence, = patch['evidence']
        self.assertEqual(patch['after_abc'],reference['abc'])
        playback = prepare_note_count(patch,evidence)
        self.assertEqual((playback['direction'],playback['token'],playback['midi']),(1,'e',76))

    def test_remove_one_of_two_identical_adjacent_notes(self):
        target = self.score('ABccdefga','1','first')
        reference = self.score('ABcdefga','2','second')
        patch, = self.scan([target,reference])
        evidence, = patch['evidence']
        self.assertEqual(patch['after_abc'],reference['abc'])
        playback = prepare_note_count(patch,evidence)
        self.assertEqual((playback['direction'],playback['token'],playback['midi']),(-1,'c',73))
        self.assertEqual(len(playback['positions']),2)

    def test_competing_duration_reading_blocks_note_insertion(self):
        target = self.score('ABcdfga','1','first')
        reference = self.score('ABcdefga','2','second')
        alternative = self.score('ABcd2fga','3','third')
        self.assertFalse(self.scan([target,reference,alternative]))

    def test_reject_an_offset_that_does_not_name_the_changed_note(self):
        target = self.score('ABcdfga','1','first')
        reference = self.score('ABcdefga','2','second')
        patch, = self.scan([target,reference])
        evidence, = patch['evidence']
        with self.assertRaises(ValueError):
            prepare_note_count(patch,{**evidence,'possible_offsets':[0]})
