"""Find note-length slips against complete written phrases."""
from collections import defaultdict
import re

from scan import measures, meter_units, sha


def context(bar):
    return bar.signature if not bar.error and len(bar.events) >= 3 else ()


def agrees(left, right, i, j, parallel=False):
    """Require a complete neighbor or four matching notes on both sides."""
    a = context(left[i-1])
    b = context(right[j-1]) if j > 0 and (not parallel or right[j].left == "|") else ()
    c = context(left[i+1])
    d = context(right[j+1]) if j+1 < len(right) and (not parallel or right[j].right == "|") else ()
    return (a and a == b) or (c and c == d) or (
        min(map(len, (a,b,c,d))) >= 4 and a[-4:] == b[-4:] and c[:4] == d[:4])


def plain_edit(source, bar, reference, other):
    changes = [(a,b) for a,b in zip(bar.events,other.events) if a.duration != b.duration]
    if len(changes) != 1:
        return None
    old, new = changes[0]
    if old.length == new.length or old.pitch in ('z','x') or old.tied or new.tied:
        return None
    # Match rhythm operators, ornaments, accidentals, rests and note spellings
    # in the complete written bar. Ignore horizontal spacing and line breaks.
    corrected = source[bar.start:old.length_start]+new.length+source[old.end:bar.end]
    compact = lambda text: re.sub(r'\s+', '', text)
    if compact(corrected) != compact(reference[other.start:other.end]):
        return None
    return old.length_start, old.end, new.length


def scan_lengths(data, upstream, parallel=False):
    groups = defaultdict(list)
    for row in data:
        groups[row['tune_id'],row['mode'],row['meter'],row['type']].append(row)
    proposals = []
    for (_, _, meter, _), group in groups.items():
        if (len(group) < 2 and not parallel) or not (unit := meter_units(meter)):
            continue
        parsed = [(r,measures(r['abc'])[0]) for r in group]
        index = defaultdict(list)
        for r,bars in parsed:
            original = upstream.get(r['setting_id'])
            if not original or any(original[k] != r[k] for k in ('tune_id','mode','meter','type')):
                continue
            # Cite only witnesses whose complete text is still the upstream text.
            if original['abc'] != r['abc']:
                continue
            for j, b in enumerate(bars):
                if not parallel and (j == 0 or j+1 == len(bars) or b.left != "|" or b.right != "|"):
                    continue
                if not b.error and b.duration == unit:
                    index[tuple(e.pitch for e in b.events)].append((r,bars,j))
        for row,bars in parsed:
            body = row['abc']
            if len(bars)<8 or sum(not b.error and b.duration==unit for b in bars)*4 < len(bars)*3:
                continue
            edits, evidence = [], []
            for i in range(1,len(bars)-1):
                b = bars[i]
                if (b.error or b.left!='|' or b.right!='|' or b.duration==unit
                        or len(b.events)<3 or abs(b.duration-unit)>2
                        or any(n.error or n.duration!=unit for n in (bars[i-1],bars[i+1]))):
                    continue
                supported = defaultdict(list)
                rhythms = set()
                for other,wb,j in index[tuple(e.pitch for e in b.events)]:
                    same_setting = other['setting_id'] == row['setting_id']
                    if same_setting != parallel or (parallel and abs(i-j) < 3):
                        continue
                    if not agrees(bars,wb,i,j,parallel):
                        continue
                    rhythms.add(wb[j].signature)
                    edit = plain_edit(body,b,other['abc'],wb[j])
                    if edit:
                        supported[edit].append((other['setting_id'],j))
                if len(rhythms)!=1 or len(supported)!=1:
                    continue
                edit,witness = next(iter(supported.items()))
                start,end,value = edit
                edits.append(edit)
                evidence.append({'rule':'note_length','bar':i+1,'before':body[b.start:b.end],
                                 'after':body[b.start:start]+value+body[end:b.end],
                                 'witnesses':witness,'method':('separate written phrase in the same upstream setting' if parallel
                                                               else 'matching rhythm and neighboring phrase in another setting')})
            if edits:
                after=body
                for start,end,value in reversed(edits):
                    after=after[:start]+value+after[end:]
                newbars,err=measures(after)
                if err or len(newbars)!=len(bars) or any(newbars[e['bar']-1].duration!=unit for e in evidence):
                    continue
                proposals.append(dict(tune_id=row['tune_id'],setting_id=row['setting_id'],name=row['name'],
                    original_contributor=row['username'],source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{row['setting_id']}",
                    category='note_length',before_abc=body,after_abc=after,before_sha256=sha(body),after_sha256=sha(after),
                    edits=[dict(start=a,end=b,text=c) for a,b,c in edits],evidence=evidence))
    return proposals
