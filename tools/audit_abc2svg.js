// Inspect syntax and the written music model with an external abc2svg core.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const core = path.resolve(process.argv[2]);
const {abc2svg, Abc} = require(core);
const rows = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const output = fs.createWriteStream(process.argv[4]);
let checked = 0;
for (const row of rows) {
    const diagnostics = [];
    let models = 0;
    let notes = 0;
    const user = {
        read_file: () => null,
        errbld: (severity, message, filename, line, column) =>
            diagnostics.push({severity, message, line, column}),
        get_abcmodel: first => {
            models++;
            for (let symbol = first; symbol; symbol = symbol.ts_next) {
                if (symbol.type === abc2svg.C.NOTE) notes++;
            }
        },
    };
    try {
        const parser = new Abc(user);
        const header = 'X:1\nT:Parser check\nM:' + row.meter + '\nL:1/8\nK:' + row.mode + '\n';
        parser.tosvg(row.setting_id + '.abc', header + row.abc.replace(/\r\n?/g, '\n') + '\n');
    } catch (error) {
        diagnostics.push({severity: 2, message: 'Exception: ' + error.message});
    }
    output.write(JSON.stringify({setting_id: row.setting_id, tune_id: row.tune_id,
        models, notes, diagnostics}) + '\n');
    checked++;
    if (checked % 5000 === 0) process.stderr.write(JSON.stringify({checked}) + '\n');
}
output.end();
process.stderr.write(JSON.stringify({checked, version: abc2svg.version, date: abc2svg.vdate,
    sha256: crypto.createHash('sha256').update(fs.readFileSync(core)).digest('hex')}) + '\n');
