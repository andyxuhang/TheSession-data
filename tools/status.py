#!/usr/bin/env python3
"""Write the current list of fixes, unresolved findings and excluded cases."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from scan import ROOT, measures, rows, sha, unique_settings


LABELS = {
    'missing_barline': 'Missing barline',
    'misplaced_barline': 'Misplaced barline',
    'note_length': 'Incorrect note length',
    'proven_long_note': 'Incorrect note length',
    'rhythm_mark': 'Incorrect broken-rhythm or tuplet mark',
    'accidental_typo': 'Incorrect accidental',
    'octave_typo': 'Incorrect octave',
    'missing_note': 'Omitted note',
    'stray_control': 'Stray control character',
    'missing_triplet': 'Omitted triplet mark',
    'missing_note_length_slash': 'Missing duration slash',
    'extra_note_length_digit': 'Extra duration digit',
    'short_bar': 'Short interior measure',
    'long_bar': 'Overfull interior measure',
    'meter_signature': 'Meter or form to review',
    'interior_short_bar': 'Possible short interior measure',
    'overfull_short_note_run': 'Possible incorrect short-note duration',
    'shifted_barline': 'Possible misplaced barline',
    'witnessed_broken_tail': 'Possible broken-rhythm marking error',
    'source_specific_correction': 'Earlier setting-specific finding',
    'missing_short_triplet': 'Possible missing triplet mark',
    'parser_rejected': 'Playback check failed',
}


def write_csv(path, records, fields):
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--findings',type=Path,default=ROOT/'reports/findings.jsonl')
    args=parser.parse_args()
    exported=list(rows(ROOT/'json/tunes.json'))
    byid=unique_settings(exported)
    data=list(byid.values())
    findings=defaultdict(list)
    for line in args.findings.read_text().splitlines():
        issue=json.loads(line);findings[issue['setting_id']].append(issue)
    plans=[json.loads(p.read_text()) for p in sorted((ROOT/'changes').glob('*.json'))]
    fixed={}
    types=Counter()
    for plan in plans:
        for patch in plan['corrections']:
            sid=patch['setting_id']
            evidence=patch['evidence']
            rules=[e['rule'] for e in evidence] if isinstance(evidence,list) else [patch['category']]
            types.update('note_length' if r in {'missing_note_length_slash','extra_note_length_digit'} else r for r in rules)
            if sid in fixed:
                patch={**patch,'before_abc':fixed[sid]['before_abc']}
                rules=sorted(set(rules+fixed[sid]['rules']))
            fixed[sid]={**patch,'rules':rules}
    old_flags={}
    flagpath=ROOT/'checks/previous-flags.json'
    if flagpath.exists():
        for flag in json.loads(flagpath.read_text())['settings']:
            r=byid.get(flag['setting_id'])
            if r and sha(r['abc'].replace('\r\n','\n').strip())==flag['body_sha256']:
                old_flags[r['setting_id']]=flag
    rejectedpath=ROOT/'checks/rejected.json'
    rejected={r['setting_id']:r for r in json.loads(rejectedpath.read_text())} if rejectedpath.exists() else {}
    groups={k:[] for k in ('fixed','review','boundaries','unsupported','playback')}
    common=['tune_id','setting_id','name','contributor','source_url','types','details','current_abc']
    for row in data:
        sid=row['setting_id']
        base={'tune_id':row['tune_id'],'setting_id':sid,'name':row['name'],'contributor':row['username'],
              'source_url':f"https://thesession.org/tunes/{row['tune_id']}#setting{sid}", 'current_abc':row['abc']}
        if sid in fixed:
            p=fixed[sid]
            assert row['abc']==p['after_abc'], 'Report does not match current data: '+sid
            groups['fixed'].append({**base,'types':'; '.join(LABELS.get(k,k) for k in p['rules']),
                                     'details':json.dumps(p['evidence'],ensure_ascii=False), 'before_abc':p['before_abc']})
        unsupported=[i for i in findings[sid] if i['category']=='unsupported']
        irregular=[i for i in findings[sid] if i['category']!='unsupported']
        internal,boundary=[],[]
        if irregular:
            bars,_=measures(row['abc'])
            for item in irregular:
                index=item['bar']-1
                b=bars[index]
                if index==0 or index==len(bars)-1 or b.left!='|' or b.right!='|':
                    boundary.append(item)
                else:
                    internal.append(item)
        flags=old_flags.get(sid,{})
        # Tie and ending spacing are parser compatibility observations, not
        # proof of a wrong source transcription.
        source_rules=[r for r in flags.get('source_rules',[]) if r not in {'tie_spacing','ending_spacing'}]
        if internal or source_rules or sid in rejected:
            kinds=set(source_rules)
            for issue in internal:
                from fractions import Fraction
                kinds.add('short_bar' if Fraction(issue['duration_eighths'])<Fraction(issue['expected_eighths']) else 'long_bar')
            detail={'current_internal_bars':internal,'previous_source_flags':source_rules}
            if sid in rejected:
                kinds.add('parser_rejected');detail['playback_rejection']=rejected[sid]['reason']
            groups['review'].append({**base,'types':'; '.join(LABELS.get(k,k) for k in sorted(kinds)),
                                      'details':json.dumps(detail,ensure_ascii=False)})
        if boundary:
            groups['boundaries'].append({**base,'types':'Pickup, ending or repeat boundary',
                                          'details':json.dumps(boundary,ensure_ascii=False)})
        if unsupported:
            groups['unsupported'].append({**base,'types':'Unsupported syntax or empty melody',
                                           'details':json.dumps(unsupported,ensure_ascii=False)})
        compatibility=flags.get('app_rules',[])+[r for r in flags.get('source_rules',[]) if r in {'tie_spacing','ending_spacing'}]
        if compatibility:
            groups['playback'].append({**base,'types':'; '.join(sorted(set(compatibility))),
                                        'details':'Playback or parser compatibility observation.'})
    out=ROOT/'reports';out.mkdir(exist_ok=True)
    for name,records in groups.items():
        write_csv(out/(name+'.csv'),records,common+(['before_abc'] if name=='fixed' else []))
    flagged={r['setting_id'] for k,v in groups.items() if k!='fixed' for r in v}
    summary={'settings_checked':len(data),'exported_tune_rows':len(exported),'tunes_checked':len({r['tune_id'] for r in data}),
             'fixed_settings':len(groups['fixed']),'fixed_tunes':len({r['tune_id'] for r in groups['fixed']}),
             'fixed_edits_by_type':dict(types), 'categories':{k:len(v) for k,v in groups.items()},
             'no_current_findings':len(data)-len(flagged),'rejected_settings':len(rejected),
             'counts_overlap':True}
    review_ids={r['setting_id'] for r in groups['review']}
    summary['fixed_with_remaining_review']=len(set(fixed)&review_ids)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    lines = [
        '# Notation review', '',
        f"Scanned {len(data):,} distinct settings of {summary['tunes_checked']:,} tunes. "
        f"The exports contain {len(exported):,} tune rows, including separate composer rows for some settings.",
        '',
        '| Status | Settings | Details |',
        '|---|---:|---|',
        f"| Corrected | {len(groups['fixed'])} | [fixed.csv](fixed.csv) |",
        f"| Needs review | {len(groups['review'])} | [review.csv](review.csv) |",
        f"| Pickups, endings and repeats | {len(groups['boundaries'])} | [boundaries.csv](boundaries.csv) |",
        f"| Unsupported syntax or empty melody | {len(groups['unsupported'])} | [unsupported.csv](unsupported.csv) |",
        f"| Playback or parser compatibility | {len(groups['playback'])} | [playback.csv](playback.csv) |",
        '',
        f"{summary['fixed_with_remaining_review']} corrected settings still have other findings. "
        "Settings can appear in multiple categories. Each CSV gives the source link and current ABC. "
        "The corrected list also gives the ABC before the changes.",
        '',
        '## Corrections by type', '',
        '| Type | Corrections |', '|---|---:|',
    ]
    for rule, count in types.most_common():
        lines.append(f"| {LABELS.get(rule,rule)} | {count} |")
    lines += [
        '', '## How corrections are checked', '',
        '- The scanner adds note lengths as exact fractions and compares neighboring written passages.',
        '- Complete measures in another passage support barline and timing corrections. '
        'A line break between two complete measures can also support a missing divider when '
        'one of those measures and its neighbor match a written reference.',
        '- A missing note requires the same completed phrase and both neighboring measures '
        'in settings from at least two other contributors.',
        '- An accidental or octave correction requires matching written phrases from independent contributors. '
        'Playback checks require the intended pitch change and preserve every other event.',
        '- Playback checks compare the original and corrected events with automatic repair disabled. '
        'Unexpected changes to pitch, duration, rests or ties block a correction.',
        '- After each round the scanner checks for further corrections. CSV, JSON and SQLite are compared record by record.',
        '',
        f"Playback checks left candidates in {len(rejected)} settings for review. "
        "See [rejected.json](../checks/rejected.json) for the recorded reasons.",
        '',
        '## Examples for review', '',
        '| Tune | Setting | Finding |', '|---|---|---|',
    ]
    for r in groups['review'][:25]:
        name=r['name'].replace('|','\\|')
        lines.append(f"| {name} | [{r['setting_id']}]({r['source_url']}) | {r['types']} |")
    lines += ['', 'For full details see the CSV files, [patches](../changes/) and [verification results](../checks/).', '']
    (out/'status.md').write_text('\n'.join(lines))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
