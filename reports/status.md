# Notation review

Scanned 55,821 distinct settings of 23,199 tunes. The exports contain 55,838 tune rows, including separate composer rows for some settings.

| Status | Settings | Details |
|---|---:|---|
| Corrected | 493 | [fixed.csv](fixed.csv) |
| Needs review | 3764 | [review.csv](review.csv) |
| Pickups, endings and repeats | 24410 | [boundaries.csv](boundaries.csv) |
| Unsupported syntax or empty melody | 6505 | [unsupported.csv](unsupported.csv) |
| Playback or parser compatibility | 3485 | [playback.csv](playback.csv) |

77 corrected settings still have other findings. Settings can appear in multiple categories. Each CSV gives the source link and current ABC. The corrected list also gives the ABC before the changes.

## Corrections by type

| Type | Corrections |
|---|---:|
| Missing barline | 330 |
| Incorrect note length | 157 |
| Misplaced barline | 64 |
| Stray control character | 19 |
| Omitted note | 2 |
| Incorrect broken-rhythm or tuplet mark | 2 |

## How corrections are checked

- The scanner adds note lengths as exact fractions and compares neighboring written passages.
- Complete measures in another passage support barline and timing corrections. A line break between two complete measures can also support a missing divider when one of those measures and its neighbor match a written reference.
- A missing note requires the same completed phrase and both neighboring measures in settings from at least two other contributors.
- Playback checks compare the original and corrected events with automatic repair disabled. Unexpected changes to pitch, duration, rests or ties block a correction.
- After each round the scanner checks for further corrections. CSV, JSON and SQLite are compared record by record.

Playback checks left candidates in 5 settings for review. See [rejected.json](../checks/rejected.json) for the recorded reasons.

## Examples for review

| Tune | Setting | Finding |
|---|---|---|
| 'Ma' McNulty's Favourite | [55813](https://thesession.org/tunes/26102#setting55813) | Possible short interior measure; Short interior measure |
| 101 To Dublin | [50416](https://thesession.org/tunes/19336#setting50416) | Overfull interior measure |
| 101 To Dublin | [38079](https://thesession.org/tunes/19336#setting38079) | Overfull interior measure |
| 1st Floor March | [42485](https://thesession.org/tunes/21293#setting42485) | Short interior measure |
| 2-Rivisjenkka | [32371](https://thesession.org/tunes/16424#setting32371) | Possible incorrect short-note duration |
| 23 | [34482](https://thesession.org/tunes/17726#setting34482) | Meter or form to review |
| 23 | [34317](https://thesession.org/tunes/17726#setting34317) | Possible short interior measure; Short interior measure |
| 4 Minutes 33 Seconds | [15743](https://thesession.org/tunes/2399#setting15743) | Overfull interior measure |
| 4 Minutes 33 Seconds | [55757](https://thesession.org/tunes/2399#setting55757) | Overfull interior measure |
| 42nd Highlanders Farewell | [28873](https://thesession.org/tunes/15410#setting28873) | Meter or form to review |
| 51st Highland Division, The | [38610](https://thesession.org/tunes/19573#setting38610) | Overfull interior measure |
| 72nd Highlanders' Farewell To Aberdeen, The | [6970](https://thesession.org/tunes/6970#setting6970) | Short interior measure |
| 78 Eatonwood Green | [43643](https://thesession.org/tunes/21785#setting43643) | Overfull interior measure; Missing barline |
| 79th's Farewell To Gibraltar | [5318](https://thesession.org/tunes/5318#setting5318) | Short interior measure |
| A Breton In Paris | [20892](https://thesession.org/tunes/12500#setting20892) | Possible short interior measure; Short interior measure |
| A Builder Of Bridges | [39057](https://thesession.org/tunes/8602#setting39057) | Overfull interior measure |
| A Chomaraigh Aoibhinn O | [48054](https://thesession.org/tunes/15714#setting48054) | Overfull interior measure |
| A Day At The Carnival | [41510](https://thesession.org/tunes/20882#setting41510) | Short interior measure |
| A Dram At The Wake | [23732](https://thesession.org/tunes/9105#setting23732) | Overfull interior measure |
| A Farruquiña | [43829](https://thesession.org/tunes/21838#setting43829) | Overfull interior measure |
| A Farruquiña | [43827](https://thesession.org/tunes/21838#setting43827) | Overfull interior measure |
| A Happy Day In June | [43454](https://thesession.org/tunes/21532#setting43454) | Meter or form to review |
| A Jig For Kim | [30014](https://thesession.org/tunes/15947#setting30014) | Short interior measure |
| A L'envers | [26313](https://thesession.org/tunes/14361#setting26313) | Short interior measure |
| A Lovely Madness | [35801](https://thesession.org/tunes/7609#setting35801) | Short interior measure |

For full details see the CSV files, [patches](../changes/) and [verification results](../checks/).
