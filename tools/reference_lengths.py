"""Correct a single duration from an otherwise matching written phrase."""

from collections import Counter, defaultdict
import re

from matching_phrases import (Score, compact, matches_more_transposed_music, normalize_note_names,
                              relative_phrase_key, separate_occurrence)
from note_count_fixes import phrase_key
from scan import NOTE, measures, parse_bar, sha
from syntax_fixes import edits_for_measure, extends_phrase
from pitch_fixes import key_signature


def recognized_readings(score, i, ref, j, transposed=False):
    bar, other = score.bars[i], ref.bars[j]
    before = score.body[bar.start:bar.end]
    normalize = normalize_note_names if transposed else compact
    expected = normalize(ref.body[other.start:other.end])
    if bar.error:
        if transposed:
            return
        key = key_signature(score.row['mode'])
        for rule,fragment,signature in edits_for_measure(score,i,key):
            if rule != 'split_note_token' or compact(fragment)!=expected or signature!=other.signature:
                continue
            parsed = parse_bar(fragment,0,bar.left,bar.right)
            for event in parsed.events:
                token = fragment[event.start:event.end]
                old = NOTE.match(before,event.start)
                if not old or old['pitch']!=event.pitch or old[0]==token:
                    continue
                gap = re.match(r'[ \t]+',before[old.end():])
                if not gap:
                    continue
                join = old.end()+gap.end()
                if before[:old.end()]+before[join:]!=fragment:
                    continue
                original = parse_bar(before[:old.end()]+before[join+len(token)-len(old[0]):],0,bar.left,bar.right)
                if (original.error or len(original.events)!=len(parsed.events)
                        or sum(a.duration!=b.duration for a,b in zip(original.events,parsed.events))!=1):
                    continue
                a,b = next((a,b) for a,b in zip(original.events,parsed.events) if a.duration!=b.duration)
                if (a.start!=event.start or b.start!=event.start or a.pitch!=b.pitch
                        or a.tied or b.tied or a.broken or b.broken or a.tuplet or b.tuplet):
                    continue
                yield fragment,old[0],token,event.start,str(a.duration),str(b.duration),'split_note_token'
        return
    if (len(bar.events)!=len(other.events)
            or any((not transposed and a.pitch!=b.pitch) or a.tied!=b.tied
                   for a,b in zip(bar.events,other.events))):
        return
    differences = [(a,b) for a,b in zip(bar.events,other.events) if a.duration!=b.duration]
    if len(differences)!=1:
        return
    a,b = differences[0]
    if (a.length==b.length or a.tied or b.tied or a.broken or b.broken or a.tuplet or b.tuplet
            or a.pitch[0] in 'xz'):
        return
    fragment = score.body[bar.start:a.length_start]+b.length+score.body[a.end:bar.end]
    if normalize(fragment)==expected:
        yield (fragment,score.body[a.start:a.end],a.pitch+b.length,a.start-bar.start,
               str(a.duration),str(b.duration),'note_length')


def find_edit(score,i,index,transposed_index):
    readings = defaultdict(list)
    for ref,j in index.get((score.row['mode'],phrase_key(score,i)),()):
        if not separate_occurrence(score,i,i+1,ref,j,j+1):
            continue
        for edit in recognized_readings(score,i,ref,j):
            readings[edit].append((ref,j,False))
    for ref,j in transposed_index.get(relative_phrase_key(score,i),()):
        if ref.row['mode']==score.row['mode'] or ref.row['username']==score.row['username']:
            continue
        if not matches_more_transposed_music(score,i,ref,j):
            continue
        for edit in recognized_readings(score,i,ref,j,transposed=True):
            readings[edit].append((ref,j,True))
    if len(readings)!=1:
        return None
    (fragment,old,new,at,old_duration,new_duration,rule),refs = next(iter(readings.items()))
    contributors = {ref.row['username'] for ref,_,_ in refs if ref.row['username']!=score.row['username']}
    own = any(ref.id==score.id for ref,_,_ in refs)
    longer = any(transposed or extends_phrase(score,i,ref,j) for ref,j,transposed in refs)
    if not (len(contributors)>=2 or (longer and (contributors or own))):
        return None
    bar = score.bars[i]
    return dict(rule=rule,bar=i+1,before=score.body[bar.start:bar.end],after=fragment,
        token_offset=at,old_token=old,new_token=new,old_duration_eighths=old_duration,
        new_duration_eighths=new_duration,reference_ranges=sorted({(ref.id,j+1,j+1) for ref,j,_ in refs}),
        transposed_references=sorted({ref.id for ref,_,transposed in refs if transposed}),
        corroborating_contributors=len(contributors),written_repeat=own,extra_matching_bar=longer)


