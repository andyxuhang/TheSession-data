#!/usr/bin/env python3
"""Compare reviewed ABC using an unmodified, pinned TradMate compiler snapshot."""

from collections import defaultdict
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from pitch_fixes import PITCH_RULES, key_signature, resolve_pitches
from scan import NOTE, measures, rows as read_rows, unique_settings
from syntax_fixes import SYNTAX_RULES

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

Map verifyInsertion(Map row, List before, List after) {
  final insertion = row['insertion'] as Map;
  final duration = (insertion['duration_quarter'] as num).toDouble();
  final token = insertion['token'];
  var i = 0, j = 0;
  var inserted = 0;
  String? writtenLocation;
  while (j < after.length) {
    final event = after[j];
    final original = i < before.length ? before[i] : null;
    final originalStart = original == null ? 0 : original['start_quarter'] as num;
    final nextStart = event['start_quarter'] as num;
    if (original != null &&
        (nextStart - originalStart - duration * inserted).abs() < .00001 &&
        ['midi_pitches', 'abc_text', 'duration_quarter', 'is_tie', 'is_rest']
            .every((key) => jsonEncode(event[key]) == jsonEncode(original[key]))) {
      i++;
      j++;
      continue;
    }
    final writtenId = event['written_id'] as String;
    final location = insertion.containsKey('midi') ? writtenId : writtenId.split(':').first;
    require(event['abc_text'] == token && !event['is_rest'] && !event['is_tie'],
        'Unexpected inserted playback event');
    require(((event['duration_quarter'] as num) - duration).abs() < .00001,
        'Unexpected inserted duration');
    if (insertion.containsKey('midi')) {
      require(jsonEncode(event['midi_pitches']) == jsonEncode([insertion['midi']]), 'Unexpected edited pitch');
    }
    require(writtenLocation == null || writtenLocation == location, 'Note count changed at another written position');
    writtenLocation = location;
    inserted++;
    j++;
  }
  require(i == before.length && inserted > 0, 'Original notes did not align after insertion');
  return {
    if (row.containsKey('variant')) 'variant':row['variant'],
    'setting_id':row['setting_id'], 'passed':true, 'event_count':after.length,
    'changed_note_occurrences':inserted,
    'inserted_playback_events': inserted, 'inserted_token': token,
    'duration_delta_quarter': inserted * duration};
}

Map verifyPitchChanges(Map row, List before, List after) {
  final sid = row['setting_id'];
  final expected = row['pitch_changes'] as List;
  final playedBefore = List.generate(expected.length, (_) => <String>{});
  final playedAfter = List.generate(expected.length, (_) => <String>{});
  require(before.length == after.length, '$sid event count');
  var changed = 0;
  for (var i = 0; i < before.length; i++) {
    final a = before[i], b = after[i];
    for (final field in ['start_quarter', 'duration_quarter', 'is_tie', 'is_rest']) {
      require(a[field] == b[field], '$sid changed $field at $i');
    }
    final unchanged = jsonEncode(a['midi_pitches']) == jsonEncode(b['midi_pitches']);
    final sameToken = a['abc_text'] == b['abc_text'];
    if (unchanged && sameToken) continue;
    final match = expected.indexWhere((change) =>
      a['abc_text'] == change['old_token'] && b['abc_text'] == change['new_token'] &&
      jsonEncode(a['midi_pitches']) == jsonEncode([change['old_midi']]) &&
      jsonEncode(b['midi_pitches']) == jsonEncode([change['new_midi']]));
    require(match >= 0, '$sid unexpected pitch or token change at $i');
    require(!a['is_tie'] && !b['is_tie'] && !a['is_rest'] && !b['is_rest'],
        '$sid corrected token is tied or silent');
    playedBefore[match].add(a['written_id'] as String);
    playedAfter[match].add(b['written_id'] as String);
    changed++;
  }
  for (var i = 0; i < expected.length; i++) {
    final count = expected[i]['written_occurrences'];
    require(playedBefore[i].length == count && playedAfter[i].length == count,
        '$sid expected written notes were not all heard');
  }
  return {
    if (row.containsKey('variant')) 'variant': row['variant'],
    'setting_id': sid,
    'passed': true,
    'event_count': before.length,
    'all_event_timings_unchanged': true,
    'changed_played_pitches': changed,
    'written_pitch_changes': expected,
  };
}

