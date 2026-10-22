# Measured reference-pack benchmarks

All numbers below are **measured**, not estimated. They come from the real
worldwide GeoNames build produced by GitHub Actions run `39827512415`
(source commit `929bbe6ec6e58af5c230d4f80979434371945b37`), downloaded and
verified locally on Windows 11 / Python 3.13.2 / SQLite 3.x.

## Source archives (pinned)

| Archive | Bytes | SHA256 |
|---|---|---|
| `allCountries.zip` | 422,156,786 | `4b8a10021d69736be2f78b75cbd6f49648f50bcd90da117cc1c4f84767725182` |
| `alternateNamesV2.zip` | 204,950,999 | `1ea8afef7da35370529cd2f7c38caac78e821ca3578f18f0207e5c31ee81fb05` |
| `cities1000.zip` | 11,077,563 | `9d3916f7a9448bb4ea45e93c06c5413d2cceb1a89e03f75c2178bbb08af12018` |

## Installed database sizes

| Profile | Places | Aliases | SQLite bytes | MiB | Compressed bytes | MiB | DB SHA256 |
|---|---:|---:|---:|---:|---:|---:|---|
| `COMPACT_GLOBAL` | 715,567 | 997,281 | 143,949,824 | 137.281 | 56,535,390 | 53.916 | `e3b8b710e7acf05e0fe3618abecc5745d13d07a7826ae1f2a41767561faa2d2d` |
| `EXTENDED_GLOBAL` | 5,776,152 | 8,126,852 | 1,098,661,888 | 1,047.766 | 423,280,495 | 403.672 | `fb0e4774cc360ec5fe7b22d2b8176feea031abf02a6277dc42a3877c9da2074a` |

Both databases pass `PRAGMA integrity_check` with `ok`.

**No size-reduction percentage is claimed.** The spec requires comparison
against an unfiltered `ALL_LANG_ALIAS` baseline, and that baseline was never
built. Until it exists, only absolute measured sizes are reported.

## Alias language distribution

`COMPACT_GLOBAL`: `source-latin` 715,518 / `ascii` 107,678 / `zh` 105,713 /
`en` 59,238 / `zh-Hant` 5,457 / `zh-Hans` 2,213 / `zh-CN` 1,149 /
`zh-TW` 314 / `source-zh` 1.

`EXTENDED_GLOBAL`: `source-latin` 5,775,722 / `ascii` 1,252,742 /
`zh` 1,006,231 / `en` 81,679 / `zh-Hant` 5,891 / `zh-Hans` 2,429 /
`zh-CN` 1,750 / `zh-TW` 387 / `source-zh` 21.

No other language tag is present in either pack.

### Known builder defect affecting these counts

`geo_aliases` has `UNIQUE (place_id, search_key)`, so one place/text pair is
indexed once and only the **first** language label inserted survives. The
builder currently inserts the derived `source-latin` / `source-zh` label
before the explicit GeoNames `alternateNames` language tags, so the explicit
tag is discarded whenever its text matches the source name. That is why
`source-latin` (715,518) is so much larger than `en` (59,238) even though the
great majority of those names are English. Matching is unaffected — the
search key and the indexed text are identical — but the **language provenance
is lossy**, and the audit report therefore understates real English and
Chinese coverage. See `docs/SECURITY_AUDIT_2026-10-23.md` finding A1.

## Coverage

| Measure | `COMPACT_GLOBAL` | `EXTENDED_GLOBAL` |
|---|---:|---:|
| Distinct countries | 253 | 253 |
| Feature classes present | `A`, `P` only | `A`, `P` only |

## Lookup latency

Single connection, serial queries, warm cache, `search_key IN (?)` joined
against `geo_places`. 1,600 queries over eight terms (Latin, Traditional
Chinese and Simplified Chinese).

| Profile | Mean | Median | p95 | Max | Lookups/sec |
|---|---:|---:|---:|---:|---:|
| `COMPACT_GLOBAL` | 0.191 ms | 0.169 ms | 0.264 ms | 4.462 ms | ~5,236 |
| `EXTENDED_GLOBAL` | 0.215 ms | 0.183 ms | 0.317 ms | 10.843 ms | ~4,641 |

Query plans confirm index use, with no table scan:

- alias lookup: `SEARCH a USING COVERING INDEX idx_geo_alias_key (search_key=?)`
- place lookup: `SEARCH p USING INTEGER PRIMARY KEY (rowid=?)`
- admin lookup: `SEARCH geo_places USING COVERING INDEX idx_geo_country_admin (country_code=? AND admin1_code=?)`

## Reproducing

    python tools/download_geonames.py --source-dir data/geonames-source
    python tools/build_reference_pack.py --source-dir data/geonames-source --output-dir builds/global --both --compress
    python tools/install_reference_pack.py --database builds/global/compact_global.sqlite --build-report builds/global/build_report.json --profile COMPACT_GLOBAL --active-root packs
    python -m pytest tests/integration/test_real_geonames_packs.py -v

The real-pack tests skip automatically when the databases are absent, so CI
without the artefacts still runs green while the local full-suite run covers
them.

## Still unmeasured

- End-to-end classification throughput at 100k / 1M / 5M rows.
- Peak RSS during a full-size batch.
- Precision, coverage and review rate against a labelled EN / zh-Hant /
  zh-Hans gold set.
- Lookup latency with the page cache cold (the figures above are warm).
- A measured `ALL_LANG_ALIAS` baseline for size comparison.
