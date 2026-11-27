#!/usr/bin/env python3
"""Summarize parser diagnostics and compare them with the existing review."""

from collections import defaultdict
import csv
import json
from pathlib import Path
import re

from scan import ROOT, rows, unique_settings


def category(message):
    lower = message.lower()
    if 'bar ' in lower and ('time units' in lower or ' is ' in lower):
        return 'Measure duration'
    if 'tie' in lower and ('tied' in lower or 'note' in lower or 'bad tie' in lower):
        return 'Tie target'
    if 'triplet' in lower or 'tuple' in lower:
        return 'Tuplet notation'
    if 'broken rhythm' in lower:
        return 'Broken rhythm'
    if 'properly closed' in lower or 'closing quote' in lower:
        return 'Unclosed chord annotation'
    if 'chord' in lower or 'guitar' in lower:
        return 'Chord or annotation syntax'
    if 'grace' in lower:
        return 'Grace-note syntax'
    if 'duration not representable' in lower:
        return 'Display duration'
    if 'bar symbol' in lower or 'bar type' in lower:
        return 'Barline compatibility'
    if 'repeat' in lower or '|:' in lower or ':|' in lower or 'variant ending' in lower:
        return 'Repeat or ending structure'
    if 'pitch specifier' in lower or 'malformed note' in lower:
        return 'Note syntax'
    if 'decoration' in lower:
        return 'Decoration compatibility'
    if 'character' in lower or 'stray' in lower:
        return 'Ignored or unsupported character'
    if 'exit code' in lower or 'exception' in lower or 'typeerror' in lower or 'timeout' in lower:
        return 'Parser process or exception'
    return 'Other diagnostic'


