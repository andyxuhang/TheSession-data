#!/usr/bin/env python3
"""Scan, cross-check and optionally apply notation fixes without model calls."""

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from scan import ROOT, rows, scan, sha


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tradmate-repo', type=Path, required=True)
    parser.add_argument('--dart', required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'reports')
    parser.add_argument('--apply', action='store_true', help='Write validated changes to the data exports')
    args = parser.parse_args()
    data = list(rows(ROOT/'json/tunes.json'))
    current = {r['setting_id']:r for r in data}
    original = {r['setting_id']:r['abc'] for r in data}
    collected, rejected, history, seen_failures = {}, {}, [], set()
    with tempfile.TemporaryDirectory(prefix='session-notation-') as temporary:
        work = Path(temporary)
        for attempt in range(1, 16):
            proposals, findings, stats = scan(data)
            candidates = [p for p in proposals if (p['before_sha256'], p['after_sha256']) not in seen_failures]
            stats['pass'] = attempt
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
        dump(work/'fixes.json',plan)
        final = playback(work/'fixes.json',work/'final-check.json',args,False)
        args.output.mkdir(parents=True,exist_ok=True)
        dump(args.output/'proposed-fixes.json',plan)
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
            dump(ROOT/'checks/rejected.json',list(rejected.values()))
            dump(ROOT/'checks/scan.json',{'passes':history,'rejected_settings':len(rejected)})
            with (ROOT/'checks/data.json').open('w') as stream:
                subprocess.run([sys.executable,str(ROOT/'tools/apply.py'),'--apply'],stdout=stream,check=True)
            subprocess.run([sys.executable,str(ROOT/'tools/status.py'),'--findings',str(args.output/'findings.jsonl')],check=True)
        print(json.dumps({'new_settings_fixed':len(collected),'all_notation_fixes':len(combined),
                          'rejected_settings':len(rejected),'applied':args.apply},indent=2))


if __name__ == '__main__':
    main()
