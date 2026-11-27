"""Compare irregular measures with intact written phrases in the same tune."""

from collections import Counter, defaultdict
from difflib import SequenceMatcher
from functools import cached_property
import re

from scan import MASK, NOTE, TYPES, measures, meter_units, sha


def compact(text):
    return re.sub(r'\s+', '', text)


def join_events(bars):
    return [event for bar in bars for event in bar.events]


def pitches(events):
    return tuple(event.pitch for event in events)


def rhythm(events):
    return tuple((event.duration, event.tied) for event in events)


class Score:
    def __init__(self, row):
        self.row = row
        self.id = row['setting_id']
        self.body = row['abc']
        self.unit = meter_units(row['meter'])
        self.key = re.fullmatch(r'[A-G][#b]?(major|minor|dorian|mixolydian|aeolian)', row['mode'])
        self.bars = measures(self.body)[0]

    @cached_property
    def full(self):
        return [not bar.error and bar.duration == self.unit for bar in self.bars]

    @cached_property
    def signatures(self):
        return [bar.signature for bar in self.bars]

    def plain_span(self, start, stop):
        return all(self.bars[i].right == self.bars[i+1].left == '|'
                   and self.bars[i].end + 1 == self.bars[i+1].start
                   for i in range(start, stop-1))


def separate_occurrence(score, a, b, reference, j, k):
    if score.id != reference.id:
        return True
    before, after = score.bars[a-1].start, score.bars[b].end
    start = reference.bars[j].start
    end = reference.bars[k-1].end
    if score.body == reference.body:
        return end <= before or after <= start
    # Reidentify the unchanged upstream occurrence after earlier fixes shifted
    # offsets. The entire reference passage must remain outside the target.
    written = reference.body[start:end]
    return written in score.body[:before] or written in score.body[after:]


def matching_sides(score, a, b, reference, j, k, transposed=False):
    """Require adjacency in the written score, on the same side of a repeat."""
    def same_measure(i, r):
        left, right = score.bars[i].events, reference.bars[r].events
        if not transposed:
            return score.signatures[i] == reference.signatures[r]
        return (rhythm(left) == rhythm(right)
                and relative_pitches(left, score.key[0]) == relative_pitches(right, reference.key[0])
                and relative_pitches(left, score.key[0]) is not None)

    before = (j > 0 and reference.plain_span(j-1, j+1) and reference.full[j-1]
              and same_measure(a-1, j-1)
              and len(score.bars[a-1].events) >= 3)
    after = (k < len(reference.bars) and reference.plain_span(k-1, k+1)
             and reference.full[k] and same_measure(b, k)
             and len(score.bars[b].events) >= 3)
    return before, after


def relative_pitches(events, key):
    # No chromatic accidentals. The spelled tonic includes its accidental,
    # while the diatonic degree depends only on the tonic letter.
    if any(not e.pitch[0].lower() in 'abcdefg' for e in events):
        return None
    tonic = 'CDEFGAB'.index(key[0])
    return tuple('CDEFGAB'.index(e.pitch[0].upper()) - tonic
                 + 7 * (e.pitch[0].islower() + e.pitch.count("'") - e.pitch.count(','))
                 for e in events)


def length_edit(score, a, b, reference, j, k, sides, transposed=False):
    bars, other_bars = score.bars[a:b], reference.bars[j:k]
    if [len(bar.events) for bar in bars] != [len(bar.events) for bar in other_bars]:
        return None
    target_events, other_events = join_events(bars), join_events(other_bars)
    changes = [(e, w) for e, w in zip(target_events, other_events) if e.duration != w.duration]
    if not 1 <= len(changes) <= 2:
        return None
    if any(e.length == w.length or e.pitch[0] in 'zx' or e.tied or w.tied
           or e.tuplet != w.tuplet or e.broken != w.broken for e, w in changes):
        return None
    start, end = bars[0].start, bars[-1].end
    fragment = score.body[start:end]
    for e, w in reversed(changes):
        fragment = fragment[:e.length_start-start] + w.length + fragment[e.end-start:]
    parsed, error = measures(fragment)
    if (error or len(parsed) != len(other_bars) or any(bar.error or bar.duration != score.unit for bar in parsed)
            or [rhythm(bar.events) for bar in parsed] != [rhythm(bar.events) for bar in other_bars]
            or pitches(join_events(parsed)) != pitches(target_events)):
        return None
    other_text = reference.body[other_bars[0].start:other_bars[-1].end]
    if compact(fragment) != compact(other_text):
        if not all(sides):
            return None
        # Different ornaments or chord annotations may appear in two otherwise
        # identical phrases. Keep them and compare all written rhythm operators.
        def clean(text):
            text = MASK.sub('', text)
            if transposed:
                text = NOTE.sub(lambda m: 'N' + (m['length'] or ''), text)
            return compact(text)

        if clean(fragment) != clean(other_text):
            return None
    if len(changes) > 1 and not all(sides):
        return None
    return fragment