def main():
    folder = ROOT/'reports/parser-audit'
    records = unique_settings(rows(ROOT/'json/tunes.json'))
    known = {json.loads(line)['setting_id'] for line in (ROOT/'reports/findings.jsonl').open()}
    by_parser, by_category, unknown, sources = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    messages = defaultdict(list)
    findings = []
    for filename in ('native-diagnostics.jsonl', 'abcjs-diagnostics.jsonl'):
        for line in (folder/filename).open():
            record = json.loads(line)
            sid = record['setting_id']
            for diagnostic in record['diagnostics']:
                if isinstance(diagnostic,dict):
                    parser, message = diagnostic['parser'],diagnostic['message']
                else:
                    parser, message = 'abcjs',diagnostic
                kind = category(message)
                by_parser[parser].add(sid)
                by_category[kind].add(sid)
                sources[kind].add(parser)
                messages[sid].append((parser,kind,message))
                if sid not in known:
                    unknown[kind].add(sid)
    for sid, diagnostics in sorted(messages.items(), key=lambda item:int(item[0])):
        kinds = sorted({kind for _,kind,_ in diagnostics})
        row = records[sid]
        findings.append(dict(setting_id=sid,tune_id=row['tune_id'],
            previous_finding=sid in known,parsers='; '.join(sorted({p for p,_,_ in diagnostics})),
            categories='; '.join(kinds),diagnostic_count=len(diagnostics),
            source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{sid}"))
    with (folder/'settings.csv').open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(findings[0]),lineterminator='\n')
        writer.writeheader()
        writer.writerows(findings)
    new_ids = set(messages)-known
    # Both parser implementations must explicitly diagnose the unclosed quote.
    confirmed = [sid for sid in sorted(new_ids,key=int)
                 if {'abcjs','abc2midi'} <= {p for p,k,_ in messages[sid] if k=='Unclosed chord annotation'}]
    summary = dict(settings_checked=len(records),settings_flagged=len(messages),
        settings_new_to_existing_scan=len(new_ids),
        parsers={p:dict(flagged=len(ids),new_to_existing_scan=len(ids-known)) for p,ids in by_parser.items()},
        categories={k:dict(settings=len(v),new_to_existing_scan=len(unknown[k]),parsers=sorted(sources[k]))
                    for k,v in sorted(by_category.items(),key=lambda item:-len(item[1]))},
        confirmed_new_unclosed_annotations=confirmed,
        source_abc_modified=False,
        caveats=['abc2midi and abc2abc are part of the same abcmidi project.',
                 'Diagnostics are review candidates. Counts overlap and include valid pickups and parser limitations.',
                 'New means absent from the current findings.jsonl, not newly introduced by recent corrections.',
                 'Every parser received an explicit L:1/8 header, matching the existing library interpretation.'])
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines = ['# Additional ABC parser review','',
        f"Checked {len(records):,} distinct settings at commit f321390.",
        'Used abc2midi 5.03 (check-only mode), abc2abc 2.22, and abcjs 6.5.2. Each setting was checked independently.',
        'abc2midi and abc2abc share the abcmidi codebase. abcjs provides the independent parser comparison.',
        'The ABC body was preserved. Every parser received explicit meter, key and L:1/8 headers.','',
        '| Parser | Settings with diagnostics | Absent from previous findings |',
        '|---|---:|---:|']
    for name in ('abc2midi','abc2abc','abcjs'):
        ids=by_parser[name]
        lines.append(f'| {name} | {len(ids):,} | {len(ids-known):,} |')
    lines += ['',f"The combined review contains {len(messages):,} settings. Of these, {len(new_ids):,} were absent from the current findings.jsonl.",
        'These are diagnostic counts, not confirmed error counts. A setting can appear under several categories.',
        'Short measures, incomplete repeats, unsupported decorations and engraving limitations require musical or specification review.','',
        '| Diagnostic category | Settings | Absent from previous findings |','|---|---:|---:|']
    for kind,item in summary['categories'].items():
        lines.append(f"| {kind} | {item['settings']:,} | {item['new_to_existing_scan']:,} |")
    lines += ['','## Newly confirmed annotation defects','',
              'abcjs and abc2midi both report unclosed quoted annotations in the following settings. The intended annotation boundaries still need reference checking.','',
              '| Setting | Tune | Source |','|---|---|---|']
    for sid in confirmed:
        tune=records[sid]['tune_id']
        lines.append(f'| {sid} | {tune} | [Original](https://thesession.org/tunes/{tune}#setting{sid}) |')
    lines += ['','## Additional examples','',
        '- Settings 20630, 20632, 20633 and 20640 contain the form (3). abcjs reports the closing parenthesis as an ignored character. abc2midi accepts this form, so the intended slur or tuplet notation needs checking.',
        '- Setting 37512 contains an incomplete explicit tuplet field. abcjs expects a number after the colon. abc2midi emits no diagnostic for this case.',
        '- Unknown bar symbols and unrepresentable display durations can reflect parser behavior. The original ABC and musical phrase must be checked before changing notes or repeats.','',
        '## Files','',
        '- [All flagged settings](settings.csv), including source links and previous-review coverage.',
        '- [Machine-readable summary](summary.json).',
        '- [abc2midi and abc2abc diagnostics](native-diagnostics.jsonl).',
        '- [abcjs diagnostics](abcjs-diagnostics.jsonl).',
        '- [Native parser versions and input hash](native-summary.json).','',
        'Run from the data fork, with the TradMate checkout two directories above it.','',
        '```bash',
        'python3 tools/audit_parsers.py --output reports/parser-audit',
        'node tools/audit_abcjs.js ../../third_party/abcjs/abcjs-basic-min.js json/tunes.json reports/parser-audit/abcjs-diagnostics.jsonl 2> reports/parser-audit/abcjs-progress.jsonl',
        'python3 tools/summarize_parsers.py',
        '```','',
        'No score corrections were applied during this audit.','']
    (folder/'README.md').write_text('\n'.join(lines))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('categories','caveats')},indent=2))


if __name__ == '__main__':
    main()
