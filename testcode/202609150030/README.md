# Sun Star daily builder candidate

This stamped candidate converts the Dropbox `build_sun.mjs` draft into a standard-library Python builder before promotion to `scripts/`. The only runtime package listed is the IANA `tzdata` database required by Python `zoneinfo` on Windows; Linux runners use their operating-system database.

It reads only public data: Sheffield Solar PV Live; a pinned public `Ventusltd/globalgrid2050` checkout for London solar geometry, Pipeline News, podcast voices and the two solar estate pages; and the official RSS feeds and `robots.txt` files of Solar Power Portal and pv magazine. Feed output retains only title, link, publication date and attribution. Every fetched or pinned input is recorded with URL, byte count, SHA-256 and fetch time.

The PV series seed is the full SHA-256 of canonical JSON for the selected day's ordered timestamp/MW pairs. No random source is used. Missing Pipeline News coordinates stay null and are enumerated rather than inferred.

Run the candidate tests:

```sh
python -m pip install -r testcode/202609150030/requirements.txt
python -m unittest -v testcode/202609150030/test_build_sun.py
```

Run a live build against an exact GlobalGrid2050 commit:

```sh
python testcode/202609150030/build_sun.py --globalgrid-root ../globalgrid2050 --globalgrid-commit FULL_40_CHARACTER_SHA --output sun
```

The default `as-of` date is the preceding UTC day, so the daily run does not seed the star from a partial day. The fixed six outputs are `sun/today.json`, `history.json`, `uk-solar.json`, `voices.json`, `press.json`, and `provenance.json`. Browsers read these committed files; they never call PV Live directly.
