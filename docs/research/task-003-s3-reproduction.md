# TASK003-S3 — complete reproduction command reference

This is the complete command reference supplementing the phase summary in the pilot report. It does not authorize another acquisition, change the two-day selection or open holdout. The completed pilot evidence remains immutable.

Install `pip install -e ".[test,flatfiles]"`. Configure `MASSIVE_S3_ACCESS_KEY_ID` and `MASSIVE_S3_SECRET_ACCESS_KEY` privately, or pass `--credentials-file` pointing to a0600 file to commands that access S3. Never put values in Git or the research config.

For a separately authorized rerun, use a new ID/config:

```sh
.venv/bin/python -m scripts.bootstrap_flatfile_pilot \
  --run-id m3-s3-pilot-rerun-v2 \
  --output-config configs/task-003-s3-pilot-rerun-v2.json
```

This performs only the same seven bounded metadata HEADs, checks disk/planned bytes, writes a new config and freezes code/source hashes. The metadata-only utility is also available, but use the bootstrap wrapper for a full research rerun so the analysis code freeze is present.

Use that new config with **every** following command. Run the three source stages concurrently in separate terminals, as in the actual pilot, so extraction/integrity can overlap acquisition within the unchanged shared execution budget:

```sh
.venv/bin/python -m market_lab.flatfile_cache probe --config configs/task-003-s3-pilot-rerun-v2.json
.venv/bin/python -m market_lab.flatfile_transfer --config configs/task-003-s3-pilot-rerun-v2.json
```

```sh
.venv/bin/python -m market_lab.flatfile_integrity --config configs/task-003-s3-pilot-rerun-v2.json
```

```sh
.venv/bin/python -m market_lab.flatfile_ingest_duckdb --watch --config configs/task-003-s3-pilot-rerun-v2.json
```

Completed content-addressed snapshots and selected extracts are reused after hash checks. CRC locks prevent simultaneous duplicate integrity passes. A stopped attempt remains explicitly incomplete. Resume within the same remaining budgets; do not increase limits or change dates to bypass a failure.

After all source stages complete, run these offline steps in order. **The change audit is required before publication**, in addition to the phase list in the short report:

```sh
.venv/bin/python -m market_lab.flatfile_revalidation baseline --config configs/task-003-s3-pilot-rerun-v2.json
.venv/bin/python -m market_lab.flatfile_reconcile --config configs/task-003-s3-pilot-rerun-v2.json
.venv/bin/python -m market_lab.flatfile_revalidation revalidate --config configs/task-003-s3-pilot-rerun-v2.json
.venv/bin/python -m scripts.audit_flatfile_changes --config configs/task-003-s3-pilot-rerun-v2.json
.venv/bin/python -m scripts.validate_flatfile_pilot --config configs/task-003-s3-pilot-rerun-v2.json
.venv/bin/python -m pytest -q > /private/tmp/s3-pilot-rerun-tests.txt
.venv/bin/python -m scripts.finalize_flatfile_pilot --config configs/task-003-s3-pilot-rerun-v2.json --pytest-output /private/tmp/s3-pilot-rerun-tests.txt
```

The original run recorded operational revisions for interrupted transfers, the fast-reader CRC regression and the source-session alignment correction. Those records and original source snapshots are preserved. A fresh run binds the current corrected implementation directly and need not reproduce failed operational attempts. Its budget counters/attempt labels can therefore differ while the fixed market evidence and policies remain comparable.

All market-wide `.csv.gz`, temporary fragments, normalized daily partitions and credentials stay local. Push code/config/tests and compact research evidence only. The separately proposed eleven-date development-sample expansion still requires its own approval, exact metadata and budget freeze.
