"""Normalize unambiguous ornament glyphs and standard decoration names."""

import re

from scan import MASK, measures, sha


ROLL_GLYPH = re.compile('\u301c(?=[A-Ga-g])')
DECORATION_CASE = re.compile(r'!(Segno|Coda|Dacapo)!')
TRILL_ALIAS = re.compile(r'!tr!')
SPECIFICATION = 'https://abcnotation.com/wiki/abc:standard:v2.1#decorations'


def scan_ornaments(data, upstream):
    proposals, counts = [], {}
    for row in data:
        before = row['abc']
        if measures(before)[1]:
            continue
        melody = MASK.sub(lambda m:' '*len(m[0]),before)
        decorations = MASK.sub(lambda m:m[0] if m[0].startswith('!') else ' '*len(m[0]),before)
        edits = []
        for match in ROLL_GLYPH.finditer(melody):
            edits.append(dict(rule='roll_glyph',start=match.start(),end=match.end(),
                              before=match[0],after='~'))
        for match in DECORATION_CASE.finditer(decorations):
            edits.append(dict(rule='decoration_case',start=match.start(),end=match.end(),
                              before=match[0],after=match[0].lower()))
        for match in TRILL_ALIAS.finditer(decorations):
            edits.append(dict(rule='decoration_alias',start=match.start(),end=match.end(),
                              before=match[0],after='!trill!'))
        if not edits:
            continue
        after = before
        for edit in sorted(edits,key=lambda e:e['start'],reverse=True):
            after = after[:edit['start']]+edit['after']+after[edit['end']:]
        for edit in edits:
            edit.update(preserve_playback=True,specification=SPECIFICATION,
                        method='ABC 2.1 ornament symbols and standard decoration spellings')
            counts[edit['rule']] = counts.get(edit['rule'],0)+1
        sid,tune = row['setting_id'],row['tune_id']
        proposals.append(dict(setting_id=sid,tune_id=tune,name=row['name'],
            original_contributor=row['username'],source_url=f'https://thesession.org/tunes/{tune}#setting{sid}',
            category='+'.join(sorted({e['rule'] for e in edits})),
            before_abc=before,after_abc=after,before_sha256=sha(before),after_sha256=sha(after),evidence=edits))
    return proposals,counts
