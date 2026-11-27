const fs = require('node:fs');
const abcjs = require(process.argv[2]);

function normalize(body) {
    return body.replace(/\r\n?/g, '\n');
}

function offset(body, codepointIndex) {
    return normalize(Array.from(body).slice(0, codepointIndex).join('')).length;
}

function playback(body, header) {
    const tunes = abcjs.parseOnly(header + normalize(body) + '\n');
    if (tunes.length !== 1) throw new Error('Expected one parsed tune');
    const tune = tunes[0];
    return {
        tracks: tune.setUpAudio({}).tracks.map(track => track.filter(event => event.cmd === 'note')),
        warnings: tune.warnings?.length ?? 0,
    };
}

function checkNoteCount(row, header, before, after) {
    const edit = row.insertion;
    const originalIsShorter = edit.direction === 1;
    const [shorter, longer] = originalIsShorter ? [before, after] : [after, before];
    const body = originalIsShorter ? row.after_abc : row.before_abc;
    const positions = edit.positions.map(at => header.length + offset(body, at));
    const duration = edit.duration_quarter / 4;
    const locations = new Set();
    let occurrences = 0;
    for (let t = 0; t < shorter.length; t++) {
        let n = 0;
        let elapsed = 0;
        for (const event of longer[t]) {
            const expected = shorter[t][n];
            if (expected && event.pitch === expected.pitch &&
                Math.abs(event.start - expected.start - elapsed) < 1e-8 &&
                Math.abs(event.duration - expected.duration) < 1e-8 && event.gap === expected.gap) {
                n++;
                continue;
            }
            const at = positions.find(p => event.startChar <= p && p < event.endChar);
            if (at === undefined || event.pitch !== edit.midi || Math.abs(event.duration - duration) >= 1e-8) {
                throw new Error('Unexpected note or timing change');
            }
            locations.add(at);
            elapsed += duration;
            occurrences++;
        }
        if (n !== shorter[t].length) throw new Error('An original note is missing');
    }
    if (!occurrences || locations.size !== 1) throw new Error('Expected note count change was not heard at one written location');
    return { passed: true, changed_note_occurrences: occurrences };
}

function check(row) {
    const header = `X:${row.setting_id}\nT:${row.name}\nR:${row.type}\nM:${row.meter}\nL:1/8\nK:${row.mode}\n`;
    const original = playback(row.before_abc, header);
    const corrected = playback(row.after_abc, header);
    const before = original.tracks;
    const after = corrected.tracks;
    if (row.syntax_only && corrected.warnings > original.warnings) {
        throw new Error('Notation warnings increased');
    }
    if (before.length !== after.length) throw new Error('Track count changed');
    if (row.insertion?.positions) return checkNoteCount(row, header, before, after);
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
