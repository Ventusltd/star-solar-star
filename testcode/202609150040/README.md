# Country and global solar star candidate

This isolated candidate defines a small, deterministic JSON contract for a country or world solar record. It uses public, dated source observations with byte-level provenance and keeps differing source statements separate instead of averaging them.

`global-solar.star.json` is the reference record. Its numerical observations come from IRENA Renewable Capacity Statistics 2026 and IEA Global Energy Review 2026. The pinned GlobalGrid2050 page supplies estate context only.

The browser creator is mobile-first and uses Web Crypto SHA-256. It prepares a reviewable issue; it does not publish directly. `issue_to_star.py` is the fail-closed conversion step after approval.

Run locally:

```sh
python build_global_star.py --output global-solar.star.json --accessed-utc 2026-09-14T23:45:00Z
python -m unittest -v test_country_star.py
python star_contract.py global-solar.star.json
```

The candidate workflow repeats the live-source build on GitHub. `write_result.py` reduces each lane to stable facts, and `merge_results.py` refuses promotion unless local and GitHub facts and code commits match exactly.

IEA currently returns HTTP 403 to GitHub-hosted runners. Local execution therefore requires the live official pages, while CI may use `iea-audited-statements.json` only after that specific response. The fixture binds the official URLs to the byte counts, SHA-256 hashes and numeric markers observed by the local lane; it is not a general network fallback.