bool verifiesNormalizedDuration(Map row, Map edit) {
    final before = compile(row, '| ${edit['before_measure'].trim()} |')['events'] as List;
    final after = compile(row, '| ${edit['after_measure'].trim()} |')['events'] as List;
    final index = edit['note_index'] as int;
    if (before.length != edit['note_count'] || after.length != before.length) return false;
    for (var i = 0; i < before.length; i++) {
      for (final field in ['abc_text', 'midi_pitches', 'start_quarter', 'duration_quarter', 'is_tie', 'is_rest']) {
        if (jsonEncode(before[i][field]) != jsonEncode(after[i][field])) return false;
      }
    }
    final event = after[index];
    return !event['is_tie'] && !event['is_rest'] && event['abc_text'] == edit['new_token'] &&
        ((event['duration_quarter'] as num) - (edit['after'] as num)).abs() < .00001;
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
    if (row.containsKey('pitch_changes')) {
      result.add(verifyPitchChanges(row, a, b));
      continue;
    }
    if (row.containsKey('insertion')) {
      final deletion = row['insertion']['direction'] == -1;
      final report = deletion ? verifyInsertion(row, b, a) : verifyInsertion(row, a, b);
      if (deletion) {
        report['event_count'] = b.length;
        report['removed_playback_events'] = report.remove('inserted_playback_events');
        report['removed_token'] = report.remove('inserted_token');
        report['duration_delta_quarter'] = -report['duration_delta_quarter'];
      }
      result.add(report);
      continue;
    }
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
          (!p.containsKey('old_token') || (p['old_token']==a[i]['abc_text'] && p['new_token']==b[i]['abc_text'])) &&
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
    final durationEdits = row['duration_edits'] as List?;
    final normalizedDuration = durationEdits != null && durationChanges == 0 &&
        durationEdits.every((edit) => verifiesNormalizedDuration(row, edit));
    if (durationEdits != null) {
      require(seen.every((count) => count > 0) || normalizedDuration, '$sid expected duration change was not heard');
    }
    result.add({
      if (row.containsKey('variant')) 'variant':row['variant'],
      'setting_id': sid, 'passed': true, 'event_count': a.length,
      'pitch_and_tie_sequence_unchanged': true,
      'all_event_timings_unchanged': durationChanges==0,
      'changed_note_durations': durationChanges,
      if (normalizedDuration) 'primary_duration_already_normalized': true,
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


def prepare_pitch_changes(patch, mode):
    before_body, after_body = patch['before_abc'], patch['after_abc']
    before, error_a = measures(before_body)
    after, error_b = measures(after_body)
    key = key_signature(mode)
    if error_a or error_b or key is None or len(before) != len(after):
        raise ValueError('Pitch edit changed measure structure: '+patch['setting_id'])
    by_position = {(e['bar'],e['note']):e for e in patch['evidence']}
    actual = set()
    deltas = defaultdict(list)
    for bar, (old, new) in enumerate(zip(before,after),1):
        if old.signature == new.signature:
            continue
        if (old.error or new.error or (old.left,old.right)!=(new.left,new.right)
                or len(old.events) != len(new.events)):
            raise ValueError('Pitch edit changed a damaged measure: '+patch['setting_id'])
        old_midi, new_midi = resolve_pitches(old.events,key), resolve_pitches(new.events,key)
        for note,(a,b) in enumerate(zip(old.events,new.events),1):
            x,y = old_midi[note-1],new_midi[note-1]
            original, corrected = before_body[a.start:a.end], after_body[b.start:b.end]
            if a.duration != b.duration or a.tied != b.tied:
                raise ValueError('Pitch edit changed timing: '+patch['setting_id'])
            if original == corrected and x == y:
                continue
            ev = by_position.get((bar,note))
            if ev is None or a.tied or (x,y) != (ev['before_midi'],ev['after_midi']) or x == y:
                raise ValueError('Unexpected written pitch change: '+patch['setting_id'])
            actual.add((bar,note))
            deltas[original,corrected,x,y].append(dict(old_start=a.start,new_start=b.start))
    if actual != by_position.keys():
        raise ValueError('Pitch changes differ from reviewed notes: '+patch['setting_id'])
    return [dict(old_token=a,new_token=b,old_midi=x,new_midi=y,written_occurrences=len(locations),
                 locations=locations)
            for (a,b,x,y),locations in deltas.items()]


def prepare_note_count(patch, edit):
    """Convert reviewed measure offsets to positions in the longer ABC body."""
    direction = edit['note_count_change']
    longer, shorter = ('after_abc','before_abc') if direction==1 else ('before_abc','after_abc')
    before, error = measures(patch[longer])
    if error or direction not in (-1,1):
        raise ValueError('Invalid reviewed note-count edit: '+patch['setting_id'])
    bar = before[edit['bar']-1]
    fragment = edit['after'] if direction==1 else edit['before']
    token = edit['token']
    positions = [bar.start+offset for offset in edit['possible_offsets']]
    if (patch[longer][bar.start:bar.end]!=fragment or not positions or any(
        patch[longer][at:at+len(token)]!=token or
        patch[longer][:at]+patch[longer][at+len(token):]!=patch[shorter]
        for at in positions
    )):
        raise ValueError('Note-count offsets differ from the reviewed change: '+patch['setting_id'])
    return {'direction':direction,'token':token,'midi':edit['midi'],'positions':positions,
            'duration_quarter':float(Fraction(edit['duration_eighths'])/2)}


def prepare_reference_duration(patch, edit):
    before,_ = measures(patch['before_abc'])
    after,_ = measures(patch['after_abc'])
    index = edit['bar']-1
    a,b = before[index],after[index]
    at = edit['token_offset']
    old,new = edit['old_token'],edit['new_token']
    old_duration = Fraction(edit['old_duration_eighths'])
    new_duration = Fraction(edit['new_duration_eighths'])
    if (old_duration==new_duration or patch['before_abc'][a.start:a.end]!=edit['before']
            or patch['after_abc'][b.start:b.end]!=edit['after']
            or edit['before'][at:at+len(old)]!=old or edit['after'][at:at+len(new)]!=new):
        raise ValueError('Duration edit does not match the reviewed note: '+patch['setting_id'])
    note_index = next(i for i,e in enumerate(b.events) if e.start==b.start+at)
    return {'note_index':note_index,'note_count':len(b.events),
            'before_measure':edit['before'],'after_measure':edit['after'],'pitch':NOTE.fullmatch(old)['pitch'],'old_token':old,'new_token':new,
            'before':float(old_duration/2),'after':float(new_duration/2),'written_occurrences':1,
            'old_start':a.start+at,'new_start':b.start+at}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tradmate-repo", type=Path, required=True)
    parser.add_argument("--dart", required=True, help="Path to a standalone Dart SDK executable")
    parser.add_argument("--plan", type=Path, action="append", help="Change file (repeatable); defaults to changes/*.json")
    parser.add_argument("--allow-failures", action="store_true", help="Report rejected proposals without a failing exit status")
    parser.add_argument("--abcjs", action="store_true", help="Cross-check pitch and notation edits with the vendored abcjs")
    args = parser.parse_args()
    repo = args.tradmate_repo.resolve()
    files = args.plan or sorted((ROOT / "changes").glob("*.json"))
    patches = defaultdict(list)
    for path in files:
        for patch in json.loads(path.read_text())["corrections"]:
            patches[patch['setting_id']].append(patch)
    rows = []
    records = unique_settings(read_rows(ROOT / "json/tunes.json"))
    for row in records.values():
        for patch in patches.get(row["setting_id"], ()):
            evidence = patch['evidence']
            if isinstance(evidence,list) and evidence and all(e['rule'] in PITCH_RULES for e in evidence):
                rows.append({**row, **patch, 'pitch_changes':prepare_pitch_changes(patch,row['mode'])})
                continue
            if isinstance(evidence,list) and evidence and all('old_duration_eighths' in ev for ev in evidence):
                edits = [prepare_reference_duration(patch,ev) for ev in evidence]
                unique = {(e['old_token'],e['new_token'],e['before'],e['after']):e for e in edits}
                rows.append({**row, **patch, 'duration_edits':edits,
                             'allowed_duration_changes':list(unique.values()), 'strict_length':True})
                continue
            if isinstance(evidence,list) and evidence and all(e['rule'] in SYNTAX_RULES for e in evidence):
                rows.append({**row, **patch, 'syntax_only':True, 'allowed_duration_changes':[]})
                continue
            if isinstance(evidence,list) and len(evidence)==1 and 'note_count_change' in evidence[0]:
                rows.append({**row, **patch, 'insertion':prepare_note_count(patch,evidence[0])})
                continue
            grouped = {}
            before = [e for b in measures(patch['before_abc'])[0] for e in b.events]
            after = [e for b in measures(patch['after_abc'])[0] for e in b.events]
            insertions = [e for e in patch['evidence'] if e['rule'] == 'missing_note'] if isinstance(patch.get('evidence'), list) else []
            if insertions:
                assert len(insertions) == 1 and len(after) == len(before)+1
                event = insertions[0]
                rows.append({**row, **patch, 'insertion':{'token':event['token'],
                    'duration_quarter':float(Fraction(event['duration_eighths'])/2)}})
                continue
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
        if args.abcjs:
            library = repo/'third_party/abcjs/abcjs-basic-min.js'
            secondary_input = root/'abcjs-input.json'
            secondary_input.write_text(json.dumps([
                {**row, 'pitch_changes': row.get('pitch_changes', [])}
                for row in rows if 'pitch_changes' in row or row.get('syntax_only')
                or row.get('insertion',{}).get('positions') or 'duration_edits' in row
            ]),encoding='utf8')
            output = subprocess.check_output(['node',str(ROOT/'tools/check_abcjs_pitches.js'),
                                              str(library),str(secondary_input)],text=True)
            comparison = json.loads(output)
            secondary = {(r['setting_id'],r.get('variant')): r for r in comparison['results']}
            library_hash = hashlib.sha256(library.read_bytes()).hexdigest()
            for check in checks:
                other = secondary.get((check['setting_id'],check.get('variant')))
                if other is None:
                    continue
                check['abcjs'] = {**other,'version':comparison['version'],
                                  'sha256':library_hash}
                if check['passed'] and (
                    not other['passed']
                    or other.get('changed_played_pitches',0) != check.get('changed_played_pitches',0)
                    or other.get('changed_note_occurrences',0) != check.get('changed_note_occurrences',0)
                    or ('changed_note_durations' in other
                        and not check.get('primary_duration_already_normalized')
                        and other['changed_note_durations']!=check.get('changed_note_durations'))
                ):
                    check['passed'] = False
                    check['reason'] = 'abcjs: '+other.get('reason','played pitch-change counts differ')
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
