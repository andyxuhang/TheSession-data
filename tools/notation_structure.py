"""Find irregular bar divisions and unmatched slurs with written witnesses."""

from collections import Counter, defaultdict

from matching_phrases import Score, compact, divider_edit, join_events, pitches, rhythm, separate_occurrence
from note_count_fixes import phrase_key
from pitch_fixes import PITCH, key_signature, resolve_pitches
from scan import TUPLET, measures, sha
from syntax_fixes import extends_phrase, without_notation


def barline_key(score, start, stop):
    bars = score.bars[start:stop]
    events = join_events(bars)
    return (score.signatures[start-1], score.signatures[stop], pitches(events), rhythm(events),
            bars[0].left, bars[-1].right)


def divider_witnesses(score):
    for start in range(1, len(score.bars)-1):
        for stop in range(start+1, min(len(score.bars), start+5)):
            if all(score.full[start-1:stop+1]) and score.plain_span(start, stop):
                yield barline_key(score, start, stop), (score, start, stop)


def divider_options(score, index):
    start = 1
    while start < len(score.bars)-1:
        if score.full[start] or not score.full[start-1]:
            start += 1
            continue
        stop = start+1
        while stop < len(score.bars) and not score.full[stop]:
            stop += 1
        a, start = start, stop
        bars = score.bars[a:stop]
        if (stop >= len(score.bars) or len(bars) > 4 or any(bar.error for bar in bars)
                or not score.plain_span(a, stop)
                or bars[0].left not in ('|', '||', '|:', ':|:')
                or bars[-1].right not in ('|', '||', ':|', ':|:', '|]')):
            continue
        events = join_events(bars)
        if min(len(score.bars[a-1].events), len(score.bars[stop].events), len(events)) < 3:
            continue
        options = defaultdict(list)
        for ref, j, k in index.get(barline_key(score, a, stop), ()):
            if not separate_occurrence(score, a, stop, ref, j, k):
                continue
            fragment = divider_edit(score, a, stop, ref, j, k, events)
            if fragment is None or compact(fragment) != compact(ref.body[ref.bars[j].start:ref.bars[k-1].end]):
                continue
            count = k-j
            rule = ('redundant_barline' if count < len(bars) else
                    'missing_barline' if count > len(bars) else 'misplaced_barline')
            options[rule, fragment].append((ref, j, k))
        if len(options) != 1:
            continue
        (rule, fragment), refs = next(iter(options.items()))
        if any(ref.row['username'] != score.row['username'] for ref, _, _ in refs):
            yield a, stop, rule, fragment, refs


def unmatched_slurs(body):
    """Locate unmatched parentheses outside comments, ornaments and tuplets."""
    masked = without_notation(body)
    openings, closings = [], []
    for i, char in enumerate(masked):
        if char == '(' and not TUPLET.match(masked, i):
            openings.append(i)
        elif char == ')':
            if openings:
                openings.pop()
            else:
                closings.append(i)
    return openings + closings


def slur_options(score, index):
    unmatched = unmatched_slurs(score.body)
    if len(unmatched) != 1:
        return
    at = unmatched[0]
    for i in range(1, len(score.bars)-1):
        bar = score.bars[i]
        if (not bar.start <= at < bar.end or not all(score.full[i-1:i+2])
                or min(len(item.events) for item in score.bars[i-1:i+2]) < 3):
            continue
        fragment = score.body[bar.start:at]+score.body[at+1:bar.end]
        refs = [(ref, j, j+1) for ref, j in index.get((phrase_key(score, i), compact(fragment)), ())
                if separate_occurrence(score, i, i+1, ref, j, j+1)]
        if any(ref.row['username'] != score.row['username'] or extends_phrase(score, i, ref, j)
               for ref, j, _ in refs):
            yield i, i+1, 'slur_delimiter', fragment, refs


