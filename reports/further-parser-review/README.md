# Further parser review

Checked all 23,149 remaining settings with abc2svg 1.22.1. The core reported diagnostics in 1,794 settings.
Prior TradMate, abcjs, abc2midi and abc2abc results were reused after checking the source hashes. The changed settings were checked again with the native tools, abcjs and abc2svg.

Corrected 23 ornament spellings in 4 settings of 3 tunes.
Twenty-two abbreviated trill names use the standard trill spelling. One Da Capo name uses the standard lowercase full-word spelling. The related second setting of the same tune shares the trill spelling issue.
TradMate and abcjs preserved the played notes and timings.

abc2svg diagnostics in the four changed settings decreased from 24 to 1. The remaining message in setting 52550 concerns a separate malformed note. The accidental-token comparison found no uniquely supported correction for it, so it remains under review.

The accepted names are defined in the [ABC 2.1 decoration specification](https://abcnotation.com/wiki/abc:standard:v2.1#decorations).

## Scope and limitations

abc2svg was used as a core syntax/model parser. Custom modules and graphic output were excluded. The npm package is deprecated and was pinned by version and core hash. Its diagnostics were considered alongside the other parsers and the specification.
The additional accidental-token comparison found no uniquely supported correction.

## Evidence

- [Input settings and source hashes](input.json)
- [Full additional-parser diagnostics](abc2svg.jsonl)
- [Corrected settings before](fixed-before.jsonl)
- [Corrected settings after](fixed-after.jsonl)
- [Fresh native and abcjs diagnostics](fixed-native-and-abcjs.json)
- [Exact source patches](../../changes/written-ornament-fixes.json)
- [Summary and pinned parser version](summary.json)

To repeat the additional parser, install the external abc2svg@1.22.1 package into a scratch directory and supply its abc2svg-1.js path to tools/audit_abc2svg.js. No third-party parser source is included in this repository.
