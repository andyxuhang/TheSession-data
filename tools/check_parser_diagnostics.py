#!/usr/bin/env python3
"""Recheck native and abcjs diagnostics before and after the parser-syntax fixes."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from audit_parsers import check
from scan import ROOT, rows, unique_settings


def main():
    records = unique_settings(rows(ROOT/'json/tunes.json'))
    patches = json.loads((ROOT/'changes/written-token-fixes.json').read_text())['corrections']
    executables = {name:shutil.which(name) for name in ('abc2midi','abc2abc')}
    if not all(executables.values()):
        raise SystemExit('abc2midi and abc2abc are required')
    results = {patch['setting_id']:{'setting_id':patch['setting_id'],'before':{},'after':{}} for patch in patches}
    with tempfile.TemporaryDirectory(prefix='abc-diagnostics-') as work:
        work = Path(work)
        for side in ('before','after'):
            data = [{**records[p['setting_id']],'abc':p[side+'_abc']} for p in patches]
            for row in data:
                result = check(row,work,executables)
                for name in executables:
                    results[row['setting_id']][side][name] = [
                        d['message'] for d in result['diagnostics'] if d['parser']==name]
            source, target = work/'source.json', work/'result.jsonl'
            source.write_text(json.dumps(data))
            subprocess.run(['node',str(ROOT/'tools/audit_abcjs.js'),
                            str(ROOT.parent.parent/'third_party/abcjs/abcjs-basic-min.js'),
                            str(source),str(target)],check=True,capture_output=True)
            flagged = {r['setting_id']:r['diagnostics'] for r in map(json.loads,target.open())}
            for row in data:
                results[row['setting_id']][side]['abcjs'] = flagged.get(row['setting_id'],[])
        for result in results.values():
            if len(result['after']['abcjs']) > len(result['before']['abcjs']):
                raise ValueError('New abcjs diagnostic for '+result['setting_id'])
    print(json.dumps(dict(settings=len(results),results=list(results.values())),indent=2))


if __name__ == '__main__':
    main()
