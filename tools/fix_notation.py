#!/usr/bin/env python3
"""Scan, cross-check and optionally apply notation fixes without model calls."""

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from matching_phrases import scan_phrases
from missing_notes import scan_missing_notes
from note_count_fixes import scan_final_notes, scan_note_counts
from notation_structure import scan_structures
from phrase_lengths import scan_lengths
from pitch_fixes import PITCH_RULES, scan_pitches
from reference_lengths import scan_opening_lengths, scan_reference_lengths
from syntax_fixes import SYNTAX_RULES, scan_syntax
from transposed_pitches import scan_transposed_pitches
from scan import ROOT, measures, rows, scan, sha, unique_settings


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def source_edits(before, after):
    return [{"start": a, "end": b, "text": after[c:d]}
            for op,a,b,c,d in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
            if op != "equal"]


def playback(plan, report, args, allow_failures, cross_check=False):
    cmd = [sys.executable, str(ROOT/'tools/check_playback.py'), '--tradmate-repo',
           str(args.tradmate_repo), '--dart', args.dart, '--plan', str(plan)]
    if allow_failures:
        cmd.append('--allow-failures')
    if cross_check:
        cmd.append('--abcjs')
    with report.open('w') as stream:
        subprocess.run(cmd, stdout=stream, check=True)
    return json.loads(report.read_text())


def measure_edits(patch):
    body = patch['before_abc']
    bars, _ = measures(body)
    for n, evidence in enumerate(patch['evidence']):
        i = evidence['bar'] - 1
        last = evidence.get('last_bar', i+1+(evidence['rule'] == 'misplaced_barline')) - 1
        start, end = bars[i].start, bars[last].end
        if body[start:end] != evidence['before']:
            raise ValueError('Bar offset mismatch for ' + patch['setting_id'])
        yield start, end, evidence, f"{patch['setting_id']}-{n}"


