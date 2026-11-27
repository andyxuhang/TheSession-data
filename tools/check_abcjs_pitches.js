const fs = require('node:fs');
const abcjs = require(process.argv[2]);

function normalize(body) {
    return body.replace(/\r\n?/g, '\n');
}

function offset(body, codepointIndex) {
    return normalize(Array.from(body).slice(0, codepointIndex).join('')).length;
}

function playback(body, header, options) {
    const tunes = abcjs.parseOnly(header + normalize(body) + '\n');
    if (tunes.length !== 1) throw new Error('Expected one parsed tune');
    const tune = tunes[0];
    return {
        tracks: tune.setUpAudio(options).tracks.map(track => track.filter(event => event.cmd === 'note')),
        warnings: tune.warnings?.length ?? 0,
    };
}

function alignWithoutNote(shorter, longer, position, edit) {
    const duration = edit.duration_quarter / 4;
    let occurrences = 0;
    for (let t = 0; t < shorter.length; t++) {
        let n = 0;
        let elapsed = 0;
        for (const event of longer[t]) {
            if (event.startChar <= position && position < event.endChar) {
                if (event.pitch !== edit.midi || Math.abs(event.duration - duration) >= 1e-8) return 0;
                elapsed += duration;
                occurrences++;
                continue;
            }
            const expected = shorter[t][n++];
            if (!expected || event.pitch !== expected.pitch ||
                Math.abs(event.start - expected.start - elapsed) >= 1e-8 ||
                Math.abs(event.duration - expected.duration) >= 1e-8 || event.gap !== expected.gap) return 0;
        }
        if (n !== shorter[t].length) return 0;
    }
    return occurrences;
}

function checkNoteCount(row, header, before, after) {
    const edit = row.insertion;
    const [shorter, longer] = edit.direction === 1 ? [before, after] : [after, before];
    const body = edit.direction === 1 ? row.after_abc : row.before_abc;
    for (const at of edit.positions) {
        const position = header.length + offset(body, at);
        const occurrences = alignWithoutNote(shorter, longer, position, edit);
        if (occurrences) return { passed: true, changed_note_occurrences: occurrences };
    }
    throw new Error('Written note could not be isolated without other pitch or timing changes');
}

function checkDuration(row, header, before, after) {
    const edits = row.duration_edits.map(edit => ({
        ...edit,
        oldAt: header.length + offset(row.before_abc, edit.old_start),
        newAt: header.length + offset(row.after_abc, edit.new_start),
    }));
    const heard = new Set();
    const equal = (a, b) => Math.abs(a - b) < 1e-8;
    let occurrences = 0;
    for (let t = 0; t < before.length; t++) {
        if (before[t].length !== after[t].length) throw new Error('Note count changed');
        let elapsed = 0;
        for (let n = 0; n < before[t].length; n++) {
            const a = before[t][n];
            const b = after[t][n];
            if (a.pitch !== b.pitch || !equal(b.start - a.start, elapsed) || a.gap !== b.gap) {
                throw new Error('Unexpected pitch or timing change');
            }
            if (equal(a.duration, b.duration)) continue;
            const index = edits.findIndex(edit => a.startChar <= edit.oldAt && edit.oldAt < a.endChar
                && b.startChar <= edit.newAt && edit.newAt < b.endChar
                && equal(a.duration, edit.before / 4) && equal(b.duration, edit.after / 4));
            if (index < 0) throw new Error('Unexpected note duration');
            heard.add(index);
            elapsed += b.duration - a.duration;
            occurrences++;
        }
    }
    if (heard.size !== edits.length) throw new Error('A reviewed duration change was not heard');
    return { passed: true, changed_note_durations: occurrences };
}

function check(row) {
    const header = `X:${row.setting_id}\nT:${row.name}\nR:${row.type}\nM:${row.meter}\nL:1/8\nK:${row.mode}\n`;
    // A duration change can reschedule generated accompaniment. For
    // note-count repairs compare the written melody, leaving chord text intact.
    const writtenNotesOnly = Boolean(row.insertion?.positions);
    const options = writtenNotesOnly ? { chordsOff: true } : {};
    const original = playback(row.before_abc, header, options);
    const corrected = playback(row.after_abc, header, options);
    const before = original.tracks;
    const after = corrected.tracks;
    if (row.syntax_only && corrected.warnings > original.warnings) {
        throw new Error('Notation warnings increased');
    }
    if (before.length !== after.length) throw new Error('Track count changed');
    if (writtenNotesOnly) return { ...checkNoteCount(row, header, before, after), generated_chords_excluded: true };
    if (row.duration_edits) return checkDuration(row, header, before, after);
    const expected = row.pitch_changes.flatMap(change => change.locations.map(location => ({
        ...change,
        beforeOffset: header.length + offset(row.before_abc, location.old_start),
        afterOffset: header.length + offset(row.after_abc, location.new_start),
    })));
    const heard = new Set();
    let occurrences = 0;
    for (let t = 0; t < before.length; t++) {
        if (before[t].length !== after[t].length) throw new Error('Note count changed');
        for (let n = 0; n < before[t].length; n++) {
            const a = before[t][n];
            const b = after[t][n];
            if (a.start !== b.start || a.duration !== b.duration || a.gap !== b.gap) {
                throw new Error('Note timing changed');
            }
            if (a.pitch === b.pitch) continue;
            const index = expected.findIndex(change =>
                change.old_midi === a.pitch && change.new_midi === b.pitch &&
                a.startChar <= change.beforeOffset && change.beforeOffset < a.endChar &&
                b.startChar <= change.afterOffset && change.afterOffset < b.endChar
            );
            if (index < 0) throw new Error('Unexpected pitch change');
            heard.add(index);
            occurrences++;
        }
    }
    if (heard.size !== expected.length) throw new Error('A reviewed note was not heard');
    return {
        passed: true,
        changed_played_pitches: occurrences,
        before_warnings: original.warnings,
        after_warnings: corrected.warnings,
    };
}

const rows = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const results = rows.map(row => {
    const id = { setting_id: row.setting_id, variant: row.variant };
    try {
        return { ...id, ...check(row) };
    } catch (error) {
        return { ...id, passed: false, reason: error.message };
    }
});
process.stdout.write(JSON.stringify({ version: abcjs.signature, results }));
