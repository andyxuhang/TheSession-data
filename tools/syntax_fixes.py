"""Find stray notation and invalid ties in otherwise matching ABC measures."""

from collections import Counter, defaultdict
import re

from matching_phrases import Score, compact, separate_occurrence
from pitch_fixes import PITCH, key_signature, resolve_pitches
from scan import MASK, NOTE, parse_bar, sha


SYNTAX_RULES = {'orphan_symbol', 'split_note_token', 'invalid_tie'}
ORPHAN = re.compile(r"""unsupported syntax (['"])([/,#0-9])\1""")


def matching_boundary(score, i, ref, j):
    target = score.bars[i-1:i+2]
    witness = ref.bars[j-1:j+2]
    return all((a.left,a.right) == (b.left,b.right) for a,b in zip(target,witness))


def extends_phrase(score, i, ref, j):
    for distance in (-2,2):
        a,b = i+distance,j+distance
        if (0 <= a < len(score.bars) and 0 <= b < len(ref.bars)
                and score.full[a] and ref.full[b] and len(score.bars[a].events) >= 3
                and score.signatures[a] == ref.signatures[b]
                and (score.bars[a].left,score.bars[a].right) == (ref.bars[b].left,ref.bars[b].right)):
            return True
    return False


def without_notation(text):
    return MASK.sub(lambda m: ' '*len(m[0]),text)


def edits_for_measure(score, i, key):
    bar = score.bars[i]
    text = score.body[bar.start:bar.end]
    masked = without_notation(text)
    # ABC operators in ornaments, annotations and comments are outside the melody.
    if match := ORPHAN.fullmatch(bar.error):
        symbol = match[2]
        for at,char in enumerate(masked):
            if char != symbol:
                continue
            # A comma or slash already attached to a note is meaningful.
            if symbol in ',/' and at > 0 and not masked[at-1].isspace() and masked[at-1] not in '(|':
                continue
            fragment = text[:at]+text[at+1:]
            parsed = parse_bar(fragment, 0, bar.left, bar.right)
            if not parsed.error and parsed.duration == score.unit:
                yield 'orphan_symbol',fragment,parsed.signature
        # A space inside a note token can separate an octave mark or duration
        # from the note. Require the joined token to consume the orphan.
        for gap in re.finditer(r"[ \t]+(?=[/,0-9])",masked):
            a,b = gap.span()
            if masked[b]!=symbol:
                continue
            fragment = text[:a]+text[b:]
            joined = without_notation(fragment)
            if not any(note.start()<a<note.end() for note in NOTE.finditer(joined)):
                continue
            parsed = parse_bar(fragment, 0, bar.left, bar.right)
            if not parsed.error and parsed.duration == score.unit:
                yield 'split_note_token',fragment,parsed.signature
        return
    if bar.error or bar.duration != score.unit or not bar.events:
        return
    if any(not PITCH.fullmatch(event.pitch) for event in bar.events):
        return
    midi = resolve_pitches(bar.events,key)
    for n,(a,b) in enumerate(zip(bar.events,bar.events[1:])):
        if not a.tied or midi[n]==midi[n+1]:
            continue
        start,end = a.end-bar.start,b.start-bar.start
        gap = masked[start:end]
        if gap.strip() != '-':
            continue
        at = start+gap.index('-')
        fragment = text[:at]+text[at+1:]
        parsed = parse_bar(fragment,0,bar.left,bar.right)
        if not parsed.error and parsed.duration == score.unit:
            yield 'invalid_tie',fragment,parsed.signature


def find_reference(score, i, options, index):
    candidates = defaultdict(list)
    a,b = score.bars[i-1],score.bars[i+1]
    for ref,j in index.get((a.signature,b.signature),()):
        if not matching_boundary(score,i,ref,j) or not separate_occurrence(score,i,i+1,ref,j,j+1):
            continue
        other = ref.bars[j]
        spelling = compact(ref.body[other.start:other.end])
        for rule,fragment,signature in options:
            if compact(fragment)==spelling and signature==other.signature:
                candidates[rule,fragment].append((ref,j))
    if len(candidates)==1:
        (rule,fragment),refs = next(iter(candidates.items()))
        return rule,fragment,refs
    return None


def scan_syntax(data, upstream):
    groups = defaultdict(list)
    for row in data:
        groups[row['tune_id'],row['meter'],row['mode'],row['type']].append(row)
    proposals, stats = [], Counter()
    for (_,_,mode,_), group in groups.items():
        key = key_signature(mode)
        if key is None:
            continue
        targets, index = [], defaultdict(list)
        for row in group:
            score = Score(row)
            if not score.unit or sum(score.full)<5 or re.search(r'(?m)^\s*%%',score.body):
                continue
            original = upstream.get(score.id)
            if not original or any(row[k]!=original[k] for k in ('tune_id','meter','mode','type')):
                continue
            targets.append(score)
            if score.body!=original['abc']:
                continue
            for i in range(1,len(score.bars)-1):
                if all(score.full[i-1:i+2]) and score.plain_span(i-1,i+2):
                    index[score.signatures[i-1],score.signatures[i+1]].append((score,i))
        for score in targets:
            corrections = []
            for i in range(1,len(score.bars)-1):
                if (not score.full[i-1] or not score.full[i+1] or not score.plain_span(i-1,i+2)
                        or min(len(score.bars[i-1].events),len(score.bars[i+1].events))<3):
                    continue
                options = list(edits_for_measure(score,i,key))
                if not options:
                    continue
                stats['marked_measures']+=1
                result = find_reference(score,i,options,index)
                if result is None:
                    continue
                rule,fragment,refs = result
                contributors = {ref.row['username'] for ref,j in refs if ref.row['username']!=score.row['username']}
                own = {j for ref,j in refs if ref.id==score.id}
                extended = any(extends_phrase(score,i,ref,j) for ref,j in refs)
                stats[rule+'_matching_measure']+=1
                if not (len(contributors)>=2 or (contributors and (own or extended)) or len(own)>=2):
                    continue
                bar = score.bars[i]
                evidence = {
                    'rule':rule,'bar':i+1,'before':score.body[bar.start:bar.end],'after':fragment,
                    'reference_ranges':sorted({(ref.id,j+1,j+1) for ref,j in refs}),
                    'corroborating_contributors':len(contributors),
                    'written_repetitions':len(own),'extra_matching_bar':extended,
                }
                corrections.append((bar.start,bar.end,fragment,evidence))
            if corrections:
                body=score.body
                for start,end,fragment,_ in reversed(corrections):
                    body = body[:start]+fragment+body[end:]
                row=score.row
                evidence=[e for _,_,_,e in corrections]
                proposals.append(dict(tune_id=row['tune_id'],setting_id=score.id,name=row['name'],
                    original_contributor=row['username'],
                    source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{score.id}",
                    category='+'.join(sorted({e['rule'] for e in evidence})),
                    before_abc=score.body,after_abc=body,before_sha256=sha(score.body),
                    after_sha256=sha(body),evidence=evidence))
    return proposals,dict(stats)
