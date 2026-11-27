#!/usr/bin/env python3
"""Compare reviewed ABC using an unmodified, pinned TradMate compiler snapshot."""

from collections import defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from scan import measures

ROOT = Path(__file__).resolve().parents[1]
REVISION = "823fbf4cb5941394d86b5dd476ba46cc6e891f47"
COMPILER = "lib/features/library/data/user_abc_import.dart"
RUNNER = r"""
import 'dart:convert';
import 'dart:io';
import 'lib/features/library/data/user_abc_import.dart';

Map compile(Map row, String body) {
  final source = 'X:${row['setting_id']}\nT:${row['name']}\nR:${row['type']}\nM:${row['meter']}\nL:1/8\nK:${row['mode']}\n$body\n';
  return UserAbcImport.compileBundledDatabase(
    assetPath: 'curation/${row['setting_id']}.abc',
    source: source, title: row['name'], rhythm: row['type'],
    meter: row['meter'], key: row['mode'], autoRepair: false,
  ).scoreSource;
}

void require(bool value, String message) {
  if (!value) throw StateError(message);
}

void main(List<String> args) {
  final rows = jsonDecode(File(args[0]).readAsStringSync()) as List;
  final result = <Map>[];
  for (final row in rows) {
    try {
    final before = compile(row, row['before_abc']);
    final after = compile(row, row['after_abc']);
    final a = before['events'] as List, b = after['events'] as List;
    final sid = row['setting_id'];
    require(a.length == b.length, '$sid event count');
    final allowed = row['allowed_duration_changes'] as List;
    final barline = allowed.isEmpty;
    var durationChanges = 0;
    var beforeDuration = 0.0, afterDuration = 0.0;
    var elapsedDelta = 0.0;
    final seen = List<int>.filled(allowed.length, 0);
    for (var i = 0; i < a.length; i++) {
      require(jsonEncode(a[i]['midi_pitches']) == jsonEncode(b[i]['midi_pitches']), '$sid pitch at $i');
      require(a[i]['is_tie'] == b[i]['is_tie'], '$sid tie at $i');
      require(a[i]['is_rest'] == b[i]['is_rest'], '$sid rest at $i');
      final da = (a[i]['duration_quarter'] as num).toDouble();
      final db = (b[i]['duration_quarter'] as num).toDouble();
      final sa = (a[i]['start_quarter'] as num).toDouble();
      final sb = (b[i]['start_quarter'] as num).toDouble();
      require((sb-sa-elapsedDelta).abs() < .00001, '$sid unplanned start-time change at $i');
      if ((da-db).abs() > .00001) {
        durationChanges++;
        if (row['strict_length'] == true) {
          require(a[i]['abc_text'] != b[i]['abc_text'], '$sid changed duration of an unedited token at $i');
        }
        final pitch = RegExp(r"^(?:\^{1,2}|_{1,2}|=)?[A-Ga-gzZxX][,']*").firstMatch(a[i]['abc_text'] as String)?.group(0);
        final match = allowed.indexWhere((p) => p['pitch']==pitch &&
          ((p['before'] as num)-da).abs()<.00001 && ((p['after'] as num)-db).abs()<.00001);
        require(match>=0, '$sid unplanned duration change at $i');
        seen[match]++;
      }
      elapsedDelta += db-da;
      if (barline) require((da-db).abs() < .00001 && (sa-sb).abs() < .00001, '$sid timing at $i');
      if (sa+da > beforeDuration) beforeDuration = sa+da;
      if (sb+db > afterDuration) afterDuration = sb+db;
    }
    require((afterDuration-beforeDuration-elapsedDelta).abs() < .00001, '$sid total duration');
    result.add({
      if (row.containsKey('variant')) 'variant':row['variant'],
      'setting_id': sid, 'passed': true, 'event_count': a.length,
      'pitch_and_tie_sequence_unchanged': true,
      'all_event_timings_unchanged': durationChanges==0,
      'changed_note_durations': durationChanges,
      'before_duration_quarter': beforeDuration,
      'after_duration_quarter': afterDuration,
      'approved_written_changes': allowed,
      'played_occurrences': seen,
      'parser_normalized_or_unplayed_change': allowed.isNotEmpty && seen.any((n)=>n==0),
      'duration_delta_quarter': elapsedDelta,
    });
    } catch (error) {
      result.add({if (row.containsKey('variant')) 'variant':row['variant'], 'setting_id':row['setting_id'], 'passed':false, 'reason':'$error'});
    }
  }
  print(jsonEncode(result));
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tradmate-repo", type=Path, required=True)
    parser.add_argument("--dart", required=True, help="Path to a standalone Dart SDK executable")
    parser.add_argument("--plan", type=Path, action="append", help="Change file (repeatable); defaults to changes/*.json")
    parser.add_argument("--allow-failures", action="store_true", help="Report rejected proposals without a failing exit status")
    args = parser.parse_args()
    repo = args.tradmate_repo.resolve()
    files = args.plan or sorted((ROOT / "changes").glob("*.json"))
    patches = defaultdict(list)
    for path in files:
        for patch in json.loads(path.read_text())["corrections"]:
            patches[patch['setting_id']].append(patch)
    rows = []
    with (ROOT / "json/tunes.json").open() as stream:
        for line in stream:
            text = line.strip().rstrip(",")
            if text and text not in ("[", "]"):
                row = json.loads(text)
                for patch in patches.get(row["setting_id"], ()):
                    grouped = {}
                    before = [e for b in measures(patch['before_abc'])[0] for e in b.events]
                    after = [e for b in measures(patch['after_abc'])[0] for e in b.events]
                    assert len(before) == len(after)
                    for a, b in zip(before, after):
                        assert a.pitch == b.pitch
                        if a.duration != b.duration:
                            key = a.pitch, float(a.duration/2), float(b.duration/2)
                            grouped[key] = grouped.get(key, 0) + 1
                    allowed = [{'pitch':p, 'before':a, 'after':b, 'written_occurrences':count}
                               for (p,a,b),count in grouped.items()]
                    rows.append({**row, **patch, 'allowed_duration_changes':allowed})
    assert len(rows) == sum(map(len, patches.values()))
    with tempfile.TemporaryDirectory(prefix="session-playback-") as temporary:
        root = Path(temporary)
        pending, hashes = [COMPILER], {}
        while pending:
            name = pending.pop()
            if name in hashes:
                continue
            code = subprocess.check_output(["git", "show", REVISION + ":" + name], cwd=repo)
            hashes[name] = hashlib.sha256(code).hexdigest()
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(code)
            for uri in re.findall(r"(?:import|export|part)\s+'([^']+)'", code.decode()):
                if uri.startswith("dart:"):
                    continue
                if uri.startswith("package:"):
                    raise ValueError("Unexpected external package: " + uri)
                path = (repo / Path(name).parent / uri).resolve().relative_to(repo)
                pending.append(str(path))
        (root / "input.json").write_text(json.dumps(rows))
        (root / "check.dart").write_text(RUNNER)
        output = subprocess.check_output([args.dart, str(root / "check.dart"), str(root / "input.json")], text=True)
        checks = json.loads(output)
        print(json.dumps({
            "compiler_repository": "TradMate", "compiler_commit": REVISION,
            "compiler_files_sha256": hashes, "compiler_modifications": [],
            "automatic_repairs": False, "setting_specific_patches": False,
            "checks": checks,
        }, indent=2))
        if not args.allow_failures and any(not r['passed'] for r in checks):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
