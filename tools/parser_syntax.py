"""Repair malformed tuplets and numeric labels using ABC syntax rules."""

import re

from notation_structure import unmatched_slurs
from scan import MASK, sha


TUPLET_CLOSER = re.compile(r'\([2-9]\)')
TUPLET_COLON = re.compile(r'\([2-9]:(?=[^:\d])')
NUMERIC_LABEL = re.compile(r'"([0-9]+)\r?\n"')


def annotation_reference(patch):
    before = patch['before_abc']
    after = NUMERIC_LABEL.sub(lambda m:'"^'+m[1]+'"',before)
    if after == before or after != patch['after_abc']:
        raise ValueError('Annotation repair differs from its numeric-label source')
    return NUMERIC_LABEL.sub('',before)


def scan_parser_syntax(data, upstream):
    proposals = []
    counts = {}
    for row in data:
        before = row['abc']
        masked = MASK.sub(lambda m:' '*len(m[0]),before)
        unmatched = set(unmatched_slurs(before))
        edits = []
        for match in TUPLET_CLOSER.finditer(masked):
            at = match.end()-1
            if at in unmatched:
                edits.append((at,at+1,'tuplet_closer'))
        for match in TUPLET_COLON.finditer(masked):
            edits.append((match.end()-1,match.end(),'incomplete_tuplet'))
        labels = list(NUMERIC_LABEL.finditer(before))
        if labels and not edits:
            after = NUMERIC_LABEL.sub(lambda m:'"^'+m[1]+'"',before)
            evidence = [dict(rule='annotation_linebreak',start=m.start(),end=m.end(),
                before=m[0],after='"^'+m[1]+'"',preserve_playback=True,
                method='Preserved numeric label as a single-line ABC text annotation',
                specification='https://abcnotation.com/wiki/abc:standard:v2.1#annotations')
                for m in labels]
        else:
            evidence = []
        if not edits:
            if not evidence:
                continue
        else:
            after = before
            for a,b,_ in sorted(edits,reverse=True):
                after = after[:a]+after[b:]
        for a,b,rule in sorted(edits):
            counts[rule] = counts.get(rule,0)+1
            evidence.append(dict(rule=rule,start=a,end=b,before=before[a-2:b],after=before[a-2:a],
                preserve_playback=True,
                method='ABC 2.1 section 4.13 tuplet syntax and unmatched-slur check',
                specification='https://abcnotation.com/wiki/abc:standard:v2.1#duplets_triplets_quadruplets_etc'))
        for ev in evidence:
            if ev['rule'] == 'annotation_linebreak':
                counts[ev['rule']] = counts.get(ev['rule'],0)+1
        sid,tune=row['setting_id'],row['tune_id']
        proposals.append(dict(setting_id=sid,tune_id=tune,name=row['name'],original_contributor=row['username'],
            source_url=f'https://thesession.org/tunes/{tune}#setting{sid}',
            category='+'.join(sorted({e['rule'] for e in evidence})),
            before_abc=before,after_abc=after,before_sha256=sha(before),after_sha256=sha(after),evidence=evidence))
    return proposals,counts
