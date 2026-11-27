import unittest
from fractions import Fraction as F

from scan import length, measures, scan


def row(body, sid="1"):
    return dict(tune_id="1", setting_id=sid, name="Test", type="reel",
                meter="4/4", mode="Dmajor", abc=body, username="test")


class NotationTests(unittest.TestCase):
    def test_lengths(self):
        for text, value in [("", 1), ("/", F(1, 2)), ("//", F(1, 4)),
                            ("3/2", F(3, 2)), ("2/", 1)]:
            self.assertEqual(length(text), value)

    def test_tuplet_and_broken_rhythm(self):
        bars, _ = measures("|(3ABC DEFGAB|A>B c<d e2 f2|")
        self.assertEqual([b.duration for b in bars], [8, 8])
        self.assertFalse(any(b.error for b in bars))

    def test_annotations_do_not_create_bars(self):
        bars, _ = measures('|"Em|G"{AB}DEFGABcd|% | comment\nDEFGABcd|')
        self.assertEqual(len(bars), 2)
        self.assertEqual([b.duration for b in bars], [8, 8])

    def test_unsupported_is_not_guessed(self):
        bars, _ = measures("|[CEG]2 DEFG|")
        self.assertTrue(bars[0].error)
        self.assertTrue(measures("|ABcd [M:3/4] e2|")[1])

    def test_split_requires_two_witnesses(self):
        data = [row("|DEFGABcd|efgabagf|DEFGABcd efgabagf|DEFGABcd|efgabagf|DEFGABcd|efgabagf|DEFGABcd|")]
        fixes, _, _ = scan(data)
        self.assertEqual(len(fixes), 1)
        self.assertIn("DEFGABcd| efgabagf", fixes[0]["after_abc"])
        data[0]["abc"] = data[0]["abc"].replace("DEFGABcd efgabagf", "DEFGABcd edcBAGFE")
        self.assertFalse(scan(data)[0])

    def test_rejecting_one_divider_keeps_its_neighbor(self):
        from unittest.mock import patch
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from fix_notation import check_barlines

        x, y = "DEFGABcd", "efgabagf"
        body = "|" + "|".join([x, y, x+y, y, x, x+y, x, y, x, y]) + "|"
        proposals, _, _ = scan([row(body)], barlines_only=True)
        self.assertEqual(len(proposals[0]['evidence']), 2)
        checks = [{'variant':'1-0','passed':False,'reason':'pitch'},
                  {'variant':'1-1','passed':True,'all_event_timings_unchanged':True}]
        with TemporaryDirectory() as directory, patch('fix_notation.playback',return_value={'checks':checks}):
            passed, failed = check_barlines(proposals,Path(directory),None)
        self.assertEqual(len(passed[0]['evidence']), 1)
        self.assertEqual(passed[0]['after_abc'],(x+'|'+y).join(body.rsplit(x+y,1)))
        self.assertEqual(failed['1']['bars'][0]['edit']['bar'],3)

    def test_early_divider_uses_an_adjacent_witness(self):
        source = row("|A8|B8|C8|D8|E8|F8|G8|DEFGAB|cdefgabagf|B8|")
        reference = row("|DEFGABcd|efgabagf|", "2")
        fixes, _, _ = scan([source, reference], barlines_only=True)
        self.assertEqual([p['after_abc'] for p in fixes], ["|A8|B8|C8|D8|E8|F8|G8|DEFGAB cd|efgabagf|B8|"])
        reference['abc'] = "|DEFGABcd|B8|efgabagf|"
        self.assertFalse(scan([source, reference], barlines_only=True)[0])

    def test_do_not_move_across_a_comment_or_empty_bar(self):
        source = row("|A8|B8|C8|D8|E8|F8|G8|DEFGAB| |cdefgabagf|B8|")
        reference = row("|DEFGABcd|efgabagf|", "2")
        self.assertFalse(scan([source, reference], barlines_only=True)[0])

    def test_consistently_long_measures_keep_their_grouping(self):
        source = row("|" + "DEFGABcd efgabagf|" * 8)
        reference = row("|DEFGABcd|efgabagf|", "2")
        self.assertFalse(scan([source, reference], barlines_only=True)[0])

    def test_duration_needs_phrase_context(self):
        body = "|DEFGABcd|efgabagf|ABcdABcd|DEFGABcd|efgabagf2|ABcdABcd|DEFGABcd|efgabagf|"
        fixes, _, _ = scan([row(body)])
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0]["category"], "note_length")
        self.assertIn("|efgabagf|ABcdABcd|", fixes[0]["after_abc"])

    def test_pickup_and_ending_not_lengthened(self):
        body = "|:AB|DEFGABcd|efgabagf|ABcdABcd|DEFGABcd|efgabagf|ABcdABcd|DEFGABcd|ABcdAB:|"
        fixes, _, _ = scan([row(body)])
        self.assertFalse(fixes)

    def test_ambiguous_duration_is_not_changed(self):
        # The same pitches also occur with another full rhythm and the same
        # phrase context. Two plausible character edits must block automation.
        # This particular alternate is not full, so construct a direct pair
        # with a 9-eighth bar and two full 8-eighth witnesses instead.
        body = "|DEFGABcd|A2BCDEFG|efgabagf|DEFGABcd|AB2CDEFG|efgabagf|DEFGABcd|A2B2CDEFG|efgabagf|"
        self.assertFalse(scan([row(body)])[0])

    def test_control_character_is_removed_without_rewriting_notes(self):
        body = "\x14|:ABcd efga|ABcd efga:|"
        fixes, _, _ = scan([row(body)])
        self.assertEqual(fixes[0]['after_abc'], body[1:])
        self.assertEqual(fixes[0]['category'], 'stray_control')

    def test_missing_triplet_has_complete_phrase_witness(self):
        r = row("|:ABc def|G2(3G/A/B/ c2 A B2c|ABc def|ABc def|G2G/A/B/ c2 A B2c|ABc def|ABc def|ABc def:|")
        r['meter'],r['type'] = '9/8','slip jig'
        # The surrounding measures must themselves fill 9/8.
        r['abc'] = r['abc'].replace('ABc def','A3 B3 c3')
        fixes, _, _ = scan([r])
        self.assertEqual(fixes[0]['category'], 'missing_triplet')
        self.assertEqual(fixes[0]['after_abc'].count('(3G/A/B/'), 2)


if __name__ == "__main__":
    unittest.main()
