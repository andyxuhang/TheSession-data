import unittest

from matching_phrases import scan_phrases
from test_scan import row


class MatchingPhraseTests(unittest.TestCase):
    def scan(self, *settings):
        return scan_phrases(settings, {r['setting_id']: r for r in settings})[0]

    def test_realign_several_measures_in_a_written_phrase(self):
        ends = ("|A8|BCDEFGAB|", "|GABcdefg|B8|C8|D8|E8|")
        notes = "ABcdefgaABCDefgaBCDefgde"
        source = row(ends[0] + "|".join((notes[:7], notes[7:14], notes[14:])) + ends[1])
        reference = row(ends[0] + "ABcdefga|ABCDefga|BCDefgde" + ends[1], "2")
        result, = self.scan(source, reference)
        change, = result["evidence"]
        self.assertEqual(change["rule"], "misplaced_barline")
        self.assertEqual(change["last_bar"], 5)
        self.assertEqual(change["reference_ranges"], [("2", 3, 5)])

    def test_two_altered_suffixes_require_both_neighbors(self):
        source = row("|A8|BCDEFGAB|ABcd2e2fga|B2decdef|B8|C8|D8|E8|")
        reference = row("|G8|BCDEFGAB|ABcdefga|B2decdef|F8|C8|D8|E8|", "2")
        result, = self.scan(source, reference)
        self.assertIn("ABcdefga", result["after_abc"])
        no_context = {**reference, "abc": reference["abc"].replace("B2decdef", "B8")}
        self.assertFalse(self.scan(source, no_context))

    def test_transposed_phrase_requires_two_anchors(self):
        source = {**row("|A8|CDEFGACA|CD2EFGACA|AGFEDCAC|A8|B8|C8|D8|"), "mode":"Cmajor"}
        reference = row("|B8|DEFGABDB|DEFGABDB|BAGFEDBD|B8|c8|D8|E8|", "2")
        result, = self.scan(source, reference)
        self.assertEqual(result["after_abc"], source["abc"].replace("CD2E", "CDE"))
        self.assertFalse(self.scan(source, {**reference, "mode":"Dminor"}))
        self.assertFalse(self.scan(source, {**reference, "abc":reference["abc"].replace("BAGFEDBD","B8")}))

    def test_incompatible_rhythms_need_review(self):
        body = "|A8|BCDEFGAB|ABcde2fga|B2decdef|B8|C8|D8|E8|"
        first = row(body.replace("e2f", "ef"), "2")
        second = row(body.replace("e2fga", "e2f/g/a"), "3")
        self.assertFalse(self.scan(row(body), first, second))

    def test_missing_rhythm_mark_in_otherwise_identical_phrase(self):
        body = "|A8|BCDEFGAB|ABcde/f/g/a3|B2decdef|B8|C8|D8|E8|"
        source = row(body)
        reference = row(body.replace("e/f/g/", "(3e/f/g/"), "2")
        changed, = self.scan(source, reference)
        self.assertEqual(changed["evidence"][0]["rule"], "rhythm_mark")
        self.assertEqual(changed["after_abc"], reference["abc"])

    def test_line_break_needs_anchored_half_measure(self):
        body = "|A8|BCDEFGAB|ABcdefga\nABCDEfga|B2decdef|B8|C8|D8|E8|"
        reference = row("|G8|BCDEFGAB|ABcdefga|F8|C8|D8|E8|G8|", "2")
        changed, = self.scan(row(body), reference)
        self.assertIn("ABcdefga|\nABCDEfga", changed["after_abc"])
        self.assertFalse(self.scan(row(body), {**reference, "abc":reference["abc"].replace("BCDEFGAB", "D8")}))
