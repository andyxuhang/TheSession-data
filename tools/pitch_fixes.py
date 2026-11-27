"""Find isolated accidental and octave errors in otherwise matching phrases."""

from collections import Counter, defaultdict
import re

from matching_phrases import Score, compact, rhythm, separate_occurrence
from scan import sha


PITCH = re.compile(r"(\^{1,2}|_{1,2}|=)?([A-Ga-g])([,']*)")
ALTERATIONS = {'^':1, '^^':2, '_':-1, '__':-2, '=':0}
NATURAL = dict(zip('CDEFGAB', (0, 2, 4, 5, 7, 9, 11)))
MODE_OFFSET = {'major':0, 'minor':-3, 'aeolian':-3, 'dorian':-2, 'mixolydian':-1,
               'phrygian':-4, 'lydian':1, 'locrian':-5}
PITCH_RULES = {'accidental_typo', 'octave_typo'}


def split_pitch(value):
    mark, letter, octave = PITCH.fullmatch(value).groups()
    return mark, letter.upper(), 4 + int(letter.islower()) + octave.count("'") - octave.count(',')


def key_signature(mode):
    parsed = re.fullmatch(r'([A-G])([#b]?)([a-z]+)', mode)
    if not parsed or parsed[3] not in MODE_OFFSET:
        return None
    tonic, mark, scale = parsed.groups()
    fifths = 'FCGDAEB'.index(tonic) - 1 + {'#':7, 'b':-7, '':0}[mark] + MODE_OFFSET[scale]
    if abs(fifths) > 7:
        return None
    order = 'FCGDAEB' if fifths > 0 else 'BEADGCF'
    return dict.fromkeys(order[:abs(fifths)], 1 if fifths > 0 else -1)


def resolve_pitches(events, key):
    state = key.copy()
    notes = []
    for event in events:
        mark, letter, octave = split_pitch(event.pitch)
        if mark:
            state[letter] = ALTERATIONS[mark]
        notes.append(12 * (octave+1) + NATURAL[letter] + state.get(letter, 0))
    return notes


def windows(score):
    for i in range(1,len(score.bars)-1):
        before, bar, after = score.bars[i-1:i+2]
        if (not all(score.full[i-1:i+2]) or not score.plain_span(i-1,i+2)
                or min(map(lambda b: len(b.events), (before,bar,after))) < 4
                or before.events[-1].tied
                or any(not PITCH.fullmatch(e.pitch) or e.tied for e in bar.events)):
            continue
        yield i, (before.signature, after.signature, rhythm(bar.events))


def same_extra_measure(score, i, reference, j):
    for offset in (-2, 2):
        a,b = i+offset,j+offset
        if (0 <= a < len(score.bars) and 0 <= b < len(reference.bars)
                and score.full[a] and reference.full[b] and len(score.bars[a].events) >= 4
                and score.plain_span(min(a,i),max(a,i)+1)
                and reference.plain_span(min(b,j),max(b,j)+1)
                and score.signatures[a] == reference.signatures[b]):
            return True
    return False


def one_change(score, i, reference, j, key):
    bar, other = score.bars[i], reference.bars[j]
    differences = [n for n,(a,b) in enumerate(zip(bar.events,other.events)) if a.pitch != b.pitch]
    if len(differences) != 1:
        return None
    n = differences[0]
    a,b = bar.events[n],other.events[n]
    am,al,ao = split_pitch(a.pitch)
    bm,bl,bo = split_pitch(b.pitch)
    if al != bl:
        return None
    before, after = resolve_pitches(bar.events,key), resolve_pitches(other.events,key)
    if [k for k,(x,y) in enumerate(zip(before,after)) if x != y] != [n]:
        return None
    change = abs(before[n]-after[n])
    if ao == bo and change == 1:
        rule = 'accidental_typo'
    elif am == bm and change == 12:
        rule = 'octave_typo'
    else:
        return None
    fragment = score.body[bar.start:a.start]+b.pitch+score.body[a.length_start:bar.end]
    if compact(fragment) != compact(reference.body[other.start:other.end]):
        return None
    # Keep plausible octave shifts unless an independent written repetition
    # corroborates them. An isolated octave slip usually jumps out and back.
    isolated = (0 < n < len(before)-1
                and all(abs(before[n]-before[k]) >= 8 and abs(after[n]-after[k]) <= 5
                        for k in (n-1,n+1)))
    return n, rule, fragment, before[n], after[n], isolated


