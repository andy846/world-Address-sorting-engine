# Build genuine worldwide GeoNames SQLite (EN / Traditional Chinese / Simplified Chinese)

**2026-10-23 status: the full real-data global build is VERIFIED.** GitHub Actions run `39827512415` built both profiles from the official GeoNames ZIPs and published them as artifact `12447987288`. The artefact was downloaded and verified locally: both databases match their published SHA-256 fingerprints byte for byte, both pass `PRAGMA integrity_check`, and their schemas, place counts, alias counts and alias language distribution match the build report. Measured sizes, coverage and lookup latency are recorded in [`docs/benchmarks.md`](benchmarks.md). An independent audit of the resulting packs and of the classification code is recorded in [`docs/SECURITY_AUDIT_2026-10-23.md`](SECURITY_AUDIT_2026-10-23.md).

Verified measurements: `COMPACT_GLOBAL` 715,567 places / 997,281 aliases / 143,949,824 bytes (137.281 MiB), DB SHA256 `e3b8b710e7acf05e0fe3618abecc5745d13d07a7826ae1f2a41767561faa2d2d`; `EXTENDED_GLOBAL` 5,776,152 places / 8,126,852 aliases / 1,098,661,888 bytes (1,047.766 MiB), DB SHA256 `fb0e4774cc360ec5fe7b22d2b8176feea031abf02a6277dc42a3877c9da2074a`.

Official upstream GeoNames list as of 2026-10-22: allCountries.zip approx 403 MB, alternateNamesV2.zip approx 195 MB, cities1000.zip approx 11 MB. These are ZIP INPUT sizes, NOT SQLite output sizes. Source: https://download.geonames.org/export/dump/. Data: GeoNames CC BY 4.0, https://www.geonames.org/export/.

## Actual-data build on an internet-enabled machine

Use Python 3.12+:

    python tools/download_geonames.py --source-dir data/geonames-source
    python tools/build_reference_pack.py --source-dir data/geonames-source --output-dir builds/global-2026 --both --compress

After one-time download, all building and runtime lookup are offline. ZIP entries are streamed directly rather than unpacking multi-GB text files. Downloads are SHA-256 pinned; integrity failures abort. GeoNames attribution must be preserved.

Outputs: compact_global.sqlite, extended_global.sqlite, their ZIP distributions and build_report.json. The report records actual SQLite byte sizes, compression sizes, geographic/place and alias counts, source checksums and language alias counts; the builder runs ANALYZE, VACUUM and SQLite integrity_check.

Compact retains all included administrative features plus cities1000 populated-place IDs; Extended retains all administrative/populated-place feature classes from worldwide allCountries. Both keep English/Chinese/Latin aliases only. Global street/building details are separate optional regional datasets.

A GitHub-hosted attempt is defined in .github/workflows/build-geonames.yml on feat/hkp-trilingual-phase1. If GitHub Actions is enabled, it can download data and publish resulting database distribution artifacts. Workflow source is not evidence of a successful run: check actual workflow status and build_report.json before reporting or relying on sizes.

## Production release gates

- Full manually source-reviewed Hongkong Post destination code catalogue remains unavailable.
- GeoNames is a geographical source, not approved HKP two-letter destination master.
- Full worldwide SQLite MB/GB, international and rural-place recognition rates and measured lookup benchmarks remain unverified.
- Do not commit real recipient addresses, customer CSVs or local .job-state.
