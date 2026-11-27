"""Shared source fingerprints and undecorated melody comparisons for review."""

import hashlib
import json
import math
import re

from scan import MASK


DECORATIONS = re.compile(r'(?m)^\s*[A-Za-z]:[^\r\n]*|\[[A-Za-z]:[^\]]*\]|[~.HLMOPSTuv]')


def comparison_body(body):
    body = MASK.sub(lambda m:''.join('\n' if c=='\n' else ' ' for c in m[0]),body)
    return DECORATIONS.sub(lambda m:m[0] if len(m[0])>1 else ' ',body)


def melody_digest(events):
    notes, pending = [], {}
    for start,duration,pitch,tied in sorted(events,key=lambda e:(e[0],e[2])):
        at = pending.pop((pitch,round(start,6)),None)
        if at is None:
            at = len(notes)
            notes.append([start,pitch,duration])
        else:
            notes[at][2] += duration
        if tied:
            pending[pitch,round(start+duration,6)] = at
    canonical = sorted([[math.floor(start*1000+0.5),pitch,math.floor(duration*1000+0.5)]
                        for start,pitch,duration in notes])
    encoded = json.dumps(canonical,separators=(',',':')).encode()
    return hashlib.sha256(encoded).hexdigest(),len(canonical)


def review_state(row, issues, flags):
    state = [[row[k] for k in ('abc','meter','mode','type')],issues,flags]
    return hashlib.sha256(json.dumps(state,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