def check_measure_edits(proposals, work, args, lengths=False):
    cross_checked_rules = PITCH_RULES | SYNTAX_RULES
    singles = []
    for patch in proposals:
        body = patch['before_abc']
        for start, end, ev, variant in measure_edits(patch):
            is_length = lengths or ev['rule'] == 'note_length'
            evidence = [ev] if ev['rule'] in cross_checked_rules else patch['evidence']
            singles.append({**patch, 'evidence':evidence, 'variant':variant, 'strict_length':is_length, 'after_abc':body[:start]+ev['after']+body[end:]})
    dump(work/'individual.json', {'corrections':singles})
    cross_check = any(ev['rule'] in cross_checked_rules for p in proposals for ev in p['evidence'])
    report = playback(work/'individual.json', work/'individual-check.json', args, True, cross_check=cross_check)
    checks = {r['variant']:r for r in report['checks']}
    accepted, failures = [], {}
    for patch in proposals:
        evidence = []
        body = patch['before_abc']
        for start, end, ev, variant in reversed(list(measure_edits(patch))):
            result = checks[variant]
            is_length = lengths or ev['rule'] == 'note_length'
            changes_duration = is_length or ev['rule'] == 'rhythm_mark'
            valid_timing = (result.get('changed_note_durations', 0) > 0
                            and not result.get('parser_normalized_or_unplayed_change', False) if changes_duration
                            else result.get('all_event_timings_unchanged', False))
            if ev['rule'] in PITCH_RULES:
                valid_timing = valid_timing and result.get('changed_played_pitches',0) > 0
            if result['passed'] and valid_timing:
                body = body[:start]+ev['after']+body[end:]
                if ev['rule'] in PITCH_RULES:
                    ev = {**ev, 'playback_occurrences':result['changed_played_pitches'],'abcjs':result['abcjs']}
                elif ev['rule'] in SYNTAX_RULES:
                    ev = {**ev, 'playback_unchanged':True, 'abcjs':result['abcjs']}
                evidence.append(ev)
            else:
                sid = patch['setting_id']
                failures.setdefault(sid, {'setting_id':sid, 'passed':False, 'reason':'individual phrase check', 'bars':[]})
                reason = result.get('reason') or ('proposed duration change not fully reflected in playback' if changes_duration else 'timing changed')
                failures[sid]['bars'].append({'edit':ev, 'reason':reason})
        if evidence:
            rules = sorted({item['rule'] for item in evidence})
            accepted.append({**patch, 'category':'+'.join(rules), 'evidence':evidence[::-1], 'after_abc':body, 'after_sha256':sha(body),
                             'edits':source_edits(patch['before_abc'],body)})
    return accepted, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tradmate-repo', type=Path, required=True)
    parser.add_argument('--dart', required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'reports')
    parser.add_argument('--apply', action='store_true', help='Write validated changes to the data exports')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--lengths', action='store_true', help='Check individual note lengths against phrases in other settings')
    mode.add_argument('--barlines', action='store_true', help='Check each structural edit separately before combining it')
    mode.add_argument('--parallel-lengths', action='store_true', help='Check note lengths against a repeated phrase in the same setting')
    mode.add_argument('--phrases', action='store_true', help='Compare damaged interior phrases with intact written passages')
    mode.add_argument('--missing-notes', action='store_true', help='Restore a missing note supported by independent settings')
    mode.add_argument('--pitches', action='store_true', help='Check accidentals and octaves in fully metered passages')
    mode.add_argument('--syntax', action='store_true', help='Check stray notation and split note tokens')
    mode.add_argument('--note-counts', action='store_true', help='Compare omitted and extra written notes')
    mode.add_argument('--final-notes', action='store_true', help='Check omitted and extra notes in explicit tune endings')
    mode.add_argument('--reference-lengths', action='store_true', help='Check durations against matching phrases at section and repeat boundaries')
    mode.add_argument('--opening-lengths', action='store_true', help='Check durations in overfull opening measures')
    mode.add_argument('--transposed-pitches', action='store_true', help='Compare isolated pitches across equivalent transposed phrases')
    mode.add_argument('--structures', action='store_true', help='Match bar divisions and slur punctuation at written boundaries')
    args = parser.parse_args()
    pitch_mode = args.pitches or args.transposed_pitches
    note_counts = args.note_counts or args.final_notes
    reference_lengths = args.reference_lengths or args.opening_lengths
    cross_checked = pitch_mode or args.syntax or note_counts or reference_lengths or args.structures
    separate_scan = args.phrases or args.missing_notes or cross_checked
    plan_name = ('written-tune-start' if args.opening_lengths else 'written-tune-end' if args.final_notes
                 else 'written-structure' if args.structures else 'written-rhythm' if args.reference_lengths
                 else 'written-note' if args.note_counts
                 else 'syntax' if args.syntax else 'pitch' if pitch_mode else 'notation')
    lengths = args.lengths or args.parallel_lengths
    current = unique_settings(rows(ROOT/'json/tunes.json'))
    data = list(current.values())
    if lengths or separate_scan:
        baseline = json.loads((ROOT/'changes/initial-fixes.json').read_text())['upstream_commit']
        exported = subprocess.check_output(['git','show',baseline+':json/tunes.json'], cwd=ROOT)
        upstream = unique_settings(json.loads(exported))
    earlier_rejections = (json.loads((ROOT/'checks/rejected.json').read_text())
                          if args.reference_lengths or args.structures else [])
    original = {r['setting_id']:r['abc'] for r in data}
    collected, rejected, history, seen_failures = {}, {}, [], set()
    with tempfile.TemporaryDirectory(prefix='session-notation-') as temporary:
        work = Path(temporary)
        for attempt in range(1, 16):
            if separate_scan:
                if args.structures:
                    scanner = lambda records,refs: scan_structures(records,refs,earlier_rejections)
                elif args.opening_lengths:
                    scanner = scan_opening_lengths
                elif args.reference_lengths:
                    scanner = lambda records,refs: scan_reference_lengths(records,refs,earlier_rejections)
                elif args.final_notes:
                    scanner = scan_final_notes
                elif args.note_counts:
                    scanner = scan_note_counts
                elif args.syntax:
                    scanner = scan_syntax
                elif args.transposed_pitches:
                    scanner = scan_transposed_pitches
                elif args.pitches:
                    scanner = scan_pitches
                elif args.missing_notes:
                    scanner = scan_missing_notes
                else:
                    scanner = scan_phrases
                proposals, stats = scanner(data, upstream)
                stats.update(settings=len(data), settings_with_proposals=len(proposals))
            elif lengths:
                proposals = scan_lengths(data, upstream, parallel=args.parallel_lengths)
                stats = {'settings':len(data), 'settings_with_proposals':len(proposals),
                         'note_length':sum(len(p['evidence']) for p in proposals)}
            else:
                proposals, findings, stats = scan(data, barlines_only=args.barlines)
            candidates = [p for p in proposals if (p['before_sha256'], p['after_sha256']) not in seen_failures]
            stats['pass'] = attempt
            if not candidates:
                stats['accepted'] = 0
                history.append(stats)
                break
            structural = [p for p in candidates if all(
                e['rule'] in {'misplaced_barline', 'missing_barline'} for e in p['evidence'])]
            individual = candidates if lengths or args.phrases or pitch_mode or args.syntax else (
                [] if args.structures else structural)
            if individual:
                structural_ids = {p['setting_id'] for p in individual}
                passed, failures = check_measure_edits(individual, work, args, lengths=lengths)
                for sid in structural_ids:
                    rejected.pop(sid, None)
                rejected.update(failures)
                candidates = passed + [p for p in candidates if p['setting_id'] not in structural_ids]
                stats['individual_rejections'] = sum(len(r['bars']) for r in failures.values())
                if not candidates:
                    stats['accepted'] = 0
                    history.append(stats)
                    break
            dump(work/'proposals.json', {'corrections':candidates})
            checked = playback(work/'proposals.json', work/'playback.json', args, True, cross_check=cross_checked)
            outcomes = {r['setting_id']:r for r in checked['checks']}
            accepted = 0
            for patch in candidates:
                sid = patch['setting_id']
                if not outcomes[sid]['passed']:
                    rejected[sid] = {**outcomes[sid], 'proposal':patch}
                    seen_failures.add((patch['before_sha256'],patch['after_sha256']))
                    continue
                accepted += 1
                for evidence in patch['evidence']:
                    evidence['scan_pass'] = attempt
                    if reference_lengths:
                        evidence['changed_played_durations'] = outcomes[sid]['changed_note_durations']
                        evidence['abcjs'] = outcomes[sid]['abcjs']
                        if outcomes[sid].get('primary_duration_already_normalized'):
                            evidence['primary_duration_already_normalized'] = True
                    if note_counts:
                        evidence['changed_note_occurrences'] = outcomes[sid]['changed_note_occurrences']
                        evidence['abcjs'] = outcomes[sid]['abcjs']
                    if args.structures:
                        evidence['all_event_timings_unchanged'] = outcomes[sid]['all_event_timings_unchanged']
                        evidence['changed_played_pitches'] = outcomes[sid].get('changed_played_pitches',0)
                        evidence['abcjs'] = outcomes[sid]['abcjs']
                if sid in collected:
                    patch['evidence'] = collected[sid]['evidence'] + patch['evidence']
                patch['before_abc'] = original[sid]
                patch['before_sha256'] = sha(original[sid])
                patch['edits'] = source_edits(original[sid],patch['after_abc'])
                collected[sid] = patch
                current[sid]['abc'] = patch['after_abc']
            stats['accepted'] = accepted
            stats['rejected'] = len(candidates)-accepted
            history.append(stats)
            print(json.dumps(stats), file=sys.stderr, flush=True)
            if not accepted:
                break
        else:
            raise RuntimeError('Scan did not converge; no data have been written')

        if lengths or separate_scan:
            _, findings, _ = scan(data)
        if separate_scan:
            batch = [{'setting_id':patch['setting_id'], 'tune_id':patch['tune_id'],
                      'source_url':patch['source_url'], **ev}
                     for patch in collected.values() for ev in patch['evidence']]
            detail_file = (f'{plan_name}-edits.json' if cross_checked else
                           'missing-notes.json' if args.missing_notes else 'matching-phrases.json')
        # Retain the complete original of any earlier run. Never overwrite the
        # history with an empty plan when the data are already corrected.
        stored = ROOT/'changes'/f'{plan_name}-fixes.json'
        previous = json.loads(stored.read_text()) if stored.exists() else {'corrections':[]}
        combined = {p['setting_id']:p for p in previous['corrections']}
        for sid,patch in collected.items():
            if sid in combined:
                old = combined[sid]
                if old['after_abc'] != patch['before_abc']:
                    raise ValueError('Previous correction changed: '+sid)
                patch['before_abc'],patch['before_sha256'] = old['before_abc'],old['before_sha256']
                patch['source_states'] = list(dict.fromkeys(old.get('source_states',[old['before_abc']])+[old['after_abc']]))
                patch['evidence'] = old['evidence'] + patch['evidence']
                patch['edits'] = source_edits(patch['before_abc'],patch['after_abc'])
            combined[sid] = patch
        plan = {
            'base_commit': previous.get('base_commit') or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'method':'Exact bar durations, complete-bar phrase witnesses, and independent playback comparison',
            'scanner_sha256':hashlib.sha256((ROOT/'tools/scan.py').read_bytes()).hexdigest(),
            'corrections':sorted(combined.values(),key=lambda p:(int(p['tune_id']),int(p['setting_id']))),
        }
        if args.transposed_pitches:
            plan['transposed_pitch_scanner_sha256'] = hashlib.sha256((ROOT/'tools/transposed_pitches.py').read_bytes()).hexdigest()
        if pitch_mode:
            plan['method'] = 'Independent matching written phrases and verified single-note pitch changes'
            plan['pitch_scanner_sha256'] = hashlib.sha256((ROOT/'tools/pitch_fixes.py').read_bytes()).hexdigest()
        if reference_lengths:
            plan['method'] = 'Matching written measures and independent checks of the intended note duration'
            plan['reference_lengths_sha256'] = hashlib.sha256((ROOT/'tools/reference_lengths.py').read_bytes()).hexdigest()
        if note_counts:
            plan['method'] = 'Matching written phrases and independent verification of an individual note count change'
            plan['written_note_scanner_sha256'] = hashlib.sha256((ROOT/'tools/note_count_fixes.py').read_bytes()).hexdigest()
        if args.structures:
            plan['method'] = 'Original barline and slur witnesses with independent full playback checks'
            plan['structure_scanner_sha256'] = hashlib.sha256((ROOT/'tools/notation_structure.py').read_bytes()).hexdigest()
        if args.syntax:
            plan['method'] = 'Matching written measures and unchanged playback in independent parsers'
            plan['syntax_scanner_sha256'] = hashlib.sha256((ROOT/'tools/syntax_fixes.py').read_bytes()).hexdigest()
        if args.phrases:
            plan['matching_phrases_sha256'] = hashlib.sha256((ROOT/'tools/matching_phrases.py').read_bytes()).hexdigest()
        if args.missing_notes:
            plan['missing_notes_scanner_sha256'] = hashlib.sha256((ROOT/'tools/missing_notes.py').read_bytes()).hexdigest()
        if lengths:
            plan['phrase_scanner_sha256'] = hashlib.sha256((ROOT/'tools/phrase_lengths.py').read_bytes()).hexdigest()
        for key, value in previous.items():
            if key.endswith('_scanner_sha256'):
                plan.setdefault(key, value)
        dump(work/'fixes.json',plan)
        final = playback(work/'fixes.json',work/'final-check.json',args,False,
                         cross_check=args.structures or args.final_notes or args.opening_lengths)
        args.output.mkdir(parents=True,exist_ok=True)
        dump(args.output/'proposed-fixes.json',plan)
        if separate_scan:
            dump(args.output/detail_file, batch)
        dump(args.output/'playback.json',final)
        dump(args.output/'rejected.json',list(rejected.values()))
        dump(args.output/'scan.json',{'passes':history,'corrected_settings':len(collected),
                                    'remaining_proposals':len(proposals), 'rejected_settings':len(rejected)})
        with (args.output/'findings.jsonl').open('w') as stream:
            for finding in findings:
                stream.write(json.dumps(finding,ensure_ascii=False)+'\n')
        if args.apply:
            dump(stored,plan)
            playback_file = f'{plan_name}-playback.json'
            dump(ROOT/'checks'/playback_file,final)
            if cross_checked:
                batch = [{'setting_id':patch['setting_id'],'tune_id':patch['tune_id'],
                          'source_url':patch['source_url'],**ev}
                         for patch in combined.values() for ev in patch['evidence']]
            if separate_scan:
                dump(ROOT/'checks'/detail_file,batch)
            if args.barlines or lengths or separate_scan:
                for old in json.loads((ROOT/'checks/rejected.json').read_text()):
                    rules = {e['rule'] for e in old.get('proposal', {}).get('evidence', [])}
                    if args.structures and old['setting_id'] in collected and old.get('bars') and not old.get('proposal'):
                        verified = {(e['rule'],e['bar'],e['before'],e['after'])
                                    for e in collected[old['setting_id']]['evidence']}
                        if all((e['rule'],e['bar'],e['before'],e['after']) in verified
                               for e in (entry['edit'] for entry in old['bars'])):
                            continue
                    if (note_counts or args.reference_lengths) and old['setting_id'] in collected:
                        accepted = collected[old['setting_id']]
                        earlier = old.get('proposal', {})
                        if (earlier.get('after_sha256') == accepted['after_sha256']
                                and earlier.get('before_sha256') == accepted['before_sha256']):
                            continue
                        if args.reference_lengths and old.get('bars'):
                            verified = {(e['rule'],e['bar'],e['after']) for e in accepted['evidence']}
                            if all((entry['edit']['rule'],entry['edit']['bar'],entry['edit']['after']) in verified
                                   for entry in old['bars']):
                                continue
                    if pitch_mode and old['setting_id'] in collected and old['setting_id'] not in rejected:
                        prior_edits = [record['edit'] for record in old.get('bars', [])]
                        prior_edits.extend(old.get('proposal', {}).get('evidence', []))
                        applied = {(ev['rule'],ev['bar'],ev['note'])
                                   for ev in collected[old['setting_id']]['evidence']}
                        if prior_edits and all(
                            ev['rule'] in PITCH_RULES and (ev['rule'],ev['bar'],ev['note']) in applied
                            for ev in prior_edits
                        ):
                            continue
                    if lengths or separate_scan or rules - {'missing_barline','misplaced_barline'}:
                        rejected.setdefault(old['setting_id'],old)
            dump(ROOT/'checks/rejected.json',list(rejected.values()))
            scan_file = f'{plan_name}-scan.json' if cross_checked else 'scan.json'
            dump(ROOT/'checks'/scan_file,{'passes':history,'rejected_settings':len(rejected)})
            with (ROOT/'checks/data.json').open('w') as stream:
                subprocess.run([sys.executable,str(ROOT/'tools/apply.py'),'--apply'],stdout=stream,check=True)
            findings_file = args.output / 'findings.jsonl'
            published = ROOT / 'reports/findings.jsonl'
            if findings_file.resolve() != published.resolve():
                published.parent.mkdir(exist_ok=True)
                shutil.copyfile(findings_file, published)
            subprocess.run([sys.executable, str(ROOT/'tools/status.py'), '--findings', str(published)], check=True)
        print(json.dumps({'new_settings_fixed':len(collected),'all_notation_fixes':len(combined),
                          'rejected_settings':len(rejected),'applied':args.apply},indent=2))


if __name__ == '__main__':
    main()
