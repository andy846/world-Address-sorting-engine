# Build genuine worldwide GeoNames SQLite (EN / Traditional Chinese / Simplified Chinese)

**2026-10-23 status:** The global DB build scripts and GitHub Actions workflow exist, but a full real-data global SQLite build has **not yet been verified**. This sandbox has no DNS/egress access to the GeoNames download host; test fixture DB sizes cannot be substituted for actual global sizes.

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
