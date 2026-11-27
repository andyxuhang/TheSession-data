"""Restore an omitted note when independent transcriptions agree."""

from collections import defaultdict
import re

from matching_phrases import Score, compact, separate_occurrence
from scan import measures, sha


SIMPLE_NOTE = re.compile(r"[A-Ga-g][,']*(?:[12]|/)?")


def restore_note(score, bar, reference, other):
    fragment = score.body[bar.start:bar.end]
    expected = reference.body[other.start:other.end]
    source = compact(fragment)
    offsets = [i for i, char in enumerate(fragment) if not char.isspace()]
    before_pitches = [e.pitch for e in bar.events]
    for index, event in enumerate(other.events):
        a, b = event.start-other.start, event.end-other.start
        token = expected[a:b]
        if (event.tied or event.broken or event.tuplet
                or event.duration != score.unit-bar.duration or not SIMPLE_NOTE.fullmatch(token)
                or compact(expected[:a] + expected[b:]) != source):
            continue
        # Insert at the start of a written note or after the last note.
        at = len(compact(expected[:a]))
        position = offsets[at] if at < len(offsets) else bar.events[-1].end-bar.start
        boundaries = {e.start-bar.start for e in bar.events} | {bar.events[-1].end-bar.start}
        if position not in boundaries:
            continue
        corrected = fragment[:position] + token + fragment[position:]
        parsed, error = measures(corrected)
        if error or len(parsed) != 1 or parsed[0].error or parsed[0].signature != other.signature:
            continue
        if [e.pitch for e in parsed[0].events[:index]+parsed[0].events[index+1:]] != before_pitches:
            continue
        yield corrected, token, str(event.duration)


def scan_missing_notes(data, upstream):
    groups = defaultdict(list)
    for row in data:
        groups[row['tune_id'], row['meter'], row['mode'], row['type']].append(row)
    proposals = []
    examined = matching = 0
    for group in groups.values():
        if len(group) < 3:
            continue
        index = defaultdict(list)
        targets = []
        for row in group:
            original = upstream.get(row['setting_id'])
            if not original or any(row[key] != original[key] for key in ('tune_id','mode','meter','type')):
                continue
            reference = Score(original)
            if reference.body == row['abc'] and not all(reference.full) and sum(reference.full) >= 6:
                targets.append(reference)
            for j in range(1, len(reference.bars)-1):
                if all(reference.full[j-1:j+2]) and reference.plain_span(j-1, j+2):
                    index[reference.signatures[j-1], reference.signatures[j+1]].append((reference,j))
        for score in targets:
            supported = []
            for i in range(1, len(score.bars)-1):
                bar = score.bars[i]
                if (not score.unit or bar.error or not 0 < score.unit-bar.duration <= 2
                        or not score.full[i-1] or not score.full[i+1] or not score.plain_span(i-1, i+2)
                        or min(len(bar.events),len(score.bars[i-1].events),len(score.bars[i+1].events)) < 4
                        or any(e.broken or e.tuplet or e.tied or e.pitch[0] in '^_=xz' for e in bar.events)):
                    continue
                examined += 1
                readings, options = set(), defaultdict(list)
                for ref,j in index[score.signatures[i-1],score.signatures[i+1]]:
                    if not separate_occurrence(score,i,i+1,ref,j,j+1):
                        continue
                    other = ref.bars[j]
                    if len(other.events) != len(bar.events)+1:
                        continue
                    for correction in restore_note(score,bar,ref,other):
                        readings.add(other.signature)
                        options[correction].append((ref.id,j+1,ref.row['username']))
                if len(readings) != 1 or len(options) != 1:
                    continue
                (fragment, token, duration), witnesses = next(iter(options.items()))
                matching += 1
                distinct_contributors = {name for sid, _, name in witnesses
                                         if sid != score.id and name != score.row['username']}
                if len(distinct_contributors) >= 2:
                    supported.append((bar, dict(rule='missing_note', bar=i+1, before=score.body[bar.start:bar.end],
                        after=fragment, token=token, duration_eighths=duration,
                        method='Identical phrase and both adjacent measures in independent transcriptions',
                        reference_ranges=[(sid, j, j) for sid,j,_ in witnesses])))
            # Check one audible note insertion per independent setting.
            if len(supported) == 1:
                bar, evidence = supported[0]
                body = score.body
                after = body[:bar.start]+evidence['after']+body[bar.end:]
                row = score.row
                proposals.append(dict(tune_id=row['tune_id'],setting_id=score.id,name=row['name'],
                    original_contributor=row['username'],
                    source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{score.id}",
                    category='missing_note',before_abc=body,after_abc=after,
                    before_sha256=sha(body),after_sha256=sha(after),evidence=[evidence]))
    return proposals, {'interior_bars_compared':examined, 'matching_insertions':matching,
                       'independently_confirmed_insertions':len(proposals)}
