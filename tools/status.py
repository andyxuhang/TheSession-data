#!/usr/bin/env python3
"""Write the current list of fixes, unresolved findings and excluded cases."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from scan import ROOT, measures, rows, sha


LABELS = {
    'missing_barline':'漏写小节线', 'misplaced_barline':'小节线错位',
    'note_length':'音长数字或斜线手误', 'proven_long_note':'音长错误',
    'stray_control':'误入的控制字符', 'missing_triplet':'三连音标记遗漏',
    'missing_note_length_slash':'音长斜线遗漏', 'extra_note_length_digit':'多写音长数字',
    'short_bar':'内部小节时值不足', 'long_bar':'内部小节时值超出',
    'meter_signature':'拍号或曲式需要核对', 'interior_short_bar':'内部短小节候选',
    'overfull_short_note_run':'短音符音长候选', 'shifted_barline':'小节线错位候选',
    'witnessed_broken_tail':'附点节奏候选', 'source_specific_correction':'旧的指定曲谱候选',
    'missing_short_triplet':'三连音候选', 'parser_rejected':'独立播放验证未通过',
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
    data=list(rows(ROOT/'json/tunes.json'))
    byid={r['setting_id']:r for r in data}
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
            groups['boundaries'].append({**base,'types':'弱起、段尾或反复边界；未按手误处理',
                                          'details':json.dumps(boundary,ensure_ascii=False)})
        if unsupported:
            groups['unsupported'].append({**base,'types':'检查器不支持的语法或无旋律音符；未判错',
                                           'details':json.dumps(unsupported,ensure_ascii=False)})
        compatibility=flags.get('app_rules',[])+[r for r in flags.get('source_rules',[]) if r in {'tie_spacing','ending_spacing'}]
        if compatibility:
            groups['playback'].append({**base,'types':'; '.join(sorted(set(compatibility))),
                                        'details':'App 播放或解析兼容记录；不作为源谱错误。'})
    out=ROOT/'reports';out.mkdir(exist_ok=True)
    for name,records in groups.items():
        write_csv(out/(name+'.csv'),records,common+(['before_abc'] if name=='fixed' else []))
    flagged={r['setting_id'] for k,v in groups.items() if k!='fixed' for r in v}
    summary={'settings_checked':len(data),'tunes_checked':len({r['tune_id'] for r in data}),
             'fixed_settings':len(groups['fixed']),'fixed_tunes':len({r['tune_id'] for r in groups['fixed']}),
             'fixed_edits_by_type':dict(types), 'categories':{k:len(v) for k,v in groups.items()},
             'no_current_findings':len(data)-len(flagged),'rejected_settings':len(rejected),
             'counts_overlap':True}
    review_ids={r['setting_id'] for r in groups['review']}
    summary['fixed_with_remaining_review']=len(set(fixed)&review_ids)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    lines=['# 当前曲谱检查清单','',
           f"检查范围：{summary['tunes_checked']:,} 首曲目，{len(data):,} 份 setting。数据文件为当前 fork 的 CSV、JSON 和 SQLite。",'',
           '这里将确定修改、待核对项和不按源谱错误处理的情况分开。未修正的候选并不等于已经确认的人为手误。', '',
           '| 分类 | Setting 数 | 完整明细 |','|---|---:|---|',
           f"| 已修正 | {len(groups['fixed'])} | [fixed.csv](fixed.csv) |",
           f"| 尚需核对 | {len(groups['review'])} | [review.csv](review.csv) |",
           f"| 弱起、段尾与反复边界记录 | {len(groups['boundaries'])} | [boundaries.csv](boundaries.csv) |",
           f"| 暂不支持的语法或空旋律 | {len(groups['unsupported'])} | [unsupported.csv](unsupported.csv) |",
           f"| 播放或解析兼容记录 | {len(groups['playback'])} | [playback.csv](playback.csv) |",'',
           f"已修正的 setting 中，有 {summary['fixed_with_remaining_review']} 份还包含其他待核对项。因此各类数量不能相加当作独立曲谱总数。所有 CSV 均包含原网站链接和当前完整 ABC；fixed.csv 另有修改前 ABC。", '',
           '## 已修正的类型','', '| 类型 | 处数 |','|---|---:|']
    lines += [f"| {LABELS.get(k,k)} | {v} |" for k,v in sorted(types.items())]
    lines += ['', '## 自动检查做了什么','',
              '- 用有理数累计音长，避免浮点误差造成缺拍误报。',
              '- 小节线补写或移动，需要同曲、同调中独立存在的完整小节作佐证。',
              '- 音长手误限于一个数字或斜线的改动，还要求整个修正小节和相邻乐句有唯一匹配。',
              '- 保留音高、连音、装饰、作者与其他元数据。不猜音符，不补休止符，不推断新拍号。',
              '- 用关闭自动修复的独立 ABC 播放解析器对比每个事件。意外的音高、休止、连音或时值变化会阻止写入。',
              '- 反复扫描直至没有新的可验证改动；最后核对全部三种导出格式及数据库完整性。', '',
              f"独立播放检查保留了 {len(rejected)} 个未通过的候选，见 [拒绝原因](../checks/rejected.json)。例如移动小节线可能重置临时升降号，因此时值凑齐本身不构成修改依据。", '',
              '首尾连续播放相关的调整继续只作为 App 行为，不计入源谱修正。内部短小节也可能来自有意的曲式或混合拍号，缺少证据时保留。暂不支持并不表示原谱错误。', '',
              '## 待核对示例','', '| 曲目 | Setting | 检查项 |','|---|---|---|']
    for r in groups['review'][:25]:
        name=r['name'].replace('|','\\|')
        lines.append(f"| {name} | [{r['setting_id']}]({r['source_url']}) | {r['types']} |")
    lines += ['', '完整列表见上方 CSV。修正的完整补丁见 [changes](../changes/)，数据及播放检查结果见 [checks](../checks/)。', '']
    (out/'status.md').write_text('\n'.join(lines))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
