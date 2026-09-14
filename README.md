# Sun Star

The Sun is the estate's daily solar clock: a deterministic, public-data foundation for the GlobalGrid2050 Solar Star. Its long-term mission is 75 TWp of global PV installed ethically by 2050.

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
