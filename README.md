# Sun Star

The Sun Star is a deterministic, public-data solar clock. Its long-term reference scenario is 75 TWp of global PV by 2050.

## Daily public data

The browser reads six committed files in `sun/`; it never calls PV Live directly.

- `today.json`: the latest complete GB national PV day, its full SHA-256 visual seed, and London daylight geometry.
- `history.json`: 30 days of half-hourly PV Live observations and derived energy totals.
- `uk-solar.json`: all solar projects in the pinned Pipeline News release, keyed by `repd_ref`, with null geometry retained explicitly.
- `voices.json`: episode titles and links from *The Future of Solar Photovoltaics*.
- `press.json`: official RSS metadata only—headline, link, date, and publisher attribution.
- `provenance.json`: source URL, bytes, SHA-256 and fetch time for every input, plus structured scans of the estate's solar deployment and component pages.

## Sources

- [Sheffield Solar PV Live](https://www.solar.sheffield.ac.uk/pvlive/) for GB national half-hourly generation.
- [GlobalGrid2050](https://globalgrid2050.com/) at the exact commit recorded in `provenance.json` for Pipeline News, London solar geometry, podcast voices, [deployment statistics](https://globalgrid2050.com/solar_deployment_statistics/) and [solar components](https://globalgrid2050.com/solar_components/).
- [Solar Power Portal public RSS](https://www.solarpowerportal.co.uk/rss.xml?content_types=article) and [robots.txt](https://www.solarpowerportal.co.uk/robots.txt).
- [pv magazine International RSS](https://www.pv-magazine.com/feed/) and [robots.txt](https://www.pv-magazine.com/robots.txt).

The daily GitHub Action builds the preceding complete UTC day at 02:37 UTC, validates the six payload contracts, and commits changes. The visual seed is the SHA-256 of canonical JSON for the ordered `[timestamp_utc, generation_mw]` series; there is no random source.

## Local build

```sh
python -m pip install -r requirements.txt
python scripts/build_sun.py --globalgrid-root ../globalgrid2050 --globalgrid-commit FULL_40_CHARACTER_SHA --output sun
python scripts/validate_sun.py sun
```

The pinned GlobalGrid2050 checkout must match the supplied commit. The initial implementation and matching local/CI evidence remain in `testcode/202609150030/`.

### UTC intervals and validation

PV Live `datetime_gmt` identifies the **end** of a half-hour interval, as specified
in the [official API guide](https://api.solar.sheffield.ac.uk/pvlive/gdocs).
The v2 daily and history payloads assign a UTC day the 48 interval ends from
00:30 to 00:00 the following day. This corrects the v1 calendar-timestamp grouping.
Missing, duplicate, off-grid, non-finite, negative or non-national samples fail
the build. The validator recomputes count, coverage, peak, energy and seed from
the actual series. Power is MW; energy is the sum of average interval power
multiplied by 0.5 hours, rounded to three decimal places in MWh.

`requested_date` identifies the day requested and the London geometry date;
`data_date` identifies the observation day. A latest-available fallback is explicit
and never selects a date after the requested day. An incomplete day fails closed.

## Country and global star definitions

[`create/`](create/) is a mobile-first editor for a small, source-bound solar record. It computes a SHA-256 seed from canonical observations, places that seed in the URL and prepares a reviewable GitHub proposal. It does not publish directly.

Each definition in [`stars/`](stars/) retains public source URLs, dates, byte counts, SHA-256 hashes, observation locators and whether a value is exact, approximate or a bound. Observations from different publications remain separate. The reference world record uses IRENA Renewable Capacity Statistics 2026 and IEA Global Energy Review 2026.

A maintainer may publish a proposal by applying the `star-approved` label. The workflow validates the record and refuses to replace a different record with the same ID. The contract, JSON Schema and initial local/GitHub agreement evidence are in `scripts/`, `schema/` and `testcode/202609150040/`.

### Seed versions

New browser preparations use `RFC8785-JCS; observations sorted by UTF-16 key; safe integers; v2`.
[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html) defines the JSON bytes;
observation-array sorting by UTF-16 key is an additional application rule.
Both runtimes reject non-finite numbers, unpaired surrogates and integer-valued
numbers outside ±9007199254740991. The production Python implementation vendors
the Apache-licensed rfc8785.py v0.1.4; browser number serialization uses ECMAScript.

Legacy descriptors still select the original Python serialization and code-point
observation ordering. The immutable world reference retains seed
`a8696b5b9286966a43af65e3556ff3805df60542ed08f6fbc841d7bfed92dffa`.
Preparing an old record under v2 may change its identity; use a new record ID.

`testcode/202609150503/` tests production imports, cross-language canonical bytes,
browser preparation and encoded-URL reload at 430px, invalid number/Unicode
rejection, and corrupted PV series. The viewport test runs desktop Chromium and
does not claim a physical-phone test.
