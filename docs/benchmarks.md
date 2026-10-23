# Measured reference-pack benchmarks

All numbers below are **measured**, not estimated. They come from the real
worldwide GeoNames build produced by GitHub Actions run `39827512415`
(source commit `929bbe6ec6e58af5c230d4f80979434371945b37`), downloaded and
verified locally on Windows 11 / Python 3.13.2 / SQLite 3.x.

## Two pack generations exist side by side

The builder's search key changed after the first published build: the
published generation keeps the punctuation of the source name
(`st. louis`), the rebuilt generation folds it away (`st louis`). The
bytes of the database depend on the key format, so the two generations
are **different databases** and each has its own version, fingerprint and
installation directory. The immutable install refuses to overwrite a
version, which is exactly why the rebuild needed a version of its own
(`ff0bef3`).

| Generation | Pack version | Status |
|---|---|---|
| Published | `2026-10-22` | Installed and SQL-queryable for audit; current batch runner refuses k1 |
| Rebuilt | `2026-10-22-k2` | Installed, verified, the generation the current builder produces |

The rebuilt generation is what the current source tree produces from the
same three pinned upstream archives. The published generation is **not**
rebuildable from the current tree: its keys differ.

### Rebuilt generation — measured

| Profile | Places | Aliases | SQLite bytes | MiB | Compressed bytes | MiB | DB SHA256 |
|---|---:|---:|---:|---:|---:|---:|---|
| `COMPACT_GLOBAL` | 715,567 | 993,537 | 142,577,664 | 135.973 | 56,480,487 | 53.864 | `f4ef044e94aa3d206f8fce1fa3e0d7ab5f03d6081d142fd7f9e8cf5837ab1b3f` |
| `EXTENDED_GLOBAL` | 5,776,152 | 8,048,422 | 1,087,344,640 | 1,036.973 | 420,832,046 | 401.337 | `70d617a532b8faedd7d9703c9b952945f101334907df5936725123d20be1f70f` |

Both pass `PRAGMA integrity_check` with `ok` (the 1 GiB EXTENDED check
takes about a minute). The place counts are identical to the published
generation; the alias counts are **lower**, because the punctuation free
key makes names that differ only by punctuation share one key and the
`(place_id, search_key)` uniqueness then stores one row instead of two.

Alias language distribution of the rebuilt generation:

`COMPACT_GLOBAL`: `source-latin` 630,004 / `ascii` 102,566 / `zh` 105,711 /
`en` 146,026 / `zh-Hant` 5,457 / `zh-Hans` 2,311 / `zh-CN` 1,148 /
`zh-TW` 313 / `source-zh` 1.

`EXTENDED_GLOBAL`: `source-latin` 5,520,403 / `ascii` 1,168,796 /
`zh` 1,006,234 / `en` 342,419 / `zh-Hant` 5,891 / `zh-Hans` 2,528 /
`zh-CN` 1,749 / `zh-TW` 386 / `source-zh` 16.

`source_sha256` over the three pinned upstream archives is
`568d05072b72ba2903804fce54a548a1d591a7302bc470db97a2fde1890e2629`
for both generations.

## Labelled golden set — measured accuracy

`tests/fixtures/golden_set.csv` holds **129 synthetic, public-safe
addresses** in English, Traditional Chinese, Simplified Chinese and
Japanese. No customer data is in it. Every row states the destination it
should produce and, separately, the **country** the geography has to
resolve to. The two are different questions: a master that issues no code
for Portugal is a coverage gap of the master, not a geographic error.

Measured with `tools/evaluate_golden_set.py` against the rebuilt
`EXTENDED_GLOBAL` pack and the signed **test fixture** master:

| Measure | Value |
|---|---|
| Rows | 129 |
| Asserted a code | 99 (coverage 0.7674) |
| Correct assertions | 99 (**precision 1.0000**) |
| False positives (wrong code asserted) | **0** |
| Geography rows | 109 |
| Geography correct | 109 (**geography accuracy 1.0000**) |
| Geography errors | 0 |
| Status errors | 0 |
| Review rate | 0.1395 |
| Unknown rate | 0.0930 |

Status mix: 99 `MATCHED`, 10 `REVIEW_CODE_MAPPING`, 6 `REVIEW_AMBIGUOUS`,
12 `UNKNOWN`, 2 `REVIEW_CONFLICT`.

Against the **published** generation the same set measured precision 0.9900
with **one** false positive: `Pitcairn, Henderson, Ducie and Oeno Islands`
was asserted as `US`, because the published pack stores the punctuation
bearing key and the reader could not reach the territory's own name. The
rebuilt generation removes it, and the subsumption rule
(`23517d8`) stops the words of the official name from being read as two
other countries.

The remaining reviews are **not** errors and are reported as such:

- `FI`, `GR`, `GY`, `KZ`, `PT`, `TF`, `UM` → `REVIEW_CODE_MAPPING`: the
  fixture master issues no code for them, so the geography is resolved and
  the review names it.
- `PN` → `REVIEW_CODE_MAPPING`: the territory resolved to Pitcairn, which
  the fixture master does not issue.
