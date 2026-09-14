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

## Country and global star definitions

[`create/`](create/) is a mobile-first editor for a small, source-bound solar record. It computes a SHA-256 seed from canonical observations, places that seed in the URL and prepares a reviewable GitHub proposal. It does not publish directly.

Each definition in [`stars/`](stars/) retains public source URLs, dates, byte counts, SHA-256 hashes, observation locators and whether a value is exact, approximate or a bound. Observations from different publications remain separate. The reference world record uses IRENA Renewable Capacity Statistics 2026 and IEA Global Energy Review 2026.

A maintainer may publish a proposal by applying the `star-approved` label. The workflow validates the record and refuses to replace a different record with the same ID. The contract, JSON Schema and initial local/GitHub agreement evidence are in `scripts/`, `schema/` and `testcode/202609150040/`.
