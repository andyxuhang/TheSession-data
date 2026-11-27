"""Review isolated accidental and octave changes against transposed settings."""

from collections import Counter, defaultdict
from dataclasses import replace
import re

from matching_phrases import Score, normalize_note_names, rhythm
from pitch_fixes import NATURAL, PITCH, key_signature, resolve_pitches, split_pitch, windows
from scan import sha

MODE = re.compile(r'([A-G])([#b]?)(major|minor|dorian|mixolydian|aeolian)')


def tonic_semitone(score):
    match = MODE.fullmatch(score.row['mode'])
    return NATURAL[match[1]] + {'#':1,'b':-1,'':0}[match[2]]


def degree(event, score):
    _,letter,octave = split_pitch(event.pitch)
    return 'CDEFGAB'.index(letter)-'CDEFGAB'.index(score.row['mode'][0])+7*(octave-4)


def comparable_measures(score):
    key = key_signature(score.row['mode'])
    tonic = tonic_semitone(score)
    comparisons = []
    for bar in score.bars:
        if bar.error or not all(PITCH.fullmatch(e.pitch) for e in bar.events):
            comparisons.append(None)
            continue
        midi = resolve_pitches(bar.events,key)
        comparisons.append((tuple(m-tonic for m in midi),rhythm(bar.events),
                            bar.left,bar.right,tuple(degree(e,score) for e in bar.events)))
    return comparisons


def fourth_measure(score,i,sigs,ref,j,refs):
    for delta in (-2,2):
        a,b = i+delta,j+delta
        if (0<=a<len(sigs) and 0<=b<len(refs) and score.full[a] and ref.full[b]
                and sigs[a] is not None and sigs[a]==refs[b] and len(score.bars[a].events)>=4):
            return True
    return False


def written_pitch(letter, octave):
    return letter.lower()+"'"*(octave-1) if octave>0 else letter+','*(-octave)


def explicit_or_implied(pitch, accidental):
    return [pitch,{-1:'_',0:'=',1:'^'}[accidental]+pitch] if accidental in (-1,0,1) else []


def edits_for_reading(score,i,comparison,ref,j,expected):
    source,guide = score.bars[i],ref.bars[j]
    present,desired = comparison[0],expected[0]
    if len(present)!=len(desired) or len(present)!=len(source.events):
        return
    differences = [n for n,(a,b) in enumerate(zip(present,desired)) if a!=b]
    if len(differences)!=1:
        return
    n = differences[0]
    event = source.events[n]
    change = desired[n]-present[n]
    isolated = (0<n<len(present)-1
                and all(abs(present[n]-present[k])>=8 and abs(desired[n]-desired[k])<=5 for k in (n-1,n+1)))
    if comparison[4][:n]+comparison[4][n+1:] != expected[4][:n]+expected[4][n+1:]:
        return
    mark,letter,octave = split_pitch(event.pitch)
    if abs(change)==1 and comparison[4]==expected[4]:
        accidental = desired[n]+tonic_semitone(score) - (12*(octave+1)+NATURAL[letter])
        candidates = explicit_or_implied(re.sub(r'^[=^_]+','',event.pitch),accidental)
        rule = 'accidental_typo'
    elif abs(change)==12 and isolated and comparison[4][n]+change//12*7==expected[4][n]:
        candidates = [(mark or '')+written_pitch(letter,octave+change//12-4)]
        rule = 'octave_typo'
    elif isolated and expected[4][n]%7!=comparison[4][n]%7:
        octave,step = divmod('CDEFGAB'.index(score.row['mode'][0])+expected[4][n],7)
        letter = 'CDEFGAB'[step]
        accidental = desired[n]+tonic_semitone(score) - (12*(octave+5)+NATURAL[letter])
        candidates = explicit_or_implied(written_pitch(letter,octave),accidental)
        rule = 'note_typo'
    else:
        return
    tonic = tonic_semitone(score)
    key = key_signature(score.row['mode'])
    for pitch in candidates:
        events = source.events[:n]+[replace(event,pitch=pitch)]+source.events[n+1:]
        if tuple(m-tonic for m in resolve_pitches(events,key))!=desired:
            continue
        fragment=score.body[source.start:event.start]+pitch+score.body[event.length_start:source.end]
        if normalize_note_names(fragment)!=normalize_note_names(ref.body[guide.start:guide.end]):
            continue
        yield n,rule,fragment,present[n]+tonic,desired[n]+tonic
        break


def scan_transposed_pitches(data, upstream):
    groups = defaultdict(list)
    for row in data:
        match = MODE.fullmatch(row['mode'])
        if match and key_signature(row['mode']) is not None:
            groups[row['tune_id'],row['meter'],row['type'],match[3]].append(row)
    proposals, stats = [], Counter()
    for group in groups.values():
        if len({r['mode'] for r in group})<2 or len({r['username'] for r in group})<3:
            continue
        index,targets = defaultdict(list),[]
        for row in group:
            original = upstream.get(row['setting_id'])
            if not original or any(row[key]!=original[key] for key in ('tune_id','type','meter','mode','abc')):
                continue
            score = Score(row)
            if not score.unit or not score.bars or re.search(r'(?m)^\s*%%',score.body):
                continue
            sigs = comparable_measures(score)
            entries = []
            for i,_ in windows(score):
                if all(sigs[i-1:i+2]):
                    key = (sigs[i-1],sigs[i][1],sigs[i+1],sigs[i][2:4])
                    index[key].append((score,i,sigs))
                    entries.append((i,key))
            targets.append((score,sigs,entries))
        for score,sigs,entries in targets:
            changes = []
            for i,key in entries:
                readings = defaultdict(list)
                for ref,j,refs in index[key]:
                    if ref.row['username']==score.row['username'] or not fourth_measure(score,i,sigs,ref,j,refs):
                        continue
                    readings[refs[j][0]].append((ref,j,refs))
                if len(readings)!=1 or sigs[i][0] in readings:
                    continue
                corroboration = defaultdict(list)
                for ref,j,refs in next(iter(readings.values())):
                    for edit in edits_for_reading(score,i,sigs[i],ref,j,refs[j]):
                        corroboration[edit].append((ref,j))
                if len(corroboration)!=1:
                    continue
                (n,rule,fragment,old,new),witnesses = next(iter(corroboration.items()))
                people = {ref.row['username'] for ref,_ in witnesses}
                transposed = sorted({ref.id for ref,_ in witnesses if ref.row['mode']!=score.row['mode']})
                if len(people)<2 or not transposed:
                    continue
                b = score.bars[i]
                ev = dict(rule=rule,bar=i+1,note=n+1,before=score.body[b.start:b.end],after=fragment,
                    before_midi=old,after_midi=new,reference_ranges=sorted({(ref.id,j+1,j+1) for ref,j in witnesses}),
                    transposed_references=transposed,corroborating_contributors=len(people),extra_matching_bar=True)
                changes.append((b,ev))
                stats[rule]+=1
            if not changes:
                continue
            body = score.body
            for b,ev in reversed(changes):
                body = body[:b.start]+ev['after']+body[b.end:]
            row = score.row
            evidence = [ev for _,ev in changes]
            proposals.append(dict(tune_id=row['tune_id'],setting_id=score.id,name=row['name'],
                original_contributor=row['username'],
                source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{score.id}",
                category='+'.join(sorted({e['rule'] for e in evidence})),
                before_abc=score.body,after_abc=body,before_sha256=sha(score.body),
                after_sha256=sha(body),evidence=evidence))
    return proposals,dict(stats)
