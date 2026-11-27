#!/usr/bin/env python3
"""Find small ABC typos with exact arithmetic and matching complete bars.

No network, model, rest insertion, pitch substitution or meter inference is used.
Unsupported syntax and unmatched irregular bars are reported, never guessed.
"""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from fractions import Fraction as F
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
NOTE = re.compile(r"(?P<pitch>(?:\^{1,2}|_{1,2}|=)?[A-Ga-gzxxZ][,']*)(?P<length>\d+(?:/\d*)*|/+(?:\d+)?)?")
BAR = re.compile(r"(?::\|:|:\||\|\||\|:|\|\]|\[\||\|)(?:[1-9](?:[,-][1-9])*)?|\[[1-9](?:[,-][1-9])*")
MASK = re.compile(r'"(?:[^"\\]|\\.)*"|\{[^{}]*\}|![^!\r\n]*!|\+[^+\r\n]*\+|%[^\r\n]*')
TUPLET = re.compile(r"\((\d)(?::(\d*))?(?::(\d+))?")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\ufeff]")
TYPES = {"reel", "jig", "slip jig", "slipjig", "polka", "hornpipe", "slide", "single jig", "double jig", "strathspey"}


@dataclass
class Event:
    pitch: str
    length: str
    start: int
    end: int
    length_start: int
    duration: F
    tuplet: bool = False
    broken: bool = False
    tied: bool = False


@dataclass
class Measure:
    start: int
    end: int
    left: str
    right: str
    events: list = field(default_factory=list)
    error: str = ""

    @property
    def duration(self):
        return sum((e.duration for e in self.events), F())

    @property
    def signature(self):
        return tuple((e.pitch, str(e.duration), e.tied) for e in self.events)


@lru_cache(maxsize=128)
def length(value):
    if not value:
        return F(1)
    if "/" not in value:
        return F(int(value))
    top, tail = value.split("/", 1)
    if tail and "/" not in tail:
        return F(int(top or 1), int(tail))
    if not tail or set(tail) == {"/"}:
        return F(int(top or 1), 2 ** (1 + len(tail)))
    raise ValueError("unsupported note length")


def parse_bar(text, offset, left, right):
    bar = Measure(offset, offset + len(text), left, right)
    masked = MASK.sub(lambda m: " " * len(m[0]), text)
    i, remaining, factor, pending = 0, 0, F(1), None
    try:
        while i < len(masked):
            c = masked[i]
            tuplet = TUPLET.match(masked, i)
            if tuplet:
                if remaining:
                    raise ValueError("nested tuplet")
                p = int(tuplet[1])
                q = int(tuplet[2]) if tuplet[2] else {2: 3, 3: 2, 4: 3}.get(p)
                if not q:
                    raise ValueError("unsupported tuplet")
                remaining = int(tuplet[3] or p)
                factor = F(q, p)
                i = tuplet.end()
                continue
            if c.isspace() or c in "()~.uvHLMOPST" or CONTROL.fullmatch(c):
                i += 1
                continue
            note = NOTE.match(masked, i)
            if note:
                if "Z" in note["pitch"]:
                    raise ValueError("multi-measure rest")
                duration = length(note["length"] or "")
                in_tuplet = remaining > 0
                if remaining:
                    duration *= factor
                    remaining -= 1
                event = Event(note["pitch"], note["length"] or "", offset + i,
                              offset + note.end(), offset + note.end("pitch"), duration, in_tuplet)
                if pending:
                    event.duration *= pending
                    event.broken = True
                    pending = None
                bar.events.append(event)
                i = note.end()
                continue
            if c in "><" and bar.events and not pending:
                j = i
                while j < len(masked) and masked[j] == c:
                    j += 1
                short = F(1, 2 ** (j - i))
                bar.events[-1].duration *= (2 - short) if c == ">" else short
                bar.events[-1].broken = True
                pending = short if c == ">" else 2 - short
                i = j
                continue
            if c == "-" and bar.events:
                bar.events[-1].tied = True
                i += 1
                continue
            if c == "\\" and not masked[i+1:].strip():
                break
            raise ValueError("unsupported syntax " + repr(c))
        if remaining or pending:
            raise ValueError("rhythm crosses barline")
    except (ValueError, ZeroDivisionError) as error:
        bar.error = str(error)
    return bar


