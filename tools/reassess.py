#!/usr/bin/env python3
"""Resolve source-format suspicions using independent parser evidence."""

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re

from review_common import review_state
from scan import ROOT, measures, rows, sha, unique_settings
from status import load_previous_flags


def implicit_repeat_warnings(diagnostics):
    allowed = ('Assuming repeat','replacing |: with double repeat (::)',
               'replacing with double repeat (::)')
    for diagnostic in diagnostics:
        message = diagnostic['message']
        if not message.startswith('Warning'):
            return False
        tail = message.split(' : ',1)[-1]
        if tail not in allowed and not re.fullmatch(r'Unexpected :\|[23]? found',tail):
            return False
    return bool(diagnostics)


def comparison_mode(primary, secondary):
    digest = primary.get('comparison_sha256')
    other = secondary.get('comparison') or {}
    if digest and digest == other.get('sha256'):
        return 'Complete written pitches'
    if digest and digest == other.get('first_chord_pitch_sha256'):
        return 'First written chord pitch, matching TradMate melody handling'
    return None


def main():
    folder = ROOT/'reports/reassessment'
    manifest = json.loads((folder/'input.json').read_text())
    expected = {r['setting_id']:r for r in manifest['settings']}
    records = unique_settings(rows(ROOT/'json/tunes.json'))
    tune_counts = Counter(row['tune_id'] for row in records.values())
    primary = {r['setting_id']:r for r in map(json.loads,(folder/'tradmate-status.jsonl').open())}
    secondary = {r['setting_id']:r for r in map(json.loads,(folder/'abcjs-status.jsonl').open())}
    native = {r['setting_id']:r['diagnostics'] for r in map(json.loads,(folder/'native-diagnostics.jsonl').open())}
    native_summary = json.loads((folder/'native-summary.json').read_text())
    assert set(primary) == set(secondary) == set(expected), 'Incomplete parser coverage'
    assert native_summary['settings'] == len(expected) and set(native) <= set(expected)
    findings = defaultdict(list)
    for line in (ROOT/'reports/findings.jsonl').open():
        item = json.loads(line)
        findings[item['setting_id']].append(item)
    flags = load_previous_flags(records)
    additive_path = folder/'additive-meter-check.json'
    additive = {r['setting_id']:r for r in json.loads(additive_path.read_text())
                if r['validated']} if additive_path.exists() else {}
    rejected = {r['setting_id'] for r in json.loads((ROOT/'checks/rejected.json').read_text())}
    destination = ROOT/'checks/reviewed-settings.json'
    previous = json.loads(destination.read_text())['settings'] if destination.exists() else []
    decisions = {r['setting_id']:r for r in previous if r['setting_id'] not in expected}
    totals, cleared, reasons = Counter(), Counter(), Counter()
    for sid,source in expected.items():
        row = records[sid]
        assert (sha(row['abc']),row['meter'],row['mode'],row['type']) == (
            source['body_sha256'],source['meter'],source['mode'],source['type']), 'Source changed during reassessment'
        a,b = primary[sid],secondary[sid]
        special = additive.get(sid)
        if special and special['body_sha256'] != sha(row['abc']):
            special = None
        if sid in rejected or (not a['healthy'] and not special) or not b['healthy']:
            continue
        if 'review' in source['categories']:
            bars,_ = measures(row['abc'])
            if any(issue['category']!='unsupported' and
                   0 < issue.get('bar',0)-1 < len(bars)-1 and
                   bars[issue['bar']-1].left == bars[issue['bar']-1].right == '|'
                   for issue in findings[sid]):
                continue
        diagnostics = native.get(sid,[])
        mode = comparison_mode(special['numeric_meter_result'] if special else a,b)
        if diagnostics and (not implicit_repeat_warnings(diagnostics) or mode is None):
            continue
        # Every native duration or syntax error continues to block clearance.
        tier = 'Standard implicit repeat with matching melody' if diagnostics else 'No parser diagnostics'
        categories = [name for name in source['categories'] if name!='playback' or (mode is not None and not special)]
        decision = dict(setting_id=sid,tune_id=row['tune_id'],
            review_state_sha256=review_state(row,findings[sid],flags.get(sid,{})),
            cleared_categories=categories,playback_agreement=mode is not None and not special,
            original_signature_supported=not bool(special),
            reason='Valid notation accepted by independent parsers',
            parser_evidence=tier,comparison_mode=mode,
            comparison_sha256=a.get('comparison_sha256'),
            native_diagnostics=len(diagnostics),
            other_settings_of_same_tune=tune_counts[row['tune_id']]-1)
        if 'unsupported' in categories:
            decision['reason']='Valid ABC construct outside the simple scanner grammar'
        elif 'review' in categories:
            decision['reason']='Meter and form accepted by independent parsers'
        elif 'boundaries' in categories:
            decision['reason']='Accepted pickup, ending or repeat notation'
        decisions[sid]=decision
        if special:
            decision['reason']='Valid additive meter with a TradMate signature compatibility limitation'
            decision['parser_evidence']='Two independent parsers accept the source; equivalent numeric meter matches TradMate'
            decision['additive_meter_evidence']=special
        totals['accepted_formats'] += 1
        totals['matching_base_melody' if mode and not special else 'playback_comparison_to_review'] += 1
        cleared.update(categories)
        reasons[decision['parser_evidence']] += 1
    remaining = 0
    before_counts,after_counts = Counter(),Counter()
    for sid,source in expected.items():
        before_counts.update(source['categories'])
        pending = set(source['categories'])-set(decisions.get(sid,{}).get('cleared_categories',[]))
        if not decisions.get(sid,{}).get('original_signature_supported',True):
            pending.add('playback')
        after_counts.update(pending)
        remaining += bool(pending)
    result = dict(base_commit=manifest['base_commit'],settings_checked=len(expected),
        parser_families=['TradMate','abcjs','abcmidi (abc2midi and abc2abc)'],
        comparison='Decorations excluded, ties joined, onsets and durations rounded to 0.001 quarter notes',
        accepted_by_reason=dict(reasons),cleared_categories=dict(cleared),
        categories_before=dict(before_counts),categories_after=dict(after_counts),
        removed_from_all_pending_categories=len(expected)-remaining,**totals)
    destination.write_text(json.dumps(dict(method=result,settings=sorted(decisions.values(),
        key=lambda r:int(r['setting_id']))),indent=2)+'\n')
    (folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    names = dict(review='Needs review',unsupported='Unsupported syntax or empty melody',
                 boundaries='Pickups, endings and repeats',playback='Playback or parser compatibility')
    lines = ['# Review of the remaining settings','',
        f"Checked all {len(expected):,} distinct settings in the pending categories at commit {manifest['base_commit'][:7]}.",
        'The check used TradMate, abcjs 6.5.2, abc2midi 5.03 and abc2abc 2.22. '
        'The two abcmidi programs share a codebase and count as one parser family.','',
        f"{totals['accepted_formats']:,} settings have accepted source notation. "
        f"{result['removed_from_all_pending_categories']:,} settings leave all existing pending categories.",
        'The source ABC is preserved. Accepted decisions record the exact source and finding state. '
        'New source text, meter, key, tune type or findings invalidate the decision.','',
        '| Category | Before | After |','|---|---:|---:|']
    for key in ('review','unsupported','boundaries','playback'):
        lines.append(f"| {names[key]} | {before_counts[key]:,} | {after_counts[key]:,} |")
    lines += [f"| Parser-reviewed valid notation | 0 | {totals['accepted_formats']:,} |",'',
        'Counts overlap because a setting can have more than one observation.','',
        '## Acceptance evidence','',
        '- Source-format clearance requires working parsers, valid nonempty musical output, and no native syntax or duration errors.',
        '- A restricted group of implicit-repeat warnings is accepted when independent base-melody playback agrees. '
        'ABC permits an omitted opening repeat, with playback restarting at the beginning or the previous repeat boundary.',
        '- Existing internal-measure errors and rejected musical edits continue to require review.',
        '- Playback observations are cleared when TradMate and abcjs agree on base pitches, onsets and durations. '
        'Decorations and generated accompaniment are excluded. Ties are joined, and time is rounded to 0.001 quarter notes. '
        'For written note chords, a separate comparison uses the first written pitch, matching TradMate melody handling.',
        f"- {totals['playback_comparison_to_review']:,} accepted-format settings have remaining interpretation differences "
        'or a TradMate signature limitation. These are recorded separately in [playback-differences.csv](playback-differences.csv).',
        '- Setting 34752 uses valid additive inline meters. The two external parser families accept it. '
        'Equivalent numeric meters produce the same base melody in TradMate, demonstrating a signature-support limitation.',
        '', 'The repeat and meter rules are documented in the '
        '[ABC 2.1 specification](https://abcnotation.com/wiki/abc:standard:v2.1).','',
        '## Correction search','',
        'Nine existing evidence-based correction passes were rerun. The only proposal is the previously held setting 31295. '
        'It still fails verification of the expected duration changes. '
        'The correction count remains 651 settings.','',
        '- [Correction search](correction-search.json)',
        '- [Candidate playback check](correction-checks.json)',
        '- [Reviewed settings and source-specific decisions](../../checks/reviewed-settings.json)',
        '- [Accepted settings](../accepted.csv)',
        '- [Current status](../status.md)','',
        '## Reproducing the checks','',
        'Select the union of the four pending reports from the current JSON export and retain the source hashes in input.json. '
        'Run audit_parsers.py on that selection. Run audit_tradmate.py and audit_abcjs.js with undecorated comparison bodies '
        'produced by review_common.comparison_body. Then run check_additive_meters.py, reassess.py and status.py.',
        'The files in this directory retain the parser outputs and version metadata.','']
    (folder/'README.md').write_text('\n'.join(lines))
    with (folder/'playback-differences.csv').open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=['setting_id','tune_id','reason','tradmate_compiled',
            'tradmate_base_events','abcjs_base_events','abcjs_first_chord_events','source_url'],
            lineterminator='\n')
        writer.writeheader()
        for sid in sorted(expected,key=int):
            decision = decisions.get(sid)
            if not decision or decision['playback_agreement']:
                continue
            other = secondary[sid].get('comparison') or {}
            writer.writerow(dict(setting_id=sid,tune_id=records[sid]['tune_id'],
                reason=('Additive meter requires TradMate signature support'
                        if not decision['original_signature_supported'] else 'Base melody interpretations differ'),
                tradmate_compiled=primary[sid]['compiled'],
                tradmate_base_events=primary[sid].get('comparison_notes'),
                abcjs_base_events=other.get('note_events'),
                abcjs_first_chord_events=other.get('melody_events'),
                source_url=f"https://thesession.org/tunes/{records[sid]['tune_id']}#setting{sid}"))
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
