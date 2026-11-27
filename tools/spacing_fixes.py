"""Normalize invisible layout characters outside annotations and comments."""

import re

from scan import MASK, sha


SPACING = re.compile('[\u00a0\u202f\u2009\u200e\u200f\u202a-\u202e\u2066-\u2069]')


def scan_spacing(data, upstream):
    proposals = []
    count = 0
    for row in data:
        before = row['abc']
        masked = MASK.sub(lambda m:' '*len(m[0]),before)
        edits = []
        for match in SPACING.finditer(masked):
            char = match[0]
            replacement = ' ' if char in '\u00a0\u202f\u2009' else ''
            edits.append(dict(start=match.start(),end=match.end(),text=replacement,codepoint=f'U+{ord(char):04X}'))
        if not edits:
            continue
        after = before
        for edit in reversed(edits):
            after = after[:edit['start']]+edit['text']+after[edit['end']:]
        evidence = [dict(rule='unicode_spacing',preserve_playback=True,
                         method='Normalize Unicode spaces and remove directional formatting outside annotations',
                         **edit) for edit in edits]
        sid,tune = row['setting_id'],row['tune_id']
        proposals.append(dict(setting_id=sid,tune_id=tune,name=row['name'],original_contributor=row['username'],
            source_url=f'https://thesession.org/tunes/{tune}#setting{sid}',category='unicode_spacing',
            before_abc=before,after_abc=after,before_sha256=sha(before),after_sha256=sha(after),evidence=evidence))
        count += len(edits)
    return proposals,dict(unicode_spacing=count)