def measures(body):
    if re.search(r"(?m)^\s*[A-Za-z]:|\[[A-Za-z]:", body):
        return [], "embedded field or voice"
    masked = MASK.sub(lambda m: " " * len(m[0]), body)
    result, start, left = [], 0, ""
    for marker in BAR.finditer(masked):
        piece = body[start:marker.start()]
        if piece.strip():
            bar = parse_bar(piece, start, left, marker[0])
            if bar.events or bar.error:
                result.append(bar)
        start, left = marker.end(), marker[0]
    if body[start:].strip():
        bar = parse_bar(body[start:], start, left, "")
        if bar.events or bar.error:
            result.append(bar)
    return result, ""


def rows(path):
    with path.open() as stream:
        for line in stream:
            text = line.strip().rstrip(",")
            if text and text not in ("[", "]"):
                yield json.loads(text)


def unique_settings(records):
    """Collapse rows duplicated by the upstream composer join for analysis."""
    by_id = {}
    for row in records:
        sid = row['setting_id']
        previous = by_id.setdefault(sid, row)
        if previous != row and any(previous[key] != row[key] for key in row if key != 'composer'):
            raise ValueError('Conflicting tune rows for setting ' + sid)
    return by_id


def meter_units(value):
    try:
        a, b = value.split("/")
        return F(int(a) * 8, int(b))
    except (ValueError, ZeroDivisionError):
        return None