def rhythm_edit(score, a, b, reference, j, k):
    """Recover one missing, duplicated or reversed written rhythm mark."""
    start, end = score.bars[a].start, score.bars[b-1].end
    original = score.body[start:end]
    wanted = compact(reference.body[reference.bars[j].start:reference.bars[k-1].end])
    offsets = [i for i, char in enumerate(original) if not char.isspace()]
    text = compact(original)
    operations = [(i, stop, wanted[m:n]) for opcode, i, stop, m, n
                  in SequenceMatcher(None, text, wanted, autojunk=False).get_opcodes()
                  if opcode != 'equal']
    if len(operations) != 1:
        return None
    i, stop, inserted = operations[0]
    removed = text[i:stop]
    if not all(re.fullmatch(r'(?:[<>]{1,2}|\([234])?', mark) for mark in (removed, inserted)):
        return None
    left = offsets[i] if i < len(offsets) else len(original)
    right = offsets[stop-1]+1 if stop > i else left
    hidden = MASK.sub(lambda m: ' ' * len(m[0]), original)
    if hidden[left:right] != original[left:right]:
        return None
    fragment = original[:left] + inserted + original[right:]
    parsed, error = measures(fragment)
    expected = reference.bars[j:k]
    if (error or len(parsed) != len(expected) or any(bar.error or bar.duration != score.unit for bar in parsed)
            or [bar.signature for bar in parsed] != [bar.signature for bar in expected]):
        return None
    return fragment


def divider_edit(score, start, stop, reference, j, k, events):
    """Use the reference's measure divisions while retaining every source token."""
    bars = score.bars[start:stop]
    old_cuts = {bar.end for bar in bars[:-1]}
    used = 0
    new_cuts = set()
    for bar in reference.bars[j:k-1]:
        used += len(bar.events)
        last, following = events[used-1:used+1]
        if last.tied or last.broken or last.tuplet or following.broken or following.tuplet:
            return None
        # Keep decorations before the first note of the following bar with it.
        gap = score.body[last.end:following.start].replace('|', '')
        if gap.strip():
            return None
        new_cuts.add(last.end)
    if old_cuts == new_cuts:
        return None
    fragment = score.body[bars[0].start:bars[-1].end]
    for offset in sorted(old_cuts | new_cuts, reverse=True):
        at = offset-bars[0].start
        if offset in old_cuts - new_cuts:
            fragment = fragment[:at] + ' ' + fragment[at+1:]
        elif offset in new_cuts - old_cuts:
            fragment = fragment[:at] + '|' + fragment[at:]
    parsed, error = measures(fragment)
    new_events = join_events(parsed)
    if (error or len(parsed) != k-j or any(b.error or b.duration != score.unit for b in parsed)
            or pitches(new_events) != pitches(events) or rhythm(new_events) != rhythm(events)):
        return None
    return fragment


def layout_split(score, i, index):
    """Restore a divider at a line break between two complete measures."""
    bar = score.bars[i]
    if bar.duration != 2*score.unit or score.row['type'].lower() not in TYPES:
        return None
    elapsed = 0
    for cut, event in enumerate(bar.events[:-1], 1):
        elapsed += event.duration
        if elapsed != score.unit or event.tied or event.tuplet or event.broken:
            continue
        next_event = bar.events[cut]
        gap = score.body[event.end:next_event.start]
        if not re.fullmatch(r'[ \t]*\r?\n[ \t]*', gap):
            continue
        halves = (bar.events[:cut], bar.events[cut:])
        references = []
        for side, events in enumerate(halves):
            for ref, j, k in index.get((score.row['mode'], pitches(events)), ()):
                if k != j+1 or rhythm(events) != rhythm(ref.bars[j].events):
                    continue
                if not separate_occurrence(score, i, i+1, ref, j, k):
                    continue
                sides = matching_sides(score, i, i+1, ref, j, k)
                if sides[side]:
                    references.append((ref.id,j+1,k))
        if not references:
            continue
        fragment = score.body[bar.start:event.end] + '|' + score.body[event.end:bar.end]
        parsed, error = measures(fragment)
        if (not error and len(parsed) == 2 and all(not b.error and b.duration == score.unit for b in parsed)
                and [pitches(b.events) for b in parsed] == [pitches(events) for events in halves]
                and [rhythm(b.events) for b in parsed] == [rhythm(events) for events in halves]):
            return fragment, references
    return None


