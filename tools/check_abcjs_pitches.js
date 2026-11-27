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
    return tunes[0].setUpAudio({}).tracks.map(track => track.filter(event => event.cmd === 'note'));
}

function check(row) {
    const header = `X:${row.setting_id}\nT:${row.name}\nR:${row.type}\nM:${row.meter}\nL:1/8\nK:${row.mode}\n`;
    const before = playback(row.before_abc, header);
    const after = playback(row.after_abc, header);
    if (before.length !== after.length) throw new Error('Track count changed');
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
    return { passed: true, changed_played_pitches: occurrences };
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