def revisit_duration_edits(data, rejected, exclude):
    """Retest earlier written references using exact sounding-note checks."""
    indexed = {row['setting_id']:row for row in data}
    results = []
    for item in rejected:
        setting_id = item['setting_id']
        if setting_id in exclude or setting_id not in indexed:
            continue
        row = indexed[setting_id]
        body = row['abc']
        bars,_ = measures(body)
        candidates = []
        for failure in item.get('bars',[]):
            e = failure['edit']
            if e['rule']!='note_length' or not e.get('reference_ranges') or e.get('last_bar',e['bar'])!=e['bar']:
                continue
            i = e['bar']-1
            if i>=len(bars):
                continue
            bar = bars[i]
            if bar.error or body[bar.start:bar.end]!=e['before']:
                continue
            revised = parse_bar(e['after'],0,bar.left,bar.right)
            if revised.error or len(bar.events)!=len(revised.events) or revised.duration!=Score(row).unit:
                continue
            changed = [(a,b) for a,b in zip(bar.events,revised.events) if a.duration!=b.duration]
            if len(changed)!=1:
                continue
            a,b = changed[0]
            old,new = body[a.start:a.end],e['after'][b.start:b.end]
            if (a.start-bar.start!=b.start or a.tied or b.tied
                    or body[bar.start:a.start]+new+body[a.end:bar.end]!=e['after']):
                continue
            candidates.append((bar,{**e,'token_offset':b.start,'old_token':old,'new_token':new,
                'old_duration_eighths':str(a.duration),'new_duration_eighths':str(b.duration)}))
        if not candidates:
            continue
        candidates.sort(key=lambda entry:entry[0].start)
        if len({bar.start for bar,_ in candidates})!=len(candidates):
            continue
        after = body
        for bar,e in reversed(candidates):
            after = after[:bar.start]+e['after']+after[bar.end:]
        results.append(dict(tune_id=row['tune_id'],setting_id=setting_id,name=row['name'],
            original_contributor=row['username'],
            source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{setting_id}",
            category='note_length',before_abc=body,after_abc=after,before_sha256=sha(body),
            after_sha256=sha(after),evidence=[e for _,e in candidates]))
    return results


def scan_reference_lengths(data, upstream, rejected=()):
    groups = defaultdict(list)
    for row in data:
        if key_signature(row['mode']) is not None:
            family = re.sub(r'^[A-G][#b]?','',row['mode'])
            groups[row['tune_id'],row['meter'],family,row['type']].append(row)
    proposals,stats = [],Counter()
    for group in groups.values():
        targets,index,transposed_index = [],defaultdict(list),defaultdict(list)
        multiple_keys = len({r['mode'] for r in group})>1
        for row in group:
            original = upstream.get(row['setting_id'])
            if not original or any(row[k]!=original[k] for k in ('tune_id','meter','mode','type','abc')):
                continue
            score = Score(row)
            if not score.unit or sum(score.full)<5 or '\n%%' in score.body or score.body.startswith('%%'):
                continue
            if not all(score.full):
                targets.append(score)
            for i in range(1,len(score.bars)-1):
                a,b,c = score.bars[i-1:i+2]
                if all(score.full[i-1:i+2]) and min(len(a.events),len(c.events))>=3:
                    index[score.row['mode'],phrase_key(score,i)].append((score,i))
                    if multiple_keys and (key := relative_phrase_key(score,i)):
                        transposed_index[key].append((score,i))
        for score in targets:
            changes = []
            for i in range(1,len(score.bars)-1):
                a,bar,b = score.bars[i-1:i+2]
                if (score.full[i] or not score.full[i-1] or not score.full[i+1]
                        or min(len(a.events),len(b.events))<3 or a.events[-1].tied
                        or bar.left not in ('|','|:',':|:','||') or bar.right not in ('|',':|',':|:','||','|]')):
                    continue
                evidence = find_edit(score,i,index,transposed_index)
                if evidence:
                    changes.append((bar,evidence))
            if len(changes)!=1:
                continue
            bar,ev = changes[0]
            body = score.body
            after = body[:bar.start]+ev['after']+body[bar.end:]
            row = score.row
            proposals.append(dict(tune_id=row['tune_id'],setting_id=score.id,name=row['name'],
                original_contributor=row['username'],
                source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{score.id}",
                category=ev['rule'],before_abc=body,after_abc=after,
                before_sha256=sha(body),after_sha256=sha(after),evidence=[ev]))
            stats[ev['rule']]+=1
    revisited = revisit_duration_edits(data,rejected,{p['setting_id'] for p in proposals})
    stats['deferred_settings_compared'] = len(revisited)
    return proposals+revisited,dict(stats)