def scan_phrases(data, upstream):
    groups = defaultdict(list)
    for row in data:
        groups[row['tune_id'], row['meter'], row['type']].append(row)
    proposals, counts = [], Counter()
    for group in groups.values():
        targets, index, transposed_index = [], defaultdict(list), defaultdict(list)
        for row in group:
            score = Score(row)
            if not score.unit or not score.bars or all(score.full):
                continue
            if sum(score.full) >= 4 and sum(score.full)*2 >= len(score.bars):
                targets.append(score)
        if not targets:
            continue
        for row in group:
            original = upstream.get(row['setting_id'])
            if not original or any(original[key] != row[key] for key in ('tune_id', 'meter', 'mode', 'type')):
                continue
            reference = Score(original)
            for j in range(len(reference.bars)):
                for k in range(j+1, min(j+4, len(reference.bars))+1):
                    if not reference.full[k-1] or not reference.plain_span(j, k):
                        break
                    events = join_events(reference.bars[j:k])
                    index[reference.row['mode'], pitches(events)].append((reference, j, k))
                    if reference.key and (relative := relative_pitches(events, reference.key[0])) is not None:
                        transposed_index[reference.key[1], relative].append((reference, j, k))
        for score in targets:
            strong_context = sum(score.full) >= 6 and sum(score.full)*4 >= len(score.bars)*3
            corrections = []
            i = 1
            while i < len(score.bars)-1:
                if score.full[i] or not score.full[i-1]:
                    i += 1
                    continue
                a = i
                while i < len(score.bars) and not score.full[i]:
                    i += 1
                b = i
                bars = score.bars[a:b]
                if b == len(score.bars) or b-a > 4 or not score.plain_span(a-1, b+1):
                    counts['boundary_or_run_too_long'] += 1
                    continue
                if any(bar.error for bar in bars):
                    counts['unsupported'] += 1
                    continue
                events = join_events(bars)
                if len(events) < 3:
                    counts['short_phrase'] += 1
                    continue
                counts['interior_phrases_compared'] += 1
                alternatives = defaultdict(list)
                readings = set()
                transposed_witnesses = set()
                mode = score.row['mode']
                refs = list(index.get((mode, pitches(events)), ()))
                if score.key and (relative := relative_pitches(events, score.key[0])) is not None:
                    refs.extend((ref, j, k) for ref, j, k in transposed_index.get((score.key[1], relative), ())
                                if ref.row['mode'] != mode)
                for ref, j, k in refs:
                    if not separate_occurrence(score, a, b, ref, j, k):
                        continue
                    transposed = ref.row['mode'] != mode
                    sides = matching_sides(score, a, b, ref, j, k, transposed)
                    if not any(sides) or ((transposed or not strong_context) and not all(sides)):
                        continue
                    ref_events = join_events(ref.bars[j:k])
                    readings.add(tuple(tuple(rhythm(bar.events)) for bar in ref.bars[j:k]))
                    if rhythm(events) == rhythm(ref_events):
                        replacement = divider_edit(score, a, b, ref, j, k, events)
                        rule = 'missing_barline' if k-j > b-a else 'misplaced_barline'
                    elif b-a == k-j:
                        replacement = length_edit(score, a, b, ref, j, k, sides, transposed)
                        rule = 'note_length'
                        if replacement is None and all(sides) and not transposed:
                            replacement = rhythm_edit(score, a, b, ref, j, k)
                            rule = 'rhythm_mark'
                    else:
                        continue
                    if replacement is not None:
                        witness = (ref.id, j+1, k)
                        alternatives[rule, replacement].append(witness)
                        if transposed:
                            transposed_witnesses.add(witness)
                layout = None
                if not readings and a+1 == b and strong_context:
                    layout = layout_split(score, a, index)
                    if layout:
                        replacement, witnesses = layout
                        alternatives['missing_barline', replacement] = witnesses
                        counts['line_break_witness'] += 1
                if len(readings) > 1 or len(alternatives) > 1:
                    counts['conflicting_phrases'] += 1
                elif not alternatives:
                    counts['no_supported_edit' if readings else 'no_matching_phrase'] += 1
                else:
                    (rule, replacement), witnesses = next(iter(alternatives.items()))
                    start, end = bars[0].start, bars[-1].end
                    counts[rule] += 1
                    corrections.append((start, end, replacement, {
                        'rule':rule, 'bar':a+1, 'last_bar':b, 'before':score.body[start:end],
                        'after':replacement, 'reference_ranges':sorted(set(witnesses)),
                        'transposed_references':sorted(set(witnesses) & transposed_witnesses),
                        'method':('Line break and matching adjacent measure' if layout
                                  else 'Matching uninterrupted written phrase in the original exports'),
                    }))
            if corrections:
                after = score.body
                for start, end, replacement, _ in reversed(corrections):
                    after = after[:start] + replacement + after[end:]
                row = score.row
                proposals.append(dict(tune_id=row['tune_id'], setting_id=score.id, name=row['name'],
                    original_contributor=row['username'],
                    source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{score.id}",
                    category='+'.join(sorted({e['rule'] for _, _, _, e in corrections})),
                    before_abc=score.body, after_abc=after, before_sha256=sha(score.body), after_sha256=sha(after),
                    evidence=[e for _, _, _, e in corrections]))
    return proposals, dict(counts)