def scan_pitches(data, upstream):
    groups = defaultdict(list)
    for row in data:
        groups[row['tune_id'],row['meter'],row['mode'],row['type']].append(row)
    edits, stats = [], Counter()
    for (_,_,mode,_), group in groups.items():
        key = key_signature(mode)
        if key is None or len({r['username'] for r in group}) < 3:
            continue
        targets, index = [], defaultdict(list)
        for row in group:
            original = upstream.get(row['setting_id'])
            if not original or any(row[k] != original[k] for k in ('tune_id','meter','mode','type')):
                continue
            score = Score(row)
            if not score.unit or not score.bars or re.search(r'(?m)^\s*%%',score.body):
                continue
            targets.append(score)
            if score.body == original['abc']:
                for i, context in windows(score):
                    index[context].append((score,i))
        for score in targets:
            corrections = []
            for i,context in windows(score):
                original = tuple(e.pitch for e in score.bars[i].events)
                readings = defaultdict(list)
                for reference,j in index.get(context,()):
                    reading = tuple(e.pitch for e in reference.bars[j].events)
                    readings[reading].append((reference,j))
                if any(ref.row['username'] != score.row['username'] for ref,_ in readings.pop(original,())):
                    continue
                if len(readings) != 1:
                    continue
                references, = readings.values()
                accepted = defaultdict(list)
                for ref,j in references:
                    if not separate_occurrence(score,i,i+1,ref,j,j+1):
                        continue
                    change = one_change(score,i,ref,j,key)
                    if change:
                        accepted[change].append((ref,j))
                if len(accepted) != 1:
                    continue
                (n,rule,fragment,before,after,isolated), witnesses = next(iter(accepted.items()))
                independent = {ref.row['username'] for ref,_ in witnesses
                               if ref.row['username'] != score.row['username']}
                repeated = any(ref.id == score.id for ref,_ in witnesses)
                extended = any(ref.row['username'] in independent and same_extra_measure(score,i,ref,j)
                               for ref,j in witnesses)
                stats[rule+'_exact_candidates'] += 1
                if len(independent) < 2 or not (repeated or extended) or (rule == 'octave_typo' and not (repeated or isolated)):
                    continue
                bar = score.bars[i]
                evidence = {
                    'rule':rule, 'bar':i+1, 'note':n+1,
                    'before':score.body[bar.start:bar.end], 'after':fragment,
                    'before_midi':before, 'after_midi':after,
                    'reference_ranges':sorted({(ref.id,j+1,j+1) for ref,j in witnesses}),
                    'corroborating_contributors':len(independent),
                    'written_repeat':repeated, 'extra_matching_bar':extended,
                    'isolated_octave_jump':rule == 'octave_typo' and isolated,
                }
                corrections.append((bar.start,bar.end,fragment,evidence))
            if not corrections:
                continue
            after = score.body
            for start,end,fragment,_ in reversed(corrections):
                after = after[:start]+fragment+after[end:]
            evidence = [ev for _,_,_,ev in corrections]
            row = score.row
            edits.append(dict(tune_id=row['tune_id'],setting_id=score.id,name=row['name'],
                original_contributor=row['username'],
                source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{score.id}",
                category='+'.join(sorted({e['rule'] for e in evidence})),
                before_abc=score.body,after_abc=after,before_sha256=sha(score.body),
                after_sha256=sha(after),evidence=evidence))
    return edits, dict(stats)
