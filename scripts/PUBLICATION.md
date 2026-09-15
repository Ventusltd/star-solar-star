# Main publication and Pages proof

The daily Sun dispatch/schedule and approved-proposal workflow share the
`star-main-publication` concurrency group. `queue: max` keeps up to 100 waiting
runs; GitHub cancels overflow. Operators must inspect cancelled/failed runs and
rerun them after queue pressure clears. A skipped or cancelled run is not a
publication receipt. See [GitHub concurrency limits](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

Each publishing job checks out fresh main after acquiring the group. The
`publish_main.py` helper requires a clean disposable Actions checkout, refreshes
main, regenerates and validates records, and retries a rejected push at most
three times. Each retry rebuilds with fresh production scripts; approved IDs
are checked again against the current repository. Identical IDs and content
are idempotent; changed content under an existing ID fails. No force push is
used. The helper resets tracked files and must not be used in a working checkout.

After publication, including an unchanged approved record, `verify_pages.py`
requests the existing legacy Pages build using the workflow token with
`pages: write`. It resolves the returned latest-build URL to a new numeric build,
requires a successful build at the publication commit or a descendant retaining
all published bytes, then compares HTTP response bytes with the Git blobs. A
queued build, mismatched bytes or timeout fails the job. Successful reports
contain the published SHA, Pages build URL/SHA, served paths and SHA-256 hashes.
See the [Pages build API](https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build).

Reports are uploaded as run artifacts even when verification fails. The proposal
receipt is posted only after served-byte verification. A failed Pages step can be
rerun safely; the immutable record stays unchanged. Daily Sun rebuilds include
fetch timestamps and may create a new provenance revision when rerun.

Local publication tests use temporary Git remotes and a local HTTP server:

```sh
python -m unittest discover -s tests -p test_publication.py -v
```

These tests prove recovery and verification behavior, not GitHub token permission
or a live deployment. A successful main dispatch with its uploaded Pages proof is
required for that evidence. Do not create artificial public proposal records to
exercise publication.
