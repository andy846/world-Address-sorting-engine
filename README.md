# World Address Sorting Engine

A Python, **offline-first** address-list analyzer. Its default workflow outputs
one **Country Code** per address plus counts by code, using English, Traditional
Chinese and Simplified Chinese input. The v0.3 candidate adds literal Zone and
NOVSN mappings from the supplied country list. It does not infer mail services
or rates.

## v0.3 candidate workflow

This branch develops **0.3.0rc1**; v0.2.0 below remains the sole accepted formal
release. Candidate builds require new manual acceptance before promotion.

- Installed global Extended (Compact fallback) and Hong Kong packs are discovered
  automatically. Hong Kong starts enabled; choose an installed pack or explicitly
  turn it off if unavailable. Reference verification runs in the background.
- Each fresh GUI analysis creates `<input-name>_output_YYYYMMDD_HHMMSS` beside
  the input. A custom output setting chooses its parent folder; collisions get
  numbered suffixes. Resume uses the original run folder. CLI `--output` still
  denotes an exact folder.
- The **Single address lookup** tab accepts multiple address lines. Ctrl+Enter
  queries locally, and Copy code copies the result. It also works during a
  batch; editing or clearing the input invalidates the previous result. No
  address history is saved.
- New detail reports append `Country_Code`, `Zone_Code`, `NOVSN_Zone_Code`.
  CN maps to `CN - Airmail` / `F`, HK to `LOCAL` / `A`, MO to
  `Macau - Surface` / `M`, and TW to `Taiwan` / `F`. These are reference-table
  labels, with no new service selection. Unresolved records leave all three
  fields blank.

New report manifests use schema 2 and pin the mapping version and hashes.
Completed legacy reports can be inspected with blank zone fields; their files
are preserved. Interrupted v0.2.0 jobs must be resumed with v0.2.0.
The PDF parser is an optional build dependency only.

## Country Code analysis (v0.2.0)

The sole current operator-accepted formal release is
[v0.2.0 — Verified Country Code Analysis](https://github.com/andy846/world-Address-sorting-engine/releases/tag/v0.2.0),
accepted by manual testing on 25 October 2026 and designated GitHub Latest.
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

This release includes country rules7, the compound-street evidence correction,
optional offline Hong Kong bilingual address evidence, source-order address
selection, native workbench and persistent System/Light/Dark themes.
Older versions remain historical downloads. See
[release scope and validation](docs/releases/v0.2.0.md) and
[the current release policy](docs/RELEASE_POLICY.md).

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

## Optional Hong Kong regional pack

v0.2.0 includes an optional,
independent ALS bilingual data pack for eligible unresolved estimates, with
offline installation, pinned recovery and GUI controls. The option is disabled
by default. Existing assigned results and explicit conflicts remain protected.
See [usage and rebuild instructions](docs/HK_REGIONAL_PACK.md).

The official snapshot's strict audit found 9,508 invalid features among 183,964.
The operator approved quarantining those features, retaining the unmodified
source/schema and building a partial-source TEST pack with 173,215 addresses.
The reference pack retains its partial-source TEST designation independently
of the operator-accepted application release. See the
[source audit](docs/HK_ALS_SOURCE_AUDIT_2026-10-24.md) and
[continuation ledger](docs/superpowers/plans/2026-10-25-hk-partial-source.md).
Current regression, public controls, private replay and performance receipts are
in the [25 October validation report](docs/HK_REGIONAL_VALIDATION_2026-10-25.md).
Country rules7 correct the two documented compound-street country errors;
the unchanged 336-case smoke bank now passes. See the
[correction and regression report](docs/COMPOUND_STREET_FIX_2026-10-25.md).
This selected smoke bank does not establish global accuracy or readiness.
v0.2.0 is the only currently supported formal application release; earlier
versions are retained as history.

## Current release status (October 2026)

- Formal v0.2.0 Country Code workflow: trilingual classification, streaming CSV/TXT/XLSX input, reconciled exports, cancellation/resume, optional verified HK evidence and a PySide6 workbench with read-only case inspection/export. Strict postal review remains separately available.
- Both worldwide packs are preserved in [versioned data releases](docs/PACK_RELEASES_2026-10-23.md), verified and installable offline. Current k2 SQLite sizes are 142,577,664 bytes (Compact) and 1,087,344,640 bytes (Extended).
- Historical country-rules6 repeated-million measurements: 183.661 seconds with the real HK pack, 149.293 seconds disabled; cancel at 500,000 and fresh-process resume passed exhaustive verification. The workload has 9,606 distinct keys. These are not relabelled as rules7/v0.2.0 throughput measurements. [Exact runtime receipts and limits](docs/HK_REGIONAL_VALIDATION_2026-10-25.md).
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
