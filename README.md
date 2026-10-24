# World Address Sorting Engine

A Python, **offline-first** address-list analyzer. Its default workflow outputs
one **Country Code** per address plus counts by code, using English, Traditional
Chinese and Simplified Chinese input. Air/surface service, rates, Zone and
Novsn codes are not part of this analysis.

## Country Code analysis (v0.1.0)

The operator-accepted formal release is
[v0.1.0 — Verified Country Code Analysis](https://github.com/andy846/world-Address-sorting-engine/releases/tag/v0.1.0).
Download the Windows EXE and checksum file there; reference databases remain
in the separate [k2 data release](https://github.com/andy846/world-Address-sorting-engine/releases/tag/geonames-packs-2026-10-22-k2).

```powershell
python -m pip install -e ".[excel,gui]"
world-address-engine-gui
```

Choose the input file and an installed GeoNames pack, then analyze. The bundled
country list contains 235 geographic entries derived from the supplied
236-row CountryList_20250708 reference: mainland China uses `CN`, and the
service-only `CNS` entry is excluded. These reference codes have their own
namespace (for example Kosovo `XO`), so they are not blindly copied from ISO.
The PDF parser is not required at runtime.

This release includes the 2026-10-24 geographic-context fixes, source-order
address selection, native workbench and persistent System/Light/Dark themes.
Published alpha releases remain available unchanged. See
[release scope and validation](docs/releases/v0.1.0.md).

```powershell
world-address-engine analyze --input "sample.csv" --output "sample-country-analysis" --geo-db "packs/geonames-extended-global-2026-10-22-k2/pack.db"
world-address-engine resume --job-dir "sample-country-analysis"
```

Outputs are `Classified_Addresses.csv` (original columns plus `Country_Code`),
`Country_Summary.csv`, `Country_Diagnostics.csv`, and the final
`Run_Manifest.json`. Clear country evidence is DETERMINED; supported estimates
are INFERRED; unresolved addresses keep a blank code. Both determined and
inferred codes contribute to counts. Coverage is not an accuracy guarantee.
The files remain local; the default completed run removes plaintext checkpoint
shards. Interrupted runs may retain sensitive `.country-state` data for resume.

The previous signed-HKP `classify` interface remains available for strict
compatibility. Its production-approval gate is separate from country analysis.

## Development candidate: optional Hong Kong regional pack

The `codex/hk-bilingual-regional` branch develops v0.2.0rc1. It adds an optional,
independent ALS bilingual data pack for eligible unresolved estimates, with
offline installation, pinned recovery and GUI controls. The option is disabled
by default. Existing assigned results and explicit conflicts remain protected.
See [usage and rebuild instructions](docs/HK_REGIONAL_PACK.md).

The official snapshot's strict audit found 9,508 invalid features among 183,964.
No final HK database or data release has been produced; a partial-coverage
source policy requires an explicit decision. See the
[source audit](docs/HK_ALS_SOURCE_AUDIT_2026-10-24.md) and
[implementation ledger](docs/superpowers/plans/2026-10-24-hk-bilingual-regional.md).
Local regression, frozen candidate and disabled-million measurements are in the
[candidate validation receipt](docs/HK_REGIONAL_VALIDATION_2026-10-24.md).
The published v0.1.0 remains the formal release.

## Current release status (October 2026)

- Formal v0.1.0 Country Code workflow: trilingual classification, streaming CSV/TXT/XLSX input, reconciled exports, cancellation/resume and a PySide6 workbench with read-only case inspection/export. Strict postal review remains separately available.
- Both worldwide packs are preserved in [versioned data releases](docs/PACK_RELEASES_2026-10-23.md), verified and installable offline. Current k2 SQLite sizes are 142,577,664 bytes (Compact) and 1,087,344,640 bytes (Extended).
- Requested repeated-million workload completed in 152.847 seconds, with 69.871 MiB peak process working set; cancellation at 500,000 rows and fresh-process resume produced byte-identical reports. This workload has 9,606 distinct address/hint keys. [Measurements, review evidence and limits](docs/REPEATED_MILLION_BENCHMARK_2026-10-24.md).
- Remaining country-analysis validation: labelled global accuracy, low-duplication/million-distinct and 5M workloads, million-row GUI interaction and clean disconnected Windows installation. The separate strict postal classifier retains its official-catalogue approval gate and existing strict-retrieval limitations.
- Test examples use synthetic fixtures. No actual recipient address file is committed to this repository.

## Preview a production address file (no database needed)

From the repository root:

```bash
python -m pip install -e .
world-address-engine preview --input "AAAAA.csv"
```

Or without installing the package:

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m world_address_engine.cli preview --input "AAAAA.csv"
```

The preview prints JSON containing only the input filename, number of records, names/number of columns, counts of populated address lines, and decoding/unnamed-column anomalies. It **does not print or upload recipient addresses** or claim to have classified them.

For a nonstandard CSV header, pass one or more `--address-column "Column Name"`. For a Big5 file, pass `--encoding big5`. Excel input requires `python -m pip install -e ".[excel]"` and optional `--sheet SheetName`.

The current sample file uses `NAME_ADDRESS_LINE1` ... `NAME_ADDRESS_LINE5` and `Control no`. The input layer automatically detects all five address fields, preserves control identifiers (including leading zeros when represented as text), and retains all original cell values, including the six duplicate blank-header columns under unique internal names (`Unnamed_1` ...).

## Dev tests

```bash
python -m pip install -e ".[excel,test,data-build]"
python -m pytest -q
```

Linux unit/integration checks are not substitutes for independent code review, comprehensive HKP postal-master verification, and Windows offline end-to-end acceptance.

See `docs/PHASE1_PROGRESS.md` and `docs/superpowers/plans/2026-10-23-hkp-trilingual-mvp-implementation.md` for plan and release gates.


## Strict Postal Classification Compatibility

Normal classification refuses the current unreviewed HKP reference master. For synthetic tests only, run:

```powershell
$env:PYTHONPATH = "src"
python -m world_address_engine.cli classify --input "synthetic.csv" --output "test-output" --geo-db "geo.db" --hkp-db "hkp.db" --address-column "Address" --batch-size 10000 --test-only
python -m world_address_engine.cli resume --job-dir "test-output"
```

Five-line CSV files named NAME_ADDRESS_LINE1–5 support automatic address-column detection. Add --max-batches 1 to pause after one checkpoint, then resume.
Outputs are Classified_Addresses.csv, Manual_Review.csv, Country_Summary.csv and Run_Manifest.json. The manifest is published LAST; without it, results are incomplete.

**Privacy:** The .job-state folder stores plaintext recipient address rows as local JSONL checkpoints. Limit filesystem access, delete according to retention policy, and never upload this folder or actual customer CSV files to GitHub. SHA256 validation detects modified source files, data packs and checkpoint batches.

**Status:** Use synthetic fixtures until the official HKP master and documented acceptance gates pass. Independent classification and packaging reviews have been performed; they do not establish postal production accuracy.

## Windows GUI

```powershell
python -m pip install -e ".[excel,gui]"
world-address-engine-gui
```

The Country Code GUI supports input mapping, pack selection, detailed progress,
cancellation/resume, summaries, case inspection/export and saved appearance
preferences. Protect local checkpoints and reports. See
[v0.1.0 release notes](docs/releases/v0.1.0.md) for accepted tests and scope.


## Official worldwide GeoNames SQLite build

The project now has a build-from-official-source path for Compact and Extended global packs, **without unpacking the large source ZIP files to disk**. Source inputs are the GeoNames allCountries.zip, alternateNamesV2.zip, and cities1000.zip downloads (CC BY 4.0).

Run once on a host with network access, using Python 3.12+:

```powershell
python tools/download_geonames.py --source-dir "data/geonames-source"
python tools/build_reference_pack.py --source-dir "data/geonames-source" --output-dir "builds/global" --both --compress
```

The output is two SQLite files and `build_report.json` reporting **actual byte sizes** and record counts, source hashes, integrity checks and archive sizes. Downloading is only a build-time operation; classification is offline.

The full official-source build succeeded in Actions run `39827512415` and its
original databases were preserved alongside the current k2 rebuild. See the
[build guide](docs/GEONAMES_DB_BUILD.md), [preserved releases and offline installation](docs/PACK_RELEASES_2026-10-23.md), and [measured sizes](docs/benchmarks.md).