def accidental_reset(before, after, mode):
    """Verify a missing barline changes only one carried accidental."""
    old_bars, old_error = measures(before)
    new_bars, new_error = measures(after)
    key = key_signature(mode)
    old_events, new_events = join_events(old_bars), join_events(new_bars)
    if (old_error or new_error or key is None or len(old_bars) != 1 or len(new_bars) != 2
            or any(bar.error for bar in old_bars+new_bars)
            or pitches(old_events) != pitches(new_events) or rhythm(old_events) != rhythm(new_events)
            or any(not PITCH.fullmatch(event.pitch) or event.tied for event in old_events)
            or compact(before) != compact(after.replace('|', ''))):
        return None
    old_midi = resolve_pitches(old_events, key)
    new_midi = [midi for bar in new_bars for midi in resolve_pitches(bar.events, key)]
    changes = [(i, x, y) for i, (x, y) in enumerate(zip(old_midi, new_midi)) if x != y]
    if len(changes) != 1:
        return None
    index, x, y = changes[0]
    a, b = old_events[index], new_events[index]
    if index < len(new_bars[0].events) or a.pitch[0] in '^=_':
        return None
    return dict(old_offset=a.start, new_offset=b.start, old_midi=x, new_midi=y,
                token=before[a.start:a.end])


def repeated_divider(score, original, rejected):
    for record in rejected.get('bars', ()):
        edit = record['edit']
        i = edit['bar']-1
        if (edit['rule'] != 'missing_barline' or not 0 < i < len(score.bars)-1
                or not score.plain_span(i-1, i+2) or not score.full[i+1]):
            continue
        bar = score.bars[i]
        if score.body[bar.start:bar.end] != edit['before'] or bar.duration != 2*score.unit:
            continue
        reset = accidental_reset(edit['before'], edit['after'], score.row['mode'])
        if reset is None:
            continue
        witnesses = []
        for j in range(1, len(original.bars)-2):
            a, b, following = original.bars[j:j+3]
            if (not all(original.full[j:j+3]) or not original.plain_span(j,j+3)
                    or following.signature != score.signatures[i+1]
                    or len(following.events) < 3
                    or not separate_occurrence(score, i, i+1, original, j, j+2)):
                continue
            if compact(original.body[a.start:b.end]) == compact(edit['after']):
                witnesses.append((original, j, j+2))
        if witnesses:
            yield i, i+1, edit['rule'], edit['after'], witnesses, reset


def scan_structures(data, upstream, rejections=()):
    groups = defaultdict(list)
    for row in data:
        groups[row['tune_id'], row['meter'], row['mode'], row['type']].append(row)
    proposals, counts = [], Counter()
    rejected = {record['setting_id']:record for record in rejections}
    for group in groups.values():
        if len(group) < 2 and group[0]['setting_id'] not in rejected:
            continue
        dividers, slurs = defaultdict(list), defaultdict(list)
        scores = []
        for row in group:
            score = Score(row)
            if not score.unit or sum(score.full) < 4:
                continue
            scores.append(score)
            if upstream.get(score.id, {}).get('abc') != score.body:
                continue
            for key, witness in divider_witnesses(score):
                dividers[key].append(witness)
            if unmatched_slurs(score.body):
                continue
            for i in range(1, len(score.bars)-1):
                if all(score.full[i-1:i+2]):
                    bar = score.bars[i]
                    slurs[phrase_key(score, i), compact(score.body[bar.start:bar.end])].append((score, i))
        for score in scores:
            edits = [(*edit, None) for edit in (*divider_options(score, dividers), *slur_options(score, slurs))]
            if not edits and score.id in rejected and score.id in upstream:
                edits = list(repeated_divider(score, Score(upstream[score.id]), rejected[score.id]))
            if len(edits) != 1:
                if edits:
                    counts['multiple_candidates'] += 1
                continue
            a, b, rule, fragment, refs, reset = edits[0]
            start, end = score.bars[a].start, score.bars[b-1].end
            before = score.body
            after = before[:start]+fragment+before[end:]
            evidence = dict(rule=rule, bar=a+1, last_bar=b, before=before[start:end], after=fragment,
                            reference_ranges=sorted({(ref.id, j+1, k) for ref, j, k in refs}),
                            method='Matching original written measures and complete adjoining measures')
            if reset is None:
                evidence['preserve_playback'] = True
            else:
                evidence['accidental_reset'] = reset
                evidence['method'] = 'Exact repeated measures and matching following measure in the original setting'
                counts['accidental_reset'] += 1
            row = score.row
            proposals.append(dict(tune_id=row['tune_id'], setting_id=score.id, name=row['name'],
                                  original_contributor=row['username'],
                                  source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{score.id}",
                                  category=rule, before_abc=before, after_abc=after,
                                  before_sha256=sha(before), after_sha256=sha(after), evidence=[evidence]))
            counts[rule] += 1
    return proposals, dict(counts)
