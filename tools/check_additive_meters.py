#!/usr/bin/env python3
"""Verify additive meters by an equivalent numeric-meter comparison."""

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from scan import ROOT, rows, sha, unique_settings


ADDITIVE = re.compile(r'\[M:((?:\d+\s*\+\s*)+\d+)/(\d+)\]')


def main():
    folder = ROOT/'reports/reassessment'
    native = {r['setting_id'] for r in map(json.loads,(folder/'native-diagnostics.jsonl').open())}
    secondary = {r['setting_id']:r for r in map(json.loads,(folder/'abcjs-status.jsonl').open())}
    primary = {r['setting_id']:r for r in map(json.loads,(folder/'tradmate-status.jsonl').open())}
    records = unique_settings(rows(ROOT/'json/tunes.json'))
    candidates, fields = [],{}
    for sid,result in primary.items():
        row = records[sid]
        if result['healthy'] or sid in native or not secondary[sid]['healthy']:
            continue
        matches = list(ADDITIVE.finditer(row['abc']))
        if not matches:
            continue
        normalized = ADDITIVE.sub(lambda m:'[M:'+str(sum(map(int,m[1].split('+'))))+'/'+m[2]+']',row['abc'])
        candidates.append({**row,'abc':normalized})
        fields[sid] = [dict(before=m[0],after='[M:'+str(sum(map(int,m[1].split('+'))))+'/'+m[2]+']')
                       for m in matches]
    verified = []
    if candidates:
        with tempfile.TemporaryDirectory(prefix='additive-meter-review-') as work:
            source,target = Path(work)/'source.json',Path(work)/'status.jsonl'
            source.write_text(json.dumps(candidates))
            subprocess.run([sys.executable,str(ROOT/'tools/audit_tradmate.py'),'--input',str(source),
                '--output',str(target),'--tradmate-repo',str(ROOT.parent.parent),
                '--dart','/opt/homebrew/share/flutter/bin/cache/dart-sdk/bin/dart'],check=True)
            for result in map(json.loads,target.open()):
                sid = result['setting_id']
                comparison = secondary[sid]['comparison']
                valid = result['healthy'] and result['comparison_sha256'] in (
                    comparison['sha256'],comparison['first_chord_pitch_sha256'])
                verified.append(dict(setting_id=sid,body_sha256=sha(records[sid]['abc']),
                    normalized_fields=fields[sid],numeric_meter_result=result,validated=valid,
                    specification='https://abcnotation.com/wiki/abc:standard:v2.1#m_meter'))
    (folder/'additive-meter-check.json').write_text(json.dumps(verified,indent=2)+'\n')


if __name__ == '__main__':
    main()