def single_character(a, b):
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    longer, shorter = (a, b) if len(a) > len(b) else (b, a)
    return any(longer[:i] + longer[i+1:] == shorter for i in range(len(longer)))


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def scan(data, barlines_only=False):
    parsed, witnesses = {}, defaultdict(list)
    for row in data:
        sid = row["setting_id"]
        bars, problem = measures(row["abc"])
        unit = meter_units(row["meter"])
        parsed[sid] = (bars, problem, unit)
        if not unit or problem:
            continue
        for index, bar in enumerate(bars):
            if not bar.error and bar.duration == unit:
                key = (row["tune_id"], row["meter"], row["mode"], bar.signature)
                witnesses[key].append((sid, index))

    proposals, issues, stats = [], [], Counter()
    for row in data:
        sid, body = row["setting_id"], row["abc"]
        bars, problem, unit = parsed[sid]
        stats["settings"] += 1
        if problem or not unit or not bars:
            issues.append({"setting_id": sid, "category": "unsupported", "reason": problem or "meter or empty melody"})
            continue
        def witness(events, exclude=()):
            signature = tuple((e.pitch, str(e.duration), e.tied) for e in events)
            key = (row["tune_id"], row["meter"], row["mode"], signature)
            return [(s, i) for s, i in witnesses[key] if (s, i) not in exclude]

        def supported_pair(left, right, ordinary):
            first, second = witness(left), witness(right)
            successors = set(second)
            adjacent = [(s, j) for s, j in first if (s, j+1) in successors
                        and parsed[s][0][j].right == "|" and parsed[s][0][j+1].left == "|"
                        and parsed[s][0][j].end + 1 == parsed[s][0][j+1].start]
            if adjacent:
                return adjacent, [(s, j+1) for s,j in adjacent]
            return (first, second) if ordinary else ([], [])

        full = sum(not b.error and b.duration == unit for b in bars)
        regular = full >= 6 and full / len(bars) >= .75
        eligible = regular and row["type"].lower() in TYPES
        edits, evidence, used = [], [], set()
        masked_body = MASK.sub(lambda m: " " * len(m[0]), body)
        for control in (() if barlines_only else CONTROL.finditer(masked_body)):
            edits.append((control.start(), control.end(), ""))
            evidence.append({"rule": "stray_control", "offset": control.start(),
                             "before": control[0], "after": "", "codepoint": f"U+{ord(control[0]):04X}"})
        for i, bar in enumerate(bars):
            if bar.error:
                issues.append({"setting_id": sid, "bar": i + 1, "category": "unsupported", "reason": bar.error,
                               "fragment": body[bar.start:bar.end]})
                continue
            if bar.duration == unit:
                continue
            detail = {"setting_id": sid, "bar": i + 1, "category": "irregular",
                      "duration_eighths": str(bar.duration), "expected_eighths": str(unit),
                      "fragment": body[bar.start:bar.end], "reason": "No unique supported correction"}
            issues.append(detail)
            if not regular or i in used:
                continue
            # A double-length measure can lose a divider, provided both halves
            # already occur as complete measures of this tune in the same key.
            if bar.duration == 2 * unit:
                total, split = F(), None
                for k, event in enumerate(bar.events[:-1], 1):
                    total += event.duration
                    if total == unit and not event.tied and not event.broken and not event.tuplet:
                        split = k
                        break
                if split:
                    left, right = bar.events[:split], bar.events[split:]
                    a, b = supported_pair(left, right, eligible and bar.left and bar.right)
                    if a and b:
                        at = left[-1].end
                        edits.append((at, at, "|"))
                        evidence.append({"rule": "missing_barline", "bar": i + 1,
                                         "witnesses": [a[:4], b[:4]], "before": body[bar.start:bar.end],
                                         "after": body[bar.start:at] + "|" + body[at:bar.end]})
                        used.add(i)
                        detail["category"] = "proposed"
                        continue
            # Reposition a plain divider between an overfull and a short bar.
            if (i + 1 < len(bars) and bar.right == "|" and bars[i+1].left == "|"
                    and not bars[i+1].error and i+1 not in used):
                nxt = bars[i+1]
                internal = i > 0 and i+2 < len(bars) and bar.left == "|" and nxt.right == "|"
                if (bar.duration + nxt.duration == 2*unit and nxt.start == bar.end+1
                        and (bar.duration > unit or internal)):
                    events = bar.events + nxt.events
                    total, split = F(), None
                    for k, event in enumerate(events[:-1], 1):
                        total += event.duration
                        if total == unit and not event.tied and not event.broken and not event.tuplet:
                            split = k
                            break
                    if split:
                        a, b = supported_pair(events[:split], events[split:], eligible and bar.duration > unit)
                        if a and b:
                            at = events[split-1].end
                            if at in (bar.end, nxt.start):
                                continue
                            divider = "" if body[bar.end-1].isspace() or body[nxt.start].isspace() else " "
                            edits.extend([(bar.end, nxt.start, divider), (at, at, "|")])
                            fragment = body[bar.start:nxt.end]
                            for x, y, value in sorted(edits[-2:], reverse=True):
                                fragment = fragment[:x-bar.start]+value+fragment[y-bar.start:]
                            evidence.append({"rule": "misplaced_barline", "bar": i+1, "witnesses": [a[:4], b[:4]],
                                             "before": body[bar.start:nxt.end],
                                             "after": fragment})
                            used.update((i, i+1))
                            detail["category"] = "proposed"
                            continue
            if barlines_only or not eligible:
                continue
            # A one-character length typo needs a matching complete bar and a
            # matching adjacent bar in that witness's phrase. Never alter a
            # pickup, cadence, repeat ending, tuplet, tie or broken rhythm.
            if (not 0 < i < len(bars)-1 or bar.left != "|" or bar.right != "|"
                    or bars[i-1].duration != unit or bars[i+1].duration != unit
                    or any(e.tuplet or e.broken or e.tied or e.pitch[0] in "zxZ" for e in bar.events)):
                continue
            candidates = {}
            for j, event in enumerate(bar.events):
                for suffix in ("", "/", "//", "2", "3", "4", "6", "8", "3/2"):
                    if not single_character(event.length, suffix):
                        continue
                    replacement = length(suffix)
                    if bar.duration - event.duration + replacement != unit:
                        continue
                    events = [Event(e.pitch, e.length, e.start, e.end, e.length_start,
                                    replacement if k == j else e.duration, e.tuplet, e.broken, e.tied)
                              for k, e in enumerate(bar.events)]
                    options = witness(events, ((sid, i),))
                    supporting = []
                    for wsid, wi in options:
                        wb = parsed[wsid][0]
                        before_match = wi > 0 and wb[wi-1].signature == bars[i-1].signature
                        after_match = wi+1 < len(wb) and wb[wi+1].signature == bars[i+1].signature
                        if before_match or after_match:
                            supporting.append((wsid, wi))
                    if supporting:
                        candidates[(event.length_start, event.end, suffix)] = supporting
            if len(candidates) == 1:
                edit, support = next(iter(candidates.items()))
                edits.append(edit)
                evidence.append({"rule": "note_length", "bar": i+1, "witnesses": support[:6],
                                 "before": body[bar.start:bar.end],
                                 "after": body[bar.start:edit[0]]+edit[2]+body[edit[1]:bar.end]})
                used.add(i)
                detail["category"] = "proposed"
                continue
            # An omitted triplet marker is accepted only when the resulting
            # entire measure and one adjacent measure have an exact witness.
            triplets = {}
            for j in range(len(bar.events)-2):
                run = bar.events[j:j+3]
                if any(e.duration != F(1, 2) for e in run) or bar.duration-F(1, 2) != unit:
                    continue
                if not re.fullmatch(r"[A-Ga-g][,']*/\s*[A-Ga-g][,']*/\s*[A-Ga-g][,']*/",
                                    body[run[0].start:run[-1].end]):
                    continue
                events = [Event(e.pitch, e.length, e.start, e.end, e.length_start,
                                e.duration*F(2, 3) if j <= k < j+3 else e.duration,
                                e.tuplet, e.broken, e.tied) for k,e in enumerate(bar.events)]
                support = []
                for wsid, wi in witness(events):
                    wb = parsed[wsid][0]
                    if ((wi > 0 and wb[wi-1].signature == bars[i-1].signature) or
                            (wi+1 < len(wb) and wb[wi+1].signature == bars[i+1].signature)):
                        support.append((wsid, wi))
                if support:
                    triplets[run[0].start] = support
            if not candidates and len(triplets) == 1:
                at, support = next(iter(triplets.items()))
                edits.append((at, at, "(3"))
                evidence.append({"rule": "missing_triplet", "bar": i+1, "witnesses": support[:6],
                                 "before": body[bar.start:bar.end],
                                 "after": body[bar.start:at]+"(3"+body[at:bar.end]})
                used.add(i)
                detail["category"] = "proposed"
        if edits:
            corrected = body
            for start, end, text in sorted(edits, reverse=True):
                corrected = corrected[:start] + text + corrected[end:]
            new_bars, error = measures(corrected)
            # Exact-written-note comparison, independent of playback parsing.
            a = [e.pitch for bar in bars for e in bar.events]
            b = [e.pitch for bar in new_bars for e in bar.events]
            if error or a != b or len(new_bars) < len(bars):
                raise ValueError("Scanner altered note sequence: " + sid)
            proposals.append({"tune_id": row["tune_id"], "setting_id": sid, "name": row["name"],
                              "original_contributor": row["username"],
                              "source_url": f"https://thesession.org/tunes/{row['tune_id']}#setting{sid}",
                              "category": "+".join(sorted({e['rule'] for e in evidence})),
                              "before_abc": body, "after_abc": corrected,
                              "before_sha256": sha(body), "after_sha256": sha(corrected),
                              "edits": [{"start": s, "end": e, "text": t} for s, e, t in sorted(edits)],
                              "evidence": evidence})
            stats["settings_with_proposals"] += 1
            for item in evidence:
                stats[item["rule"]] += 1
        stats["bars"] += len(bars)
    return proposals, issues, dict(stats)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "json/tunes.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = list(rows(args.source))
    proposals, issues, stats = scan(data)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "fixes.json").write_text(json.dumps({"corrections": proposals}, ensure_ascii=False, indent=2)+"\n")
    with (args.output / "findings.jsonl").open("w") as out:
        for issue in issues:
            out.write(json.dumps(issue, ensure_ascii=False)+"\n")
    (args.output / "summary.json").write_text(json.dumps(stats, indent=2)+"\n")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
