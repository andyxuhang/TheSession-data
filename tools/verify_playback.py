#!/usr/bin/env python3
"""Compare reviewed ABC using an unmodified, pinned TradMate compiler snapshot."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

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
    final before = compile(row, row['before_abc']);
    final after = compile(row, row['after_abc']);
    final a = before['events'] as List, b = after['events'] as List;
    final sid = row['setting_id'];
    require(a.length == b.length, '$sid event count');
    final barline = row['category'].toString().contains('barline');
    var durationChanges = 0;
    var beforeDuration = 0.0, afterDuration = 0.0;
    for (var i = 0; i < a.length; i++) {
      require(jsonEncode(a[i]['midi_pitches']) == jsonEncode(b[i]['midi_pitches']), '$sid pitch at $i');
      require(a[i]['is_tie'] == b[i]['is_tie'], '$sid tie at $i');
      final da = (a[i]['duration_quarter'] as num).toDouble();
      final db = (b[i]['duration_quarter'] as num).toDouble();
      final sa = (a[i]['start_quarter'] as num).toDouble();
      final sb = (b[i]['start_quarter'] as num).toDouble();
      if ((da-db).abs() > .00001) durationChanges++;
      if (barline) require((da-db).abs() < .00001 && (sa-sb).abs() < .00001, '$sid timing at $i');
      if (sa+da > beforeDuration) beforeDuration = sa+da;
      if (sb+db > afterDuration) afterDuration = sb+db;
    }
    final expected = sid == '25362' ? -.5 : sid == '1797' ? -1.0 : 0.0;
    require((afterDuration-beforeDuration-expected).abs() < .00001, '$sid total duration');
    require(durationChanges == (barline ? 0 : 2), '$sid changed duration count');
    result.add({
      'setting_id': sid, 'passed': true, 'event_count': a.length,
      'pitch_and_tie_sequence_unchanged': true,
      'all_event_timings_unchanged': barline,
      'changed_note_durations': durationChanges,
      'before_duration_quarter': beforeDuration,
      'after_duration_quarter': afterDuration,
      'expected_duration_delta_quarter': expected,
    });
  }
  print(jsonEncode(result));
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tradmate-repo", type=Path, required=True)
    parser.add_argument("--dart", required=True, help="Path to a standalone Dart SDK executable")
    args = parser.parse_args()
    repo = args.tradmate_repo.resolve()
    plan = json.loads((ROOT / "corrections/round-001.json").read_text())
    patches = {row["setting_id"]: row for row in plan["corrections"]}
    rows = []
    with (ROOT / "json/tunes.json").open() as stream:
        for line in stream:
            text = line.strip().rstrip(",")
            if text and text not in ("[", "]"):
                row = json.loads(text)
                if row["setting_id"] in patches:
                    rows.append({**row, **patches[row["setting_id"]]})
    assert len(rows) == len(patches)
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
        print(json.dumps({
            "compiler_repository": "TradMate", "compiler_commit": REVISION,
            "compiler_files_sha256": hashes, "compiler_modifications": [],
            "automatic_repairs": False, "setting_specific_patches": False,
            "checks": json.loads(output),
        }, indent=2))


if __name__ == "__main__":
    main()
