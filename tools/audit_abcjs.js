// Parse every distinct setting and retain diagnostics without rendering or audio.
const fs = require('node:fs');
const path = require('node:path');
const abcjs = require(path.resolve(process.argv[2]));
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const records = new Map(data.map(row => [row.setting_id, row]));
const stream = fs.createWriteStream(process.argv[4]);
let checked = 0;
let flagged = 0;
for (const row of records.values()) {
    const abc = 'X:1\nT:Parser check\nM:' + row.meter + '\nL:1/8\nK:' + row.mode + '\n' +
        row.abc.replace(/\r\n?/g, '\n') + '\n';
    let diagnostics;
    try {
        const tunes = abcjs.parseOnly(abc);
        diagnostics = tunes.flatMap(tune => tune.warnings || []);
        if (tunes.length !== 1) diagnostics.push('Unexpected tune count ' + tunes.length);
    } catch (error) {
        diagnostics = ['Exception: ' + error.message];
    }
    if (diagnostics.length) {
        flagged++;
        stream.write(JSON.stringify({setting_id: row.setting_id, tune_id: row.tune_id, diagnostics}) + '\n');
    }
    checked++;
    if (checked % 5000 === 0) process.stderr.write(JSON.stringify({checked, flagged}) + '\n');
}
stream.end();
process.stderr.write(JSON.stringify({version: abcjs.signature, checked, flagged}) + '\n');
