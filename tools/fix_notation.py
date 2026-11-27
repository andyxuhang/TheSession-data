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
from phrase_lengths import scan_lengths
from scan import ROOT, measures, rows, scan, sha, unique_settings


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def source_edits(before, after):
    return [{"start": a, "end": b, "text": after[c:d]}
            for op,a,b,c,d in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
            if op != "equal"]


def playback(plan, report, args, allow_failures):
    cmd = [sys.executable, str(ROOT/'tools/check_playback.py'), '--tradmate-repo',
           str(args.tradmate_repo), '--dart', args.dart, '--plan', str(plan)]
    if allow_failures:
        cmd.append('--allow-failures')
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
    singles = []
    for patch in proposals:
        body = patch['before_abc']
        for start, end, ev, variant in measure_edits(patch):
            is_length = lengths or ev['rule'] == 'note_length'
            singles.append({**patch, 'variant':variant, 'strict_length':is_length, 'after_abc':body[:start]+ev['after']+body[end:]})
    dump(work/'individual.json', {'corrections':singles})
    report = playback(work/'individual.json', work/'individual-check.json', args, True)
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
            if result['passed'] and valid_timing:
                body = body[:start]+ev['after']+body[end:]
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
    args = parser.parse_args()
    lengths = args.lengths or args.parallel_lengths
    current = unique_settings(rows(ROOT/'json/tunes.json'))
    data = list(current.values())
    if lengths or args.phrases or args.missing_notes:
        baseline = json.loads((ROOT/'changes/initial-fixes.json').read_text())['upstream_commit']
        exported = subprocess.check_output(['git','show',baseline+':json/tunes.json'], cwd=ROOT)
        upstream = unique_settings(json.loads(exported))
    original = {r['setting_id']:r['abc'] for r in data}
    collected, rejected, history, seen_failures = {}, {}, [], set()
    with tempfile.TemporaryDirectory(prefix='session-notation-') as temporary:
        work = Path(temporary)
        for attempt in range(1, 16):
            if args.phrases or args.missing_notes:
                scanner = scan_missing_notes if args.missing_notes else scan_phrases
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
            individual = candidates if lengths or args.phrases else structural
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
            checked = playback(work/'proposals.json', work/'playback.json', args, True)
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

        if lengths or args.phrases or args.missing_notes:
            _, findings, _ = scan(data)
        if args.phrases or args.missing_notes:
            batch = [{'setting_id':patch['setting_id'], 'tune_id':patch['tune_id'],
                      'source_url':patch['source_url'], **ev}
                     for patch in collected.values() for ev in patch['evidence']]
            detail_file = 'missing-notes.json' if args.missing_notes else 'matching-phrases.json'
        # Retain the complete original of any earlier run. Never overwrite the
        # history with an empty plan when the data are already corrected.
        stored = ROOT/'changes/notation-fixes.json'
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
        final = playback(work/'fixes.json',work/'final-check.json',args,False)
        args.output.mkdir(parents=True,exist_ok=True)
        dump(args.output/'proposed-fixes.json',plan)
        if args.phrases or args.missing_notes:
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
            dump(ROOT/'checks/notation-playback.json',final)
            if args.phrases or args.missing_notes:
                dump(ROOT/'checks'/detail_file,batch)
            if args.barlines or lengths or args.phrases or args.missing_notes:
                for old in json.loads((ROOT/'checks/rejected.json').read_text()):
                    rules = {e['rule'] for e in old.get('proposal', {}).get('evidence', [])}
                    if lengths or args.phrases or args.missing_notes or rules - {'missing_barline','misplaced_barline'}:
                        rejected.setdefault(old['setting_id'],old)
            dump(ROOT/'checks/rejected.json',list(rejected.values()))
            dump(ROOT/'checks/scan.json',{'passes':history,'rejected_settings':len(rejected)})
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