- Hangul, Cyrillic and Greek rows → `UNKNOWN` with
  `reason=UNSUPPORTED_LANGUAGE`.

**These numbers are not a postal accuracy claim.** The master in use is a
synthetic 36-country fixture, not the verified Hongkong Post master, so a
country the real master covers would move from review to a code. The
figures measure only these fixtures: no wrong code was asserted within
those 129 rows. Independent review found additional cases outside this
set: `Northern Ireland` could resolve incorrectly to `IE`, and
`Papua New Guinea, Guinea` could lose its explicit-country conflict. Those
cases were subsequently fixed and pinned in real-pack regressions. The table
above is the earlier golden-set measurement, not a new accuracy claim for
rules `2026-10-23.5`. The k2 packs still lack the Simplified Chinese alias
`香港特别行政区`; the full phrase `中华人民共和国香港特别行政区` currently
resolves incorrectly to CN. Two expected-failure regressions document this
pack gap, one per profile. A future pack rebuild must address it.

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

- Completed end-to-end classification throughput at 1M and 5M rows.
  A valid completed 100k measurement is recorded below; larger volumes
  have not been measured and are not extrapolated.
- Lookup latency with the page cache cold (the figures above are warm).
- A measured `ALL_LANG_ALIAS` baseline for size comparison. **No size
  reduction percentage is claimed**, because the baseline was never built.
- Postal accuracy against the real Hongkong Post master, which does not
  exist yet.

## End-to-end pipeline throughput - completed 100k measurement

`tools/benchmark_batch.py` runs the **whole** pipeline — CSV reader,
classification, checkpoint writer, exporter — over a synthetic file
against a real installed pack, and reports only what that run measured.
The synthetic places are the ones the catalogue in use actually issues,
so a row that the master cannot answer is not counted as a matched row.

Measured with clean commit `ec5301c4addaa605deac3ca01b9e8ff3d215bb5c`, rules
`2026-10-23.5`, Windows / Python 3.13.2, against the real k2 Extended pack
and a signed synthetic fixture catalogue. Later test/documentation/release
workflow changes do not modify the measured classifier. The result JSON
records `git_dirty: false`, source fingerprints, per-process RSS, input hashes,
and exact status reconciliation. This is synthetic pipeline performance,
not production postal accuracy.

| Rows | Seconds | Records/sec | Peak RSS bytes | Checkpoint bytes | Export bytes | MATCHED | REVIEW_AMBIGUOUS |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2,000 | 18.651 | 107.2 | 50,139,136 | 1,228,565 | 515,426 | 1,928 | 72 |
| 100,000 | 911.675 | 109.7 | 59,535,360 | 62,057,316 | 25,944,558 | 96,364 | 3,636 |

Pack: 1,087,344,640 bytes; fixture catalogue: 45,056 bytes. Each measurement
runs in a fresh process to attribute peak memory to that run. Street names
were checked against all 55 fixture places and carry no additional country
evidence. Peak RSS is 47.8 / 56.8 MiB respectively; the 100k checkpoint is
59.18 MiB and contains plaintext synthetic rows. The 1M/5M runs, cold-cache
and clean-machine measurements remain outstanding. Any classifier change
requires new results. A second run with changing Git provenance was rejected
by the benchmark and is excluded from these figures.

### How to reproduce

    python tools/install_reference_pack.py --database builds/real-2026-10-23/pack/compact_global.sqlite --build-report builds/real-2026-10-23/pack/build_report.json --profile COMPACT_GLOBAL --active-root packs
    python tools/benchmark_batch.py --rows 100000 --pack packs/geonames-extended-global-2026-10-22-k2/pack.db --out .tmp/bench_extended.json

## Retrieval-only cost (Milestone 2, superseded by the pipeline measurement above)

This figure measures `retrieve_candidates` alone, with the pack opened once
per record. It is kept because it is the number the retrieval optimisation
was measured against; the pipeline measurement above is the one that
describes a whole job.

Measured on 2026-10-23 with the evidence-mass classifier, single process,
single thread, warm page cache, 20 addresses drawn from the spec's
acceptance fixtures in English and Chinese, repeated three times
(`n = 60` per profile). The pack is opened once per record.

| Profile | Mean | Median | p95 | Max | Throughput |
|---|---:|---:|---:|---:|---:|
| `COMPACT_GLOBAL` | 4.07 ms | 3.81 ms | 8.16 ms | 9.14 ms | ~246 records/sec |
| `EXTENDED_GLOBAL` | 4.33 ms | 3.76 ms | 9.66 ms | 11.15 ms | ~231 records/sec |

Status mix over the same sample: 54 `MATCHED`, 3 `REVIEW_AMBIGUOUS`,
3 `UNKNOWN` per 20 distinct addresses.

**This is not yet a production throughput figure.** The number is dominated
by opening the reference database and re-running the same gazetteer queries
for every record, and it does not include the record reader, the exporter
or the checkpoint writer. Extrapolated naively it is ~5.7 hours for five
million records on one core. The high-volume batch work in Priority 4 must
add a normalised-address cache, reuse one open connection per job and
measure the real pipeline before any speed is claimed.
