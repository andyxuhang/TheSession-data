#!/usr/bin/env python3
"""Check the current export with abc2midi and abc2abc without rewriting ABC."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from scan import ROOT, rows, unique_settings


def check(row, directory, executables):
    directory = directory / row['setting_id']
    directory.mkdir()
    path = directory / 'input.abc'
    header = f"X:1\nT:Parser check\nM:{row['meter']}\nL:1/8\nK:{row['mode']}\n"
    path.write_text(header + row['abc'].replace('\r\n', '\n').replace('\r', '\n') + '\n', encoding='utf8')
    diagnostics = []
    for name, executable in executables.items():
        command = [executable, str(path)] + (['-c'] if name == 'abc2midi' else [])
        try:
            result = subprocess.run(command, cwd=directory, capture_output=True, text=True, errors='replace', timeout=15)
            output = result.stdout + '\n' + result.stderr
            if name == 'abc2abc':
                messages = re.findall(r'(?m)^%((?:Error|Warning)[^\n]*)', output)
            else:
                messages = re.findall(r'(?m)^((?:Error|Warning|Fatal)[^\n]*)', output)
            if result.returncode != 0:
                messages.append('Process exit code ' + str(result.returncode))
        except subprocess.TimeoutExpired:
            messages = ['Parser timeout after 15 seconds']
        for message in messages:
            diagnostics.append(dict(parser=name, message=message))
    shutil.rmtree(directory)
    return dict(setting_id=row['setting_id'], tune_id=row['tune_id'],
                source_url=f"https://thesession.org/tunes/{row['tune_id']}#setting{row['setting_id']}",
                diagnostics=diagnostics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--input',type=Path,help='Optional JSON array of settings to check')
    args = parser.parse_args()
    executables = {name:shutil.which(name) for name in ('abc2midi', 'abc2abc')}
    if not all(executables.values()):
        raise SystemExit('abc2midi and abc2abc are required')
    versions = {name:subprocess.check_output([path,'-ver'],text=True).strip()
                for name,path in executables.items()}
    source = args.input or ROOT/'json/tunes.json'
    records = json.loads(source.read_text()) if args.input else rows(source)
    data = sorted(unique_settings(records).values(), key=lambda r:int(r['setting_id']))
    known = {json.loads(line)['setting_id'] for line in (ROOT/'reports/findings.jsonl').open()}
    args.output.mkdir(parents=True, exist_ok=True)
    counts, types = Counter(), Counter()
    flagged = set()
    with tempfile.TemporaryDirectory(prefix='abc-parser-check-') as work:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = pool.map(lambda row:check(row,Path(work),executables),data)
            with (args.output/'native-diagnostics.jsonl').open('w') as stream:
                for i, result in enumerate(results, 1):
                    if result['diagnostics']:
                        result['previous_finding'] = result['setting_id'] in known
                        flagged.add(result['setting_id'])
                        stream.write(json.dumps(result,ensure_ascii=False)+'\n')
                    for name in {d['parser'] for d in result['diagnostics']}:
                        counts[name] += 1
                    for d in result['diagnostics']:
                        kind = re.sub(r'\d+(?:/\d+)?','N',d['message'])
                        types[d['parser'],kind] += 1
                    if i % 5000 == 0:
                        print(json.dumps(dict(checked=i,total=len(data))),flush=True)
    summary = dict(settings=len(data),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                   parser_versions=versions,settings_with_diagnostics=dict(counts),
                   flagged_settings=len(flagged),newly_flagged_settings=len(flagged-known),
                   messages=[dict(parser=p,message=m,count=n) for (p,m),n in types.most_common()],
                   writes_to_source=False,unit_note_length='1/8')
    (args.output/'native-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='messages'},indent=2))


if __name__ == '__main__':
    main()
