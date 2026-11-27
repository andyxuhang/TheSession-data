// Parse every distinct setting and retain diagnostics without rendering or audio.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const abcjs = require(path.resolve(process.argv[2]));
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const records = new Map(data.map(row => [row.setting_id, row]));
const stream = fs.createWriteStream(process.argv[4]);
const stats = process.argv[5] ? fs.createWriteStream(process.argv[5]) : null;
let checked = 0;
let flagged = 0;
function melodySignature(notes) {
    const timeline = notes.map(note =>
        [Math.round(note.start * 4000), note.pitch, Math.round(note.duration * 4000)])
        .sort((a,b) => a[0]-b[0] || a[1]-b[1] || a[2]-b[2]);
    return crypto.createHash('sha256').update(JSON.stringify(timeline)).digest('hex');
}
for (const row of records.values()) {
    const abc = 'X:1\nT:Parser check\nM:' + row.meter + '\nL:1/8\nK:' + row.mode + '\n' +
        row.abc.replace(/\r\n?/g, '\n') + '\n';
    let diagnostics;
    let audio = null;
    let comparison = null;
    try {
        const tunes = abcjs.parseOnly(abc);
        diagnostics = tunes.flatMap(tune => tune.warnings || []);
        if (tunes.length !== 1) diagnostics.push('Unexpected tune count ' + tunes.length);
        if (stats && tunes.length === 1) {
            const tracks = tunes[0].setUpAudio({chordsOff: true}).tracks;
            const notes = tracks.flatMap(track => track.filter(event => event.cmd === 'note'));
            audio = {note_events: notes.length, tracks: tracks.length,
                     valid_timing: notes.every(note => Number.isFinite(note.start) &&
                         Number.isFinite(note.duration) && note.start >= 0 && note.duration > 0)};
            if (row._comparison_abc !== undefined) {
                const plainSource = 'X:1\nT:Parser check\nM:' + row.meter +
                    '\nL:1/8\nK:' + row.mode + '\n' + row._comparison_abc + '\n';
                const plain = abcjs.parseOnly(plainSource)[0];
                const tracks = plain.setUpAudio({chordsOff: true}).tracks;
                const plainNotes = tracks.flatMap(track => track.filter(event => event.cmd === 'note'));
                const melody = tracks.flatMap(track => {
                    const seen = new Set();
                    return track.filter(event => {
                        if (event.cmd !== 'note') return false;
                        const text = plainSource.slice(event.startChar, event.endChar).trimStart();
                        if (!/^\[(?:\^\^|__|\^|_|=)?[A-Ga-g]/.test(text)) return true;
                        const key = event.startChar + ':' + event.endChar + ':' + event.start;
                        if (seen.has(key)) return false;
                        seen.add(key);
                        return true;
                    });
                });
                comparison = {sha256: melodySignature(plainNotes),note_events: plainNotes.length,
                              first_chord_pitch_sha256: melodySignature(melody),melody_events: melody.length};
            }
        }
    } catch (error) {
        diagnostics = ['Exception: ' + error.message];
    }
    if (diagnostics.length) {
        flagged++;
        stream.write(JSON.stringify({setting_id: row.setting_id, tune_id: row.tune_id, diagnostics}) + '\n');
    }
    if (stats) stats.write(JSON.stringify({setting_id: row.setting_id, diagnostics: diagnostics.length,
        audio, comparison, healthy: diagnostics.length === 0 && audio !== null &&
            audio.note_events > 0 && audio.valid_timing}) + '\n');
    checked++;
    if (checked % 5000 === 0) process.stderr.write(JSON.stringify({checked, flagged}) + '\n');
}
stream.end();
if (stats) stats.end();
process.stderr.write(JSON.stringify({version: abcjs.signature, checked, flagged}) + '\n');
