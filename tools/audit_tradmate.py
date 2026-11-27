#!/usr/bin/env python3
"""Compile each setting with the pinned TradMate parser and record health checks."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from check_playback import REVISION, RUNNER, write_compiler
from review_common import comparison_body, melody_digest


AUDIT = RUNNER.split('void require',1)[0] + r"""
void main(List<String> args) {
  final rows = jsonDecode(File(args[0]).readAsStringSync()) as List;
  final sink = File(args[1]).openWrite();
  for (final row in rows) {
    try {
      final score = compile(row, row['abc']);
      final events = score['events'] as List;
      final notes = events.where((e) => e['is_rest'] != true &&
          (e['midi_pitches'] as List).isNotEmpty).toList();
      final timingValid = events.every((e) {
        final start = (e['start_quarter'] as num).toDouble();
        final duration = (e['duration_quarter'] as num).toDouble();
        return start.isFinite && duration.isFinite && start >= 0 && duration > 0;
      });
      final plain = compile(row, row['_comparison_abc']);
      final plainNotes = <List>[];
      for (final event in plain['events'] as List) {
        if (event['is_rest'] == true) continue;
        for (final pitch in event['midi_pitches'] as List) {
          plainNotes.add([event['start_quarter'],event['duration_quarter'],pitch,event['is_tie'] == true]);
        }
      }
      sink.writeln(jsonEncode({
        'setting_id': row['setting_id'],
        'compiled': true,
        'events': events.length,
        'note_events': notes.length,
        'valid_timing': timingValid,
        'normalized_events': events.where((e) => e['abc_repaired'] == true).length,
        'repair_flags': score['abc_repairs'] ?? [],
        'healthy': notes.isNotEmpty && timingValid &&
            events.every((e) => e['abc_repaired'] != true),
        'comparison_notes': plainNotes,
      }));
    } catch (error) {
      sink.writeln(jsonEncode({'setting_id':row['setting_id'],
        'compiled':false,'healthy':false,
        'reason':RegExp(r'^[\x00-\x7f]*$').hasMatch('$error') ? '$error' :
            'Unsupported signature or melody; inspect the source metadata'}));
    }
  }
  sink.close();
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tradmate-repo',type=Path,required=True)
    parser.add_argument('--dart',required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tradmate-review-') as work:
        root = Path(work)
        hashes = write_compiler(args.tradmate_repo.resolve(),root)
        (root/'audit.dart').write_text(AUDIT)
        data = json.loads(args.input.read_text())
        for row in data:
            row['_comparison_abc'] = comparison_body(row['abc'])
        source,target = root/'source.json',root/'raw-status.jsonl'
        source.write_text(json.dumps(data))
        subprocess.run([args.dart,str(root/'audit.dart'),str(source),str(target)],check=True)
        with args.output.open('w') as output:
            for line in target.open():
                result = json.loads(line)
                if 'comparison_notes' in result:
                    digest,count = melody_digest(result.pop('comparison_notes'))
                    result.update(comparison_sha256=digest,comparison_notes=count)
                output.write(json.dumps(result)+'\n')
    metadata = dict(compiler_commit=REVISION,compiler_files_sha256=hashes,
                    automatic_repairs=False,compiler_modifications=[])
    args.output.with_suffix('.metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')


if __name__ == '__main__':
    main()
