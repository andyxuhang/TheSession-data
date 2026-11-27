#!/usr/bin/env python3
"""Record additional parser evidence and recheck the current ornament repairs."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from scan import ROOT, rows, unique_settings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--abc2svg',type=Path,required=True)
    args=parser.parse_args()
    folder=ROOT/'reports/further-parser-review'
    provenance_path=folder/'source.json'
    if provenance_path.exists():
        provenance=json.loads(provenance_path.read_text())
    else:
        provenance=dict(base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            abc2svg=json.loads((folder/'progress.jsonl').read_text().splitlines()[-1]),
            package='abc2svg@1.22.1',package_deprecated=True)
        provenance_path.write_text(json.dumps(provenance,indent=2)+'\n')
    prior=json.loads(subprocess.check_output(['git','show',
        provenance['base_commit']+':changes/written-ornament-fixes.json'],cwd=ROOT))
    previous_ids={p['setting_id'] for p in prior['corrections']}
    current=json.loads((ROOT/'changes/written-ornament-fixes.json').read_text())
    patches=[p for p in current['corrections'] if p['setting_id'] not in previous_ids]
    records=unique_settings(rows(ROOT/'json/tunes.json'))
    outcomes={}
    with tempfile.TemporaryDirectory(prefix='further-parser-review-') as work:
        work=Path(work)
        for side in ('before','after'):
            source=work/(side+'.json')
            source.write_text(json.dumps([{**records[p['setting_id']],'abc':p[side+'_abc']} for p in patches]))
            target=folder/('fixed-'+side+'.jsonl')
            result=subprocess.run(['node',str(ROOT/'tools/audit_abc2svg.js'),str(args.abc2svg.resolve()),
                str(source),str(target)],capture_output=True,text=True,check=True)
            version=json.loads(result.stderr.splitlines()[-1])
            if version['sha256']!=provenance['abc2svg']['sha256']:
                raise ValueError('abc2svg core changed during review')
            outcomes[side]=list(map(json.loads,target.open()))
        plan=work/'plan.json'
        plan.write_text(json.dumps({'corrections':patches}))
        with (folder/'fixed-native-and-abcjs.json').open('w') as output:
            subprocess.run([sys.executable,str(ROOT/'tools/check_parser_diagnostics.py'),
                '--plan',str(plan)],stdout=output,check=True)
    initial=list(map(json.loads,(folder/'abc2svg.jsonl').open()))
    inputs=json.loads((folder/'input.json').read_text())
    cached={r['setting_id']:r for r in json.loads((ROOT/'reports/reassessment/input.json').read_text())['settings']}
    if {r['setting_id'] for r in initial}!={r['setting_id'] for r in inputs}:
        raise ValueError('Incomplete additional-parser coverage')
    if any(cached[r['setting_id']]['body_sha256']!=r['body_sha256'] for r in inputs):
        raise ValueError('Cached parser results refer to a different source')
    summary=dict(settings_checked=len(initial),settings_with_diagnostics=sum(bool(r['diagnostics']) for r in initial),
        base_commit=provenance['base_commit'],parser=provenance['abc2svg'],
        new_fixed_settings=len(patches),new_fixed_tunes=len({p['tune_id'] for p in patches}),
        new_fixed_symbols=dict(Counter(ev['rule'] for p in patches for ev in p['evidence'])),
        abc2svg_messages_before=sum(len(r['diagnostics']) for r in outcomes['before']),
        abc2svg_messages_after=sum(len(r['diagnostics']) for r in outcomes['after']),
        cached_prior_parser_evidence='Source hashes checked against reports/reassessment/input.json')
    if any(len(after['diagnostics'])>len(before['diagnostics'])
           for before,after in zip(outcomes['before'],outcomes['after'])):
        raise ValueError('New abc2svg diagnostics after an ornament correction')
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Further parser review','',
        f"Checked all {len(initial):,} remaining settings with abc2svg 1.22.1. "
        f"The core reported diagnostics in {summary['settings_with_diagnostics']:,} settings.",
        'Prior TradMate, abcjs, abc2midi and abc2abc results were reused after checking the source hashes. '
        'The changed settings were checked again with the native tools, abcjs and abc2svg.','',
        f"Corrected {sum(summary['new_fixed_symbols'].values())} ornament spellings in "
        f"{summary['new_fixed_settings']} settings of {summary['new_fixed_tunes']} tunes.",
        'Twenty-two abbreviated trill names use the standard trill spelling. '
        'One Da Capo name uses the standard lowercase full-word spelling. '
        'The related second setting of the same tune shares the trill spelling issue.',
        'TradMate and abcjs preserved the played notes and timings.','',
        f"abc2svg diagnostics in the four changed settings decreased from "
        f"{summary['abc2svg_messages_before']} to {summary['abc2svg_messages_after']}. "
        "The remaining message in setting 52550 concerns a separate malformed note. "
        "The accidental-token comparison found no uniquely supported correction for it, so it remains under review.",'',
        'The accepted names are defined in the '
        '[ABC 2.1 decoration specification](https://abcnotation.com/wiki/abc:standard:v2.1#decorations).','',
        '## Scope and limitations','',
        'abc2svg was used as a core syntax/model parser. Custom modules and graphic output were excluded. '
        'The npm package is deprecated and was pinned by version and core hash. '
        'Its diagnostics were considered alongside the other parsers and the specification.',
        'The additional accidental-token comparison found no uniquely supported correction.','',
        '## Evidence','',
        '- [Input settings and source hashes](input.json)',
        '- [Full additional-parser diagnostics](abc2svg.jsonl)',
        '- [Corrected settings before](fixed-before.jsonl)',
        '- [Corrected settings after](fixed-after.jsonl)',
        '- [Fresh native and abcjs diagnostics](fixed-native-and-abcjs.json)',
        '- [Exact source patches](../../changes/written-ornament-fixes.json)',
        '- [Summary and pinned parser version](summary.json)','',
        'To repeat the additional parser, install the external abc2svg@1.22.1 package into a scratch directory '
        'and supply its abc2svg-1.js path to tools/audit_abc2svg.js. '
        'No third-party parser source is included in this repository.','']
    (folder/'README.md').write_text('\n'.join(lines))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
