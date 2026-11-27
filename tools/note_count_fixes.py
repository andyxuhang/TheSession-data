"""Find a single omitted or surplus note using complete reference phrases."""

from collections import Counter, defaultdict

from matching_phrases import Score, compact, separate_occurrence
from missing_notes import SIMPLE_NOTE, restore_note
from pitch_fixes import key_signature, resolve_pitches
from scan import parse_bar, sha
from syntax_fixes import extends_phrase


def phrase_key(score, i):
    a,b,c = score.bars[i-1:i+2]
    return (a.signature,c.signature,a.right,b.left,b.right,c.left)


def trim_note(score, bar, reference, other):
    text = score.body[bar.start:bar.end]
    expected = compact(reference.body[other.start:other.end])
    for event in bar.events:
        a,b = event.start-bar.start,event.end-bar.start
        token = text[a:b]
        if not SIMPLE_NOTE.fullmatch(token) or event.duration != bar.duration-score.unit:
            continue
        fragment = text[:a]+text[b:]
        if compact(fragment) != expected:
            continue
        parsed = parse_bar(fragment,0,bar.left,bar.right)
        if not parsed.error and parsed.signature == other.signature:
            yield fragment,token,str(event.duration)


def plain_events(bar):
    return all(not (e.broken or e.tuplet or e.tied or e.pitch[0] in '^_=xz') for e in bar.events)


def supported_edit(score, i, index):
    target = score.bars[i]
    insert = target.duration < score.unit
    alternatives = defaultdict(list)
    for ref,j in index.get(phrase_key(score,i),()):
        if not separate_occurrence(score,i,i+1,ref,j,j+1):
            continue
        other = ref.bars[j]
        if not plain_events(other):
            continue
        if (tuple(e.pitch for e in target.events) == tuple(e.pitch for e in other.events)
                and sum(a.duration!=b.duration for a,b in zip(target.events,other.events))==1):
            # A competing reading shifts one duration and keeps the notes.
            return None
        if len(other.events) != len(target.events)+(1 if insert else -1):
            continue
        edits = restore_note(score,target,ref,other) if insert else trim_note(score,target,ref,other)
        for edit in edits:
            alternatives[edit].append((ref,j))
    if len(alternatives)!=1:
        return None
    (fragment,token,duration),refs = next(iter(alternatives.items()))
    contributors = {ref.row['username'] for ref,_ in refs if ref.row['username']!=score.row['username']}
    written_repeat = any(ref.id==score.id for ref,_ in refs)
    longer_phrase = any(extends_phrase(score,i,ref,j) for ref,j in refs)
    if not (len(contributors)>=2 or (contributors and longer_phrase) or (written_repeat and longer_phrase)):
        return None
    if (target.left,target.right)!=('|','|') and not (contributors and longer_phrase):
        return None
    # Use an unambiguous whole-token change. Adjacent identical notes may
    # give two equivalent offsets, and the playback check accepts either.
    original = score.body[target.start:target.end]
    more, less = (fragment,original) if insert else (original,fragment)
    parsed = parse_bar(more,0,target.left,target.right)
    key = key_signature(score.row['mode'])
    notes = resolve_pitches(parsed.events,key)
    positions = [e.start for e in parsed.events if more[e.start:e.end] == token
                 and more[:e.start]+more[e.end:]==less]
    if not positions:
        return None
    midis = {note for note,event in zip(notes,parsed.events) if event.start in positions}
    if len(midis)!=1:
        return None
    return {
        'rule':'missing_note' if insert else 'extra_note', 'bar':i+1,
        'note_count_change':1 if insert else -1,
        'before':original, 'after':fragment, 'token':token, 'duration_eighths':duration,
        'midi':next(iter(midis)), 'possible_offsets':positions,
        'reference_ranges':sorted({(ref.id,j+1,j+1) for ref,j in refs}),
        'corroborating_contributors':len(contributors),
        'written_repeat':written_repeat, 'extra_matching_bar':longer_phrase,
    }


def scan_note_counts(data, upstream):
    groups = defaultdict(list)
    for row in data:
        groups[row['tune_id'],row['meter'],row['mode'],row['type']].append(row)
    proposals, stats = [], Counter()
    for (_,_,mode,_),group in groups.items():
        if key_signature(mode) is None:
            continue
        targets,index = [],defaultdict(list)
        for row in group:
            original = upstream.get(row['setting_id'])
            if not original or any(row[k]!=original[k] for k in ('tune_id','mode','meter','type','abc')):
                continue
            score = Score(row)
            if not score.unit or sum(score.full)<5 or '\n%%' in score.body or score.body.startswith('%%'):
                continue
            if not all(score.full):
                targets.append(score)
            for i in range(1,len(score.bars)-1):
                a,b,c = score.bars[i-1:i+2]
                if all(score.full[i-1:i+2]) and min(len(a.events),len(c.events))>=3:
                    index[phrase_key(score,i)].append((score,i))
        for score in targets:
            corrections = []
            for i in range(1,len(score.bars)-1):
                a,b,c = score.bars[i-1:i+2]
                if (b.error or not 0<abs(b.duration-score.unit)<=2 or not score.full[i-1] or not score.full[i+1]
                        or min(len(a.events),len(b.events),len(c.events))<3
                        or b.left not in ('|','|:',':|:','||') or b.right not in ('|',':|',':|:','||','|]')
                        or a.events[-1].tied or not plain_events(b)):
                    continue
                stats['short_measures' if b.duration<score.unit else 'long_measures']+=1
                evidence = supported_edit(score,i,index)
                if evidence:
                    corrections.append((b,evidence))
            if len(corrections)!=1:
                continue
            bar,ev = corrections[0]
            body = score.body
            after = body[:bar.start]+ev['after']+body[bar.end:]
            row = score.row
            proposals.append(dict(tune_id=row['tune_id'],setting_id=score.id,name=row['name'],
                original_contributor=row['username'],
                source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{score.id}",
                category=ev['rule'],before_abc=body,after_abc=after,
                before_sha256=sha(body),after_sha256=sha(after),evidence=[ev]))
            stats[ev['rule']]+=1
    return proposals,dict(stats)
